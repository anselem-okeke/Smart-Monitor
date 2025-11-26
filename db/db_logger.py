#------------------------------------------
"""Author: Anselem Okeke"""
#------------------------------------------


# db_logger.py (portable version)
import os
from datetime import datetime

# Use the dual-backend helpers from db/core.py
from db.core import connect_rw, execute, ph, resolve_db_path

# Detect PG just to skip SQLite-only schema tweaks
_IS_PG = os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://"))


# ------------------------------------------
# db_logger.py  — portable writes for SQLite & Postgres
# Author: Anselem Okeke
# ------------------------------------------

from datetime import datetime
from typing import Any, Dict, List

from db.core import connect_rw, execute, ph, resolve_db_path

# ---------- numeric coercion helpers ----------
def _f(x: Any):
    """float or None (handles '92', 92, None, 'n/a', etc.)"""
    try:
        if x is None:
            return None
        xf = float(x)
        if xf != xf or xf in (float("inf"), float("-inf")):  # NaN/Inf
            return None
        return xf
    except (TypeError, ValueError):
        return None

def _i(x: Any):
    """int or None (via float → int to allow '3.0')"""
    try:
        if x is None:
            return None
        return int(float(x))
    except (TypeError, ValueError):
        return None

def _trim(s: Any, maxlen: int = 1000) -> str:
    """Safe stringify + truncate for large text fields."""
    if s is None:
        return ""
    out = str(s)
    return out if len(out) <= maxlen else out[:maxlen]


