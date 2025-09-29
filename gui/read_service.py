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



#--------------NOT IN USE---------------------------
def cpu_breakdown(minutes_now: int = 10, minutes_avg: int = 60, limit: int = 5):
    """
    Returns top hosts by current CPU:
      [{hostname, cpu_now, cpu_1h, last_ts}, ...]
    cpu_now  = latest sample per host within minutes_now (fallback: latest per host)
    cpu_1h   = average over minutes_avg per host
    """
    since_now = (datetime.utcnow() - timedelta(minutes=minutes_now)).strftime("%Y-%m-%d %H:%M:%S")
    since_avg = (datetime.utcnow() - timedelta(minutes=minutes_avg)).strftime("%Y-%m-%d %H:%M:%S")

    with connect_ro() as conn:
        cur = conn.cursor()

        # latest per host within minutes_now
        cur.execute("""
            SELECT s.hostname, s.cpu_usage AS cpu_now, s.timestamp AS last_ts
            FROM system_metrics s
            JOIN (
              SELECT hostname, MAX(id) AS max_id
              FROM system_metrics
              WHERE timestamp >= ?
              GROUP BY hostname
            ) t ON s.hostname = t.hostname AND s.id = t.max_id
        """, (since_now,))
        now_rows = {r["hostname"]: {"cpu_now": float(r["cpu_now"]), "last_ts": r["last_ts"]}
                    for r in cur.fetchall()}

        # fallback: if nobody reported in minutes_now, use latest per host
        if not now_rows:
            cur.execute("""
                SELECT s.hostname, s.cpu_usage AS cpu_now, s.timestamp AS last_ts
                FROM system_metrics s
                JOIN (
                  SELECT hostname, MAX(id) AS max_id
                  FROM system_metrics
                  GROUP BY hostname
                ) t ON s.hostname = t.hostname AND s.id = t.max_id
            """)
            now_rows = {r["hostname"]: {"cpu_now": float(r["cpu_now"]), "last_ts": r["last_ts"]}
                        for r in cur.fetchall()}

        # per-host 1h average
        cur.execute("""
            SELECT hostname, AVG(cpu_usage) AS cpu_1h
            FROM system_metrics
            WHERE timestamp >= ?
            GROUP BY hostname
        """, (since_avg,))
        avg_rows = {r["hostname"]: float(r["cpu_1h"] or 0.0) for r in cur.fetchall()}

    result = []
    for host, d in now_rows.items():
        result.append({
            "hostname": host,
            "cpu_now": round(d["cpu_now"], 2),
            "cpu_1h": round(avg_rows.get(host, 0.0), 2),
            "last_ts": d["last_ts"]
        })
    result.sort(key=lambda x: x["cpu_now"], reverse=True)
    return result[:limit] if limit else result





def _table_exists(conn, name: str) -> bool:
    c = conn.cursor()
    c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return c.fetchone() is not None

def _latest_per_host(conn, since_iso: str, use_guard: bool = True):
    """
    Returns {hostname: {'id': id, 'timestamp': ts}} for latest rows per host,
    optionally restricted to timestamp >= since_iso (guard window).
    """
    cur = conn.cursor()
    if use_guard:
        cur.execute("""
            SELECT hostname, MAX(id) AS max_id
            FROM system_metrics
            WHERE timestamp >= ?
            GROUP BY hostname
        """, (since_iso,))
    else:
        cur.execute("""
            SELECT hostname, MAX(id) AS max_id
            FROM system_metrics
            GROUP BY hostname
        """)
    rows = cur.fetchall()
    if not rows:
        return {}
    ids = tuple(r["max_id"] for r in rows)
    placeholders = ",".join("?" for _ in ids)
    cur.execute(f"""
        SELECT id, hostname, timestamp, cpu_usage, memory_usage, load_average
        FROM system_metrics
        WHERE id IN ({placeholders})
    """, ids)
    out = {}
    for r in cur.fetchall():
        out[r["hostname"]] = {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "cpu_usage": float(r["cpu_usage"] or 0.0),
            "memory_usage": float(r["memory_usage"] or 0.0),
            "load_average": float(r["load_average"] or 0.0),
        }
    return out
























