from flask import request, jsonify, Response
from . import api_bp
from .. import read_service as rs
import csv
from io import StringIO
from urllib.parse import quote

@api_bp.get("/alerts")
def api_alerts():
    severity = request.args.get("severity") or None
    host = request.args.get("host") or None
    since = request.args.get("since_minutes") or None
    limit = int(request.args.get("limit", 50))
    offset = int(request.args.get("offset", 0))

    items = rs.get_alerts(
        seveiry=severity,
        host=host,
        since_minutes=since,
        limit=limit,
        offset=offset
    )

    total = rs.count_alerts(
        severity=severity,
        host=host,
        since_minutes=since
    )

    return jsonify({
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    })

@api_bp.get("/alerts.csv")
def api_alerts_csv():
    severity = request.args.get("severity") or None
    host = request.args.get("host") or None
    since = request.args.get("since_minutes") or None
    limit = int(request.args.get("limit", 1000))  # generous for export
    offset = int(request.args.get("offset", 0))

    rows = rs.get_alerts(
        seveiry=severity,
        host=host,
        since_minutes=since,
        limit=limit,
        offset=offset
    )

    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "timestamp", "hostname", "severity", "source", "message"])
    for r in rows:
        w.writerow([r["id"], r["timestamp"], r["hostname"], r["severity"], r["source"], r["message"]])

    csv_bytes = buf.getvalue()
    fname = "alerts.csv"
    headers = {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(fname)}"
    }
    return Response(csv_bytes, headers=headers)
