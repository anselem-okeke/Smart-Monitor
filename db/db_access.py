import json
import os
import platform
import socket
import sqlite3
from datetime import  datetime, timedelta
from db.core import DB_PATH, connect_ro

# CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config/db_config.json"))
# with open(CONFIG_PATH, "r") as f:
#     config = json.load(f)
#
# DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../" + config["path"]))


# def db_access_for_service_recovery():
#     conn = None
#     hostname    = socket.gethostname()
#     os_platform = platform.system()
#
#     print(f"[DEBUG] db_access: host={hostname}  os={os_platform}")
#
#     try:
#         conn   = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#
#         cursor.execute("""
#             SELECT service_name,
#                    normalized_status,
#                    hostname                -- keep for sanity-check
#             FROM   service_status
#             WHERE  hostname    = ?
#               AND  os_platform = ?
#               AND  timestamp = (
#                     SELECT MAX(timestamp)
#                     FROM   service_status AS s2
#                     WHERE  s2.service_name = service_status.service_name
#                       AND  s2.hostname     = service_status.hostname
#                   )
#         """, (hostname, os_platform))
#
#         rows = cursor.fetchall()
#
#         # ── DEBUG: show what we got ───────────────────────────────
#         for r in rows:
#             print(f"[DEBUG] db_access row → {r}")   # ('nginx.service', 'stopped', 'web01')
#         print(f"[DEBUG] db_access total rows: {len(rows)}\n")
#
#         return rows
#
#     except Exception as e:
#         print(f"[ERROR] Failed to fetch service status: {e}")
#         return []
#
#     finally:
#         conn and conn.close()

# def db_access_for_service_recovery():
#     hostname = socket.gethostname()
#     os_platform = platform.system()
#     conn = None
#     try:
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#
#         cursor.execute(
#             """
#             SELECT service_name, normalized_status, hostname
#             FROM service_status
#             WHERE hostname     = ?
#               AND os_platform  = ?
#               AND timestamp = (
#                   SELECT MAX(timestamp)
#                   FROM service_status s2
#                   WHERE s2.service_name = service_status.service_name
#                     AND s2.hostname     = service_status.hostname
#               )
#             """,
#             (hostname, os_platform)
#         )
#
#         rows = cursor.fetchall()
#         return rows
#
#     except Exception as e:
#         print(f"[ERROR] Failed to fetch service status: {e}")
#         return []
#
#     finally:
#         if conn:
#             conn.close()


# def db_access_for_service_recovery():
#     hostname = socket.gethostname()
#     os_platform = platform.system()
#     conn = None
#     try:
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#
#         cursor.execute(
#             """
#             SELECT service_name, normalized_status, hostname,
#                    sub_state, service_type, unit_file_state, recoverable
#             FROM service_status
#             WHERE hostname     = ?
#               AND os_platform  = ?
#               AND timestamp = (
#                   SELECT MAX(timestamp)
#                   FROM service_status s2
#                   WHERE s2.service_name = service_status.service_name
#                     AND s2.hostname     = service_status.hostname
#               )
#             """,
#             (hostname, os_platform)
#         )
#
#         rows = cursor.fetchall()
#         return rows
#
#     except Exception as e:
#         print(f"[ERROR] Failed to fetch service status: {e}")
#         return []
#
#     finally:
#         if conn:
#             conn.close()

