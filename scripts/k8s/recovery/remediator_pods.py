"""
remediator_pods.py

Remediation logic for K8s pods, based on decision dicts from classifier_pods.

- Applies guardrails from config_pod_guardrails.json
- For v1, only CrashLoopBackOff is eligible for auto-remediation
- Everything else will be alert-only (implemented later)

This module:
  - READS a small bit from the DB (restart_attempts for cooldown checks)
  - WRITES via db_logger (alerts, recovery_logs, restart_attempts)
  - Talks to K8s API only for allowed auto-actions
"""

import json
import socket
import platform
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from db.core import connect_ro
from db.db_logger import log_alert, log_recovery, log_restart_attempt

# Reuse the K8s client helper from monitor module
from scripts.k8s.monitor.monitor_k8s_pods import get_core_v1

try:
    from utils.network_file_logger import net_log
except ImportError:
    # Fallback stub so this file is importable even if net_log isn't wired yet
    def net_log(level: str, msg: str) -> None:
        print(f"[NETLOG:{level}] {msg}")


# -------------------------------
# Guardrails config loading
# -------------------------------

def _default_guardrails() -> Dict[str, Any]:
    """
    Safe defaults if config file is missing or broken.
    """
    return {
        "enabled": True,
        "dry_run": True,
        "namespace_blacklist": ["kube-system", "kube-public", "kube-node-lease"],
        "namespace_whitelist": [],
        "pod_name_blacklist": [
            "smart-monitor-orchestrator",
            "smart-monitor-db",
            "kube-apiserver",
            "kube-scheduler",
            "kube-controller-manager",
        ],
        "cooldown_seconds_per_pod": 300,
        "max_actions_per_pod": {
            "window_seconds": 3600,
            "max_actions": 3,
        },
        "max_actions_global": {
            "window_seconds": 600,
            "max_actions": 20,
        },
        "allowed_auto_actions": {
            "CrashLoopBackOff": True,
            "OOMKilled": False,
            "ProbeFailure": False,
            "StuckTerminating": False,
            "ImagePullBackOff": False,
            "ErrImagePull": False,
            "LongPending": False,
            "Unschedulable": False,
            "Evicted": False,
            "Flapping": False,
        },
    }


def load_pod_guardrails() -> Dict[str, Any]:
    """
    Load guardrails from config/config_pod_guardrails.json, with safe defaults.
    """
    cfg_path = Path("config/config_pod_guardrails.json")
    if not cfg_path.exists():
        print(f"[WARN] Guardrails config not found at {cfg_path}, using defaults")
        return _default_guardrails()

    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Failed to load guardrails config: {e}, using defaults")
        return _default_guardrails()

    # Mix defaults with overrides
    base = _default_guardrails()
    base.update(data)
    return base


# -------------------------------
# Simple DB-based guardrail helpers
# -------------------------------

def _pod_key(decision: Dict[str, Any]) -> str:
    """
    Build a stable key for this pod for logging/cooldowns.
    """
    return f"k8s://{decision['cluster_name']}/{decision['namespace']}/{decision['pod_name']}"


def _last_restart_attempt_ts(pod_key: str) -> Optional[datetime]:
    """
    Look up the most recent restart_attempts row for this pod_key.
    """
    sql = """
        SELECT "timestamp"
        FROM restart_attempts
        WHERE service_name = %s
        ORDER BY "timestamp" DESC
        LIMIT 1
    """
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, (pod_key,))
        row = cur.fetchone()
        if not row:
            return None
        # For Postgres, timestamp comes back as datetime already
        return row[0]


def _cooldown_ok(pod_key: str, cooldown_sec: int) -> bool:
    """
    Check if enough time has passed since the last restart attempt for this pod.
    """
    if cooldown_sec <= 0:
        return True

    last_ts = _last_restart_attempt_ts(pod_key)
    if not last_ts:
        return True

    now = datetime.now(timezone.utc)
    delta = (now - last_ts).total_seconds()
    if delta < cooldown_sec:
        remaining = int(cooldown_sec - delta)
        print(f"[GUARDRAIL] Cooldown not met for {pod_key}: {remaining}s remaining")
        return False

    return True


# NOTE: For v1 we don't yet enforce max_actions_per_pod / max_actions_global.
# We can add those later as separate helpers once basic flow is stable.


# -------------------------------
# Core decision: should we auto-remediate?
# -------------------------------

