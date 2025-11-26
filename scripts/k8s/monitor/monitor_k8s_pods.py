import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from kubernetes import client, config
from kubernetes.client import V1Pod, V1ContainerStatus

from db.db_logger import log_k8s_pod_health


def env():
    """
    export DATABASE_URL=postgresql://smart:smartpass@localhost:5432/smartdb
    export K8S_CLUSTER_NAME=kind-smart-monitor
    export K8S_CONTEXT=kind-smart-monitor
    export K8S_POD_RECOVERY_LOOKBACK_MIN=5
    export K8S_POD_RECOVERY_INTERVAL=60
    :return:
    """

# -------------------------------
# K8s client helper
# -------------------------------

def get_core_v1(context: Optional[str] = None) -> client.CoreV1Api:
    """
    Return a CoreV1Api client.

    - Inside a Kubernetes pod: uses in-cluster config
    - Outside: uses ~/.kube/config (optionally with a context)
    """
    try:
        config.load_incluster_config()
        print("[INFO] monitor_k8s_pods: using in-cluster Kubernetes config")
    except Exception as e:
        print(f"{e}")
        config.load_kube_config(context=context)
        print(f"[INFO] monitor_k8s_pods: using kubeconfig (context={context or 'default'})")

    return client.CoreV1Api()


# -------------------------------
# Helpers to classify pod issues
# -------------------------------

def classify_container_statuses(
    statuses: List[V1ContainerStatus],
) -> Tuple[int, Optional[str], Optional[str], Optional[str], Optional[int], Optional[str], bool]:
    """
    Inspect container statuses for:
      - CrashLoopBackOff
      - ImagePullBackOff / ErrImagePull
      - OOMKilled

    Returns:
      total_restart_count,
      problem_type,           # one of the above or None
      problem_reason,
      problem_message,
      last_exit_code,
      last_termination_reason,
      last_termination_oom

    NOTE: problem_type may be None if no issue is detected at container level.
    """
    total_restart = 0
    problem_type = None
    problem_reason = None
    problem_message = None
    last_exit_code = None
    last_term_reason = None
    last_term_oom = False

    # Simple priority: OOMKilled > CrashLoopBackOff > ImagePull*
    priority = {
        "OOMKilled": 3,
        "CrashLoopBackOff": 2,
        "ImagePullBackOff": 1,
        "ErrImagePull": 1,
    }

    for cs in statuses:
        try:
            total_restart += int(cs.restart_count or 0)
        except Exception as e:
            print(f"[WARN] classify_container_statuses: restart_count parse error: {e}")

        state = cs.state
        last_state = cs.last_state

        # 1) Waiting: CrashLoopBackOff / ImagePullBackOff / ErrImagePull
        if state and state.waiting:
            reason = (state.waiting.reason or "").strip()
            message = state.waiting.message or ""

            if reason in ("CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"):
                if not problem_type or priority.get(reason, 0) > priority.get(problem_type, 0):
                    problem_type = reason
                    problem_reason = reason
                    problem_message = message

        # 2) Terminated: OOMKilled etc.
        term = None
        if state and state.terminated:
            term = state.terminated
        elif last_state and last_state.terminated:
            term = last_state.terminated

        if term:
            reason = (term.reason or "").strip() if term.reason else None
            exit_code = term.exit_code

            if exit_code is not None:
                last_exit_code = exit_code
            if reason:
                last_term_reason = reason

            if reason == "OOMKilled":
                # OOMKilled always wins
                if not problem_type or priority["OOMKilled"] > priority.get(problem_type, 0):
                    problem_type = "OOMKilled"
                    problem_reason = reason
                    if not problem_message:
                        problem_message = "Container terminated due to OOMKilled"
                    last_term_oom = True

    return (
        total_restart,
        problem_type,
        problem_reason,
        problem_message,
        last_exit_code,
        last_term_reason,
        last_term_oom,
    )


def detect_long_pending(pod: V1Pod, now: datetime, threshold_sec: int) -> Optional[Tuple[str, str]]:
    """
    Detect pods that are Pending for longer than threshold_sec.
    Returns (reason, message) if LongPending, else None.
    """
    status = pod.status or {}
    if (status.phase or "").strip() != "Pending":
        return None

    start_time = status.start_time  # datetime with tz
    if not start_time:
        return None

    age_sec = (now - start_time).total_seconds()
    if age_sec < threshold_sec:
        return None

    reason = "Pending"
    msg = f"Pod pending for {int(age_sec)}s (threshold={threshold_sec}s)"
    return reason, msg


