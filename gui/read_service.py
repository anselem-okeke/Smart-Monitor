# ─────────────────────────────────────────────────────────────────────────────
# gui/read_service.py  (portable DB READS; SQLite today, Postgres tomorrow)
# ─────────────────────────────────────────────────────────────────────────────
import os, time
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from db.core import connect_ro, fetchall_dicts

_IS_PG = os.getenv("DATABASE_URL", "").startswith(("postgres://", "postgresql://"))
_P = "%s" if _IS_PG else "?"                         # portable placeholder
UPDATED_EXPR = "to_timestamp(ts_epoch)" if _IS_PG else "datetime(ts_epoch,'unixepoch')"

# ---------- helpers -----------------------------------------------------------

def _table_exists(conn, name: str) -> bool:
    """Portable table-exists check without context-manager cursors (SQLite-safe)."""
    try:
        if _IS_PG:
            cur = conn.cursor()
            cur.execute(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name=%s LIMIT 1",
                (name,),
            )
            ok = cur.fetchone() is not None
            cur.close()
            return ok
        else:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
            ok = cur.fetchone() is not None
            cur.close()
            return ok
    except Exception as e:
        print(f"{e}")
        return False

def present_columns(conn, table: str):
    if _IS_PG:
        sql = f"""SELECT column_name FROM information_schema.columns
                  WHERE table_schema='public' AND table_name={_P}"""
        rows = fetchall_dicts(conn, sql, (table,))
        return {r["column_name"] for r in rows}
    else:
        rows = fetchall_dicts(conn, f"PRAGMA table_info({table})")
        return {r["name"] for r in rows}

def _latest_per_host(conn, since_iso: str, use_guard: bool = True):
    """
    {hostname: {id, timestamp, cpu_usage, memory_usage, load_average}} for latest rows per host.
    Works on SQLite + PG (no DISTINCT ON).
    """
    where = f'WHERE "timestamp" >= {_P}' if use_guard else ""
    sub = f"""
      SELECT hostname, MAX(id) AS max_id
      FROM system_metrics
      {where}
      GROUP BY hostname
    """
    params = (since_iso,) if use_guard else ()
    sql = f"""
      SELECT s.id, s.hostname, s."timestamp", s.cpu_usage, s.memory_usage, s.load_average
      FROM system_metrics s
      JOIN ({sub}) m
        ON s.hostname = m.hostname AND s.id = m.max_id
    """
    rows = fetchall_dicts(conn, sql, params)
    out = {}
    for r in rows:
        out[r["hostname"]] = {
            "id": r["id"],
            "timestamp": r["timestamp"],
            "cpu_usage": float(r.get("cpu_usage") or 0.0),
            "memory_usage": float(r.get("memory_usage") or 0.0),
            "load_average": float(r.get("load_average") or 0.0),
        }
    return out

# ───────── Summary & lists ─────────

