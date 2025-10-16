# api/services.py  (portable: SQLite now, Postgres later)
import json
import os
import re
import socket
import time
from datetime import datetime, timedelta
from io import StringIO
from typing import Optional
from urllib.parse import quote, unquote

from flask import request, jsonify, Response, render_template, abort

from . import api_bp
from ..views import ui_bp
from ..read_service import latest_services, services_count
from datetime import datetime, timedelta, timezone

from db.core import (
    connect_ro, connect_rw, fetchall_dicts, execute,
)

import csv

API_KEY = os.getenv("SMARTMON_API_KEY")  # RBAC: set as required
APPROVED_PATH = os.getenv("SMARTMON_APPROVED_JSON", "config/approved_services.json")

COOLDOWN_MIN        = int(os.getenv("SMARTMON_RESTART_COOLDOWN_MIN", "10"))
BACKOFF_FAILS       = int(os.getenv("SMARTMON_RESTART_BACKOFF_FAILS", "3"))
BACKOFF_WINDOW_MIN  = int(os.getenv("SMARTMON_RESTART_BACKOFF_WINDOW_MIN", "30"))

THIS_HOST = socket.gethostname()

# def _normalize_status_param(raw: str):
#     if not raw:
#         return None
#     s = raw.strip().lower()
#     # strip any " (…)" suffixes like "active (running)"
#     s = re.sub(r"\s*\(.*\)$", "", s)
#     if s in ("any", "any status", "all"):
#         return None
#     if s in ("active", "running"):
#         return "active"
#     if s in ("stopped", "inactive"):
#         return "stopped"
#     if s in ("failed",):
#         return "failed"
#     return s

# ─────────────────────────────────────────────────────────────────────────────
# List + CSV
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.get("/services")
def api_services():
    host   = request.args.get("host") or None
    status = request.args.get("status") or None
    since  = int(request.args.get("since_minutes") or 1440)
    limit  = max(1, min(int(request.args.get("limit") or 200), 1000))
    offset = max(0, int(request.args.get("offset") or 0))

    items = latest_services(host=host, status=status, since_minutes=since, limit=limit, offset=offset)
    total = services_count(host=host, status=status, since_minutes=since)
    return jsonify({"total": total, "items": items, "limit": limit, "offset": offset})


@api_bp.get("/services.csv")
def api_services_csv():
    host   = request.args.get("host") or None
    status = request.args.get("status")
    since  = int(request.args.get("since_minutes") or 1440)

    rows = latest_services(host=host, status=status, since_minutes=since, limit=20000, offset=0)

    buf = StringIO()
    fieldnames = [
        "host","service_name","os_platform","status","sub_state","unit_file_state",
        "recoverable","updated","last_recovery_result","last_recovery_at","recent_failures"
    ]
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    for r in rows:
        w.writerow({k: r.get(k, "") for k in fieldnames})

    data = buf.getvalue().encode("utf-8-sig")
    filename = f"services_{host or 'all'}_{since}m.csv"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "Content-Type": "text/csv; charset=utf-8",
    }
    return Response(data, headers=headers)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _require_api_key():
    if not API_KEY:
        # In dev we allow; in prod set SMARTMON_API_KEY
        return
    key = request.headers.get("X-API-Key")
    if key != API_KEY:
        abort(401, description="Missing/invalid API key")

def _is_allowed(host, service) -> bool:
    try:
        with open(APPROVED_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"[ERROR] approved_services: {e}")
        return False
    for item in cfg.get("allow", []):
        h = item.get("host", "*")
        s = item.get("service", "*")
        if (h in ("*", host)) and (s in ("*", service)):
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# UI: service detail page (reads DB in portable way)
# ─────────────────────────────────────────────────────────────────────────────