def db_access_for_service_recovery():
    hostname = socket.gethostname()
    os_platform = platform.system()
    conn = None
    try:
        conn = connect_ro()  # your hardened RO connector
        cur = conn.cursor()

        # Detect ts_epoch
        cols = {c[1] for c in cur.execute("PRAGMA table_info(service_status);").fetchall()}
        use_epoch = "ts_epoch" in cols

        if use_epoch:
            sql = """
            SELECT ss.service_name, ss.normalized_status, ss.hostname,
                   ss.sub_state, ss.service_type, ss.unit_file_state,
                   COALESCE(ss.recoverable,1) AS recoverable
            FROM service_status ss
            JOIN (
                SELECT service_name, hostname, MAX(ts_epoch) AS max_ts
                FROM service_status
                WHERE hostname = ? AND os_platform = ?
                GROUP BY service_name, hostname
            ) m
              ON m.service_name = ss.service_name
             AND m.hostname     = ss.hostname
             AND m.max_ts       = ss.ts_epoch
            WHERE ss.hostname    = ?
              AND ss.os_platform = ?
            """
        else:
            # Fallback using timestamp text; assumes ISO-8601 UTC strings
            sql = """
            SELECT ss.service_name, ss.normalized_status, ss.hostname,
                   ss.sub_state, ss.service_type, ss.unit_file_state,
                   COALESCE(ss.recoverable,1) AS recoverable
            FROM service_status ss
            JOIN (
                SELECT service_name, hostname, MAX(timestamp) AS max_ts
                FROM service_status
                WHERE hostname = ? AND os_platform = ?
                GROUP BY service_name, hostname
            ) m
              ON m.service_name = ss.service_name
             AND m.hostname     = ss.hostname
             AND m.max_ts       = ss.timestamp
            WHERE ss.hostname    = ?
              AND ss.os_platform = ?
            """

        rows = cur.execute(sql, (hostname, os_platform, hostname, os_platform)).fetchall()
        return rows

    except Exception as e:
        print(f"[ERROR] Failed to fetch service status: {e}")
        return []
    finally:
        if conn:
            conn.close()




def count_recent_restart_attempts(service_name, minutes=10):
    interval_limit = datetime.utcnow() - timedelta(minutes=minutes)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*) FROM restart_attempts
        WHERE timestamp >= ? AND hostname = ? AND service_name = ?
    """, (
        interval_limit.isoformat(),
        socket.gethostname(),
        service_name
    ))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def mark_service_running(service_name, hostname, platform_name):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO service_status (
            timestamp,
            hostname,
            os_platform,
            service_name,
            raw_status,
            normalized_status
        )
        VALUES (CURRENT_TIMESTAMP, ?, ?, ?, 'running', 'active')
    """,
        (service_name, hostname, platform_name),
    )
    conn.commit()
    conn.close()

def recent_failed_network_events(host, minutes=5):
    """Return all rows with status != 'success' in the last N minutes."""
    threshold = (datetime.utcnow() - timedelta(minutes=minutes)
                ).strftime("%Y-%m-%d %H:%M:%S")

    sql = """
        SELECT id, target, method, result, latency_ms, packet_loss_percent
        FROM network_logs
        WHERE timestamp > ? AND hostname = ? AND status != 'success'
        ORDER BY timestamp DESC
    """

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cur = conn.cursor()
            cur.execute(sql, (threshold, host))
            return cur.fetchall()
    except Exception as e:
        print(f"[ERROR] Failed to fetch network events: {e}")
        return []

# def add_handled_column():
#     try:
#         conn = sqlite3.connect(DB_PATH)
#         cur = conn.cursor()
#         cur.execute("ALTER TABLE network_logs ADD COLUMN handled INTEGER DEFAULT 0;")
#         conn.close()
#         print("[SUCCESS] 'handled' column added to network_logs")
#         return True
#     except sqlite3.OperationalError as e:
#         if "duplicate column name" in str(e).lower():
#             print("[INFO] Column 'handled' already exists.")
#         else:
#             print(f"[ERROR] {e}")

# if __name__ == '__main__':
#     add_handled_column()  # Ensure schema is up-to-date
#     # continue with your main loop...


def recent_system_metrics(hostname, minutes):
    """
    Returns the newest system metrics rows for this host wint N minutes
    Columns we care about is timestamp, disk_usage
    :param hostname:
    :param minutes:
    :return: rows
    """

    threshold = (datetime.utcnow() - timedelta(minutes=minutes)
                 ).strftime("%Y-%m-%d %H:%M:%S")

    sql = """SELECT timestamp, disk_usage
                FROM system_metrics
                WHERE timestamp > ? AND hostname = ?
                ORDER BY timestamp DESC"""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(sql, (threshold, hostname))
        return cur.fetchall()
# print(recent_system_metrics(socket.gethostname(),minutes=50))