# ───────── Summary & lists ─────────

def get_summary():
    """
    Overview header data:
      - hosts_active_10m: count and sample list of hostnames (last 10m)
      - total_hosts: distinct hosts seen in last 24h
      - alerts_24h, recovery_24h
      - cpu_now (fleet avg), cpu_1h_avg, cpu_top {host, value}
      - mem_now (fleet avg), mem_1h_avg, mem_top {host, value}
      - load_now (fleet avg), load_1h_avg, load_top {host, value}
      - latest_alerts (last 10)
    """
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    since_24h = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    since_60m = (now - timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S")
    since_10m = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

    with connect_ro() as conn:
        cur = conn.cursor()

        # hosts seen in last 24h
        cur.execute("""
            SELECT COUNT(DISTINCT hostname) AS c
            FROM system_metrics WHERE timestamp >= ?
        """, (since_24h,))
        total_hosts = int(cur.fetchone()["c"] or 0)

        # active hosts (10m) + names
        cur.execute("""
            SELECT DISTINCT hostname
            FROM system_metrics WHERE timestamp >= ?
            ORDER BY hostname
        """, (since_10m,))
        active_hosts_list = [r["hostname"] for r in cur.fetchall()]
        hosts_active_10m = len(active_hosts_list)

        # alerts/recoveries 24h
        cur.execute("SELECT COUNT(*) AS c FROM alerts WHERE timestamp >= ?", (since_24h,))
        alerts_24h = int(cur.fetchone()["c"] or 0)

        recovery_24h = 0
        if _table_exists(conn, "recovery_logs"):
            cur.execute("SELECT COUNT(*) AS c FROM recovery_logs WHERE timestamp >= ?", (since_24h,))
            recovery_24h = int(cur.fetchone()["c"] or 0)

        # latest per host within 10m (fallback to latest per host if nobody fresh)
        latest_guarded = _latest_per_host(conn, since_10m, use_guard=True)
        latest_any = latest_guarded or _latest_per_host(conn, since_10m, use_guard=False)

        # fleet "now" avgs (across hosts) and "top host" for each metric
        def fleet_now(metric):
            vals = [v.get(metric, 0.0) for v in latest_any.values()]
            return (sum(vals) / len(vals)) if vals else 0.0

        def top_host(metric):
            if not latest_any:
                return {"host": None, "value": 0.0}
            host, d = max(latest_any.items(), key=lambda kv: kv[1].get(metric, 0.0))
            return {"host": host, "value": float(d.get(metric, 0.0))}

        cpu_now = fleet_now("cpu_usage")
        mem_now = fleet_now("memory_usage")
        load_now = fleet_now("load_average")

        cpu_top = top_host("cpu_usage")
        mem_top = top_host("memory_usage")
        load_top = top_host("load_average")

        # 1h averages (fleet)
        def avg_1h(expr):
            cur.execute(f"SELECT AVG({expr}) AS a FROM system_metrics WHERE timestamp >= ?", (since_60m,))
            return float(cur.fetchone()["a"] or 0.0)

        cpu_1h_avg  = avg_1h("cpu_usage")
        mem_1h_avg  = avg_1h("memory_usage")
        load_1h_avg = avg_1h("load_average")

        # latest alerts
        cur.execute("""
            SELECT id, timestamp, hostname, severity, source, message
            FROM alerts ORDER BY id DESC LIMIT 10
        """)
        latest_alerts = cur.fetchall()

    # compact host list (show up to 4 inline, with "+N more")
    hosts_inline = active_hosts_list[:4]
    hosts_extra = max(0, hosts_active_10m - len(hosts_inline))

    return {
        "total_hosts": total_hosts,
        "hosts_active_10m": hosts_active_10m,
        "hosts_inline": hosts_inline,
        "hosts_extra": hosts_extra,

        "alerts_24h": alerts_24h,
        "recovery_24h": recovery_24h,

        "cpu_now": round(cpu_now, 2),
        "cpu_1h_avg": round(cpu_1h_avg, 2),
        "cpu_top": {"host": cpu_top["host"], "value": round(cpu_top["value"], 2)},

        "mem_now": round(mem_now, 2),
        "mem_1h_avg": round(mem_1h_avg, 2),
        "mem_top": {"host": mem_top["host"], "value": round(mem_top["value"], 2)},

        "load_now": round(load_now, 2),
        "load_1h_avg": round(load_1h_avg, 2),
        "load_top": {"host": load_top["host"], "value": round(load_top["value"], 2)},

        "latest_alerts": latest_alerts,
    }


















# def get_summary():
#     """
#     Returns a compact summary for the overview cards:
#       - total_hosts       : distinct hosts seen in last 24h
#       - alerts_24h        : count of alerts in last 24h
#       - recovery_24h      : count of recovery_logs in last 24h (if table exists)
#       - avg_cpu_1h        : avg cpu_usage over last 60 minutes (all samples)
#       - cpu_now           : avg of the latest cpu_usage per host within last 10 minutes
#       - latest_alerts     : last 10 alerts
#     """
#
#     now = datetime.utcnow()
#     since_24h = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
#     since_60m = (now - timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S")
#     since_10m = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
#
#     def _table_exists(conn, name):
#         c = conn.cursor()
#         c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
#         return c.fetchone() is not None
#
#     with connect_ro() as conn:
#         cur = conn.cursor()
#
#         # total hosts seen recently (24h)
#         cur.execute("""
#             SELECT COUNT(DISTINCT hostname) AS c
#             FROM system_metrics
#             WHERE timestamp >= ?
#         """, (since_24h,))
#         total_hosts = int(cur.fetchone()["c"] or 0)
#
#         # alerts in 24h
#         cur.execute("""
#             SELECT COUNT(*) AS c
#             FROM alerts
#             WHERE timestamp >= ?
#         """, (since_24h,))
#         alerts_24h = int(cur.fetchone()["c"] or 0)
#
#         # recoveries in 24h (if table exists)
#         recovery_24h = 0
#         if _table_exists(conn, "recovery_logs"):
#             cur.execute("""
#                 SELECT COUNT(*) AS c
#                 FROM recovery_logs
#                 WHERE timestamp >= ?
#             """, (since_24h,))
#             recovery_24h = int(cur.fetchone()["c"] or 0)
#
#         # avg CPU over last 60m (all samples)
#         cur.execute("""
#             SELECT AVG(cpu_usage) AS a
#             FROM system_metrics
#             WHERE timestamp >= ?
#         """, (since_60m,))
#         avg_cpu_1h = float(cur.fetchone()["a"] or 0.0)
#
#         # CPU now = average of latest row per host within last 10m
#         # (fallback: if no host has a row in 10m, use latest per host without time filter)
#         cur.execute(f"""
#             SELECT AVG(s.cpu_usage) AS a
#             FROM system_metrics s
#             JOIN (
#                 SELECT hostname, MAX(id) AS max_id
#                 FROM system_metrics
#                 WHERE timestamp >= ?
#                 GROUP BY hostname
#             ) t ON s.hostname = t.hostname AND s.id = t.max_id
#         """, (since_10m,))
#         cpu_now = cur.fetchone()["a"]
#
#         if cpu_now is None:
#             # fallback without 10m guard (handles very quiet hosts)
#             cur.execute("""
#                 SELECT AVG(s.cpu_usage) AS a
#                 FROM system_metrics s
#                 JOIN (
#                     SELECT hostname, MAX(id) AS max_id
#                     FROM system_metrics
#                     GROUP BY hostname
#                 ) t ON s.hostname = t.hostname AND s.id = t.max_id
#             """)
#             cpu_now = cur.fetchone()["a"]
#
#         cpu_now = float(cpu_now or 0.0)
#
#         # latest alerts (top 10)
#         cur.execute("""
#             SELECT id, timestamp, hostname, severity, source, message
#             FROM alerts
#             ORDER BY id DESC
#             LIMIT 10
#         """)
#         latest_alerts = cur.fetchall()
#
#     summary = {
#         "total_hosts": total_hosts,
#         "alerts_24h": alerts_24h,
#         "recovery_24h": recovery_24h,
#         "avg_cpu_1h": round(avg_cpu_1h, 2),
#         "cpu_now": round(cpu_now, 2),
#         "latest_alerts": latest_alerts,
#         "cpu_top": cpu_breakdown(limit=5)}
#
#     return summary










# def get_summary():
#     """Return cards + latest alerts for overview."""
#     with connect_ro() as conn:
#         cur = conn.cursor()
#         # Hosts seen (union of both tables for tolerance)
#         hosts = set()
#         for row in cur.execute("SELECT DISTINCT hostname FROM system_metrics"):
#             if row["hostname"]: hosts.add(row["hostname"])
#         for row in cur.execute("SELECT DISTINCT hostname AS host FROM service_status"):
#             if row["host"]: hosts.add(row["host"])
#         total_hosts = len(hosts)
#
#         # Alerts last 24h
#         since = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
#         cur.execute("SELECT COUNT(*) AS c FROM alerts WHERE timestamp > ?", (since,))
#         alerts_24h = cur.fetchone()["c"]
#         cur.execute("SELECT COUNT(*) AS c FROM recovery_logs WHERE timestamp > ?", (since,))
#         rec_24h = cur.fetchone()["c"]
#
#         # Latest alerts
#         cur.execute("""
#             SELECT id, timestamp, hostname, severity, source, message
#             FROM alerts ORDER BY id DESC LIMIT 10
#         """)
#         latest_alerts = cur.fetchall()
#
#         # Quick CPU avg over last hour (for fun)
#         hour = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
#         cur.execute("""
#             SELECT AVG(cpu_usage) AS avg_cpu
#             FROM system_metrics WHERE timestamp > ?
#         """, (hour,))
#         avg_cpu = round(cur.fetchone()["avg_cpu"] or 0.0, 1)
#
#     return {
#         "total_hosts": total_hosts,
#         "alerts_24h": alerts_24h,
#         "recovery_24h": rec_24h,
#         "avg_cpu": avg_cpu,
#         "latest_alerts": latest_alerts,
#     }

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


#-----------Alerts (Filters + Pagination)-------
def get_alerts(seveiry=None, host=None, since_minutes=None, limit=100, offset=0):
    """

    :param seveiry:
    :param host:
    :param since_minutes:
    :param limit:
    :param offset:
    :return:  Returns a list of alerts ordered by newest first with optional filters
    """

    where, params = [], []

    if seveiry:
        where.append("LOWER(severity) = ?")
        params.append(seveiry.strip().lower())

    if host:
        where.append("LOWER(hostname) LIKE ?")
        params.append(f"%{host.strip().lower()}%")

    if since_minutes:
        ts = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
        where.append("timestamp > ?")
        params.append(ts)

    sql = "SELECT id, timestamp, hostname, severity, source, message FROM alerts"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([int(limit), int(offset)])

    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        return cur.fetchall()


def count_alerts(severity=None, host=None, since_minutes=None):
    """
    Counts total alerts for the given filter (for pagination).
    """
    from datetime import datetime, timedelta
    where, params = [], []

    if severity:
        where.append("LOWER(severity) = ?")
        params.append(severity.strip().lower())

    if host:
        where.append("LOWER(hostname) LIKE ?")
        params.append(f"%{host.strip().lower()}%")

    if since_minutes:
        ts = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
        where.append("timestamp > ?")
        params.append(ts)

    sql = "SELECT COUNT(*) AS c FROM alerts"
    if where:
        sql += " WHERE " + " AND ".join(where)

    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        row = cur.fetchone()
        return int(row["c"] if row else 0)


def last_alert_id():
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute("SELECT IFNULL(MAX(id),0) AS max_id FROM alerts")
        return int(cur.fetchone()["max_id"])

def alerts_after(after_id: int, max_rows: int = 50):
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, timestamp, hostname, severity, source, message
            FROM alerts WHERE id > ? ORDER BY id ASC LIMIT ?
        """, (int(after_id), int(max_rows)))
        return cur.fetchall()


# -------- Network page helpers --------

def network_targets(since_minutes: int = 1440):
    """
    Distinct targets seen recently with their last status/latency/packet_loss.
    """
    from datetime import datetime, timedelta
    since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
    with connect_ro() as conn:
        cur = conn.cursor()
        # latest row per target (in the window)
        cur.execute("""
            SELECT nl.*
            FROM network_logs nl
            JOIN (
              SELECT target, MAX(id) AS max_id
              FROM network_logs
              WHERE timestamp >= ?
              GROUP BY target
            ) t ON nl.target = t.target AND nl.id = t.max_id
            ORDER BY nl.target
        """, (since,))
        return cur.fetchall()


def network_events(host=None, target=None, since_minutes=None, limit=200, offset=0, method=None):
    """
    Raw network events (for table). Filters are optional.
    """
    where, params = [], []
    if host:
        where.append("LOWER(hostname) LIKE ?")
        params.append(f"%{host.strip().lower()}%")
    if target:
        where.append("LOWER(target) = ?")
        params.append(target.strip().lower())
    if method:
        where.append("LOWER(method) = ?")
        params.append(method.strip().lower())
    if since_minutes:
        ts = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
        where.append("timestamp >= ?")
        params.append(ts)

    sql = """SELECT id, timestamp, hostname, target, method, status,
                    latency_ms, packet_loss_percent, result
             FROM network_logs"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([int(limit), int(offset)])

    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        return cur.fetchall()

# Distinct (host, target) with their latest status in the window
def network_pairs(since_minutes: int = 1440):
    from datetime import datetime, timedelta
    since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT nl.*
            FROM network_logs nl
            JOIN (
              SELECT hostname, target, MAX(id) AS max_id
              FROM network_logs
              WHERE timestamp >= ?
              GROUP BY hostname, target
            ) t ON nl.hostname = t.hostname
               AND nl.target   = t.target
               AND nl.id       = t.max_id
            ORDER BY nl.target, nl.hostname
        """, (since,))
        return cur.fetchall()


# time series for one target; optionally restrict to host and method (default ping)
def network_latency_series(target: str, since_minutes: int = 60, host: str = None, method: str = "ping"):
    from datetime import datetime, timedelta
    since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")

    sql = """
        SELECT timestamp, latency_ms
        FROM network_logs
        WHERE LOWER(target) = ?
          AND timestamp >= ?
          AND method = ?
          AND latency_ms IS NOT NULL
    """
    params = [target.strip().lower(), since, method]

    if host:
        sql += " AND LOWER(hostname) = ?"
        params.append(host.strip().lower())

    sql += " ORDER BY timestamp ASC"

    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        return cur.fetchall()



# latest traceroute / nslookup for a (host, target)
def latest_result_for(target: str, method: str, host: str = None):
    sql = """
        SELECT timestamp, result, status
        FROM network_logs
        WHERE LOWER(target) = ? AND LOWER(method) = ?
    """
    params = [target.strip().lower(), method.strip().lower()]
    if host:
        sql += " AND LOWER(hostname) = ?"
        params.append(host.strip().lower())
    sql += " ORDER BY id DESC LIMIT 1"
    with connect_ro() as conn:
        cur = conn.cursor()
        cur.execute(sql, tuple(params))
        return cur.fetchone()