@ui_bp.get("/services/<host>/<path:service>")
def service_detail(host, service):
    service = unquote(service)

    minutes = int(request.args.get("minutes", 1440))
    minutes = max(5, min(minutes, 10080))
    since_epoch = int(time.time()) - minutes * 60

    with connect_ro(dicts=True) as con:
        latest = fetchall_dicts(con, """
            SELECT *
            FROM service_status
            WHERE hostname = %s AND service_name = %s
            ORDER BY ts_epoch DESC
            LIMIT 1
        """, (host, service))
        if not latest:
            abort(404, description="No records for this host/service")

        history_asc = fetchall_dicts(con, """
            SELECT ts_epoch, "timestamp", raw_status, normalized_status, sub_state, unit_file_state, recoverable
            FROM service_status
            WHERE hostname = %s AND service_name = %s AND ts_epoch >= %s
            ORDER BY ts_epoch ASC
            LIMIT 2000
        """, (host, service, since_epoch))

        attempts = fetchall_dicts(con, """
            SELECT "timestamp", result, COALESCE(error_message,'') AS error_message
            FROM recovery_logs
            WHERE hostname = %s AND service_name = %s
            ORDER BY "timestamp" DESC
            LIMIT 100
        """, (host, service))

    def _compute_uptime_and_last_change(rows, window_start, window_end):
        if not rows:
            return 0.0, None
        pts = [(window_start, rows[0]["normalized_status"])]
        pts += [(int(r["ts_epoch"]), r["normalized_status"]) for r in rows]
        pts.append((window_end, rows[-1]["normalized_status"]))
        up = 0
        for (t1, s1), (t2, _s2) in zip(pts, pts[1:]):
            dur = max(0, t2 - t1)
            if s1 == "active":
                up += dur
        uptime_pct = (up / max(1, (window_end - window_start))) * 100.0

        last_change = None
        last_state = rows[-1]["normalized_status"]
        for r in reversed(rows[:-1]):
            if r["normalized_status"] != last_state:
                last_change = r["timestamp"]
                break
        return round(uptime_pct, 2), last_change

    now_epoch = int(time.time())
    uptime_pct, last_change = _compute_uptime_and_last_change(history_asc, since_epoch, now_epoch)
    history_desc = list(reversed(history_asc))

    return render_template(
        "service_details.html",
        host=host, service=service,
        latest=latest[0],
        history=history_desc,
        attempts=attempts,
        minutes=minutes,
        uptime_pct=uptime_pct,
        last_change=last_change
    )


# ─────────────────────────────────────────────────────────────────────────────
# API: history JSON & CSV
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.get("/services/<host>/<path:service>/history")
def api_service_history(host, service):
    since = int(request.args.get("since_minutes") or 1440)
    since = max(5, min(since, 10080))  # 5 min .. 7 days
    t0 = int(time.time()) - since * 60

    with connect_ro(dicts=True) as con:
        rows = fetchall_dicts(con, """
            SELECT ts_epoch, "timestamp", raw_status, normalized_status, sub_state, unit_file_state, recoverable
            FROM service_status
            WHERE hostname = %s AND service_name = %s AND ts_epoch >= %s
            ORDER BY ts_epoch ASC
            LIMIT 2000
        """, (host, service, t0))
    return jsonify(rows)

@api_bp.get("/services/<host>/<path:service>/export.csv")
def api_service_history_csv(host, service):
    since = int(request.args.get("since_minutes") or 1440)
    since = max(5, min(since, 10080))
    t0 = int(time.time()) - since * 60

    with connect_ro(dicts=True) as con:
        rows = fetchall_dicts(con, """
            SELECT ts_epoch, "timestamp", raw_status, normalized_status, sub_state, unit_file_state, recoverable
            FROM service_status
            WHERE hostname = %s AND service_name = %s AND ts_epoch >= %s
            ORDER BY ts_epoch ASC
            LIMIT 2000
        """, (host, service, t0))

    buf = StringIO()
    cols = ["ts_epoch","timestamp","raw_status","normalized_status","sub_state","unit_file_state","recoverable"]
    w = csv.DictWriter(buf, fieldnames=cols); w.writeheader()
    for r in rows: w.writerow({k: r.get(k) for k in cols})
    data = buf.getvalue().encode("utf-8-sig")
    fn = f"{host}_{service.replace('/','-')}_{since}m.csv"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(fn)}",
        "Content-Type": "text/csv; charset=utf-8",
    }
    return Response(data, headers=headers)


