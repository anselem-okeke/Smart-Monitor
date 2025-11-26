"""
remediator_cluster.py

Alert-only remediation for cluster-level issues (API down).

- Uses config_cluster_guardrails.json
- Enforces per-cluster cooldown (min_alert_interval_seconds)
- Writes alerts + restart_attempts + net_log
"""

import json
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from db.core import connect_ro
from db.db_logger import log_alert, log_restart_attempt

try:
    from utils.network_file_logger import net_log
except ImportError:
    def net_log(level: str, msg: str) -> None:
        print(f"[NETLOG:{level}] {msg}")


# -------------------------------
# Guardrails loading
# -------------------------------

def _default_guardrails() -> Dict[str, Any]:
    return {
        "enabled": True,
        "cluster_blacklist": [],
        "cluster_whitelist": [],
        "min_alert_interval_seconds": 300,
    }


def load_cluster_guardrails() -> Dict[str, Any]:
    cfg_path = Path("config/config_cluster_guardrails.json")
    if not cfg_path.exists():
        print(f"[WARN] Cluster guardrails not found at {cfg_path}, using defaults")
        return _default_guardrails()

    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Failed to load cluster guardrails: {e}, using defaults")
        return _default_guardrails()

    base = _default_guardrails()
    base.update(data)
    return base


# -------------------------------
# Cooldown helpers
# -------------------------------

def _cluster_key(cluster_name: str) -> str:
    return f"k8s-cluster://{cluster_name}"


def _last_cluster_alert_ts(cluster_key: str) -> Optional[datetime]:
    """
    Use restart_attempts as generic 'we acted on this key' log.
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
        cur.execute(sql, (cluster_key,))
        row = cur.fetchone()
        if not row:
            return None
        return row[0]


def _cooldown_ok(cluster_key: str, min_interval: int) -> bool:
    if min_interval <= 0:
        return True

    last_ts = _last_cluster_alert_ts(cluster_key)
    if not last_ts:
        return True

    now = datetime.now(timezone.utc)
    delta = (now - last_ts).total_seconds()
    if delta < min_interval:
        remaining = int(min_interval - delta)
        print(f"[GUARDRAIL] Cluster alert cooldown not met for {cluster_key}: {remaining}s remaining")
        return False

    return True

# -------------------------------
# Remediator
# -------------------------------

def remediate_cluster(decision: Dict[str, Any], guardrails: Dict[str, Any]) -> None:
    """
    v1: alert-only. No auto-fix for clusters.

    We log:
      - alerts row
      - restart_attempt (for cooldown)
      - net_log line
    """
    if not guardrails.get("enabled", True):
        print("[GUARDRAIL] Cluster remediation globally disabled")
        return

    cluster_name = decision["cluster_name"]
    cluster_key = _cluster_key(cluster_name)

    blk = set(guardrails.get("cluster_blacklist", []))
    if cluster_name in blk:
        print(f"[GUARDRAIL] Cluster {cluster_name!r} is blacklisted; skipping cluster alert")
        return

    wl = guardrails.get("cluster_whitelist") or []
    if wl and cluster_name not in wl:
        print(f"[GUARDRAIL] Cluster {cluster_name!r} not in whitelist; skipping cluster alert")
        return

    min_interval = int(guardrails.get("min_alert_interval_seconds", 300))
    if not _cooldown_ok(cluster_key, min_interval):
        return

    hostname = socket.gethostname()
    msg = decision["message"]
    severity = decision.get("severity", "critical")

    # alerts
    log_alert({
        "hostname": hostname,
        "severity": severity,
        "source": cluster_key,
        "message": msg,
    })

    # restart_attempts (used here as "we sent a cluster alert at this time")
    log_restart_attempt({
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": hostname,
        "service_name": cluster_key,
    })

    # logfile
    net_log("critical", msg)
