from flask import request, jsonify
from . import api_bp
from .. import read_service as rs

@api_bp.get("/hosts")
def api_hosts():
    return jsonify(rs.list_hosts())

@api_bp.get("/hosts/<host>/metrics")
def api_host_metrics(host):
    minutes = int(request.args.get("minutes", 60))
    return jsonify(rs.host_metrics(host, minutes=minutes))

@api_bp.get("/hosts/<host>/services")
def api_host_services(host):
    return jsonify(rs.host_services(host))