# ─────────────────────────────────────────────────────────────────────────────
# Safe Restart (portable)
# ─────────────────────────────────────────────────────────────────────────────

from scripts.recovery.service.service_recovery import (
    restart_service_linux, restart_service_windows
)

@api_bp.post("/services/restart")
def api_service_restart():
    _require_api_key()

    payload = request.get_json(silent=True) or {}
    host = payload.get("host")
    service = payload.get("service")
    if not host or not service:
        return jsonify({"ok": False, "error": "host and service required"}), 400
    if not _is_allowed(host, service):
        return jsonify({"ok": False, "error": "not in approved_services.json"}), 403

    # latest snapshot (recoverable + os)
    with connect_ro(dicts=True) as con:
        latest = fetchall_dicts(con, """
            SELECT recoverable, os_platform
            FROM service_status
            WHERE hostname = %s AND service_name = %s
            ORDER BY ts_epoch DESC
            LIMIT 1
        """, (host, service))

    if not latest:
        return jsonify({"ok": False, "error": "no snapshot for host/service"}), 404

    recoverable = int(latest[0].get("recoverable") or 0)
    osplat = (latest[0].get("os_platform") or "").lower()
    if recoverable != 1:
        return jsonify({"ok": False, "error": "service not recoverable"}), 409

    # Cooldown & backoff — do time arithmetic in Python (portable)

    now = datetime.utcnow()
    cooldown_cut = datetime.now(timezone.utc) - timedelta(minutes=COOLDOWN_MIN)
    backoff_cut  = now - timedelta(minutes=BACKOFF_WINDOW_MIN)

    with connect_ro(dicts=True) as con:
        # last non-queued attempt
        rows = fetchall_dicts(con, """
            SELECT MAX("timestamp") AS last_ts
            FROM recovery_logs
            WHERE hostname = %s AND service_name = %s AND result != 'queued'
        """, (host, service))
        last_ts_val = rows[0].get("last_ts") if rows else None

    def _parse_dt(x):
        if x is None:
            return None
        if isinstance(x, datetime):
            return x
        # SQLite returns text "YYYY-MM-DD HH:MM:SS"
        try:
            # tolerate both " " and "T"
            s = str(x).replace("T", " ")
            return datetime.fromisoformat(s)
        except Exception:
            return None

    last_dt = _parse_dt(last_ts_val)
    if last_dt and last_dt > cooldown_cut:
        return jsonify({"ok": False, "error": f"cooldown {COOLDOWN_MIN}m active"}), 429

    with connect_ro(dicts=True) as con:
        rows = fetchall_dicts(con, """
            SELECT COUNT(*) AS n
            FROM recovery_logs
            WHERE hostname = %s AND service_name = %s
              AND result = 'fail' AND "timestamp" >= %s
        """, (host, service, backoff_cut))
        nfail = int(rows[0]["n"] if rows else 0)
    if nfail >= BACKOFF_FAILS:
        return jsonify({"ok": False, "error": f"backoff: {nfail} fails in {BACKOFF_WINDOW_MIN}m"}), 429

    DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
    if DRY_RUN:
        with connect_rw() as con:
            execute(con, """
                INSERT INTO recovery_logs("timestamp", hostname, os_platform, service_name, result, error_message)
                VALUES (CURRENT_TIMESTAMP, %s, %s, %s, 'queued', 'dry-run')
            """, (host, osplat, service))
        return jsonify({"ok": True, "result": "queued", "dry_run": True}), 202

    # local vs remote
    if host == THIS_HOST:
        try:
            if "win" in osplat:
                ok, msg = restart_service_windows(service)
            else:
                ok, msg = restart_service_linux(service)

            if ok:
                with connect_rw() as con:
                    execute(con, """
                        INSERT INTO recovery_logs("timestamp", hostname, os_platform, service_name, result, error_message)
                        VALUES (CURRENT_TIMESTAMP, %s, %s, %s, 'success', '')
                    """, (host, osplat, service))
                return jsonify({"ok": True, "executed_on": THIS_HOST, "result": "success"})
            else:
                with connect_rw() as con:
                    execute(con, """
                        INSERT INTO recovery_logs("timestamp", hostname, os_platform, service_name, result, error_message)
                        VALUES (CURRENT_TIMESTAMP, %s, %s, %s, 'fail', %s)
                    """, (host, osplat, service, (msg or "")[:500]))
                return jsonify({"ok": False, "executed_on": THIS_HOST, "result": "fail", "stderr": msg}), 500

        except Exception as e:
            with connect_rw() as con:
                execute(con, """
                    INSERT INTO recovery_logs("timestamp", hostname, os_platform, service_name, result, error_message)
                    VALUES (CURRENT_TIMESTAMP, %s, %s, %s, 'fail', %s)
                """, (host, osplat, service, str(e)[:500]))
            return jsonify({"ok": False, "executed_on": THIS_HOST, "result": "fail", "error": str(e)}), 500

    else:
        # Not this host → queue; remote agent can pick it up
        with connect_rw() as con:
            execute(con, """
                INSERT INTO recovery_logs("timestamp", hostname, os_platform, service_name, result, error_message)
                VALUES (CURRENT_TIMESTAMP, %s, %s, %s, 'queued', 'manual restart request')
            """, (host, osplat, service))
        return jsonify({"ok": True, "queued_for": host, "result": "queued"}), 202










































