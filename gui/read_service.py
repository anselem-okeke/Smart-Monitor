# ─────────────────────────────────────────────────────────────────────────────
# gui/read_service.py  (all DB READS live here; writes stay in db_logger)
# ─────────────────────────────────────────────────────────────────────────────
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from db.core import resolve_db_path

ROOT = Path(__file__).resolve().parents[1]  # repo root (…/Smart-Factory-IT-Monitor)

# def _load_db_path():
#     cfg_path = ROOT / "config" / "db_config.json"
#     if cfg_path.exists():
#         cfg = json.loads(cfg_path.read_text())
#         p = cfg.get("path") or cfg.get("sqlite_path") or "db/smart_factory_monitor.db"
#     else:
#         p = "db/smart_factory_monitor.db"
#     # Absolute path + SQLite readonly URI
#     abs_p = (ROOT / p).resolve()
#     return f"file:{abs_p.as_posix()}?mode=ro&cache=shared"
#
# DB_URI_RO = _load_db_path()

def _to_sqlite_ro_uri(path):
    p = Path(path).resolve().as_posix()
    if os.name == "nt":
        return f"file:/{p}?mode=ro&cache=shared"
    else:
        return f"file:{p}?mode=ro&cache=shared"


def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def connect_ro():
    db_path = resolve_db_path()
    uri = _to_sqlite_ro_uri(db_path)
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = _dict_factory
    return conn


# ───────── Summary & lists ─────────
def get_summary():
    """Return cards + latest alerts for overview."""
    with connect_ro() as conn:
        cur = conn.cursor()
        # Hosts seen (union of both tables for tolerance)
        hosts = set()
        for row in cur.execute("SELECT DISTINCT hostname FROM system_metrics"):
            if row["hostname"]: hosts.add(row["hostname"])
        for row in cur.execute("SELECT DISTINCT hostname AS host FROM service_status"):
            if row["host"]: hosts.add(row["host"])
        total_hosts = len(hosts)

        # Alerts last 24h
        since = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("SELECT COUNT(*) AS c FROM alerts WHERE timestamp > ?", (since,))
        alerts_24h = cur.fetchone()["c"]
        cur.execute("SELECT COUNT(*) AS c FROM recovery_logs WHERE timestamp > ?", (since,))
        rec_24h = cur.fetchone()["c"]

        # Latest alerts
        cur.execute("""
            SELECT id, timestamp, hostname, severity, source, message
            FROM alerts ORDER BY id DESC LIMIT 10
        """)
        latest_alerts = cur.fetchall()

        # Quick CPU avg over last hour (for fun)
        hour = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            SELECT AVG(cpu_usage) AS avg_cpu
            FROM system_metrics WHERE timestamp > ?
        """, (hour,))
        avg_cpu = round(cur.fetchone()["avg_cpu"] or 0.0, 1)

    return {
        "total_hosts": total_hosts,
        "alerts_24h": alerts_24h,
        "recovery_24h": rec_24h,
        "avg_cpu": avg_cpu,
        "latest_alerts": latest_alerts,
    }