def _should_auto_remediate_crashloop(
    decision: Dict[str, Any],
    guardrails: Dict[str, Any],
) -> bool:
    """
    Decide whether we are allowed to auto-remediate this CrashLoopBackOff pod
    according to guardrails.

    Returns True if we *may* attempt a pod delete; False otherwise.
    """
    if not guardrails.get("enabled", True):
        print("[GUARDRAIL] Pod remediation globally disabled")
        return False

    allowed_auto = guardrails.get("allowed_auto_actions", {})
    if not allowed_auto.get("CrashLoopBackOff", False):
        print("[GUARDRAIL] Auto-remediation for CrashLoopBackOff is disabled in config")
        return False

    namespace = decision["namespace"]
    pod_name = decision["pod_name"]

    # Namespace blacklist
    ns_black = set(guardrails.get("namespace_blacklist", []))
    if namespace in ns_black:
        print(f"[GUARDRAIL] Namespace {namespace!r} is blacklisted; skipping auto-remediation")
        return False

    # Namespace whitelist (if non-empty, only those are allowed)
    ns_white = guardrails.get("namespace_whitelist") or []
    if ns_white and namespace not in ns_white:
        print(f"[GUARDRAIL] Namespace {namespace!r} not in whitelist; skipping auto-remediation")
        return False

    # Pod name blacklist
    pod_black = set(guardrails.get("pod_name_blacklist", []))
    if pod_name in pod_black:
        print(f"[GUARDRAIL] Pod {pod_name!r} is blacklisted; skipping auto-remediation")
        return False

    # Cooldown per pod
    cooldown_sec = int(guardrails.get("cooldown_seconds_per_pod", 300))
    key = _pod_key(decision)
    if not _cooldown_ok(key, cooldown_sec):
        return False

    # (In future we could also enforce max_actions_per_pod/global here)
    return True


# -------------------------------
# CrashLoopBackOff remediation
# -------------------------------

def remediate_crashloop(
    decision: Dict[str, Any],
    guardrails: Dict[str, Any],
    context: Optional[str] = None,
) -> None:
    """
    Remediation for CrashLoopBackOff pods.

    v1 behavior:
      - If guardrails say NO → just emit an alert (no delete)
      - If guardrails say YES:
          - If dry_run = true → log what we WOULD do, but don't delete
          - If dry_run = false → delete the pod via K8s API
      - In both cases, log alerts and recovery attempts to DB + net_log.
    """
    pod_key = _pod_key(decision)
    namespace = decision["namespace"]
    pod_name = decision["pod_name"]
    cluster_name = decision["cluster_name"]

    dry_run = bool(guardrails.get("dry_run", True))
    hostname = socket.gethostname()
    os_platform = platform.system()

    # Build a human-readable message
    base_msg = (
        f"[CrashLoopBackOff] cluster={cluster_name} ns={namespace} "
        f"pod={pod_name} restarts={decision['total_restart_count']}"
    )

    may_auto = _should_auto_remediate_crashloop(decision, guardrails)

    # If we are not allowed to auto-remediate, just raise an alert & return
    if not may_auto:
        msg = base_msg + " (auto-remediation blocked by guardrails)"
        log_alert({
            "hostname": hostname,
            "severity": decision.get("severity", "critical"),
            "source": pod_key,
            "message": msg,
        })
        net_log("warning", msg)
        return

    # We ARE allowed by guardrails; now check dry_run
    if dry_run:
        action_result = "dry_run_noop"
        msg = base_msg + " (DRY RUN: would delete pod, but no action taken)"
        delete_success = False
    else:
        # Real deletion: talk to K8s API
        try:
            api = get_core_v1(context=context)
            api.delete_namespaced_pod(
                name=pod_name,
                namespace=namespace,
                grace_period_seconds=0,
            )
            action_result = "deleted"
            msg = base_msg + " (pod delete requested; ReplicaSet/Deployment should recreate)"
            delete_success = True
        except Exception as e:
            action_result = f"delete_failed: {e}"
            msg = base_msg + f" (ERROR deleting pod: {e})"
            delete_success = False

    # Log alert to alerts table
    log_alert({
        "hostname": hostname,
        "severity": decision.get("severity", "critical"),
        "source": pod_key,
        "message": msg,
    })

    # Log to recovery_logs
    log_recovery([{
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": hostname,
        "os_platform": os_platform,
        "service_name": pod_key,
        "result": action_result,
        "error_message": None if delete_success or dry_run else "K8s delete failed",
    }])

    # Record restart_attempt (for cooldown / audit), even in dry_run
    log_restart_attempt({
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": hostname,
        "service_name": pod_key,
    })

    # Log to external logfile
    level = "warning" if delete_success or dry_run else "error"
    net_log(level, msg)


# -------------------------------
# Dispatcher for all pod decisions
# -------------------------------

def remediate_pod(
    decision: Dict[str, Any],
    guardrails: Dict[str, Any],
    context: Optional[str] = None,
) -> None:
    """
    Top-level remediator entry for a single pod decision.

    For v1:
      - CrashLoopBackOff → remediate_crashloop (with guardrails)
      - All other kinds → alert-only (to be implemented later)
    """
    kind = decision.get("kind") or decision.get("problem_type") or "Unknown"

    if kind == "CrashLoopBackOff":
        remediate_crashloop(decision, guardrails, context=context)
        return

    # v1: Everything else is alert-only (no auto-remediation yet)
    hostname = socket.gethostname()
    pod_key = _pod_key(decision)
    msg = (
        f"[{kind}] cluster={decision['cluster_name']} "
        f"ns={decision['namespace']} pod={decision['pod_name']} "
        f"→ alert-only (no auto-remediation in v1)"
    )

    log_alert({
        "hostname": hostname,
        "severity": decision.get("severity", "warning"),
        "source": pod_key,
        "message": msg,
    })
    net_log("warning", msg)
