# db_access.py (portable drop-in)
import os, socket, platform
from datetime import datetime, timedelta

from db.core import connect_ro

_IS_PG = os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://"))
_P = "%s" if _IS_PG else "?"  # portable placeholder


def _has_column(conn, table: str, column: str) -> bool:
    """Detect if a column exists, for both SQLite and Postgres."""
    if _IS_PG:
        sql = """
          SELECT 1
          FROM information_schema.columns
          WHERE table_schema = 'public' AND table_name = %s AND column_name = %s
          LIMIT 1
        """
        with conn.cursor() as cur:
            cur.execute(sql, (table, column))
            return cur.fetchone() is not None
    else:
        # SQLite cursors are NOT context managers; don't use "with".
        cur = conn.cursor()
        try:
            cur.execute(f"PRAGMA table_info({table});")
            cols = {row[1] for row in cur.fetchall()}  # name is index 1
            return column in cols
        finally:
            try: cur.close()
            except Exception as e:
                print(f"{e}")
                pass


def db_access_for_service_recovery():
    hostname = socket.gethostname()
    os_platform = platform.system()
    try:
        with connect_ro() as conn:
            use_epoch = _has_column(conn, "service_status", "ts_epoch")

            if use_epoch:
                sql = f"""
                SELECT ss.service_name, ss.normalized_status, ss.hostname,
                       ss.sub_state, ss.service_type, ss.unit_file_state,
                       COALESCE(ss.recoverable, TRUE) AS recoverable
                FROM service_status ss
                JOIN (
                    SELECT service_name, hostname, MAX(ts_epoch) AS max_ts
                    FROM service_status
                    WHERE hostname = {_P} AND os_platform = {_P}
                    GROUP BY service_name, hostname
                ) m
                  ON m.service_name = ss.service_name
                 AND m.hostname     = ss.hostname
                 AND m.max_ts       = ss.ts_epoch
                WHERE ss.hostname    = {_P}
                  AND ss.os_platform = {_P}
                """
                params = (hostname, os_platform, hostname, os_platform)
            else:
                # Fallback using textual timestamp (stored as ISO-8601)
                sql = f"""
                SELECT ss.service_name, ss.normalized_status, ss.hostname,
                       ss.sub_state, ss.service_type, ss.unit_file_state,
                       COALESCE(ss.recoverable, 1) AS recoverable
                FROM service_status ss
                JOIN (
                    SELECT service_name, hostname, MAX("timestamp") AS max_ts
                    FROM service_status
                    WHERE hostname = {_P} AND os_platform = {_P}
                    GROUP BY service_name, hostname
                ) m
                  ON m.service_name = ss.service_name
                 AND m.hostname     = ss.hostname
                 AND m.max_ts       = ss."timestamp"
                WHERE ss.hostname    = {_P}
                  AND ss.os_platform = {_P}
                """
                params = (hostname, os_platform, hostname, os_platform)

            cur = conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()

    except Exception as e:
        print(f"[ERROR] Failed to fetch service status: {e}")
        return []


def count_recent_restart_attempts(service_name, minutes=10):
    interval_limit = datetime.utcnow() - timedelta(minutes=minutes)
    sql = f"""
        SELECT COUNT(*) AS c FROM restart_attempts
        WHERE "timestamp" >= {_P} AND hostname = {_P} AND service_name = {_P}
    """
    params = (interval_limit.isoformat(), socket.gethostname(), service_name)
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else 0


def recent_failed_network_events(host, minutes=5):
    """Return all rows with status != 'success' in the last N minutes."""
    threshold = (datetime.utcnow() - timedelta(minutes=minutes)
                ).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        SELECT id, target, method, result, latency_ms, packet_loss_percent
        FROM network_logs
        WHERE "timestamp" > {_P} AND hostname = {_P} AND status != 'success'
        ORDER BY "timestamp" DESC
    """
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, (threshold, host))
        return cur.fetchall()


def recent_system_metrics(hostname, minutes):
    """
    Returns newest system metrics rows for this host within N minutes.
    Columns we care about: timestamp, disk_usage
    """
    threshold = (datetime.utcnow() - timedelta(minutes=minutes)
                 ).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        SELECT "timestamp", disk_usage
        FROM system_metrics
        WHERE "timestamp" > {_P} AND hostname = {_P}
        ORDER BY "timestamp" DESC
    """
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, (threshold, hostname))
        return cur.fetchall()


def recovery_fail_count(host, service_name, minutes) -> int:
    threshold = (datetime.utcnow() - timedelta(minutes=minutes)
                 ).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        SELECT COUNT(*) AS c FROM recovery_logs
        WHERE hostname = {_P} AND service_name = {_P}
          AND result = 'fail' AND "timestamp" > {_P}
    """
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, (host, service_name, threshold))
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else 0


def recent_inode_usage(host, minutes=5):
    """Return (timestamp, inode_usage) rows within N minutes for host."""
    t = (datetime.utcnow() - timedelta(minutes=minutes)
         ).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        SELECT "timestamp", inode_usage
        FROM system_metrics
        WHERE "timestamp" > {_P} AND hostname = {_P}
        ORDER BY "timestamp" DESC
    """
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, (t, host))
        return cur.fetchall()


def recent_alert_exist(host, source, minutes):
    """Return True if an alert for source was logged within N minutes for host."""
    threshold = (datetime.utcnow() - timedelta(minutes=minutes)
                 ).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        SELECT 1 FROM alerts
        WHERE hostname = {_P} AND source = {_P} AND "timestamp" > {_P}
        LIMIT 1
    """
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, (host, source, threshold))
        return cur.fetchone() is not None


def recent_cpu_samples(host, samples=3, minutes=5):
    """Return the last `samples` rows (timestamp, cpu_usage) within `minutes`. Newest first."""
    threshold = (datetime.utcnow() - timedelta(minutes=minutes)
                 ).strftime("%Y-%m-%d %H:%M:%S")
    samples = int(samples)
    sql = f"""
        SELECT "timestamp", cpu_usage
        FROM system_metrics
        WHERE "timestamp" > {_P} AND hostname = {_P}
        ORDER BY "timestamp" DESC
        LIMIT {samples}
    """
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, (threshold, host))
        return cur.fetchall()


def recent_memory_samples(host, samples=3, minutes=3):
    """Return last `samples` rows (timestamp, memory_usage, swap_usage) within minutes. Newest first."""
    t = (datetime.utcnow() - timedelta(minutes=minutes)
         ).strftime("%Y-%m-%d %H:%M:%S")
    samples = int(samples)
    sql = f"""
        SELECT "timestamp", memory_usage, swap_usage
        FROM system_metrics
        WHERE "timestamp" > {_P} AND hostname = {_P}
        ORDER BY "timestamp" DESC
        LIMIT {samples}
    """
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, (t, host))
        return cur.fetchall()


def recent_load_samples(host, samples=3, minutes=5):
    """Returns last `samples` rows (timestamp, load_average) within minutes. Newest first."""
    t = (datetime.utcnow() - timedelta(minutes=minutes)
         ).strftime("%Y-%m-%d %H:%M:%S")
    samples = int(samples)
    sql = f"""
        SELECT "timestamp", load_average
        FROM system_metrics
        WHERE "timestamp" > {_P} AND hostname = {_P}
        ORDER BY "timestamp" DESC
        LIMIT {samples}
    """
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, (t, host))
        return cur.fetchall()







