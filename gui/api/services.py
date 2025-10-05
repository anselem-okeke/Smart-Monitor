# api/services.py
from flask import request, jsonify, Response
from . import api_bp
from ..read_service import latest_services, services_count
import csv
from io import StringIO
from urllib.parse import quote

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
    status = request.args.get("status") or None
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




























# from flask import request, jsonify, Response
# from . import api_bp
# from .. import read_service as rs
# import csv
# from io import StringIO
# from urllib.parse import quote
#
# @api_bp.get("/services")
# def api_services():
#     host   = request.args.get("host") or None
#     status = request.args.get("status") or None     # expects normalized_status values
#     since  = int(request.args.get("since_minutes") or 1440)
#     limit  = max(1, min(int(request.args.get("limit") or 200), 1000))
#     offset = max(0, int(request.args.get("offset") or 0))
#
#     rows = rs.latest_services(host=host, status=status, since_minutes=since, limit=limit, offset=offset)
#     total = rs.services_count(host=host, status=status, since_minutes=since)
#     return jsonify({"total": total, "items": rows, "limit": limit, "offset": offset})
#
# @api_bp.get("/services.csv")
# def api_services_csv():
#     host   = request.args.get("host") or None
#     status = request.args.get("status") or None
#     since  = int(request.args.get("since_minutes") or 1440)
#     rows   = rs.latest_services(host=host, status=status, since_minutes=since, limit=20000, offset=0)
#
#     buf = StringIO()
#     w = csv.DictWriter(buf, fieldnames=[
#         "host","os_platform","service_name","status","sub_state","unit_file_state",
#         "recoverable","updated","last_recovery_result","last_recovery_at","recent_failures"
#     ])
#     w.writeheader()
#     for r in rows:
#         w.writerow(r)
#
#     data = buf.getvalue().encode("utf-8-sig")
#     filename = f"services_{host or 'all'}_{since}m.csv"
#     headers = {
#         "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
#         "Content-Type": "text/csv; charset=utf-8"
#     }
#     return Response(data, headers=headers)








# from flask import request, jsonify, Response
# from . import api_bp
# from .. import read_service as rs
# import csv
# from io import StringIO
# from urllib.parse import quote
#
# @api_bp.get("/services")
# def api_services():
#     host   = request.args.get("host") or None
#     status = request.args.get("status") or None     # expects normalized_status values
#     since  = int(request.args.get("since_minutes") or 1440)
#     limit  = max(1, min(int(request.args.get("limit") or 200), 1000))
#     offset = max(0, int(request.args.get("offset") or 0))
#
#     rows = rs.latest_services(host=host, status=status, since_minutes=since, limit=limit, offset=offset)
#     total = rs.services_count(host=host, status=status, since_minutes=since)
#     return jsonify({"total": total, "items": rows, "limit": limit, "offset": offset})
#
# @api_bp.get("/services.csv")
# def api_services_csv():
#     host   = request.args.get("host") or None
#     status = request.args.get("status") or None
#     since  = int(request.args.get("since_minutes") or 1440)
#     rows   = rs.latest_services(host=host, status=status, since_minutes=since, limit=20000, offset=0)
#
#     buf = StringIO()
#     w = csv.DictWriter(buf, fieldnames=[
#         "host","os_platform","service_name","status","sub_state","unit_file_state",
#         "recoverable","updated","last_recovery_result","last_recovery_at","recent_failures"
#     ])
#     w.writeheader()
#     for r in rows:
#         w.writerow(r)
#
#     data = buf.getvalue().encode("utf-8-sig")
#     filename = f"services_{host or 'all'}_{since}m.csv"
#     headers = {
#         "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
#         "Content-Type": "text/csv; charset=utf-8"
#     }
#     return Response(data, headers=headers)