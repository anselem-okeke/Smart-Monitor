from flask import request, jsonify
from . import api_bp
from .. import read_service as rs

@api_bp.get("/smart")
def api_smart():
    host = request.args.get("host") or None
    items = rs.smart_latest(host)
    return jsonify(items)
