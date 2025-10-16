# api/hosts.py
from flask import request, jsonify
from . import api_bp
from .. import read_service as rs

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

@api_bp.get("/hosts")
def api_hosts():
    """
    Returns a list of hosts with their last-seen timestamp and a tiny metrics snapshot.
    Shape: [{ hostname, last_ts, last: {timestamp, cpu_usage, memory_usage, ...} }, ...]
    """
    rows = rs.list_hosts()
    return jsonify(rows)

@api_bp.get("/hosts/<host>/metrics")
def api_host_metrics(host):
    """
    Time-series for charts. Query param:
      - minutes (int, default 60, 5..10080)
    """
    minutes = _as_int(request.args.get("minutes"), 60, lo=5, hi=10080)
    rows = rs.host_metrics(host, minutes=minutes)
    return jsonify(rows)

@api_bp.get("/hosts/<host>/services")
def api_host_services(host):
    """
    Latest status per service for a host.
    """
    rows = rs.host_services(host)
    return jsonify(rows)




















# from flask import request, jsonify
# from . import api_bp
# from .. import read_service as rs
#
# @api_bp.get("/hosts")
# def api_hosts():
#     return jsonify(rs.list_hosts())
#
# @api_bp.get("/hosts/<host>/metrics")
# def api_host_metrics(host):
#     minutes = int(request.args.get("minutes", 60))
#     return jsonify(rs.host_metrics(host, minutes=minutes))
#
# @api_bp.get("/hosts/<host>/services")
# def api_host_services(host):
#     return jsonify(rs.host_services(host))