# ---------------------------
# Log system metrics (single row)
# ---------------------------
def log_system_metrics(metrics: Dict[str, Any]):
    """
    metrics keys:
      hostname, os_platform, cpu_usage, memory_usage, disk_usage,
      temperature, uptime, process_count, load_average, inode_usage, swap_usage
    """
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        INSERT INTO system_metrics (
            "timestamp", hostname, os_platform,
            cpu_usage, memory_usage, disk_usage,
            temperature, uptime, process_count, load_average,
            inode_usage, swap_usage
        ) VALUES ({ph(12)})
    """
    params = (
        ts,
        metrics.get("hostname"),
        metrics.get("os_platform"),
        _f(metrics.get("cpu_usage")),
        _f(metrics.get("memory_usage")),
        _f(metrics.get("disk_usage")),
        _f(metrics.get("temperature")),
        _f(metrics.get("uptime")),
        _i(metrics.get("process_count")),
        _f(metrics.get("load_average")),
        _f(metrics.get("inode_usage")),
        _f(metrics.get("swap_usage")),
    )
    try:
        with connect_rw() as conn:
            execute(conn, sql, params)
        print("[INFO] system_metrics insert OK")
    except Exception as e:
        print(f"[ERROR] log_system_metrics: {e}")
        raise


# ---------------------------
# Batch log process status
# ---------------------------
def log_process_status_batch(processes: List[Dict[str, Any]]):
    """
    Each item keys:
      timestamp, hostname, os_platform, pid, process_name, raw_status,
      normalized_status, cpu_percent, memory_percent
    """
    if not processes:
        return
    sql = f"""
        INSERT INTO process_status (
            "timestamp", hostname, os_platform, pid, process_name,
            raw_status, normalized_status, cpu_percent, memory_percent
        ) VALUES ({ph(9)})
    """
    try:
        with connect_rw() as conn:
            for p in processes:
                params = (
                    p.get("timestamp"),
                    p.get("hostname"),
                    p.get("os_platform"),
                    _i(p.get("pid")),
                    p.get("process_name"),
                    p.get("raw_status"),
                    p.get("normalized_status"),
                    _f(p.get("cpu_percent")),
                    _f(p.get("memory_percent")),
                )
                execute(conn, sql, params)
        print(f"[INFO] process_status batch insert OK (rows={len(processes)})")
    except Exception as e:
        print(f"[ERROR] log_process_status_batch: {e}")


# ---------------------------
# Batch log service status
# ---------------------------
def log_service_status_batch(services: List[Dict[str, Any]]):
    if not services:
        return
    db_target = resolve_db_path()  # useful when on SQLite
    print(f"[DEBUG] service_status -> {db_target} (rows={len(services)})")
    sql = f"""
        INSERT INTO service_status (
            "timestamp", hostname, os_platform, service_name, raw_status, normalized_status,
            sub_state, service_type, unit_file_state, recoverable
        ) VALUES ({ph(10)})
    """
    try:
        with connect_rw() as conn:
            for s in services:
                params = (
                    s.get("timestamp"),
                    s.get("hostname"),
                    s.get("os_platform"),
                    s.get("service_name"),
                    s.get("raw_status"),
                    s.get("normalized_status"),
                    s.get("sub_state"),
                    s.get("service_type"),
                    s.get("unit_file_state"),
                    bool(s.get("recoverable", False)),
                )
                execute(conn, sql, params)
        print(f"[INFO] service_status batch insert OK (rows={len(services)})")
    except Exception as e:
        print(f"[ERROR] log_service_status_batch: {e}")


# ------------------------------------------
# Batch log recovery logs
# ------------------------------------------
def log_recovery(entries: List[Dict[str, Any]]):
    """
    entries: list[dict] with keys:
      timestamp, hostname, os_platform, service_name, result, error_message
    """
    if not entries:
        return
    sql = f"""
        INSERT INTO recovery_logs (
            "timestamp", hostname, os_platform, service_name, result, error_message
        ) VALUES ({ph(6)})
    """
    try:
        with connect_rw() as conn:
            for r in entries:
                params = (
                    r.get("timestamp"),
                    r.get("hostname"),
                    r.get("os_platform"),
                    r.get("service_name"),
                    _trim(r.get("result"), 2000),
                    _trim(r.get("error_message"), 2000),
                )
                execute(conn, sql, params)
        print(f"[INFO] recovery_logs batch insert OK (rows={len(entries)})")
    except Exception as e:
        print(f"[ERROR] log_recovery_status_batch: {e}")


# ------------------------------------------
# Log network event (ping, traceroute, etc.)
# ------------------------------------------
def log_network_event(event: Dict[str, Any]):
    """
    Required keys:
      hostname, target, method, result, latency_ms, packet_loss_percent, status
    """
    required = ("hostname", "target", "method", "result", "status")
    try:
        for k in required:
            if k not in event:
                raise KeyError(f"Missing required key: '{k}' in event → {event}")

        sql = f"""
            INSERT INTO network_logs (
                "timestamp", hostname, target, method, result,
                latency_ms, packet_loss_percent, status
            ) VALUES (
                CURRENT_TIMESTAMP, {ph(7)}
            )
        """
        params = (
            event.get("hostname"),
            event.get("target"),
            event.get("method"),
            _trim(event.get("result"), 1000),
            _f(event.get("latency_ms")),
            _f(event.get("packet_loss_percent")),
            event.get("status"),
        )
        with connect_rw() as conn:
            execute(conn, sql, params)
        print("[INFO] network_logs insert OK")
    except Exception as e:
        print(f"[ERROR] log_network_event: {e}")


# ---------------------------
# Log system alert (anomaly, threshold breach)
# ---------------------------
def log_alert(alert: Dict[str, Any]):
    """
    alert keys:
      hostname, severity, source, message
    """
    sql = f"""
        INSERT INTO alerts (
            "timestamp", hostname, severity, source, message
        ) VALUES (CURRENT_TIMESTAMP, {ph(4)})
    """
    params = (
        alert.get("hostname"),
        alert.get("severity"),
        alert.get("source"),
        _trim(alert.get("message"), 2000),
    )
    try:
        with connect_rw() as conn:
            execute(conn, sql, params)
        print("[INFO] alerts insert OK")
    except Exception as e:
        print(f"[ERROR] log_alert: {e}")


# ---------------------------
# Log restart attempts
# ---------------------------
def log_restart_attempt(entry: Dict[str, Any]):
    """
    entry keys: timestamp, hostname, service_name
    """
    sql = f"""
        INSERT INTO restart_attempts (
            "timestamp", hostname, service_name
        ) VALUES ({ph(3)})
    """
    params = (
        entry.get("timestamp"),
        entry.get("hostname"),
        entry.get("service_name"),
    )
    try:
        with connect_rw() as conn:
            execute(conn, sql, params)
        print("[INFO] restart_attempts insert OK")
    except Exception as e:
        print(f"[ERROR] restart_attempts: {e}")


# ---------------------------
# SQLite-only schema adders (no-op on Postgres)
# ---------------------------
def create_inode_usage_column():
    if _IS_PG:
        print("[INFO] (PG) inode_usage already present; skip ALTER")
        return
    sql = "ALTER TABLE system_metrics ADD COLUMN inode_usage REAL;"
    try:
        with connect_rw() as conn:
            try:
                execute(conn, sql)
                print("[INFO] Column 'inode_usage' added.")
            except Exception as e:
                msg = str(e).lower()
                if "duplicate column" in msg or "already exists" in msg:
                    print("[INFO] column inode_usage already exists")
                else:
                    print(f"[ERROR] {e}")
    except Exception as e:
        print(f"[ERROR] create_inode_usage_column: {e}")

def create_swap_usage_column():
    if _IS_PG:
        print("[INFO] (PG) swap_usage already present; skip ALTER")
        return
    sql = "ALTER TABLE system_metrics ADD COLUMN swap_usage REAL;"
    try:
        with connect_rw() as conn:
            try:
                execute(conn, sql)
                print("[INFO] Column 'swap_usage' added.")
            except Exception as e:
                msg = str(e).lower()
                if "duplicate column" in msg or "already exists" in msg:
                    print("[INFO] column swap_usage already exists")
                else:
                    print(f"[ERROR] {e}")
    except Exception as e:
        print(f"[ERROR] create_swap_usage_column: {e}")


# -------------------------------------
# SMART health (single or many rows)
# -------------------------------------
def log_smart_health(entries):
    """
    Insert one or many SMART results.
    Each entry: {
      "hostname": str,
      "device": str,             # e.g. /dev/sda or \\.\PHYSICALDRIVE0
      "health": str,             # e.g. PASSED / FAILED / Unknown
      "model": str | None,
      "temp_c": float | None,    # numeric; coerced to float or None
      "output": str | None       # raw smartctl snippet; truncated
    }
    """
    rows = entries if isinstance(entries, list) else [entries]
    sql = f"""
        INSERT INTO smart_health
          ("timestamp", hostname, device, health, model, temp_c, output)
        VALUES (CURRENT_TIMESTAMP, {ph(6)})
    """
    try:
        with connect_rw() as conn:
            for r in rows:
                params = (
                    r.get("hostname"),
                    r.get("device"),
                    # normalize health a bit but keep original if not a str
                    (r.get("health") or "").strip() if isinstance(r.get("health"), str) else r.get("health"),
                    _trim(r.get("model"), 255),
                    _f(r.get("temp_c")),                 # <-- numeric coercion
                    _trim(r.get("output"), 4000),        # <-- cap size to avoid huge rows
                )
                execute(conn, sql, params)
        print(f"[INFO] smart_health insert OK (rows={len(rows)})")
    except Exception as e:
        print(f"[ERROR] log_smart_health: {e}")


# ------------------------------------------
# Kubernetes v1 logging
#   - k8s_pod_health: only problematic pods (CrashLoop, OOM, ImagePull, LongPending)
#   - k8s_cluster_health: API up/down snapshots
# ------------------------------------------
from typing import Dict, Any


def log_k8s_pod_health(incident: Dict[str, Any]) -> None:
    """
    Insert a single Kubernetes pod incident into k8s_pod_health.

    This is **incident-only**: call it only when there is a problem, for example:
      - problem_type = 'CrashLoopBackOff'
      - problem_type = 'ImagePullBackOff' or 'ErrImagePull'
      - problem_type = 'OOMKilled'
      - problem_type = 'LongPending'

    Expected keys in `incident`:
      - cluster_name: str
      - namespace: str
      - pod_name: str
      - phase: Optional[str]  (Running / Pending / Failed / Unknown)
      - problem_type: Optional[str]
      - problem_reason: Optional[str]
      - problem_message: Optional[str]
      - total_restart_count: Optional[int]
      - last_exit_code: Optional[int]
      - last_termination_reason: Optional[str]
      - last_termination_oom: Optional[bool]
    """
    sql = f"""
        INSERT INTO k8s_pod_health (
            "timestamp",
            cluster_name,
            namespace,
            pod_name,
            phase,
            problem_type,
            problem_reason,
            problem_message,
            total_restart_count,
            last_exit_code,
            last_termination_reason,
            last_termination_oom
        ) VALUES (
            CURRENT_TIMESTAMP,
            {ph(11)}
        )
    """

    params = (
        incident.get("cluster_name"),
        incident.get("namespace"),
        incident.get("pod_name"),
        incident.get("phase"),
        incident.get("problem_type"),
        incident.get("problem_reason"),
        _trim(incident.get("problem_message"), 2000),
        _i(incident.get("total_restart_count")),
        _i(incident.get("last_exit_code")),
        incident.get("last_termination_reason"),
        bool(incident.get("last_termination_oom")) if incident.get("last_termination_oom") is not None else None,
    )

    try:
        with connect_rw() as conn:
            execute(conn, sql, params)
        print("[INFO] k8s_pod_health insert OK")
    except Exception as e:
        print(f"[ERROR] log_k8s_pod_health: {e}")


def log_k8s_cluster_health(snapshot: Dict[str, Any]) -> None:
    """
    Insert a Kubernetes cluster API health snapshot into k8s_cluster_health.

    Recommended usage for v1:
      - Call this only when API is unreachable (api_reachable = False)
        and optionally when it recovers (api_reachable = True).

    Expected keys in `snapshot`:
      - cluster_name: str
      - api_reachable: bool
      - k8s_version: Optional[str]
    """
    sql = f"""
        INSERT INTO k8s_cluster_health (
            "timestamp",
            cluster_name,
            api_reachable,
            k8s_version
        ) VALUES (
            CURRENT_TIMESTAMP,
            {ph(3)}
        )
    """

    params = (
        snapshot.get("cluster_name"),
        bool(snapshot.get("api_reachable")),
        snapshot.get("k8s_version"),
    )

    try:
        with connect_rw() as conn:
            execute(conn, sql, params)
        print("[INFO] k8s_cluster_health insert OK")
    except Exception as e:
        print(f"[ERROR] log_k8s_cluster_health: {e}")




















# # ---------- helpers ----------
# def _num_or_none(x):
#     """
#     Normalize numeric-ish values to float/int or None.
#     Handles 'Not Available', 'N/A', '', NaN, inf, etc.
#     """
#     if x is None:
#         return None
#     if isinstance(x, (int, float)):
#         try:
#             xf = float(x)
#             if xf != xf or xf in (float("inf"), float("-inf")):
#                 return None
#             return xf
#         except Exception:
#             return None
#     if isinstance(x, str):
#         s = x.strip().lower()
#         if s in ("", "n/a", "na", "not available", "none", "null", "-", "nan"):
#             return None
#         try:
#             xf = float(s)
#             if xf != xf or xf in (float("inf"), float("-inf")):
#                 return None
#             return xf
#         except Exception:
#             return None
#     return None
#
# def _int_or_none(x):
#     v = _num_or_none(x)
#     if v is None:
#         return None
#     try:
#         return int(v)
#     except Exception:
#         return None
#
#
#
# # ---------------------------
# # Log system metrics (single row)
# # ---------------------------
# def log_system_metrics(metrics):
#     """
#     metrics keys:
#       hostname, os_platform,
#       cpu_usage, memory_usage, disk_usage,
#       temperature, uptime, process_count, load_average,
#       inode_usage, swap_usage
#     """
#     ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
#     sql = f"""
#         INSERT INTO system_metrics (
#             "timestamp", hostname, os_platform,
#             cpu_usage, memory_usage, disk_usage,
#             temperature, uptime, process_count, load_average,
#             inode_usage, swap_usage
#         ) VALUES ({ph(12)})
#     """
#     params = (
#         ts,
#         metrics.get("hostname"),
#         metrics.get("os_platform"),
#         _num_or_none(metrics.get("cpu_usage")),
#         _num_or_none(metrics.get("memory_usage")),
#         _num_or_none(metrics.get("disk_usage")),
#         _num_or_none(metrics.get("temperature")),
#         _num_or_none(metrics.get("uptime")),
#         _int_or_none(metrics.get("process_count")),
#         _num_or_none(metrics.get("load_average")),
#         _num_or_none(metrics.get("inode_usage")),
#         _num_or_none(metrics.get("swap_usage")),
#     )
#     try:
#         with connect_rw() as conn:
#             execute(conn, sql, params)
#         print("[INFO] system_metrics insert OK")
#     except Exception as e:
#         print(f"[ERROR] log_system_metrics: {e}")
#         raise
#
# # ---------------------------
# # Batch log process status
# # ---------------------------
# def log_process_status_batch(processes):
#     """
#     processes: list of dicts with keys:
#       timestamp, hostname, os_platform, pid, process_name, raw_status,
#       normalized_status, cpu_percent, memory_percent
#     """
#     if not processes:
#         return
#     sql = f"""
#         INSERT INTO process_status (
#             "timestamp", hostname, os_platform, pid, process_name,
#             raw_status, normalized_status, cpu_percent, memory_percent
#         ) VALUES ({ph(9)})
#     """
#     try:
#         with connect_rw() as conn:
#             for p in processes:
#                 params = (
#                     p.get("timestamp"),
#                     p.get("hostname"),
#                     p.get("os_platform"),
#                     _int_or_none(p.get("pid")),
#                     p.get("process_name"),
#                     p.get("raw_status"),
#                     p.get("normalized_status"),
#                     _num_or_none(p.get("cpu_percent")),
#                     _num_or_none(p.get("memory_percent")),
#                 )
#                 execute(conn, sql, params)
#         print(f"[INFO] process_status batch insert OK (rows={len(processes)})")
#     except Exception as e:
#         print(f"[ERROR] log_process_status_batch: {e}")
#
# # ---------------------------
# # Batch log service status
# # ---------------------------
# def log_service_status_batch(services):
#     db_target = resolve_db_path()  # still useful when on SQLite
#     print(f"[DEBUG] service_status -> {db_target} (rows={len(services)})")
#     if not services:
#         return
#     sql = f"""
#         INSERT INTO service_status (
#             "timestamp", hostname, os_platform, service_name,
#             raw_status, normalized_status, sub_state, service_type,
#             unit_file_state, recoverable
#         ) VALUES ({ph(10)})
#     """
#     try:
#         with connect_rw() as conn:
#             for s in services:
#                 params = (
#                     s.get("timestamp"),
#                     s.get("hostname"),
#                     s.get("os_platform"),
#                     s.get("service_name"),
#                     s.get("raw_status"),
#                     s.get("normalized_status"),
#                     s.get("sub_state"),
#                     s.get("service_type"),
#                     s.get("unit_file_state"),
#                     bool(s.get("recoverable", False)),
#                 )
#                 execute(conn, sql, params)
#         print(f"[INFO] service_status batch insert OK (rows={len(services)})")
#     except Exception as e:
#         print(f"[ERROR] log_service_status_batch: {e}")
#
# # ---------------------------
# # Batch log recovery logs
# # ---------------------------
# def log_recovery(service_name):
#     """
#     service_name: list[dict] with keys:
#       timestamp, hostname, os_platform, service_name, result, error_message
#     """
#     if not service_name:
#         return
#     sql = f"""
#         INSERT INTO recovery_logs (
#             "timestamp", hostname, os_platform, service_name, result, error_message
#         ) VALUES ({ph(6)})
#     """
#     try:
#         with connect_rw() as conn:
#             for r in service_name:
#                 params = (
#                     r.get("timestamp"),
#                     r.get("hostname"),
#                     r.get("os_platform"),
#                     r.get("service_name"),
#                     r.get("result"),
#                     r.get("error_message"),
#                 )
#                 execute(conn, sql, params)
#         print(f"[INFO] recovery_logs batch insert OK (rows={len(service_name)})")
#     except Exception as e:
#         print(f"[ERROR] log_recovery_status_batch: {e}")
#
# # ---------------------------
# # Log network event
# # ---------------------------
# def log_network_event(event):
#     """
#     event keys required:
#       hostname, target, method, result, latency_ms, packet_loss_percent, status
#     """
#     required = ("hostname", "target", "method", "result", "status")
#     try:
#         for k in required:
#             if k not in event:
#                 raise KeyError(f"Missing required key: '{k}' in event -> {event}")
#
#         sql = f"""
#             INSERT INTO network_logs (
#                 "timestamp", hostname, target, method, result,
#                 latency_ms, packet_loss_percent, status
#             ) VALUES (
#                 CURRENT_TIMESTAMP, {ph(7)}
#             )
#         """
#         params = (
#             event.get("hostname"),
#             event.get("target"),
#             event.get("method"),
#             str(event.get("result", ""))[:1000],  # keep it reasonable
#             _num_or_none(event.get("latency_ms")),
#             _num_or_none(event.get("packet_loss_percent")),
#             event.get("status"),
#         )
#         with connect_rw() as conn:
#             execute(conn, sql, params)
#         print("[INFO] network_logs insert OK")
#     except Exception as e:
#         print(f"[ERROR] log_network_event: {e}")
#
# # ---------------------------
# # Log system alert (anomaly, threshold breach)
# # ---------------------------
# def log_alert(alert):
#     """
#     alert keys:
#       hostname, severity, source, message
#     """
#     sql = f"""
#         INSERT INTO alerts (
#             "timestamp", hostname, severity, source, message
#         ) VALUES (CURRENT_TIMESTAMP, {ph(4)})
#     """
#     params = (
#         alert.get('hostname'),
#         alert['severity'],
#         alert['source'],
#         alert['message'],
#     )
#     try:
#         with connect_rw() as conn:
#             execute(conn, sql, params)
#         print("[INFO] alerts insert OK")
#     except Exception as e:
#         print(f"[ERROR] log_alert: {e}")
#
# # ---------------------------
# # Log restart attempts
# # ---------------------------
# def log_restart_attempt(entry):
#     """
#     entry keys: timestamp, hostname, service_name
#     """
#     sql = f"""
#         INSERT INTO restart_attempts (
#             "timestamp", hostname, service_name
#         ) VALUES ({ph(3)})
#     """
#     params = (
#         entry.get("timestamp"),
#         entry.get("hostname"),
#         entry.get("service_name"),
#     )
#     try:
#         with connect_rw() as conn:
#             execute(conn, sql, params)
#         print("[INFO] restart_attempts insert OK")
#     except Exception as e:
#         print(f"[ERROR] restart_attempts: {e}")





