def detect_probe_failure(pod: V1Pod) -> Optional[Tuple[str, str]]:
    """
    Detect pods that are Running but not Ready due to probe failures.

    We approximate this by:
      - conditions Ready / ContainersReady = False
      - and message mentioning 'probe' (case-insensitive).
    """
    status = pod.status or {}
    conditions = list(status.conditions or [])

    for cond in conditions:
        c_type = (cond.type or "").strip()
        c_status = (cond.status or "").strip()
        msg = f"{cond.reason or ''} {cond.message or ''}".strip()
        msg_lower = msg.lower()

        if c_type in ("Ready", "ContainersReady") and c_status == "False":
            if "probe" in msg_lower:
                reason = cond.reason or "ProbeFailure"
                message = cond.message or "Pod failing health probes"
                return reason, message

    return None


def detect_stuck_terminating(pod: V1Pod, now: datetime, threshold_sec: int) -> Optional[Tuple[str, str]]:
    """
    Detect pods stuck in Terminating for longer than threshold_sec.
    Uses metadata.deletion_timestamp.
    """
    meta = pod.metadata or {}
    deletion_ts = getattr(meta, "deletion_timestamp", None)
    if not deletion_ts:
        return None

    age_sec = (now - deletion_ts).total_seconds()
    if age_sec < threshold_sec:
        return None

    reason = "StuckTerminating"
    msg = f"Pod terminating for {int(age_sec)}s (threshold={threshold_sec}s)"
    return reason, msg


def detect_unschedulable(pod: V1Pod) -> Optional[Tuple[str, str]]:
    """
    Detect pods that are Pending due to scheduler 'Unschedulable' condition.
    """
    status = pod.status or {}
    if (status.phase or "").strip() != "Pending":
        return None

    conditions = list(status.conditions or [])
    for cond in conditions:
        c_type = (cond.type or "").strip()
        c_status = (cond.status or "").strip()
        c_reason = (cond.reason or "").strip()
        if c_type == "PodScheduled" and c_status == "False" and c_reason == "Unschedulable":
            msg = cond.message or "Pod unschedulable"
            return c_reason, msg

    return None


def detect_evicted(pod: V1Pod) -> Optional[Tuple[str, str]]:
    """
    Detect pods that were evicted by the kubelet / scheduler.
    """
    status = pod.status or {}
    phase = (status.phase or "").strip()
    reason = (getattr(status, "reason", "") or "").strip()

    if reason == "Evicted" or (phase == "Failed" and reason == "Evicted"):
        msg = getattr(status, "message", None) or "Pod evicted by Kubernetes"
        return reason, msg

    return None


def build_pod_record(
    pod: V1Pod,
    cluster_name: str,
    now: datetime,
    long_pending_threshold: int,
) -> Dict[str, Any]:
    """
    Build a snapshot record for this pod.

    - Healthy pods  → problem_type = 'Healthy'
    - Unhealthy pods → problem_type is one of:
        'CrashLoopBackOff', 'ImagePullBackOff', 'ErrImagePull',
        'OOMKilled', 'LongPending',
        'ProbeFailure', 'StuckTerminating', 'Unschedulable', 'Evicted'
    """
    meta = pod.metadata or {}
    status = pod.status or {}

    namespace = meta.namespace or "default"
    pod_name = meta.name or "<unknown>"
    phase = (status.phase or "Unknown").strip()

    statuses: List[V1ContainerStatus] = list(status.container_statuses or []) + list(
        status.init_container_statuses or []
    )

    (
        total_restart,
        problem_type,
        problem_reason,
        problem_message,
        last_exit_code,
        last_term_reason,
        last_term_oom,
    ) = classify_container_statuses(statuses)

    # LongPending if no other container-level problem yet
    if not problem_type:
        lp = detect_long_pending(pod, now, long_pending_threshold)
        if lp:
            lp_reason, lp_msg = lp
            problem_type = "LongPending"
            problem_reason = lp_reason
            problem_message = lp_msg

    # Probe failures (only if still no problem_type)
    if not problem_type:
        pf = detect_probe_failure(pod)
        if pf:
            pf_reason, pf_msg = pf
            problem_type = "ProbeFailure"
            problem_reason = pf_reason
            problem_message = pf_msg

    # Stuck terminating (reuse same threshold for now)
    if not problem_type:
        st = detect_stuck_terminating(pod, now, long_pending_threshold)
        if st:
            st_reason, st_msg = st
            problem_type = "StuckTerminating"
            problem_reason = st_reason
            problem_message = st_msg

    # Unschedulable
    if not problem_type:
        us = detect_unschedulable(pod)
        if us:
            us_reason, us_msg = us
            problem_type = "Unschedulable"
            problem_reason = us_reason
            problem_message = us_msg

    # Evicted
    if not problem_type:
        ev = detect_evicted(pod)
        if ev:
            ev_reason, ev_msg = ev
            problem_type = "Evicted"
            problem_reason = ev_reason
            problem_message = ev_msg

    # if no problem was detected at all, mark as healthy
    if not problem_type:
        problem_type = "Healthy"

    return {
        "cluster_name": cluster_name,
        "namespace": namespace,
        "pod_name": pod_name,
        "phase": phase,
        "problem_type": problem_type,              # 'Healthy' or one of the problem types
        "problem_reason": problem_reason,
        "problem_message": problem_message,
        "total_restart_count": total_restart,
        "last_exit_code": last_exit_code,
        "last_termination_reason": last_term_reason,
        "last_termination_oom": last_term_oom,
    }

