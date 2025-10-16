# api/summary.py
from flask import jsonify, Response
from . import api_bp
from .. import read_service as rs

@api_bp.get("/summary")
def api_summary():
    try:
        data = rs.get_summary()
        # Avoid stale dashboards behind proxies/CDNs
        resp = jsonify(data)
        resp.headers["Cache-Control"] = "no-store"
        return resp
    except Exception as e:
        # Keep it terse for clients; logs will have the stack
        return jsonify({"error": "summary_failed", "detail": str(e)[:200]}), 500









# from flask import jsonify
# from . import api_bp
# from .. import read_service as rs
#
# @api_bp.get("/summary")
# def api_summary():
#     return jsonify(rs.get_summary())
