#------------------------------------------
"""Author: Anselem Okeke
    MIT License
    Copyright (c) 2025 Anselem Okeke
    See LICENSE file in the project root for full license text.
"""
#------------------------------------------

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


def _k8s_summary(conn, since_iso: str, cluster_name: Optional[str] = None) -> Dict[str, int]:
    """
    Returns counts from latest snapshots (per pod / per cluster) within a time window.

    Output:
      {
        "k8s_pods_total": int,
        "k8s_pods_unhealthy": int,
        "k8s_clusters_total": int,
        "k8s_clusters_api_down": int,
      }
    """
    out = {
        "k8s_pods_total": 0,
        "k8s_pods_unhealthy": 0,
        "k8s_clusters_total": 0,
        "k8s_clusters_api_down": 0,
    }

    # ---- Pods (latest row per pod) ----
    if _table_exists(conn, "k8s_pod_health"):
        where = [f'"timestamp" >= {_P}']
        params = [since_iso]

        if cluster_name:
            where.append(f"cluster_name = {_P}")
            params.append(cluster_name)

        where_sql = " AND ".join(where)

        sub = f"""
            SELECT cluster_name, namespace, pod_name, MAX(id) AS max_id
            FROM k8s_pod_health
            WHERE {where_sql}
            GROUP BY cluster_name, namespace, pod_name
        """

        sql = f"""
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN COALESCE(p.problem_type,'') <> 'Healthy' THEN 1 ELSE 0 END) AS unhealthy
            FROM k8s_pod_health p
            JOIN ({sub}) m
              ON p.id = m.max_id
        """
        rows = fetchall_dicts(conn, sql, tuple(params))
        if rows:
            out["k8s_pods_total"] = int(rows[0]["total"] or 0)
            out["k8s_pods_unhealthy"] = int(rows[0]["unhealthy"] or 0)

    # ---- Clusters (latest row per cluster) ----
    if _table_exists(conn, "k8s_cluster_health"):
        where = [f'"timestamp" >= {_P}']
        params = [since_iso]

        if cluster_name:
            where.append(f"cluster_name = {_P}")
            params.append(cluster_name)

        where_sql = " AND ".join(where)

        sub = f"""
            SELECT cluster_name, MAX(id) AS max_id
            FROM k8s_cluster_health
            WHERE {where_sql}
            GROUP BY cluster_name
        """

        sql = f"""
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN c.api_reachable = FALSE THEN 1 ELSE 0 END) AS api_down
            FROM k8s_cluster_health c
            JOIN ({sub}) m
              ON c.id = m.max_id
        """
        rows = fetchall_dicts(conn, sql, tuple(params))
        if rows:
            out["k8s_clusters_total"] = int(rows[0]["total"] or 0)
            out["k8s_clusters_api_down"] = int(rows[0]["api_down"] or 0)

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

        k8s = _k8s_summary(conn, since_10m)

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

        **k8s,
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


# ───────── Kubernetes: latest snapshots (per pod / per cluster) ─────────

def k8s_pods_latest(
    cluster: Optional[str] = None,
    namespace: Optional[str] = None,
    problem_type: Optional[str] = None,
    only_unhealthy: bool = False,
    since_minutes: int = 10,
    limit: int = 300,
    offset: int = 0,
):
    """
    Latest row per (cluster_name, namespace, pod_name) within a lookback window.
    Portable SQLite + Postgres (MAX(id) join, no DISTINCT ON).

    Filters:
      - cluster, namespace
      - problem_type
      - only_unhealthy (problem_type != 'Healthy')
    """
    since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")

    with connect_ro(dicts=True) as conn:
        if not _table_exists(conn, "k8s_pod_health"):
            return []

        # subquery filters (to keep grouping small)
        where_sub, params = [f'"timestamp" >= {_P}'], [since]
        if cluster:
            where_sub.append(f"cluster_name = {_P}")
            params.append(cluster)
        if namespace:
            where_sub.append(f"namespace = {_P}")
            params.append(namespace)

        sub = f"""
            SELECT cluster_name, namespace, pod_name, MAX(id) AS max_id
            FROM k8s_pod_health
            WHERE {" AND ".join(where_sub)}
            GROUP BY cluster_name, namespace, pod_name
        """

        # outer filters (after latest-per-pod is selected)
        where_outer, params2 = [], list(params)
        if only_unhealthy:
            where_outer.append("COALESCE(p.problem_type,'') <> 'Healthy'")
        if problem_type:
            where_outer.append(f"p.problem_type = {_P}")
            params2.append(problem_type)

        outer_where_sql = ("WHERE " + " AND ".join(where_outer)) if where_outer else ""

        sql = f"""
            SELECT
              p.id, p."timestamp",
              p.cluster_name, p.namespace, p.pod_name,
              p.phase, p.problem_type, p.problem_reason, p.problem_message,
              p.total_restart_count, p.last_exit_code,
              p.last_termination_reason, p.last_termination_oom
            FROM k8s_pod_health p
            JOIN ({sub}) m
              ON p.id = m.max_id
            {outer_where_sql}
            ORDER BY p.id DESC
            LIMIT {int(limit)} OFFSET {int(offset)}
        """
        return fetchall_dicts(conn, sql, tuple(params2))


