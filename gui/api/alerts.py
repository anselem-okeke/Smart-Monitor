# api/alerts.py
from flask import request, jsonify, Response
from . import api_bp
from .. import read_service as rs
import csv
from io import StringIO
from urllib.parse import quote

# NEW: for datetime normalization
from datetime import datetime, date, timezone

MAX_LIMIT_JSON = 1000
MAX_LIMIT_CSV  = 50000

def _as_int(v, default, lo=None, hi=None):
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n

# NEW: make rows JSON-safe (datetimes -> ISO-8601 Z)
def _jsonable(obj):
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, datetime):
                # normalize to UTC ISO with Z
                v = (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc))
                out[k] = v.isoformat().replace("+00:00", "Z")
            elif isinstance(v, date):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out
    return obj

@api_bp.get("/alerts")
def api_alerts():
    severity = request.args.get("severity") or None
    host     = request.args.get("host") or None
    since    = request.args.get("since_minutes") or None  # let rs layer handle None
    limit    = _as_int(request.args.get("limit"), 50, lo=1, hi=MAX_LIMIT_JSON)
    offset   = _as_int(request.args.get("offset"), 0, lo=0)

    items = rs.get_alerts(
        seveiry=severity,       # (sic) matches read_service signature
        host=host,
        since_minutes=since,
        limit=limit,
        offset=offset,
    )
    total = rs.count_alerts(
        severity=severity,
        host=host,
        since_minutes=since,
    )

    # NEW: normalize before jsonify
    items = _jsonable(items)

    return jsonify({"items": items, "total": total, "limit": limit, "offset": offset})

@api_bp.get("/alerts.csv")
def api_alerts_csv():
    severity = request.args.get("severity") or None
    host     = request.args.get("host") or None
    since    = request.args.get("since_minutes") or None
    limit    = _as_int(request.args.get("limit"), 1000, lo=1, hi=MAX_LIMIT_CSV)
    offset   = _as_int(request.args.get("offset"), 0, lo=0)

    rows = rs.get_alerts(
        seveiry=severity,
        host=host,
        since_minutes=since,
        limit=limit,
        offset=offset,
    )

    # Build CSV in memory
    buf = StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["id", "timestamp", "hostname", "severity", "source", "message"])
    for r in rows:
        # ensure timestamp becomes text for CSV too
        ts = r.get("timestamp", "")
        if isinstance(ts, datetime):
            ts = (ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc))
            ts = ts.isoformat().replace("+00:00", "Z")
        writer.writerow([
            r.get("id", ""),
            ts,
            r.get("hostname", ""),
            r.get("severity", ""),
            r.get("source", ""),
            r.get("message", ""),
        ])

    data = buf.getvalue().encode("utf-8-sig")  # BOM for Excel-friendliness
    fname = "alerts.csv"
    headers = {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}",
        "Cache-Control": "no-store",
    }
    return Response(data, headers=headers)





























# # api/alerts.py
# from flask import request, jsonify, Response
# from . import api_bp
# from .. import read_service as rs
# import csv
# from io import StringIO
# from urllib.parse import quote
#
# MAX_LIMIT_JSON = 1000
# MAX_LIMIT_CSV  = 50000
#
# def _as_int(v, default, lo=None, hi=None):
#     try:
#         n = int(v)
#     except (TypeError, ValueError):
#         n = default
#     if lo is not None:
#         n = max(lo, n)
#     if hi is not None:
#         n = min(hi, n)
#     return n
#
# @api_bp.get("/alerts")
# def api_alerts():
#     severity = request.args.get("severity") or None
#     host     = request.args.get("host") or None
#     since    = request.args.get("since_minutes") or None  # let rs layer handle None
#     limit    = _as_int(request.args.get("limit"), 50, lo=1, hi=MAX_LIMIT_JSON)
#     offset   = _as_int(request.args.get("offset"), 0, lo=0)
#
#     items = rs.get_alerts(
#         seveiry=severity,       # read_service.get_alerts() expects 'seveiry' (sic)
#         host=host,
#         since_minutes=since,
#         limit=limit,
#         offset=offset,
#     )
#     total = rs.count_alerts(
#         severity=severity,
#         host=host,
#         since_minutes=since,
#     )
#
#     return jsonify({"items": items, "total": total, "limit": limit, "offset": offset})
#
# @api_bp.get("/alerts.csv")
# def api_alerts_csv():
#     severity = request.args.get("severity") or None
#     host     = request.args.get("host") or None
#     since    = request.args.get("since_minutes") or None
#     limit    = _as_int(request.args.get("limit"), 1000, lo=1, hi=MAX_LIMIT_CSV)
#     offset   = _as_int(request.args.get("offset"), 0, lo=0)
#
#     rows = rs.get_alerts(
#         seveiry=severity,
#         host=host,
#         since_minutes=since,
#         limit=limit,
#         offset=offset,
#     )
#
#     # Build CSV in memory
#     buf = StringIO()
#     writer = csv.writer(buf, lineterminator="\n")
#     writer.writerow(["id", "timestamp", "hostname", "severity", "source", "message"])
#     for r in rows:
#         writer.writerow([
#             r.get("id", ""),
#             r.get("timestamp", ""),
#             r.get("hostname", ""),
#             r.get("severity", ""),
#             r.get("source", ""),
#             r.get("message", ""),
#         ])
#
#     data = buf.getvalue().encode("utf-8-sig")  # BOM for Excel-friendliness
#     fname = "alerts.csv"
#     headers = {
#         "Content-Type": "text/csv; charset=utf-8",
#         "Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}",
#         "Cache-Control": "no-store",
#     }
#     return Response(data, headers=headers)

































# from flask import request, jsonify, Response
# from . import api_bp
# from .. import read_service as rs
# import csv
# from io import StringIO
# from urllib.parse import quote
#
# @api_bp.get("/alerts")
# def api_alerts():
#     severity = request.args.get("severity") or None
#     host = request.args.get("host") or None
#     since = request.args.get("since_minutes") or None
#     limit = int(request.args.get("limit", 50))
#     offset = int(request.args.get("offset", 0))
#
#     items = rs.get_alerts(
#         seveiry=severity,
#         host=host,
#         since_minutes=since,
#         limit=limit,
#         offset=offset
#     )
#
#     total = rs.count_alerts(
#         severity=severity,
#         host=host,
#         since_minutes=since
#     )
#
#     return jsonify({
#         "items": items,
#         "total": total,
#         "limit": limit,
#         "offset": offset
#     })
#
# @api_bp.get("/alerts.csv")
# def api_alerts_csv():
#     severity = request.args.get("severity") or None
#     host = request.args.get("host") or None
#     since = request.args.get("since_minutes") or None
#     limit = int(request.args.get("limit", 1000))  # generous for export
#     offset = int(request.args.get("offset", 0))
#
#     rows = rs.get_alerts(
#         seveiry=severity,
#         host=host,
#         since_minutes=since,
#         limit=limit,
#         offset=offset
#     )
#
#     buf = StringIO()
#     w = csv.writer(buf)
#     w.writerow(["id", "timestamp", "hostname", "severity", "source", "message"])
#     for r in rows:
#         w.writerow([r["id"], r["timestamp"], r["hostname"], r["severity"], r["source"], r["message"]])
#
#     csv_bytes = buf.getvalue()
#     fname = "alerts.csv"
#     headers = {
#         "Content-Type": "text/csv; charset=utf-8",
#         "Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"
#     }
#     return Response(csv_bytes, headers=headers)
