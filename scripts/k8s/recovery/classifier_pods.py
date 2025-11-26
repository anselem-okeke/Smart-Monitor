"""
classifier_pods.py

Pure classification logic for K8s pods based on rows from k8s_pod_health.

- Input: rows from db_access_pods.recent_unhealthy_pods(...)
- Output: "decision" dicts consumed later by remediator_pods

No DB writes, no K8s API, no logging here.
"""

from typing import Any, Dict, Optional, Tuple


# -------------------------------
# Helpers
# -------------------------------

def _row_to_record(row: Tuple[Any, ...]) -> Dict[str, Any]:
    """
    Map a k8s_pod_health row tuple to a named dict.

    Expected tuple order (from recent_unhealthy_pods):
      0: id
      1: timestamp
      2: cluster_name
      3: namespace
      4: pod_name
      5: phase
      6: problem_type
      7: problem_reason
      8: problem_message
      9: total_restart_count
     10: last_exit_code
     11: last_termination_reason
     12: last_termination_oom
    """
    return {
        "id": row[0],
        "timestamp": row[1],
        "cluster_name": row[2],
        "namespace": row[3],
        "pod_name": row[4],
        "phase": row[5],
        "problem_type": row[6],
        "problem_reason": row[7],
        "problem_message": row[8],
        "total_restart_count": row[9],
        "last_exit_code": row[10],
        "last_termination_reason": row[11],
        "last_termination_oom": row[12],
    }


def _build_decision(
    rec: Dict[str, Any],
    severity: str,
    action: str,
    kind: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a standard decision dict from a pod record plus classification data.

    Fields are intentionally flat/simple so remediator can consume them easily.
    """
    return {
        # identity
        "id": rec["id"],
        "timestamp": rec["timestamp"],
        "cluster_name": rec["cluster_name"],
        "namespace": rec["namespace"],
        "pod_name": rec["pod_name"],

        # raw status from k8s_pod_health
        "phase": rec["phase"],
        "problem_type": rec["problem_type"],
        "problem_reason": rec["problem_reason"],
        "problem_message": rec["problem_message"],
        "total_restart_count": rec["total_restart_count"],
        "last_exit_code": rec["last_exit_code"],
        "last_termination_reason": rec["last_termination_reason"],
        "last_termination_oom": rec["last_termination_oom"],

        # classifier output
        "severity": severity,      # e.g. "warning" / "critical"
        "action": action,          # e.g. "auto_restart_pod" / "alert_only" / "ignore"
        "kind": kind or rec["problem_type"],  # logical kind; same as problem_type for now
    }


# -------------------------------
# Tiny classifiers per problem_type
# -------------------------------

def classify_crashloop(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    CrashLoopBackOff → critical, candidate for auto-remediation.
    """
    if rec["problem_type"] != "CrashLoopBackOff":
        return None

    return _build_decision(
        rec=rec,
        severity="critical",
        action="auto_restart_pod",   # v1: only CrashLoopBackOff gets auto-restart
        kind="CrashLoopBackOff",
    )


def classify_oomkilled(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    OOMKilled → critical, but v1 is alert-only (no auto-restart yet).
    """
    if rec["problem_type"] != "OOMKilled":
        return None

    return _build_decision(
        rec=rec,
        severity="critical",
        action="alert_only",
        kind="OOMKilled",
    )


def classify_imagepull(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    ImagePullBackOff / ErrImagePull → deployment/registry issues → alert-only.
    """
    if rec["problem_type"] not in ("ImagePullBackOff", "ErrImagePull"):
        return None

    return _build_decision(
        rec=rec,
        severity="warning",
        action="alert_only",
        kind=rec["problem_type"],
    )


def classify_longpending(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    LongPending → scheduling or resource issues → alert-only in v1.
    """
    if rec["problem_type"] != "LongPending":
        return None

    return _build_decision(
        rec=rec,
        severity="warning",
        action="alert_only",
        kind="LongPending",
    )


def classify_probefailure(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    ProbeFailure → liveness/readiness/startup probe problems → alert-only.
    """
    if rec["problem_type"] != "ProbeFailure":
        return None

    return _build_decision(
        rec=rec,
        severity="warning",
        action="alert_only",
        kind="ProbeFailure",
    )


def classify_stuckterminating(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    StuckTerminating → pod stuck in terminating state → alert-only in v1.
    """
    if rec["problem_type"] != "StuckTerminating":
        return None

    return _build_decision(
        rec=rec,
        severity="warning",
        action="alert_only",
        kind="StuckTerminating",
    )


def classify_unschedulable(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Unschedulable → Pending due to CPU/memory/taints → alert-only.
    """
    if rec["problem_type"] != "Unschedulable":
        return None

    return _build_decision(
        rec=rec,
        severity="warning",
        action="alert_only",
        kind="Unschedulable",
    )


def classify_evicted(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Evicted → node pressure, eviction by kubelet → alert-only in v1.
    """
    if rec["problem_type"] != "Evicted":
        return None

    return _build_decision(
        rec=rec,
        severity="warning",
        action="alert_only",
        kind="Evicted",
    )


# Placeholder for future derived signal (restart-rate / Flapping)
def classify_flapping(rec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Placeholder for a future 'Flapping' classifier that will look at restart
    history across multiple snapshots. For now, we return None.
    """
    return None


# -------------------------------
# Main classifier entry point
# -------------------------------

def classify_pod_row(row: Any) -> Optional[Dict[str, Any]]:
    """
    Public entry point:

      - Accepts a raw DB row from recent_unhealthy_pods(...)
      - Converts it to a dict
      - Runs problem-type-specific classifiers
      - Returns a single decision dict or None

    NOTE:
      - We assume recent_unhealthy_pods already filtered out Healthy pods
        (problem_type <> 'Healthy'), but we guard for it anyway.
    """
    rec = _row_to_record(row)
    ptype = (rec["problem_type"] or "").strip()

    # Safety guard: ignore Healthy rows
    if not ptype or ptype == "Healthy":
        return None

    # In future we can make Flapping highest priority here
    # decision = classify_flapping(rec)
    # if decision:
    #     return decision

    # Next: concrete problem_type classifiers
    for fn in (
        classify_crashloop,
        classify_oomkilled,
        classify_probefailure,
        classify_stuckterminating,
        classify_imagepull,
        classify_longpending,
        classify_unschedulable,
        classify_evicted,
    ):
        decision = fn(rec)
        if decision is not None:
            return decision

    # Fallback: unknown problem_type → warning, alert-only
    return _build_decision(
        rec=rec,
        severity="warning",
        action="alert_only",
        kind=ptype or "Unknown",
    )