# import sqlite3
# from datetime import datetime
# from db.core import DB_PATH, connect_rw, resolve_db_path
#
#
# # CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config/db_config.json"))
# # with open(CONFIG_PATH, "r") as f:
# #     config = json.load(f)
# #
# # DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../" + config["path"]))
# # print(f"[DEBUG] Connecting to DB at: {DB_PATH}")
#
#
#
# def log_system_metrics(metrics):
#     """
#     metrics should have keys:
#       hostname, os_platform, cpu_usage, memory_usage, disk_usage,
#       temperature, uptime, process_count, load_average, inode_usage, swap_usage
#     """
#     try:
#         with connect_rw() as conn:
#             conn.execute("""
#                 INSERT INTO system_metrics (
#                     timestamp, hostname, os_platform, cpu_usage, memory_usage,
#                     disk_usage, temperature, uptime, process_count, load_average,
#                     inode_usage, swap_usage
#                 ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
#             """, (
#                 datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
#                 metrics['hostname'],
#                 metrics['os_platform'],
#                 metrics['cpu_usage'],
#                 metrics['memory_usage'],
#                 metrics['disk_usage'],
#                 metrics['temperature'],
#                 metrics['uptime'],
#                 metrics['process_count'],
#                 metrics['load_average'],
#                 metrics['inode_usage'],
#                 metrics['swap_usage'],
#             ))
#             # context manager commits on successful block exit
#         print(f"[INFO] system_metrics insert OK → {DB_PATH}")
#     except Exception as e:
#         # Make failures visible to the orchestrator logs
#         print(f"[ERROR] log_system_metrics: {e}")
#         raise
#
# # ---------------------------
# # Batch log process status
# # ---------------------------
# def log_process_status_batch(processes):
#     conn = None
#     try:
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#
#         cursor.executemany("""
#             INSERT INTO process_status (
#                 timestamp, hostname, os_platform, pid, process_name, raw_status, normalized_status,
#                 cpu_percent, memory_percent
#             ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
#         """, [
#             (
#                 proc['timestamp'],
#                 proc['hostname'],
#                 proc['os_platform'],
#                 proc['pid'],
#                 proc['process_name'],
#                 proc['raw_status'],
#                 proc['normalized_status'],
#                 proc['cpu_percent'],
#                 proc['memory_percent']
#             ) for proc in processes
#         ])
#
#         conn.commit()
#     except Exception as e:
#         print(f"[ERROR] log_process_status_batch: {e}")
#     finally:
#         if conn:
#             conn.close()
#
# # ---------------------------
# # Batch log service status
# # ---------------------------
# def log_service_status_batch(services):
#     db_target = resolve_db_path()
#     print(f"[DEBUG] service_status -> {db_target} (rows={len(services)})")
#
#     conn = None
#     try:
#         conn = connect_rw()
#         cursor = conn.cursor()
#
#         cursor.executemany("""
#             INSERT INTO service_status (
#                 timestamp, hostname, os_platform, service_name, raw_status, normalized_status,
#                 sub_state, service_type, unit_file_state, recoverable
#             ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
#         """, [
#             (
#                 svc['timestamp'],
#                 svc['hostname'],
#                 svc['os_platform'],
#                 svc['service_name'],
#                 svc['raw_status'],
#                 svc['normalized_status'],
#                 svc['sub_state'],
#                 svc['service_type'],
#                 svc['unit_file_state'],
#                 svc['recoverable']
#             ) for svc in services
#         ])
#
#         conn.commit()
#     except Exception as e:
#         print(f"[ERROR] log_service_status_batch: {e}")
#     finally:
#         if conn:
#             conn.close()
#
# # ------------------------------------------
# # Batch log recovery log
# # ------------------------------------------
# def log_recovery(service_name):
#     conn = None
#     try:
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#
#         cursor.executemany("""
#             INSERT INTO recovery_logs (
#                 timestamp, hostname, os_platform, service_name, result, error_message
#             ) VALUES (?, ?, ?, ?, ?, ?)
#         """, [
#             (
#                 svc['timestamp'],
#                 svc['hostname'],
#                 svc['os_platform'],
#                 svc['service_name'],
#                 svc['result'],
#                 svc['error_message']
#             ) for svc in service_name
#         ])
#
#         conn.commit()
#     except Exception as e:
#         print(f"[ERROR] log_recovery_status_batch: {e}")
#     finally:
#         if conn:
#             conn.close()
#
# # ------------------------------------------
# # Log network event (ping, traceroute, etc.)
# # ------------------------------------------
# def log_network_event(event):
#     conn = None
#     try:
#         required_keys = ["hostname", "target", "method", "result", "latency_ms", "packet_loss_percent", "status"]
#         for key in required_keys:
#             if key not in event:
#                 raise KeyError(f"Missing required key: '{key}' in event → {event}")
#
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#
#         cursor.execute("""
#             INSERT INTO network_logs (
#                 timestamp, hostname, target, method, result,
#                 latency_ms, packet_loss_percent, status
#             ) VALUES (
#                 CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?
#             )
#         """, (
#             event['hostname'],
#             event['target'],
#             event['method'],
#             event['result'],
#             event.get('latency_ms'),
#             event.get('packet_loss_percent'),
#             event['status']
#         ))
#
#         conn.commit()
#     except Exception as e:
#         print(f"[ERROR] log_network_event: {e}")
#     finally:
#         if conn:
#             conn.close()
#
#
# # ---------------------------
# # Log system alert (anomaly, threshold breach)
# # ---------------------------
# def log_alert(alert):
#     conn = None
#     try:
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#
#         cursor.execute("""
#             INSERT INTO alerts (
#                 timestamp, hostname, severity, source, message
#             ) VALUES (
#                 CURRENT_TIMESTAMP, ?, ?, ?, ?
#             )
#         """, (
#             alert['hostname'],
#             alert['severity'],
#             alert['source'],
#             alert['message']
#         ))
#
#         conn.commit()
#     except Exception as e:
#         print(f"[ERROR] log_alert: {e}")
#     finally:
#         if conn:
#             conn.close()
#
# # ---------------------------
# # Log restart attempts
# # ---------------------------
# def log_restart_attempt(entry):
#     conn = None
#     try:
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#         cursor.execute("""
#             INSERT INTO restart_attempts (
#                 timestamp, hostname, service_name
#             ) VALUES (?, ?, ?)
#         """, (
#             entry['timestamp'],
#             entry['hostname'],
#             entry['service_name']
#         ))
#
#         conn.commit()
#     except Exception as e:
#         print(f"[ERROR] restart_attempts: {e}")
#     finally:
#         if conn:
#             conn.close()
#
# # ---------------------------
# # Adding inode_usage into log system metrics
# # ---------------------------
# def create_inode_usage_column():
#     conn = sqlite3.connect(DB_PATH)
#     cur = conn.cursor()
#     try:
#         cur.execute("ALTER TABLE system_metrics ADD COLUMN inode_usage REAL;")
#         print("[INFO] Column 'inode_usage' added.")
#     except sqlite3.OperationalError as e:
#         if "duplicate column name" in str(e).lower():
#             print("[INFO] column inode_usage already exits")
#         else:
#             print(f"[ERROR] {e}")
#     finally:
#         conn.commit()
#         conn.close()
#
# # ---------------------------
# # Adding swap_usage into log system metrics
# # ---------------------------
# def create_swap_usage_column():
#     conn = sqlite3.connect(DB_PATH)
#     cur = conn.cursor()
#     try:
#         cur.execute("ALTER TABLE system_metrics ADD COLUMN swap_usage REAL;")
#         print("[INFO] Column 'swap_usage' added.")
#     except sqlite3.OperationalError as e:
#         if "duplicate column name" in str(e).lower():
#             print("[INFO] column swap_usage already exits")
#         else:
#             print(f"[ERROR] {e}")
#     finally:
#         conn.commit()
#         conn.close()
#
# # -------------------------------------
# #    SMART health
# # -------------------------------------
# def log_smart_health(entries):
#     """
#     Insert one or many SMART results.
#     Each entry: {
#       "hostname": str,
#       "device": str,             # e.g. /dev/sda or \\.\PHYSICALDRIVE0
#       "health": str,             # PASSED / FAILED / Unknown
#       "model": str | None,
#       "temp_c": float | None,
#       "output": str | None       # raw smartctl -H/-A snippet (optional)
#     }
#     """
#     conn = None
#     try:
#         conn = sqlite3.connect(DB_PATH)
#         cur = conn.cursor()
#         rows = entries if isinstance(entries, list) else [entries]
#         cur.executemany("""
#             INSERT INTO smart_health
#               (timestamp, hostname, device, health, model, temp_c, output)
#             VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)
#         """, [
#             (
#                 r.get("hostname"),
#                 r.get("device"),
#                 r.get("health"),
#                 r.get("model"),
#                 r.get("temp_c"),
#                 r.get("output"),
#             )
#             for r in rows
#         ])
#         conn.commit()
#     except Exception as e:
#         print(f"[ERROR] log_smart_health: {e}")
#     finally:
#         if conn:
#             conn.close()
#