def count_k8s_pods_latest(
    cluster: Optional[str] = None,
    namespace: Optional[str] = None,
    problem_type: Optional[str] = None,
    only_unhealthy: bool = False,
    since_minutes: int = 10,
):
    """Count rows that would be returned by k8s_pods_latest (pagination support)."""
    since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")

    with connect_ro(dicts=True) as conn:
        if not _table_exists(conn, "k8s_pod_health"):
            return 0

        where_sub, params = [f'"timestamp" >= {_P}'], [since]
        if cluster:
            where_sub.append(f"cluster_name = {_P}")
            params.append(cluster)
        if namespace:
            where_sub.append(f"namespace = {_P}")
            params.append(namespace)

        sub = f"""
            SELECT cluster_name, namespace, pod_name, MAX(id) AS max_id
            FROM k8s_pod_health
            WHERE {" AND ".join(where_sub)}
            GROUP BY cluster_name, namespace, pod_name
        """

        where_outer, params2 = [], list(params)
        if only_unhealthy:
            where_outer.append("COALESCE(p.problem_type,'') <> 'Healthy'")
        if problem_type:
            where_outer.append(f"p.problem_type = {_P}")
            params2.append(problem_type)

        outer_where_sql = ("WHERE " + " AND ".join(where_outer)) if where_outer else ""

        sql = f"""
            SELECT COUNT(*) AS c
            FROM k8s_pod_health p
            JOIN ({sub}) m ON p.id = m.max_id
            {outer_where_sql}
        """
        rows = fetchall_dicts(conn, sql, tuple(params2))
        return int(rows[0]["c"] if rows else 0)


def k8s_clusters_latest(
    cluster: Optional[str] = None,
    since_minutes: int = 60,
    limit: int = 50,
    offset: int = 0,
):
    """
    Latest row per cluster_name within lookback window.
    """
    since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
    with connect_ro(dicts=True) as conn:
        if not _table_exists(conn, "k8s_cluster_health"):
            return []

        where_sub, params = [f'"timestamp" >= {_P}'], [since]
        if cluster:
            where_sub.append(f"cluster_name = {_P}")
            params.append(cluster)

        sub = f"""
            SELECT cluster_name, MAX(id) AS max_id
            FROM k8s_cluster_health
            WHERE {" AND ".join(where_sub)}
            GROUP BY cluster_name
        """

        sql = f"""
            SELECT c.id, c."timestamp", c.cluster_name, c.api_reachable, c.k8s_version
            FROM k8s_cluster_health c
            JOIN ({sub}) m ON c.id = m.max_id
            ORDER BY c.id DESC
            LIMIT {int(limit)} OFFSET {int(offset)}
        """
        return fetchall_dicts(conn, sql, tuple(params))


def count_k8s_clusters_latest(
    cluster: Optional[str] = None,
    since_minutes: int = 60,
):
    since = (datetime.utcnow() - timedelta(minutes=int(since_minutes))).strftime("%Y-%m-%d %H:%M:%S")
    with connect_ro(dicts=True) as conn:
        if not _table_exists(conn, "k8s_cluster_health"):
            return 0

        where_sub, params = [f'"timestamp" >= {_P}'], [since]
        if cluster:
            where_sub.append(f"cluster_name = {_P}")
            params.append(cluster)

        sub = f"""
            SELECT cluster_name, MAX(id) AS max_id
            FROM k8s_cluster_health
            WHERE {" AND ".join(where_sub)}
            GROUP BY cluster_name
        """

        sql = f"""
            SELECT COUNT(*) AS c
            FROM k8s_cluster_health c
            JOIN ({sub}) m ON c.id = m.max_id
        """
        rows = fetchall_dicts(conn, sql, tuple(params))
        return int(rows[0]["c"] if rows else 0)