def recovery_fail_count(host, service_name, minutes) -> bool:
    threshold = (datetime.utcnow() - timedelta(minutes=minutes)
          ).strftime("%Y-%m-%d %H:%M:%S")
    sql = """SELECT COUNT(*) FROM recovery_logs
                WHERE hostname=? AND service_name=?
                AND result='fail' AND timestamp > ?"""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(sql, (host, service_name, threshold))
        return cur.fetchone()[0]

def recent_inode_usage(host, minutes=5):
    """

    :param host: current host
    :param minutes: current timestamp within N minutes
    :return: (timestamp, inode_usage) rows in N minutes
    """
    t = (datetime.utcnow() - timedelta(minutes=minutes)
         ).strftime("%Y-%m-%d %H:%M:%S")
    sql = """SELECT timestamp, inode_usage
                FROM system_metrics
                WHERE timestamp > ? AND hostname = ?
                ORDER BY timestamp DESC"""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(sql, (t, host))
        return cur.fetchall()

def recent_alert_exist(host, source, minutes):
    """

    :param host:
    :param source:
    :param minutes:
    :return: Return True if an alert for source was logged with N minutes
    """
    threshold = (datetime.utcnow() - timedelta(minutes=minutes)
                 ).strftime("%Y-%m-%d %H:%M:%S")
    sql = "SELECT 1 FROM alerts WHERE hostname=? AND source=? AND timestamp>? LIMIT 1"
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(sql, (host, source, threshold))
        return cur.fetchone() is not None

def recent_cpu_samples(host, samples=3, minutes=5):
    """
    Return the last `samples` rows (timestamp, cpu_usage) within `minutes`.
    Ordered newest first.
    """
    from datetime import datetime, timedelta
    threshold = (datetime.utcnow() - timedelta(minutes=minutes)
                ).strftime("%Y-%m-%d %H:%M:%S")
    sql = """SELECT timestamp, cpu_usage
             FROM system_metrics
             WHERE timestamp > ? AND hostname = ?
             ORDER BY timestamp DESC
             LIMIT ?"""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(sql, (threshold, host, samples))
        return cur.fetchall()

def recent_memory_samples(host, samples=3, minutes=3):
    """
    :param host:
    :param samples:
    :param minutes:
    :return:
        Return last `samples` rows (timestamp, memory_usage, swap_usage)
        within `minutes`. Newest first.
    """
    t = (datetime.utcnow() - timedelta(minutes=minutes)
         ).strftime("%Y-%m-%d %H:%M:%S")
    sql = """SELECT timestamp, memory_usage, swap_usage
                FROM system_metrics
                WHERE timestamp > ? AND hostname = ?
                ORDER BY timestamp DESC
                LIMIT ?"""

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(sql, (t, host, samples))
        return cur.fetchall()

def recent_load_samples(host, samples=3, minutes=5):
    """
    :param host:
    :param samples:
    :param minutes:
    :return: Returns last `samples` rows (timestamp, load_average) within `minutes`.
    Newest first.
    """
    t = (datetime.utcnow() - timedelta(minutes=minutes)
         ).strftime("%Y-%m-%d %H:%M:%S")
    sql = """SELECT timestamp, load_average
                 FROM system_metrics
                 WHERE timestamp > ? AND hostname = ?
                 ORDER BY timestamp DESC
                 LIMIT ?"""

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(sql, (t, host, samples))
        return cur.fetchall()

def recent_process_samples(host, samples=3, minutes=5):
    """

    :param host:
    :param samples:
    :param minutes:
    :return: Return last `samples` rows (timestamp, process_count) within `minutes`.
    Newest first; gives context alongside live scan.
    """

    t = (datetime.utcnow() - timedelta(minutes=minutes)
         ).strftime("%Y-%m-%d %H:%M:%S")
    sql = """SELECT timestamp, process_count
                FROM system_metrics
                WHERE timestamp > ? AND hostname = ?
                ORDER BY timestamp DESC
                LIMIT ?"""

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(sql, (t, host, samples))
        return cur.fetchall()









