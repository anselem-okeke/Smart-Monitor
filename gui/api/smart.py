# api/smart.py
from flask import request, jsonify
from . import api_bp
from .. import read_service as rs

@api_bp.get("/smart")
def api_smart():
    host = request.args.get("host")
    if host:
        host = host.strip()
        # lightweight guardrail; avoid absurdly long inputs
        if len(host) > 255:
            return jsonify({"error": "host too long"}), 400
    items = rs.smart_latest(host or None)
    return jsonify(items)









# from flask import request, jsonify
# from . import api_bp
# from .. import read_service as rs
#
# @api_bp.get("/smart")
# def api_smart():
#     host = request.args.get("host") or None
#     items = rs.smart_latest(host)
#     return jsonify(items)