def get_summary():
    now = datetime.utcnow()
    since_24h = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    since_60m = (now - timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S")
    since_10m = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

    with connect_ro(dicts=True) as conn:
        # hosts seen in last 24h
        rows = fetchall_dicts(conn,
            f'SELECT COUNT(DISTINCT hostname) AS c FROM system_metrics WHERE "timestamp" >= {_P}',
            (since_24h,))
        total_hosts = int(rows[0]["c"] if rows else 0)

        # active hosts (10m) + names
        rows = fetchall_dicts(conn,
            f'SELECT DISTINCT hostname FROM system_metrics WHERE "timestamp" >= {_P} ORDER BY hostname',
            (since_10m,))
        active_hosts_list = [r["hostname"] for r in rows]
        hosts_active_10m = len(active_hosts_list)

        # alerts/recoveries 24h
        rows = fetchall_dicts(conn,
            f'SELECT COUNT(*) AS c FROM alerts WHERE "timestamp" >= {_P}', (since_24h,))
        alerts_24h = int(rows[0]["c"] if rows else 0)

        recovery_24h = 0
        if _table_exists(conn, "recovery_logs"):
            rows = fetchall_dicts(conn,
                f'SELECT COUNT(*) AS c FROM recovery_logs WHERE "timestamp" >= {_P}', (since_24h,))
            recovery_24h = int(rows[0]["c"] if rows else 0)

        latest_guarded = _latest_per_host(conn, since_10m, use_guard=True)
        latest_any = latest_guarded or _latest_per_host(conn, since_10m, use_guard=False)

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

        def avg_1h(expr):
            rows = fetchall_dicts(conn,
                f'SELECT AVG({expr}) AS a FROM system_metrics WHERE "timestamp" >= {_P}',
                (since_60m,))
            return float(rows[0]["a"] or 0.0) if rows else 0.0

        cpu_1h_avg  = avg_1h("cpu_usage")
        mem_1h_avg  = avg_1h("memory_usage")
        load_1h_avg = avg_1h("load_average")

        latest_alerts = fetchall_dicts(conn, """
            SELECT id, "timestamp", hostname, severity, source, message
            FROM alerts ORDER BY id DESC LIMIT 10
        """)

    hosts_inline = active_hosts_list[:4]
    hosts_extra  = max(0, hosts_active_10m - len(hosts_inline))

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

def list_hosts():
    """Basic host list with last-seen timestamp + last metrics snapshot."""
    with connect_ro(dicts=True) as conn:
        # last row per host via join on MAX(id)
        rows = fetchall_dicts(conn, """
            WITH last AS (
              SELECT hostname, MAX(id) AS max_id
              FROM system_metrics
              GROUP BY hostname
            )
            SELECT s.hostname,
                   s."timestamp" AS last_ts,
                   s.cpu_usage, s.memory_usage, s.load_average,
                   s.swap_usage, s.inode_usage, s.disk_usage
            FROM system_metrics s
            JOIN last l ON s.hostname=l.hostname AND s.id=l.max_id
            ORDER BY s.hostname
        """)
        out = []
        for r in rows:
            out.append({
                "hostname": r["hostname"],
                "last_ts": r["last_ts"],
                "last": {
                    "timestamp": r["last_ts"],
                    "cpu_usage": r["cpu_usage"],
                    "memory_usage": r["memory_usage"],
                    "load_average": r["load_average"],
                    "swap_usage": r.get("swap_usage"),
                    "inode_usage": r.get("inode_usage"),
                    "disk_usage": r.get("disk_usage"),
                }
            })
        return out

def host_metrics(hostname: str, minutes: int = 60, limit: int = 5000):
    """Time-series for charts; missing columns come back as NULL."""
    since = (datetime.utcnow() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
    with connect_ro(dicts=True) as conn:
        cols_all = ["timestamp","cpu_usage","memory_usage","load_average","swap_usage","inode_usage","disk_usage"]
        present = present_columns(conn, "system_metrics")
        select_exprs = [c if c in present else f"NULL AS {c}" for c in cols_all]
        sql = f"""
            SELECT {", ".join(select_exprs)}
            FROM system_metrics
            WHERE hostname={_P} AND "timestamp" >= {_P}
            ORDER BY "timestamp" ASC
            LIMIT {int(limit)}
        """
        return fetchall_dicts(conn, sql, (hostname, since))

def host_services(hostname: str):
    """Latest status per service for a host."""
    with connect_ro(dicts=True) as conn:
        sql = f"""
            WITH last AS (
              SELECT service_name, MAX(id) AS max_id
              FROM service_status WHERE hostname={_P}
              GROUP BY service_name
            )
            SELECT s1.service_name, s1.normalized_status, s1."timestamp"
            FROM service_status s1
            JOIN last s2 ON s1.service_name = s2.service_name AND s1.id = s2.max_id
            ORDER BY s1.service_name
        """
        return fetchall_dicts(conn, sql, (hostname,))

#-----------Alerts (Filters + Pagination)-------

def get_alerts(seveiry=None, host=None, since_minutes=None, limit=100, offset=0):
    where, params = [], []

    if seveiry:
        where.append(f"LOWER(severity) = {_P}")
        params.append(seveiry.strip().lower())

    if host:
        where.append(f"LOWER(hostname) LIKE {_P}")
        params.append(f"%{host.strip().lower()}%")

    if since_minutes:
        ts = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
        where.append(f'"timestamp" > {_P}')
        params.append(ts)

    sql = 'SELECT id, "timestamp", hostname, severity, source, message FROM alerts'
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY id DESC LIMIT {int(limit)} OFFSET {int(offset)}"

    with connect_ro(dicts=True) as conn:
        return fetchall_dicts(conn, sql, tuple(params))

def count_alerts(severity=None, host=None, since_minutes=None):
    where, params = [], []

    if severity:
        where.append(f"LOWER(severity) = {_P}")
        params.append(severity.strip().lower())

    if host:
        where.append(f"LOWER(hostname) LIKE {_P}")
        params.append(f"%{host.strip().lower()}%")

    if since_minutes:
        ts = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
        where.append(f'"timestamp" > {_P}')
        params.append(ts)

    sql = "SELECT COUNT(*) AS c FROM alerts"
    if where:
        sql += " WHERE " + " AND ".join(where)

    with connect_ro(dicts=True) as conn:
        rows = fetchall_dicts(conn, sql, tuple(params))
        return int(rows[0]["c"] if rows else 0)

def last_alert_id():
    with connect_ro(dicts=True) as conn:
        rows = fetchall_dicts(conn, "SELECT COALESCE(MAX(id),0) AS max_id FROM alerts")
        return int(rows[0]["max_id"] if rows else 0)

def alerts_after(after_id: int, max_rows: int = 50):
    sql = f"""
        SELECT id, "timestamp", hostname, severity, source, message
        FROM alerts WHERE id > {_P} ORDER BY id ASC LIMIT {int(max_rows)}
    """
    with connect_ro(dicts=True) as conn:
        return fetchall_dicts(conn, sql, (int(after_id),))

# -------- Network page helpers --------

def network_targets(since_minutes: int = 1440):
    """Distinct targets seen recently with their last status/latency/packet_loss."""
    since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        WITH last AS (
          SELECT target, MAX(id) AS max_id
          FROM network_logs
          WHERE "timestamp" >= {_P}
          GROUP BY target
        )
        SELECT nl.*
        FROM network_logs nl
        JOIN last t ON nl.target=t.target AND nl.id=t.max_id
        ORDER BY nl.target
    """
    with connect_ro(dicts=True) as conn:
        return fetchall_dicts(conn, sql, (since,))

def network_events(host=None, target=None, since_minutes=None, limit=200, offset=0, method=None):
    """Raw network events (for table). Filters are optional."""
    where, params = [], []
    if host:
        where.append(f"LOWER(hostname) LIKE {_P}")
        params.append(f"%{host.strip().lower()}%")
    if target:
        where.append(f"LOWER(target) = {_P}")
        params.append(target.strip().lower())
    if method:
        where.append(f"LOWER(method) = {_P}")
        params.append(method.strip().lower())
    if since_minutes:
        ts = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
        where.append(f'"timestamp" >= {_P}')
        params.append(ts)

    sql = """SELECT id, "timestamp", hostname, target, method, status,
                    latency_ms, packet_loss_percent, result
             FROM network_logs"""
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY id DESC LIMIT {int(limit)} OFFSET {int(offset)}"

    with connect_ro(dicts=True) as conn:
        return fetchall_dicts(conn, sql, tuple(params))

def network_pairs(since_minutes: int = 1440):
    """Distinct (host, target) with their latest status in the window."""
    since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        WITH last AS (
          SELECT hostname, target, MAX(id) AS max_id
          FROM network_logs
          WHERE "timestamp" >= {_P}
          GROUP BY hostname, target
        )
        SELECT nl.*
        FROM network_logs nl
        JOIN last t
          ON nl.hostname=t.hostname AND nl.target=t.target AND nl.id=t.max_id
        ORDER BY nl.target, nl.hostname
    """
    with connect_ro(dicts=True) as conn:
        return fetchall_dicts(conn, sql, (since,))

def network_latency_series(target: str, since_minutes: int = 60, host: str = None, method: str = "ping"):
    since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
    sql = f"""
        SELECT "timestamp", latency_ms
        FROM network_logs
        WHERE LOWER(target) = {_P}
          AND "timestamp" >= {_P}
          AND method = {_P}
          AND latency_ms IS NOT NULL
    """
    params = [target.strip().lower(), since, method]
    if host:
        sql += f" AND LOWER(hostname) = {_P}"
        params.append(host.strip().lower())
    sql += ' ORDER BY "timestamp" ASC'
    with connect_ro(dicts=True) as conn:
        return fetchall_dicts(conn, sql, tuple(params))

def latest_result_for(target: str, method: str, host: str = None):
    sql = f"""
        SELECT "timestamp", result, status
        FROM network_logs
        WHERE LOWER(target) = {_P} AND LOWER(method) = {_P}
    """
    params = [target.strip().lower(), method.strip().lower()]
    if host:
        sql += f" AND LOWER(hostname) = {_P}"
        params.append(host.strip().lower())
    sql += " ORDER BY id DESC LIMIT 1"
    with connect_ro(dicts=True) as conn:
        rows = fetchall_dicts(conn, sql, tuple(params))
        return rows[0] if rows else None

# -------- SMART health --------------------------------------------------------

def smart_latest(host: Optional[str] = None):
    """
    Return the latest SMART health per (hostname, device).
    """
    with connect_ro(dicts=True) as conn:
        if not _table_exists(conn, "smart_health"):
            return []
        where, params = [], []
        if host:
            where.append(f"hostname = {_P}")
            params.append(host)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        sql = f"""
          WITH latest AS (
            SELECT hostname, device, MAX("timestamp") AS ts
            FROM smart_health
            {where_sql}
            GROUP BY hostname, device
          )
          SELECT s."timestamp", s.hostname, s.device, s.health, s.model, s.temp_c
          FROM smart_health s
          JOIN latest L
            ON s.hostname=L.hostname AND s.device=L.device AND s."timestamp"=L.ts
          ORDER BY s.hostname, s.device
        """
        return fetchall_dicts(conn, sql, tuple(params))

def hosts_for_smart():
    """Hosts that either have SMART rows or at least system_metrics."""
    with connect_ro(dicts=True) as conn:
        if _table_exists(conn, "smart_health"):
            rows = fetchall_dicts(conn, "SELECT DISTINCT hostname FROM smart_health ORDER BY hostname")
            hs = [r["hostname"] for r in rows]
            if hs:
                return hs
        rows = fetchall_dicts(conn, "SELECT DISTINCT hostname FROM system_metrics ORDER BY hostname")
        return [r["hostname"] for r in rows]

# -------- Services (filters + pagination) ------------------------------------
def _services_query(
    windowed: bool,
    host: Optional[str],
    status: Optional[str],
    since_minutes: int,
    limit: int,
    offset: int,
) -> List[Dict[str, Any]]:
    """
    Latest row per (hostname, service_name), optional time-window by ts_epoch.
    Joins last recovery row + recent failure counter.
    """
    since_epoch = int(time.time()) - int(since_minutes) * 60

    # --- normalize status defensively ---
    norm_status = None
    if status:
        s = str(status).strip().lower()
        if s in ("any", "any status", "all"):
            norm_status = None
        elif s.startswith("active") or s == "running":
            norm_status = "active"
        elif s in ("stopped", "inactive"):
            norm_status = "stopped"  # treat 'inactive' as stopped
        elif s == "failed":
            norm_status = "failed"
        else:
            norm_status = s

    # --- outer WHERE (host/status) ---
    where_outer, params_outer = [], []
    if host:
        where_outer.append(f"l.hostname = {_P}")
        params_outer.append(host)

    if norm_status:
        if norm_status == "stopped":
            # match both 'stopped' and historical 'inactive'
            where_outer.append(f"LOWER(TRIM(l.normalized_status)) IN ({_P}, {_P})")
            params_outer += ["stopped", "inactive"]
        else:
            where_outer.append(f"LOWER(TRIM(l.normalized_status)) = {_P}")
            params_outer.append(norm_status)

    where_sql = ("WHERE " + " AND ".join(where_outer)) if where_outer else ""

    # --- inner time window on ts_epoch (only if windowed) ---
    time_filter = f"WHERE ts_epoch >= {_P}" if windowed else ""
    params_inner = ([since_epoch] if windowed else [])

    # cutoff for "recent_failures" subquery (30 minutes) — appears in SELECT list
    thirty_iso = (datetime.utcnow() - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")

    sql = f"""
    WITH latest AS (
      SELECT s.*
      FROM service_status s
      JOIN (
        SELECT hostname, service_name, MAX(ts_epoch) AS max_ts
        FROM service_status
        {time_filter}
        GROUP BY hostname, service_name
      ) m
        ON s.hostname     = m.hostname
       AND s.service_name = m.service_name
       AND s.ts_epoch     = m.max_ts
    ),
    last_rec AS (
      SELECT rl.hostname, rl.service_name,
             rl."timestamp" AS last_recovery_at,
             rl.result      AS last_recovery_result
      FROM recovery_logs rl
      JOIN (
        SELECT hostname, service_name, MAX("timestamp") AS max_t
        FROM recovery_logs
        GROUP BY hostname, service_name
      ) rmax
        ON rl.hostname     = rmax.hostname
       AND rl.service_name = rmax.service_name
       AND rl."timestamp"  = rmax.max_t
    )
    SELECT
      l.hostname                      AS host,
      l.service_name                  AS service_name,
      l.os_platform                   AS os_platform,
      l.normalized_status             AS status,
      COALESCE(l.sub_state, '')       AS sub_state,
      COALESCE(l.unit_file_state, '') AS unit_file_state,
      CAST(l.recoverable AS INTEGER)  AS recoverable,
      {UPDATED_EXPR}                  AS updated,
      COALESCE(r.last_recovery_result,'') AS last_recovery_result,
      r.last_recovery_at,
      (
        SELECT COUNT(*)
        FROM recovery_logs rf
        WHERE rf.hostname = l.hostname
          AND rf.service_name = l.service_name
          AND rf.result = 'fail'
          AND rf."timestamp" > {_P}
      ) AS recent_failures
    FROM latest l
    LEFT JOIN last_rec r
      ON r.hostname     = l.hostname
     AND r.service_name = l.service_name
    {where_sql}
    ORDER BY l.hostname, l.service_name
    LIMIT {int(limit)} OFFSET {int(offset)};
    """

    # IMPORTANT: placeholder order == left-to-right in the SQL
    params: List[Any] = []
    params.extend(params_inner)   # time_filter param (since_epoch) if windowed
    params.append(thirty_iso)     # subselect cutoff appears BEFORE outer WHERE
    params.extend(params_outer)   # then host/status filters

    with connect_ro(dicts=True) as conn:
        return fetchall_dicts(conn, sql, tuple(params))



def _services_count_query(
    windowed: bool,
    host: Optional[str],
    status: Optional[str],
    since_minutes: int,
) -> int:
    since_epoch = int(time.time()) - int(since_minutes) * 60
    where_outer, params_outer = [], []
    if host:
        where_outer.append(f"l.hostname = {_P}")
        params_outer.append(host)
    if status:
        where_outer.append(f"l.normalized_status = {_P}")
        params_outer.append(status)
    where_sql = ("WHERE " + " AND ".join(where_outer)) if where_outer else ""

    time_filter = f"WHERE ts_epoch >= {_P}" if windowed else ""
    params_inner = ([since_epoch] if windowed else [])

    sql = f"""
    WITH latest AS (
      SELECT s.*
      FROM service_status s
      JOIN (
        SELECT hostname, service_name, MAX(ts_epoch) AS max_ts
        FROM service_status
        {time_filter}
        GROUP BY hostname, service_name
      ) m
        ON s.hostname     = m.hostname
       AND s.service_name = m.service_name
       AND s.ts_epoch     = m.max_ts
    )
    SELECT COUNT(*) AS n FROM latest l
    {where_sql};
    """
    params = []
    params.extend(params_inner)
    params.extend(params_outer)
    with connect_ro(dicts=True) as conn:
        rows = fetchall_dicts(conn, sql, tuple(params))
        return int(rows[0]["n"] if rows else 0)

# --- public ------------------------------------------------------------------

def latest_services(
    host: Optional[str] = None,
    status: Optional[str] = None,
    since_minutes: int = 1440,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    rows = _services_query(True, host, status, since_minutes, limit, offset)
    if rows:
        return rows
    return _services_query(False, host, status, since_minutes, limit, offset)

def services_count(
    host: Optional[str] = None,
    status: Optional[str] = None,
    since_minutes: int = 1440,
) -> int:
    n = _services_count_query(True, host, status, since_minutes)
    if n > 0:
        return n
    return _services_count_query(False, host, status, since_minutes)








































# # ─────────────────────────────────────────────────────────────────────────────
# # gui/read_service.py  (all DB READS live here; writes stay in db_logger)
# # ─────────────────────────────────────────────────────────────────────────────
# import os
# import sqlite3
# from datetime import datetime, timedelta
# from pathlib import Path
# from typing import Optional
#
# from db.core import resolve_db_path, DB_PATH
#
# ROOT = Path(__file__).resolve().parents[1]  # repo root (…/Smart-Factory-IT-Monitor)
#
# # def _load_db_path():
# #     cfg_path = ROOT / "config" / "db_config.json"
# #     if cfg_path.exists():
# #         cfg = json.loads(cfg_path.read_text())
# #         p = cfg.get("path") or cfg.get("sqlite_path") or "db/smart_factory_monitor.db"
# #     else:
# #         p = "db/smart_factory_monitor.db"
# #     # Absolute path + SQLite readonly URI
# #     abs_p = (ROOT / p).resolve()
# #     return f"file:{abs_p.as_posix()}?mode=ro&cache=shared"
# #
# # DB_URI_RO = _load_db_path()
#
#
#
# def _to_sqlite_ro_uri(path):
#     p = Path(path).resolve().as_posix()
#     if os.name == "nt":
#         return f"file:/{p}?mode=ro&cache=shared"
#     else:
#         return f"file:{p}?mode=ro&cache=shared"
#
#
# def _dict_factory(cursor, row):
#     return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}
#
#
# def connect_ro():
#     db_path = resolve_db_path()
#     uri = _to_sqlite_ro_uri(db_path)
#     conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
#     conn.row_factory = _dict_factory
#     return conn
#
#
#
# #--------------NOT IN USE---------------------------
# def cpu_breakdown(minutes_now: int = 10, minutes_avg: int = 60, limit: int = 5):
#     """
#     Returns top hosts by current CPU:
#       [{hostname, cpu_now, cpu_1h, last_ts}, ...]
#     cpu_now  = latest sample per host within minutes_now (fallback: latest per host)
#     cpu_1h   = average over minutes_avg per host
#     """
#     since_now = (datetime.utcnow() - timedelta(minutes=minutes_now)).strftime("%Y-%m-%d %H:%M:%S")
#     since_avg = (datetime.utcnow() - timedelta(minutes=minutes_avg)).strftime("%Y-%m-%d %H:%M:%S")
#
#     with connect_ro() as conn:
#         cur = conn.cursor()
#
#         # latest per host within minutes_now
#         cur.execute("""
#             SELECT s.hostname, s.cpu_usage AS cpu_now, s.timestamp AS last_ts
#             FROM system_metrics s
#             JOIN (
#               SELECT hostname, MAX(id) AS max_id
#               FROM system_metrics
#               WHERE timestamp >= ?
#               GROUP BY hostname
#             ) t ON s.hostname = t.hostname AND s.id = t.max_id
#         """, (since_now,))
#         now_rows = {r["hostname"]: {"cpu_now": float(r["cpu_now"]), "last_ts": r["last_ts"]}
#                     for r in cur.fetchall()}
#
#         # fallback: if nobody reported in minutes_now, use latest per host
#         if not now_rows:
#             cur.execute("""
#                 SELECT s.hostname, s.cpu_usage AS cpu_now, s.timestamp AS last_ts
#                 FROM system_metrics s
#                 JOIN (
#                   SELECT hostname, MAX(id) AS max_id
#                   FROM system_metrics
#                   GROUP BY hostname
#                 ) t ON s.hostname = t.hostname AND s.id = t.max_id
#             """)
#             now_rows = {r["hostname"]: {"cpu_now": float(r["cpu_now"]), "last_ts": r["last_ts"]}
#                         for r in cur.fetchall()}
#
#         # per-host 1h average
#         cur.execute("""
#             SELECT hostname, AVG(cpu_usage) AS cpu_1h
#             FROM system_metrics
#             WHERE timestamp >= ?
#             GROUP BY hostname
#         """, (since_avg,))
#         avg_rows = {r["hostname"]: float(r["cpu_1h"] or 0.0) for r in cur.fetchall()}
#
#     result = []
#     for host, d in now_rows.items():
#         result.append({
#             "hostname": host,
#             "cpu_now": round(d["cpu_now"], 2),
#             "cpu_1h": round(avg_rows.get(host, 0.0), 2),
#             "last_ts": d["last_ts"]
#         })
#     result.sort(key=lambda x: x["cpu_now"], reverse=True)
#     return result[:limit] if limit else result
#
#
#
#
#
# def _table_exists(conn, name: str) -> bool:
#     c = conn.cursor()
#     c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
#     return c.fetchone() is not None
#
# def _latest_per_host(conn, since_iso: str, use_guard: bool = True):
#     """
#     Returns {hostname: {'id': id, 'timestamp': ts}} for latest rows per host,
#     optionally restricted to timestamp >= since_iso (guard window).
#     """
#     cur = conn.cursor()
#     if use_guard:
#         cur.execute("""
#             SELECT hostname, MAX(id) AS max_id
#             FROM system_metrics
#             WHERE timestamp >= ?
#             GROUP BY hostname
#         """, (since_iso,))
#     else:
#         cur.execute("""
#             SELECT hostname, MAX(id) AS max_id
#             FROM system_metrics
#             GROUP BY hostname
#         """)
#     rows = cur.fetchall()
#     if not rows:
#         return {}
#     ids = tuple(r["max_id"] for r in rows)
#     placeholders = ",".join("?" for _ in ids)
#     cur.execute(f"""
#         SELECT id, hostname, timestamp, cpu_usage, memory_usage, load_average
#         FROM system_metrics
#         WHERE id IN ({placeholders})
#     """, ids)
#     out = {}
#     for r in cur.fetchall():
#         out[r["hostname"]] = {
#             "id": r["id"],
#             "timestamp": r["timestamp"],
#             "cpu_usage": float(r["cpu_usage"] or 0.0),
#             "memory_usage": float(r["memory_usage"] or 0.0),
#             "load_average": float(r["load_average"] or 0.0),
#         }
#     return out
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
# # ───────── Summary & lists ─────────
#
# def get_summary():
#     """
#     Overview header data:
#       - hosts_active_10m: count and sample list of hostnames (last 10m)
#       - total_hosts: distinct hosts seen in last 24h
#       - alerts_24h, recovery_24h
#       - cpu_now (fleet avg), cpu_1h_avg, cpu_top {host, value}
#       - mem_now (fleet avg), mem_1h_avg, mem_top {host, value}
#       - load_now (fleet avg), load_1h_avg, load_top {host, value}
#       - latest_alerts (last 10)
#     """
#     from datetime import datetime, timedelta
#     now = datetime.utcnow()
#     since_24h = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
#     since_60m = (now - timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S")
#     since_10m = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
#
#     with connect_ro() as conn:
#         cur = conn.cursor()
#
#         # hosts seen in last 24h
#         cur.execute("""
#             SELECT COUNT(DISTINCT hostname) AS c
#             FROM system_metrics WHERE timestamp >= ?
#         """, (since_24h,))
#         total_hosts = int(cur.fetchone()["c"] or 0)
#
#         # active hosts (10m) + names
#         cur.execute("""
#             SELECT DISTINCT hostname
#             FROM system_metrics WHERE timestamp >= ?
#             ORDER BY hostname
#         """, (since_10m,))
#         active_hosts_list = [r["hostname"] for r in cur.fetchall()]
#         hosts_active_10m = len(active_hosts_list)
#
#         # alerts/recoveries 24h
#         cur.execute("SELECT COUNT(*) AS c FROM alerts WHERE timestamp >= ?", (since_24h,))
#         alerts_24h = int(cur.fetchone()["c"] or 0)
#
#         recovery_24h = 0
#         if _table_exists(conn, "recovery_logs"):
#             cur.execute("SELECT COUNT(*) AS c FROM recovery_logs WHERE timestamp >= ?", (since_24h,))
#             recovery_24h = int(cur.fetchone()["c"] or 0)
#
#         # latest per host within 10m (fallback to latest per host if nobody fresh)
#         latest_guarded = _latest_per_host(conn, since_10m, use_guard=True)
#         latest_any = latest_guarded or _latest_per_host(conn, since_10m, use_guard=False)
#
#         # fleet "now" avgs (across hosts) and "top host" for each metric
#         def fleet_now(metric):
#             vals = [v.get(metric, 0.0) for v in latest_any.values()]
#             return (sum(vals) / len(vals)) if vals else 0.0
#
#         def top_host(metric):
#             if not latest_any:
#                 return {"host": None, "value": 0.0}
#             host, d = max(latest_any.items(), key=lambda kv: kv[1].get(metric, 0.0))
#             return {"host": host, "value": float(d.get(metric, 0.0))}
#
#         cpu_now = fleet_now("cpu_usage")
#         mem_now = fleet_now("memory_usage")
#         load_now = fleet_now("load_average")
#
#         cpu_top = top_host("cpu_usage")
#         mem_top = top_host("memory_usage")
#         load_top = top_host("load_average")
#
#         # 1h averages (fleet)
#         def avg_1h(expr):
#             cur.execute(f"SELECT AVG({expr}) AS a FROM system_metrics WHERE timestamp >= ?", (since_60m,))
#             return float(cur.fetchone()["a"] or 0.0)
#
#         cpu_1h_avg  = avg_1h("cpu_usage")
#         mem_1h_avg  = avg_1h("memory_usage")
#         load_1h_avg = avg_1h("load_average")
#
#         # latest alerts
#         cur.execute("""
#             SELECT id, timestamp, hostname, severity, source, message
#             FROM alerts ORDER BY id DESC LIMIT 10
#         """)
#         latest_alerts = cur.fetchall()
#
#     # compact host list (show up to 4 inline, with "+N more")
#     hosts_inline = active_hosts_list[:4]
#     hosts_extra = max(0, hosts_active_10m - len(hosts_inline))
#
#     return {
#         "total_hosts": total_hosts,
#         "hosts_active_10m": hosts_active_10m,
#         "hosts_inline": hosts_inline,
#         "hosts_extra": hosts_extra,
#
#         "alerts_24h": alerts_24h,
#         "recovery_24h": recovery_24h,
#
#         "cpu_now": round(cpu_now, 2),
#         "cpu_1h_avg": round(cpu_1h_avg, 2),
#         "cpu_top": {"host": cpu_top["host"], "value": round(cpu_top["value"], 2)},
#
#         "mem_now": round(mem_now, 2),
#         "mem_1h_avg": round(mem_1h_avg, 2),
#         "mem_top": {"host": mem_top["host"], "value": round(mem_top["value"], 2)},
#
#         "load_now": round(load_now, 2),
#         "load_1h_avg": round(load_1h_avg, 2),
#         "load_top": {"host": load_top["host"], "value": round(load_top["value"], 2)},
#
#         "latest_alerts": latest_alerts,
#     }
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
#
# # def get_summary():
# #     """
# #     Returns a compact summary for the overview cards:
# #       - total_hosts       : distinct hosts seen in last 24h
# #       - alerts_24h        : count of alerts in last 24h
# #       - recovery_24h      : count of recovery_logs in last 24h (if table exists)
# #       - avg_cpu_1h        : avg cpu_usage over last 60 minutes (all samples)
# #       - cpu_now           : avg of the latest cpu_usage per host within last 10 minutes
# #       - latest_alerts     : last 10 alerts
# #     """
# #
# #     now = datetime.utcnow()
# #     since_24h = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
# #     since_60m = (now - timedelta(minutes=60)).strftime("%Y-%m-%d %H:%M:%S")
# #     since_10m = (now - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")
# #
# #     def _table_exists(conn, name):
# #         c = conn.cursor()
# #         c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
# #         return c.fetchone() is not None
# #
# #     with connect_ro() as conn:
# #         cur = conn.cursor()
# #
# #         # total hosts seen recently (24h)
# #         cur.execute("""
# #             SELECT COUNT(DISTINCT hostname) AS c
# #             FROM system_metrics
# #             WHERE timestamp >= ?
# #         """, (since_24h,))
# #         total_hosts = int(cur.fetchone()["c"] or 0)
# #
# #         # alerts in 24h
# #         cur.execute("""
# #             SELECT COUNT(*) AS c
# #             FROM alerts
# #             WHERE timestamp >= ?
# #         """, (since_24h,))
# #         alerts_24h = int(cur.fetchone()["c"] or 0)
# #
# #         # recoveries in 24h (if table exists)
# #         recovery_24h = 0
# #         if _table_exists(conn, "recovery_logs"):
# #             cur.execute("""
# #                 SELECT COUNT(*) AS c
# #                 FROM recovery_logs
# #                 WHERE timestamp >= ?
# #             """, (since_24h,))
# #             recovery_24h = int(cur.fetchone()["c"] or 0)
# #
# #         # avg CPU over last 60m (all samples)
# #         cur.execute("""
# #             SELECT AVG(cpu_usage) AS a
# #             FROM system_metrics
# #             WHERE timestamp >= ?
# #         """, (since_60m,))
# #         avg_cpu_1h = float(cur.fetchone()["a"] or 0.0)
# #
# #         # CPU now = average of latest row per host within last 10m
# #         # (fallback: if no host has a row in 10m, use latest per host without time filter)
# #         cur.execute(f"""
# #             SELECT AVG(s.cpu_usage) AS a
# #             FROM system_metrics s
# #             JOIN (
# #                 SELECT hostname, MAX(id) AS max_id
# #                 FROM system_metrics
# #                 WHERE timestamp >= ?
# #                 GROUP BY hostname
# #             ) t ON s.hostname = t.hostname AND s.id = t.max_id
# #         """, (since_10m,))
# #         cpu_now = cur.fetchone()["a"]
# #
# #         if cpu_now is None:
# #             # fallback without 10m guard (handles very quiet hosts)
# #             cur.execute("""
# #                 SELECT AVG(s.cpu_usage) AS a
# #                 FROM system_metrics s
# #                 JOIN (
# #                     SELECT hostname, MAX(id) AS max_id
# #                     FROM system_metrics
# #                     GROUP BY hostname
# #                 ) t ON s.hostname = t.hostname AND s.id = t.max_id
# #             """)
# #             cpu_now = cur.fetchone()["a"]
# #
# #         cpu_now = float(cpu_now or 0.0)
# #
# #         # latest alerts (top 10)
# #         cur.execute("""
# #             SELECT id, timestamp, hostname, severity, source, message
# #             FROM alerts
# #             ORDER BY id DESC
# #             LIMIT 10
# #         """)
# #         latest_alerts = cur.fetchall()
# #
# #     summary = {
# #         "total_hosts": total_hosts,
# #         "alerts_24h": alerts_24h,
# #         "recovery_24h": recovery_24h,
# #         "avg_cpu_1h": round(avg_cpu_1h, 2),
# #         "cpu_now": round(cpu_now, 2),
# #         "latest_alerts": latest_alerts,
# #         "cpu_top": cpu_breakdown(limit=5)}
# #
# #     return summary
#
#
#
#
#
#
#
#
#
#
# # def get_summary():
# #     """Return cards + latest alerts for overview."""
# #     with connect_ro() as conn:
# #         cur = conn.cursor()
# #         # Hosts seen (union of both tables for tolerance)
# #         hosts = set()
# #         for row in cur.execute("SELECT DISTINCT hostname FROM system_metrics"):
# #             if row["hostname"]: hosts.add(row["hostname"])
# #         for row in cur.execute("SELECT DISTINCT hostname AS host FROM service_status"):
# #             if row["host"]: hosts.add(row["host"])
# #         total_hosts = len(hosts)
# #
# #         # Alerts last 24h
# #         since = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
# #         cur.execute("SELECT COUNT(*) AS c FROM alerts WHERE timestamp > ?", (since,))
# #         alerts_24h = cur.fetchone()["c"]
# #         cur.execute("SELECT COUNT(*) AS c FROM recovery_logs WHERE timestamp > ?", (since,))
# #         rec_24h = cur.fetchone()["c"]
# #
# #         # Latest alerts
# #         cur.execute("""
# #             SELECT id, timestamp, hostname, severity, source, message
# #             FROM alerts ORDER BY id DESC LIMIT 10
# #         """)
# #         latest_alerts = cur.fetchall()
# #
# #         # Quick CPU avg over last hour (for fun)
# #         hour = (datetime.utcnow() - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
# #         cur.execute("""
# #             SELECT AVG(cpu_usage) AS avg_cpu
# #             FROM system_metrics WHERE timestamp > ?
# #         """, (hour,))
# #         avg_cpu = round(cur.fetchone()["avg_cpu"] or 0.0, 1)
# #
# #     return {
# #         "total_hosts": total_hosts,
# #         "alerts_24h": alerts_24h,
# #         "recovery_24h": rec_24h,
# #         "avg_cpu": avg_cpu,
# #         "latest_alerts": latest_alerts,
# #     }
#
# def present_columns(conn, table):
#     cur = conn.cursor()
#     cur.execute(f"PRAGMA table_info({table})")
#     return {row["name"] for row in cur.fetchall()}
#
# def list_hosts():
#     """Basic host list with last-seen timestamp + last metrics snapshot."""
#     with connect_ro() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT hostname, MAX(timestamp) AS last_ts
#             FROM system_metrics GROUP BY hostname ORDER BY hostname
#         """)
#         rows = cur.fetchall()
#         out = []
#         for r in rows:
#             hostname = r["hostname"]
#             cur.execute("""
#                 SELECT timestamp, cpu_usage, memory_usage, load_average, swap_usage, inode_usage, disk_usage
#                 FROM system_metrics WHERE hostname=? ORDER BY id DESC LIMIT 1
#             """, (hostname,))
#             last = cur.fetchone()
#             out.append({"hostname": hostname, "last_ts": r["last_ts"], "last": last})
#         return out
#
# def host_metrics(hostname: str, minutes: int = 60, limit: int = 5000):
#     """
#     Return time-series for charts. If optional columns don't exist, they come back as NULL.
#     """
#     from datetime import datetime, timedelta
#     since = (datetime.utcnow() - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
#     with connect_ro() as conn:
#         cols_all = ["timestamp","cpu_usage","memory_usage","load_average","swap_usage","inode_usage","disk_usage"]
#         present = present_columns(conn, "system_metrics")
#         select_exprs = [c if c in present else f"NULL AS {c}" for c in cols_all]
#         sql = f"""
#             SELECT {", ".join(select_exprs)}
#             FROM system_metrics
#             WHERE hostname=? AND timestamp >= ?
#             ORDER BY timestamp ASC LIMIT ?
#         """
#         cur = conn.cursor()
#         cur.execute(sql, (hostname, since, limit))
#         return cur.fetchall()
#
# def host_services(hostname: str):
#     """Latest status per service for a host."""
#     with connect_ro() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT s1.service_name, s1.normalized_status, s1.timestamp
#             FROM service_status s1
#             JOIN (
#               SELECT service_name, MAX(id) AS max_id
#               FROM service_status WHERE hostname=? GROUP BY service_name
#             ) s2 ON s1.service_name = s2.service_name AND s1.id = s2.max_id
#             ORDER BY s1.service_name
#         """, (hostname,))
#         return cur.fetchall()
#
#
# #-----------Alerts (Filters + Pagination)-------
# def get_alerts(seveiry=None, host=None, since_minutes=None, limit=100, offset=0):
#     """
#
#     :param seveiry:
#     :param host:
#     :param since_minutes:
#     :param limit:
#     :param offset:
#     :return:  Returns a list of alerts ordered by newest first with optional filters
#     """
#
#     where, params = [], []
#
#     if seveiry:
#         where.append("LOWER(severity) = ?")
#         params.append(seveiry.strip().lower())
#
#     if host:
#         where.append("LOWER(hostname) LIKE ?")
#         params.append(f"%{host.strip().lower()}%")
#
#     if since_minutes:
#         ts = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
#         where.append("timestamp > ?")
#         params.append(ts)
#
#     sql = "SELECT id, timestamp, hostname, severity, source, message FROM alerts"
#     if where:
#         sql += " WHERE " + " AND ".join(where)
#     sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
#     params.extend([int(limit), int(offset)])
#
#     with connect_ro() as conn:
#         cur = conn.cursor()
#         cur.execute(sql, tuple(params))
#         return cur.fetchall()
#
#
# def count_alerts(severity=None, host=None, since_minutes=None):
#     """
#     Counts total alerts for the given filter (for pagination).
#     """
#     from datetime import datetime, timedelta
#     where, params = [], []
#
#     if severity:
#         where.append("LOWER(severity) = ?")
#         params.append(severity.strip().lower())
#
#     if host:
#         where.append("LOWER(hostname) LIKE ?")
#         params.append(f"%{host.strip().lower()}%")
#
#     if since_minutes:
#         ts = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
#         where.append("timestamp > ?")
#         params.append(ts)
#
#     sql = "SELECT COUNT(*) AS c FROM alerts"
#     if where:
#         sql += " WHERE " + " AND ".join(where)
#
#     with connect_ro() as conn:
#         cur = conn.cursor()
#         cur.execute(sql, tuple(params))
#         row = cur.fetchone()
#         return int(row["c"] if row else 0)
#
#
# def last_alert_id():
#     with connect_ro() as conn:
#         cur = conn.cursor()
#         cur.execute("SELECT IFNULL(MAX(id),0) AS max_id FROM alerts")
#         return int(cur.fetchone()["max_id"])
#
# def alerts_after(after_id: int, max_rows: int = 50):
#     with connect_ro() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT id, timestamp, hostname, severity, source, message
#             FROM alerts WHERE id > ? ORDER BY id ASC LIMIT ?
#         """, (int(after_id), int(max_rows)))
#         return cur.fetchall()
#
#
# # -------- Network page helpers --------
#
# def network_targets(since_minutes: int = 1440):
#     """
#     Distinct targets seen recently with their last status/latency/packet_loss.
#     """
#     from datetime import datetime, timedelta
#     since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
#     with connect_ro() as conn:
#         cur = conn.cursor()
#         # latest row per target (in the window)
#         cur.execute("""
#             SELECT nl.*
#             FROM network_logs nl
#             JOIN (
#               SELECT target, MAX(id) AS max_id
#               FROM network_logs
#               WHERE timestamp >= ?
#               GROUP BY target
#             ) t ON nl.target = t.target AND nl.id = t.max_id
#             ORDER BY nl.target
#         """, (since,))
#         return cur.fetchall()
#
#
# def network_events(host=None, target=None, since_minutes=None, limit=200, offset=0, method=None):
#     """
#     Raw network events (for table). Filters are optional.
#     """
#     where, params = [], []
#     if host:
#         where.append("LOWER(hostname) LIKE ?")
#         params.append(f"%{host.strip().lower()}%")
#     if target:
#         where.append("LOWER(target) = ?")
#         params.append(target.strip().lower())
#     if method:
#         where.append("LOWER(method) = ?")
#         params.append(method.strip().lower())
#     if since_minutes:
#         ts = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
#         where.append("timestamp >= ?")
#         params.append(ts)
#
#     sql = """SELECT id, timestamp, hostname, target, method, status,
#                     latency_ms, packet_loss_percent, result
#              FROM network_logs"""
#     if where:
#         sql += " WHERE " + " AND ".join(where)
#     sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
#     params.extend([int(limit), int(offset)])
#
#     with connect_ro() as conn:
#         cur = conn.cursor()
#         cur.execute(sql, tuple(params))
#         return cur.fetchall()
#
# # Distinct (host, target) with their latest status in the window
# def network_pairs(since_minutes: int = 1440):
#     from datetime import datetime, timedelta
#     since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
#     with connect_ro() as conn:
#         cur = conn.cursor()
#         cur.execute("""
#             SELECT nl.*
#             FROM network_logs nl
#             JOIN (
#               SELECT hostname, target, MAX(id) AS max_id
#               FROM network_logs
#               WHERE timestamp >= ?
#               GROUP BY hostname, target
#             ) t ON nl.hostname = t.hostname
#                AND nl.target   = t.target
#                AND nl.id       = t.max_id
#             ORDER BY nl.target, nl.hostname
#         """, (since,))
#         return cur.fetchall()
#
#
# # time series for one target; optionally restrict to host and method (default ping)
# def network_latency_series(target: str, since_minutes: int = 60, host: str = None, method: str = "ping"):
#     from datetime import datetime, timedelta
#     since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
#
#     sql = """
#         SELECT timestamp, latency_ms
#         FROM network_logs
#         WHERE LOWER(target) = ?
#           AND timestamp >= ?
#           AND method = ?
#           AND latency_ms IS NOT NULL
#     """
#     params = [target.strip().lower(), since, method]
#
#     if host:
#         sql += " AND LOWER(hostname) = ?"
#         params.append(host.strip().lower())
#
#     sql += " ORDER BY timestamp ASC"
#
#     with connect_ro() as conn:
#         cur = conn.cursor()
#         cur.execute(sql, tuple(params))
#         return cur.fetchall()
#
#
# # latest traceroute / nslookup for a (host, target)
# def latest_result_for(target: str, method: str, host: str = None):
#     sql = """
#         SELECT timestamp, result, status
#         FROM network_logs
#         WHERE LOWER(target) = ? AND LOWER(method) = ?
#     """
#     params = [target.strip().lower(), method.strip().lower()]
#     if host:
#         sql += " AND LOWER(hostname) = ?"
#         params.append(host.strip().lower())
#     sql += " ORDER BY id DESC LIMIT 1"
#     with connect_ro() as conn:
#         cur = conn.cursor()
#         cur.execute(sql, tuple(params))
#         return cur.fetchone()
#
# def _smart_table_exists(cur) -> bool:
#     cur.execute("""SELECT name FROM sqlite_master
#                        WHERE type='table' AND name='smart_health'""")
#     return cur.fetchone() is not None
#
# def smart_latest(host: Optional[str] = None):
#     """
#     Return the latest SMART health per (hostname, device).
#     Expects table:
#       smart_health(id, timestamp, hostname, device, health, model, temp_c, output)
#     health examples: 'PASSED', 'FAILED', 'Unknown'
#     """
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     cur = conn.cursor()
#
#     if not _smart_table_exists(cur):
#         conn.close()
#         return []  # graceful: no table yet
#
#     params = []
#     where = " WHERE 1=1 "
#     if host:
#         where += " AND hostname = ? "
#         params.append(host)
#
#     # latest row per host+device
#     sql = f"""
#       WITH latest AS (
#         SELECT hostname, device, MAX(timestamp) AS ts
#         FROM smart_health {where}
#         GROUP BY hostname, device
#       )
#       SELECT s.timestamp, s.hostname, s.device, s.health, s.model, s.temp_c
#       FROM smart_health s
#       JOIN latest L
#         ON s.hostname=L.hostname AND s.device=L.device AND s.timestamp=L.ts
#       ORDER BY s.hostname, s.device;
#     """
#     cur.execute(sql, params)
#     rows = [dict(r) for r in cur.fetchall()]
#     conn.close()
#     return rows
#
# # -------improved version with connect_ro will be implemented later------
# # def smart_latest(host: str | None = None):
# #     where, params = " WHERE 1=1 ", []
# #     if host:
# #         where += " AND hostname = ? "; params.append(host)
# #
# #     sql = f"""
# #       WITH latest AS (
# #         SELECT hostname, device, MAX(timestamp) AS ts
# #         FROM smart_health {where}
# #         GROUP BY hostname, device
# #       )
# #       SELECT s.timestamp, s.hostname, s.device, s.health, s.model, s.temp_c
# #       FROM smart_health s
# #       JOIN latest L
# #         ON s.hostname=L.hostname AND s.device=L.device AND s.timestamp=L.ts
# #       ORDER BY s.hostname, s.device;
# #     """
# #     with connect_ro(dicts=True) as conn:
# #         return conn.execute(sql, params).fetchall()   # list[dict]
#
#
# def hosts_for_smart():
#     """Hosts that either have SMART rows or at least system_metrics (for charts)."""
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     cur = conn.cursor()
#
#     # Try smart_health first, fallback to system_metrics
#     cur.execute("""SELECT name FROM sqlite_master
#                    WHERE type='table' AND name='smart_health'""")
#     if cur.fetchone():
#         cur.execute("SELECT DISTINCT hostname FROM smart_health ORDER BY hostname")
#         hs = [r[0] for r in cur.fetchall()]
#         conn.close()
#         if hs:
#             return hs
#
#     cur.execute("SELECT DISTINCT hostname FROM system_metrics ORDER BY hostname")
#     hs = [r[0] for r in cur.fetchall()]
#     conn.close()
#     return hs
#
# # -------improved version with connect_ro will be implemented later------
# # def hosts_for_smart():
# #     with connect_ro() as conn:
# #         cur = conn.cursor()
# #         cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='smart_health'")
# #         if cur.fetchone():
# #             return [r["hostname"] for r in conn.execute(
# #                 "SELECT DISTINCT hostname FROM smart_health ORDER BY hostname"
# #             )]
# #         return [r["hostname"] for r in conn.execute(
# #             "SELECT DISTINCT hostname FROM system_metrics ORDER BY hostname"
# #         )]
#
#
#
#
#
#
# # --- Services (fleet view) ----------------------------------------------------
#
# from typing import Optional, List, Dict, Any
#
# # --- internal ---------------------------------------------------------------
#
# def _services_query(
#     windowed: bool,
#     host: Optional[str],
#     status: Optional[str],
#     since_minutes: int,
#     limit: int,
#     offset: int,
# ) -> List[Dict[str, Any]]:
#     """
#     Latest row per (hostname, service_name), optionally time-windowed by ts_epoch.
#     Joins last recovery row and a recent failure counter.
#     Returns a list of dicts with stable field names for the UI.
#     """
#     con = sqlite3.connect(DB_PATH)
#     con.row_factory = sqlite3.Row
#     cur = con.cursor()
#
#     # Optional WHERE on outer SELECT
#     where = []
#     params: List[Any] = []
#     if host:
#         where.append("l.hostname = ?")
#         params.append(host)
#     if status:
#         where.append("l.normalized_status = ?")
#         params.append(status)
#     where_sql = ("WHERE " + " AND ".join(where)) if where else ""
#
#     # Time filter for the inner MAX(ts_epoch) subquery
#     time_filter = "WHERE ts_epoch >= (strftime('%s','now') - (? * 60))" if windowed else ""
#
#     sql = f"""
#     WITH latest AS (
#       SELECT s.*
#       FROM service_status s
#       JOIN (
#         SELECT hostname, service_name, MAX(ts_epoch) AS max_ts
#         FROM service_status
#         {time_filter}
#         GROUP BY hostname, service_name
#       ) m
#         ON s.hostname     = m.hostname
#        AND s.service_name = m.service_name
#        AND s.ts_epoch     = m.max_ts
#     ),
#     last_rec AS (
#       SELECT rl.hostname, rl.service_name,
#              rl.timestamp AS last_recovery_at,
#              rl.result    AS last_recovery_result
#       FROM recovery_logs rl
#       JOIN (
#         SELECT hostname, service_name, MAX(timestamp) AS max_t
#         FROM recovery_logs
#         GROUP BY hostname, service_name
#       ) rmax
#         ON rl.hostname     = rmax.hostname
#        AND rl.service_name = rmax.service_name
#        AND rl.timestamp   = rmax.max_t
#     )
#     SELECT
#       l.hostname                          AS host,
#       l.service_name                      AS service_name,
#       l.os_platform                       AS os_platform,
#       l.normalized_status                 AS status,
#       COALESCE(l.sub_state, '')           AS sub_state,
#       COALESCE(l.unit_file_state, '')     AS unit_file_state,
#       CAST(l.recoverable AS INTEGER)      AS recoverable,
#       datetime(l.ts_epoch, 'unixepoch')   AS updated,
#       COALESCE(r.last_recovery_result,'') AS last_recovery_result,
#       r.last_recovery_at,
#       (
#         SELECT COUNT(*)
#         FROM recovery_logs rf
#         WHERE rf.hostname = l.hostname
#           AND rf.service_name = l.service_name
#           AND rf.result = 'fail'
#           AND rf.timestamp > datetime('now','-30 minutes')
#       ) AS recent_failures
#     FROM latest l
#     LEFT JOIN last_rec r
#       ON r.hostname     = l.hostname
#      AND r.service_name = l.service_name
#     {where_sql}
#     ORDER BY l.hostname, l.service_name
#     LIMIT ? OFFSET ?;
#     """
#
#     exec_params: List[Any] = []
#     if windowed:
#         exec_params.append(int(since_minutes))   # minutes for ts_epoch filter
#     exec_params.extend(params)                   # WHERE host/status (outer)
#     exec_params.extend([limit, offset])          # pagination
#
#     cur.execute(sql, exec_params)
#     rows = [dict(r) for r in cur.fetchall()]
#     con.close()
#     return rows
#
#
# def _services_count_query(
#     windowed: bool,
#     host: Optional[str],
#     status: Optional[str],
#     since_minutes: int,
# ) -> int:
#     """
#     Count distinct (host, service) from the same latest snapshot CTE.
#     """
#     con = sqlite3.connect(DB_PATH)
#     con.row_factory = sqlite3.Row
#     cur = con.cursor()
#
#     where = []
#     params: List[Any] = []
#     if host:
#         where.append("l.hostname = ?")
#         params.append(host)
#     if status:
#         where.append("l.normalized_status = ?")
#         params.append(status)
#     where_sql = ("WHERE " + " AND ".join(where)) if where else ""
#
#     time_filter = "WHERE ts_epoch >= (strftime('%s','now') - (? * 60))" if windowed else ""
#
#     sql = f"""
#     WITH latest AS (
#       SELECT s.*
#       FROM service_status s
#       JOIN (
#         SELECT hostname, service_name, MAX(ts_epoch) AS max_ts
#         FROM service_status
#         {time_filter}
#         GROUP BY hostname, service_name
#       ) m
#         ON s.hostname     = m.hostname
#        AND s.service_name = m.service_name
#        AND s.ts_epoch     = m.max_ts
#     )
#     SELECT COUNT(*) AS n
#     FROM latest l
#     {where_sql};
#     """
#
#     exec_params: List[Any] = []
#     if windowed:
#         exec_params.append(int(since_minutes))
#     exec_params.extend(params)
#
#     cur.execute(sql, exec_params)
#     n = int(cur.fetchone()[0])
#     con.close()
#     return n
#
# # --- public ------------------------------------------------------------------
#
# def latest_services(
#     host: Optional[str] = None,
#     status: Optional[str] = None,
#     since_minutes: int = 1440,
#     limit: int = 200,
#     offset: int = 0,
# ) -> List[Dict[str, Any]]:
#     """
#     Prefer a time-window (since_minutes); if empty, fall back to unwindowed latest.
#     """
#     rows = _services_query(True, host, status, since_minutes, limit, offset)
#     if rows:
#         return rows
#     return _services_query(False, host, status, since_minutes, limit, offset)
#
#
# def services_count(
#     host: Optional[str] = None,
#     status: Optional[str] = None,
#     since_minutes: int = 1440,
# ) -> int:
#     n = _services_count_query(True, host, status, since_minutes)
#     if n > 0:
#         return n
#     return _services_count_query(False, host, status, since_minutes)
#






































#
# def _services_query(windowed: bool,
#                     host: Optional[str],
#                     status: Optional[str],
#                     since_minutes: int,
#                     limit: int,
#                     offset: int) -> List[Dict[str, Any]]:
#     """
#     Run the 'latest per (host, service)' selection, optionally windowed by time.
#     Returns list of dict rows.
#     """
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     cur = conn.cursor()
#
#     # WHERE filters for the outer SELECT
#     where = []
#     params: List[Any] = []
#
#     if host:
#         where.append("l.hostname = ?")
#         params.append(host)
#     if status:
#         where.append("l.normalized_status = ?")
#         params.append(status)
#
#     where_sql = ("WHERE " + " AND ".join(where)) if where else ""
#
#     # Time filter appears in the MAX(ts_epoch) subqueries when windowed
#     time_filter = "WHERE timestamp > DATETIME('now', ?)" if windowed else ""
#
#     # NOTE: we use MAX(ts_epoch) to pick the latest row per (host, service)
#     sql = f"""
#     WITH latest AS (
#       SELECT s.*
#       FROM service_status s
#       JOIN (
#         SELECT hostname, service_name, MAX(ts_epoch) AS max_ts
#         FROM service_status
#         {time_filter}
#         GROUP BY hostname, service_name
#       ) m
#       ON s.hostname = m.hostname
#      AND s.service_name = m.service_name
#      AND s.ts_epoch = m.max_ts
#     ),
#     last_rec AS (
#       SELECT rl.hostname, rl.service_name,
#              rl.timestamp AS last_recovery_at,
#              rl.result    AS last_recovery_result
#       FROM recovery_logs rl
#       JOIN (
#         SELECT hostname, service_name, MAX(timestamp) AS max_t
#         FROM recovery_logs
#         GROUP BY hostname, service_name
#       ) rmax
#       ON rl.hostname = rmax.hostname
#      AND rl.service_name = rmax.service_name
#      AND rl.timestamp = rmax.max_t
#     )
#     SELECT
#       l.hostname            AS host,
#       l.os_platform,
#       l.service_name,
#       l.normalized_status   AS status,
#       l.sub_state,
#       l.unit_file_state,
#       l.recoverable,
#       l.timestamp           AS updated,
#       COALESCE(r.last_recovery_result,'') AS last_recovery_result,
#       r.last_recovery_at,
#       (
#         SELECT COUNT(*)
#         FROM recovery_logs rf
#         WHERE rf.hostname = l.hostname
#           AND rf.service_name = l.service_name
#           AND rf.result = 'fail'
#           AND rf.timestamp > DATETIME('now', '-30 minutes')
#       ) AS recent_failures
#     FROM latest l
#     LEFT JOIN last_rec r
#       ON r.hostname = l.hostname
#      AND r.service_name = l.service_name
#     {where_sql}
#     ORDER BY l.hostname, l.service_name
#     LIMIT ? OFFSET ?;
#     """
#
#     # Build parameters in the order of placeholders in SQL
#     exec_params: List[Any] = []
#     if windowed:
#         # time parameter for the CTE's inner subquery
#         exec_params.append(f"-{since_minutes} minutes")
#     # filters for WHERE
#     exec_params.extend(params)
#     # pagination
#     exec_params.extend([limit, offset])
#
#     cur.execute(sql, exec_params)
#     rows = [dict(r) for r in cur.fetchall()]
#     conn.close()
#     return rows
#
#
# def latest_services(
#         host: Optional[str] = None,
#         status: Optional[str] = None,   # matches normalized_status
#         since_minutes: int = 1440,
#         limit: int = 200,
#         offset: int = 0,
# ) -> List[Dict[str, Any]]:
#     """
#     Return one row per (host, service) = latest in service_status,
#     joined with last recovery_logs row and a recent fail counter.
#
#     Robust behavior:
#     - Try 'windowed' (within since_minutes).
#     - If 0 rows, fall back to 'unwindowed' (any time).
#     """
#     # 1) windowed attempt
#     rows = _services_query(
#         windowed=True,
#         host=host,
#         status=status,
#         since_minutes=since_minutes,
#         limit=limit,
#         offset=offset,
#     )
#     if rows:
#         return rows
#
#     # 2) fallback (no time window)
#     return _services_query(
#         windowed=False,
#         host=host,
#         status=status,
#         since_minutes=since_minutes,  # not used when windowed=False
#         limit=limit,
#         offset=offset,
#     )
#
#
# def _services_count_query(windowed: bool,
#                           host: Optional[str],
#                           status: Optional[str],
#                           since_minutes: int) -> int:
#     """
#     Count distinct (host, service) pairs for the latest snapshot.
#     """
#     conn = sqlite3.connect(DB_PATH)
#     conn.row_factory = sqlite3.Row
#     cur = conn.cursor()
#
#     where = []
#     params: List[Any] = []
#
#     if host:
#         where.append("l.hostname = ?")
#         params.append(host)
#     if status:
#         where.append("l.normalized_status = ?")
#         params.append(status)
#     where_sql = ("WHERE " + " AND ".join(where)) if where else ""
#
#     time_filter = "WHERE timestamp > DATETIME('now', ?)" if windowed else ""
#
#     sql = f"""
#     WITH latest AS (
#       SELECT s.*
#       FROM service_status s
#       JOIN (
#         SELECT hostname, service_name, MAX(ts_epoch) AS max_ts
#         FROM service_status
#         {time_filter}
#         GROUP BY hostname, service_name
#       ) m
#       ON s.hostname = m.hostname
#      AND s.service_name = m.service_name
#      AND s.ts_epoch = m.max_ts
#     )
#     SELECT COUNT(*) AS n
#     FROM latest l
#     {where_sql};
#     """
#
#     exec_params: List[Any] = []
#     if windowed:
#         exec_params.append(f"-{since_minutes} minutes")
#     exec_params.extend(params)
#
#     cur.execute(sql, exec_params)
#     n = cur.fetchone()[0]
#     conn.close()
#     return int(n)
#
#
# def services_count(host: Optional[str] = None,
#                    status: Optional[str] = None,
#                    since_minutes: int = 1440) -> int:
#     """
#     Robust count with the same fallback logic used by latest_services().
#     """
#     n = _services_count_query(
#         windowed=True,
#         host=host,
#         status=status,
#         since_minutes=since_minutes,
#     )
#     if n > 0:
#         return n
#     return _services_count_query(
#         windowed=False,
#         host=host,
#         status=status,
#         since_minutes=since_minutes,
#     )
#










