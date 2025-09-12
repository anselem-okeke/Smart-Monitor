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

def present_columns(conn, table):
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return {row["name"] for row in cur.fetchall()}

def list_hosts():
    """Basic host list with last-seen timestamp + last metrics snapshot."""
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT hostname, MAX(timestamp) AS last_ts
            FROM system_metrics GROUP BY hostname ORDER BY hostname
        """)
        rows = cur.fetchall()
        out = []
        for r in rows:
            hostname = r["hostname"]
            cur.execute("""
                SELECT timestamp, cpu_usage, memory_usage, load_average, swap_usage, inode_usage, disk_usage
                FROM system_metrics WHERE hostname=? ORDER BY id DESC LIMIT 1
            """, (hostname,))
            last = cur.fetchone()
            out.append({"hostname": hostname, "last_ts": r["last_ts"], "last": last})
        return out

def host_metrics(hostname: str, minutes: int = 60, limit: int = 5000):
    """
    Return time-series for charts. If optional columns don't exist, they come back as NULL.
    """
    from datetime import datetime, timedelta
    since = (datetime.utcnow() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    with connect_ro() as conn:
        cols_all = ["timestamp","cpu_usage","memory_usage","load_average","swap_usage","inode_usage","disk_usage"]
        present = present_columns(conn, "system_metrics")
        select_exprs = [c if c in present else f"NULL AS {c}" for c in cols_all]
        sql = f"""
            SELECT {", ".join(select_exprs)}
            FROM system_metrics
            WHERE hostname=? AND timestamp >= ?
            ORDER BY timestamp ASC LIMIT ?
        """
        cur = conn.cursor()
        cur.execute(sql, (hostname, since, limit))
        return cur.fetchall()

def host_services(hostname: str):
    """Latest status per service for a host."""
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT s1.service_name, s1.normalized_status, s1.timestamp
            FROM service_status s1
            JOIN (
              SELECT service_name, MAX(id) AS max_id
              FROM service_status WHERE hostname=? GROUP BY service_name
            ) s2 ON s1.service_name = s2.service_name AND s1.id = s2.max_id
            ORDER BY s1.service_name
        """, (hostname,))
        return cur.fetchall()