# # api/services.py
# import json
# import os
# import socket
# import subprocess
#
# from flask import request, jsonify, Response, render_template, abort
# from . import api_bp
# from ..views import ui_bp
# from ..read_service import latest_services, services_count
# import csv
# from io import StringIO
# from urllib.parse import quote
# import sqlite3, urllib.parse, time
# from db.core import resolve_db_path
# from scripts.recovery.service.service_recovery import restart_service_linux, restart_service_windows
#
# API_KEY = os.getenv("SMARTMON_API_KEY")  # RBAC: set as required
#
# APPROVED_PATH = os.getenv("SMARTMON_APPROVED_JSON", "config/approved_services.json")
# COOLDOWN_MIN = int(os.getenv("SMARTMON_RESTART_COOLDOWN_MIN", "10"))
# BACKOFF_FAILS = int(os.getenv("SMARTMON_RESTART_BACKOFF_FAILS", "3"))
# BACKOFF_WINDOW_MIN = int(os.getenv("SMARTMON_RESTART_BACKOFF_WINDOW_MIN", "30"))
#
# THIS_HOST = socket.gethostname()
#
#
# @api_bp.get("/services")
# def api_services():
#     host   = request.args.get("host") or None
#     status = request.args.get("status") or None
#     since  = int(request.args.get("since_minutes") or 1440)
#     limit  = max(1, min(int(request.args.get("limit") or 200), 1000))
#     offset = max(0, int(request.args.get("offset") or 0))
#
#     items = latest_services(host=host, status=status, since_minutes=since, limit=limit, offset=offset)
#     total = services_count(host=host, status=status, since_minutes=since)
#     return jsonify({"total": total, "items": items, "limit": limit, "offset": offset})
#
#
# @api_bp.get("/services.csv")
# def api_services_csv():
#     host   = request.args.get("host") or None
#     status = request.args.get("status") or None
#     since  = int(request.args.get("since_minutes") or 1440)
#
#     rows = latest_services(host=host, status=status, since_minutes=since, limit=20000, offset=0)
#
#     buf = StringIO()
#     fieldnames = [
#         "host","service_name","os_platform","status","sub_state","unit_file_state",
#         "recoverable","updated","last_recovery_result","last_recovery_at","recent_failures"
#     ]
#     w = csv.DictWriter(buf, fieldnames=fieldnames)
#     w.writeheader()
#     for r in rows:
#         w.writerow({k: r.get(k, "") for k in fieldnames})
#
#     data = buf.getvalue().encode("utf-8-sig")
#     filename = f"services_{host or 'all'}_{since}m.csv"
#     headers = {
#         "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
#         "Content-Type": "text/csv; charset=utf-8",
#     }
#     return Response(data, headers=headers)
#
#
#
# def _q(sql, params=()):
#     DB_PATH = resolve_db_path()
#     con = sqlite3.connect(DB_PATH)
#     con.row_factory = sqlite3.Row
#     cur = con.execute(sql, params)
#     rows = cur.fetchall()
#     con.close()
#     return rows
#
# @ui_bp.get("/services/<host>/<path:service>")
# def service_detail(host, service):
#     import urllib.parse, time
#     service = urllib.parse.unquote(service)
#
#     # window clamp
#     minutes = int(request.args.get("minutes", 1440))
#     minutes = max(5, min(minutes, 10080))
#     since = int(time.time()) - minutes * 60
#
#     # latest row (header)
#     latest = _q("""
#         SELECT *
#         FROM service_status
#         WHERE hostname=? AND service_name=?
#         ORDER BY ts_epoch DESC
#         LIMIT 1
#     """, (host, service))
#     if not latest:
#         abort(404, description="No records for this host/service")
#
#     # history for metrics (ASC, includes ts_epoch)
#     history_asc = _q("""
#         SELECT ts_epoch, timestamp, raw_status, normalized_status, sub_state, unit_file_state, recoverable
#         FROM service_status
#         WHERE hostname=? AND service_name=? AND ts_epoch >= ?
#         ORDER BY ts_epoch ASC
#         LIMIT 2000
#     """, (host, service, since))
#
#     # compute uptime % and last-change from ASC series
#     def _compute_uptime_and_last_change(rows, window_start, window_end):
#         if not rows:
#             return 0.0, None
#         pts = [(window_start, rows[0]["normalized_status"])]
#         pts += [(int(r["ts_epoch"]), r["normalized_status"]) for r in rows]
#         pts.append((window_end, rows[-1]["normalized_status"]))
#         up = 0
#         for (t1, s1), (t2, _s2) in zip(pts, pts[1:]):
#             dur = max(0, t2 - t1)
#             if s1 == "active":
#                 up += dur
#         uptime_pct = (up / max(1, (window_end - window_start))) * 100.0
#
#         last_change = None
#         last_state = rows[-1]["normalized_status"]
#         for r in reversed(rows[:-1]):
#             if r["normalized_status"] != last_state:
#                 last_change = r["timestamp"]
#                 break
#         return round(uptime_pct, 2), last_change
#
#     now = int(time.time())
#     uptime_pct, last_change = _compute_uptime_and_last_change(history_asc, since, now)
#
#     # attempts (optional)
#     attempts = _q("""
#         SELECT timestamp, result, COALESCE(error_message,'') AS error_message
#         FROM recovery_logs
#         WHERE hostname=? AND service_name=?
#         ORDER BY timestamp DESC
#         LIMIT 100
#     """, (host, service))
#
#     # for your table, you probably want newest first:
#     history_desc = list(reversed(history_asc))
#
#     return render_template(
#         "service_details.html",          # use your actual filename
#         host=host, service=service,
#         latest=latest[0],
#         history=history_desc,            # table uses DESC
#         attempts=attempts,
#         minutes=minutes,
#         uptime_pct=uptime_pct,
#         last_change=last_change
#     )
#
#
# # @ui_bp.get("/services/<host>/<path:service>")
# # def service_detail(host, service):
# #     service = urllib.parse.unquote(service)
# #     minutes = int(request.args.get("minutes", 1440))
# #     minutes = max(5, min(minutes, 10080))
# #     since = int(time.time()) - minutes * 60
# #
# #     latest = _q("""
# #         SELECT *
# #         FROM service_status
# #         WHERE hostname=? AND service_name=?
# #         ORDER BY ts_epoch DESC
# #         LIMIT 1
# #     """, (host, service))
# #     if not latest:
# #         abort(404, description="No records for this host/service")
# #
# #     history = _q("""
# #         SELECT timestamp, raw_status, normalized_status, sub_state, unit_file_state, recoverable
# #         FROM service_status
# #         WHERE hostname=? AND service_name=? AND ts_epoch >= ?
# #         ORDER BY ts_epoch DESC
# #         LIMIT 1000
# #     """, (host, service, since))
# #
# #     attempts = _q("""
# #         SELECT timestamp, result, COALESCE(error_message,'') AS error_message
# #         FROM recovery_logs
# #         WHERE hostname=? AND service_name=?
# #         ORDER BY timestamp DESC
# #         LIMIT 100
# #     """, (host, service))
# #
# #     return render_template(
# #         "service_details.html",
# #         host=host, service=service,
# #         latest=latest[0], history=history, attempts=attempts, minutes=minutes
# #     )
#
#
# def _db():
#     DB_PATH = resolve_db_path()
#     con = sqlite3.connect(DB_PATH)
#     con.row_factory = sqlite3.Row
#     return con
#
# def _require_api_key():
#     if not API_KEY:
#         print(f"[ERROR] no RBAC configured ->> allow (dev)")
#         return
#     key = request.headers.get("X-API-Key")
#     if key != API_KEY:
#         abort(401, description="Missing/invalid API key")
#
# def _is_allowed(host, service):
#     try:
#         with open(APPROVED_PATH, "r", encoding="utf-8") as f:
#             cfg = json.load(f)
#     except Exception as e:
#         print(f"[ERROR] not allowed as {e}")
#         return False
#     allow = cfg.get("allow", [])
#     for item in allow:
#         h = item.get("host", "*")
#         s = item.get("service", "*")
#         if (h in ("*", host)) and (s in ("*", service)):
#             return True
#     return False
#
# # ---------- History (JSON) ----------
# @api_bp.get("/services/<host>/<path:service>/history")
# def api_service_history(host, service):
#     since = int(request.args.get("since_minutes") or 1440)
#     since = max(5, min(since, 10080))  # 5 min .. 7 days
#     t0 = int(time.time()) - since * 60
#
#     con = _db()
#     rows = con.execute("""
#         SELECT ts_epoch, timestamp, raw_status, normalized_status, sub_state, unit_file_state, recoverable
#         FROM service_status
#         WHERE hostname=? AND service_name=? AND ts_epoch >= ?
#         ORDER BY ts_epoch ASC
#         LIMIT 2000
#     """, (host, service, t0)).fetchall()
#     con.close()
#     return jsonify([dict(r) for r in rows])
#
# # ---------- History (CSV) ----------
# @api_bp.get("/services/<host>/<path:service>/export.csv")
# def api_service_history_csv(host, service):
#     since = int(request.args.get("since_minutes") or 1440)
#     since = max(5, min(since, 10080))
#     t0 = int(time.time()) - since * 60
#
#     con = _db()
#     rows = con.execute("""
#         SELECT ts_epoch, timestamp, raw_status, normalized_status, sub_state, unit_file_state, recoverable
#         FROM service_status
#         WHERE hostname=? AND service_name=? AND ts_epoch >= ?
#         ORDER BY ts_epoch ASC
#         LIMIT 2000
#     """, (host, service, t0)).fetchall()
#     con.close()
#
#     buf = StringIO()
#     cols = ["ts_epoch","timestamp","raw_status","normalized_status","sub_state","unit_file_state","recoverable"]
#     w = csv.DictWriter(buf, fieldnames=cols); w.writeheader()
#     for r in rows: w.writerow({k: r[k] for k in cols})
#     data = buf.getvalue().encode("utf-8-sig")
#     fn = f"{host}_{service.replace('/','-')}_{since}m.csv"
#     headers = {
#         "Content-Disposition": f"attachment; filename*=UTF-8''{quote(fn)}",
#         "Content-Type": "text/csv; charset=utf-8",
#     }
#     return Response(data, headers=headers)
#
# # ---------- Safe Restart ----------
# @api_bp.post("/services/restart")
# def api_service_restart():
#     _require_api_key()
#
#     payload = request.get_json(silent=True) or {}
#     host = payload.get("host")
#     service = payload.get("service")
#     if not host or not service:
#         return jsonify({"ok": False, "error": "host and service required"}), 400
#     if not _is_allowed(host, service):
#         return jsonify({"ok": False, "error": "not in approved_services.json"}), 403
#
#     con = _db()
#
#     latest = con.execute("""
#         SELECT recoverable, os_platform
#         FROM service_status
#         WHERE hostname=? AND service_name=?
#         ORDER BY ts_epoch DESC
#         LIMIT 1
#     """, (host, service)).fetchone()
#     if not latest:
#         con.close()
#         return jsonify({"ok": False, "error": "no snapshot for host/service"}), 404
#
#     recoverable = int(latest["recoverable"])
#     osplat = (latest["os_platform"] or "").lower()
#     if recoverable != 1:
#         con.close()
#         return jsonify({"ok": False, "error": "service not recoverable"}), 409
#
#     # cooldown / backoff identical to what you already have (optionally ignore queued rows in cooldown during dev)
#     now = int(time.time())
#     cooldown_cut = now - COOLDOWN_MIN * 60
#     last_ts = con.execute("""
#         SELECT strftime('%s', MAX(timestamp)) AS t
#         FROM recovery_logs
#         WHERE hostname=? AND service_name=? AND result!='queued'
#     """, (host, service)).fetchone()
#     if last_ts and last_ts["t"] and int(last_ts["t"]) > cooldown_cut:
#         con.close()
#         return jsonify({"ok": False, "error": f"cooldown {COOLDOWN_MIN}m active"}), 429
#
#     backoff_cut = now - BACKOFF_WINDOW_MIN * 60
#     nfail = con.execute("""
#         SELECT COUNT(*) AS n
#         FROM recovery_logs
#         WHERE hostname=? AND service_name=? AND result='fail'
#           AND strftime('%s', timestamp) >= ?
#     """, (host, service, backoff_cut)).fetchone()["n"]
#     if nfail >= BACKOFF_FAILS:
#         con.close()
#         return jsonify({"ok": False, "error": f"backoff: {nfail} fails in {BACKOFF_WINDOW_MIN}m"}), 429
#
#     # 3) DRY-RUN support (no systemctl, just log intent)
#     DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
#     # DRY-RUN
#     if DRY_RUN:
#         con.execute("""
#             INSERT INTO recovery_logs(timestamp, hostname, os_platform, service_name, result, error_message)
#             VALUES (CURRENT_TIMESTAMP, ?, ?, ?, 'queued', 'dry-run')
#         """, (host, osplat, service))
#         con.commit(); con.close()
#         return jsonify({"ok": True, "result": "queued", "dry_run": True}), 202
#
#     # Local or remote
#     if host == THIS_HOST:
#         # Choose helper by OS
#         try:
#             if "win" in osplat:
#                 ok, msg = restart_service_windows(service)
#             else:
#                 ok, msg = restart_service_linux(service)
#
#             if ok:
#                 con.execute("""
#                     INSERT INTO recovery_logs(timestamp, hostname, os_platform, service_name, result, error_message)
#                     VALUES (CURRENT_TIMESTAMP, ?, ?, ?, 'success', '')
#                 """, (host, osplat, service))
#                 con.commit(); con.close()
#                 return jsonify({"ok": True, "executed_on": THIS_HOST, "result": "success"})
#             else:
#                 con.execute("""
#                     INSERT INTO recovery_logs(timestamp, hostname, os_platform, service_name, result, error_message)
#                     VALUES (CURRENT_TIMESTAMP, ?, ?, ?, 'fail', ?)
#                 """, (host, osplat, service, (msg or "")[:500]))
#                 con.commit(); con.close()
#                 return jsonify({"ok": False, "executed_on": THIS_HOST, "result": "fail", "stderr": msg}), 500
#         except Exception as e:
#             con.execute("""
#                 INSERT INTO recovery_logs(timestamp, hostname, os_platform, service_name, result, error_message)
#                 VALUES (CURRENT_TIMESTAMP, ?, ?, ?, 'fail', ?)
#             """, (host, osplat, service, str(e)[:500]))
#             con.commit(); con.close()
#             return jsonify({"ok": False, "executed_on": THIS_HOST, "result": "fail", "error": str(e)}), 500
#     else:
#         # Not this host → queue for your agent
#         con.execute("""
#             INSERT INTO recovery_logs(timestamp, hostname, os_platform, service_name, result, error_message)
#             VALUES (CURRENT_TIMESTAMP, ?, ?, ?, 'queued', 'manual restart request')
#         """, (host, osplat, service))
#         con.commit(); con.close()
#         return jsonify({"ok": True, "queued_for": host, "result": "queued"}), 202