# -------------------------------
# Adhoc-style collector (no DB)
# -------------------------------

def collect_k8s_pod_incidents(
    cluster_name: str,
    context: Optional[str] = None,
    long_pending_threshold: int = 300,
) -> List[Dict[str, Any]]:
    """
   Pure collector (adhoc-friendly):

      - Connects to Kubernetes
      - Lists all pods
      - Returns a list of snapshot dicts, one per pod.

      For each snapshot:
        - problem_type = 'Healthy'
          → if no issue was detected

        - problem_type in:
            'CrashLoopBackOff', 'ImagePullBackOff', 'ErrImagePull',
            'OOMKilled', 'LongPending',
            'ProbeFailure', 'StuckTerminating',
            'Unschedulable', 'Evicted'
          → if a corresponding issue was detected

      All snapshots are built purely from the current PodStatus; no DB writes.
    """
    v1 = get_core_v1(context=context)
    now = datetime.now(timezone.utc)

    try:
        pods = v1.list_pod_for_all_namespaces(watch=False).items
    except Exception as e:
        print(f"[ERROR] collect_k8s_pod_incidents: failed to list pods: {e}")
        return []

    snapshots: List[Dict[str, Any]] = []
    for pod in pods:
        record = build_pod_record(
            pod=pod,
            cluster_name=cluster_name,
            now=now,
            long_pending_threshold=long_pending_threshold,
        )
        snapshots.append(record)

    print(
        f"[INFO] collect_k8s_pod_incidents: scanned {len(pods)} pods, "
        f"built {len(snapshots)} pod records"
    )
    return snapshots

# -------------------------------
# Handler (like handle_monitor_system)
# -------------------------------

def handle_monitor_k8s_pods():
    """
    Oneshot handler used by the orchestrator:

      - Reads env vars for cluster/context/threshold
      - Collects snapshots for ALL pods via collect_k8s_pod_incidents
      - Logs each snapshot to the DB via log_k8s_pod_health

    Each DB row in k8s_pod_health will have:
      - problem_type = 'Healthy'
        or one of:
          'CrashLoopBackOff', 'ImagePullBackOff', 'ErrImagePull',
          'OOMKilled', 'LongPending',
          'ProbeFailure', 'StuckTerminating',
          'Unschedulable', 'Evicted'
    """
    cluster_name = os.getenv("K8S_CLUSTER_NAME", "kind-smart-monitor")
    context = os.getenv("K8S_CONTEXT") or None
    long_pending_threshold = int(os.getenv("K8S_LONG_PENDING_THRESHOLD", "300"))

    snapshots = collect_k8s_pod_incidents(
        cluster_name=cluster_name,
        context=context,
        long_pending_threshold=long_pending_threshold,
    )

    logged = 0
    for rec in snapshots:
        log_k8s_pod_health(rec)
        logged += 1

    print(f"[INFO] handle_monitor_k8s_pods: logged {logged} pod snapshots to k8s_pod_health")


# -------------------------------
# Oneshot / daemon mode (optional)
# -------------------------------

if __name__ == "__main__":
    print("[INFO] Starting K8s pod health monitor ...")
    interval = int(os.getenv("K8S_POD_MONITOR_INTERVAL", "60"))  # seconds

    try:
        while True:
            handle_monitor_k8s_pods()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("[INFO] K8s pod health monitor stopped by user.")
