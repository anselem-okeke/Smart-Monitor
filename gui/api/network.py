# api/network.py
from flask import request, jsonify
from . import api_bp
from .. import read_service as rs

MAX_LIMIT = 5000

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

@api_bp.get("/network/events")
def api_network_events():
    """
    Query params:
      - host:    optional
      - target:  optional (exact, case-insensitive)
      - method:  optional ('ping' | 'traceroute' | 'nslookup'), case-insensitive
      - since_minutes: optional int (defaults handled inside rs.network_events)
      - limit:   int, 1..MAX_LIMIT (default 200)
      - offset:  int, >=0
    """
    items = rs.network_events(
        host=request.args.get("host") or None,
        target=request.args.get("target") or None,
        since_minutes=request.args.get("since_minutes") or None,
        limit=_as_int(request.args.get("limit"), 200, lo=1, hi=MAX_LIMIT),
        offset=_as_int(request.args.get("offset"), 0, lo=0),
        method=(request.args.get("method") or None),
    )
    return jsonify(items)

@api_bp.get("/network/targets")
def api_network_targets():
    """
    Returns the latest status per (hostname,target) seen within the window.
    Query params:
      - since_minutes: int, 5..10080 (default 1440)
    """
    since = _as_int(request.args.get("since_minutes"), 1440, lo=5, hi=10080)
    items = rs.network_pairs(since)
    return jsonify(items)

@api_bp.get("/network/series")
def api_network_series():
    """
    Time series latency for one target.
    Query params:
      - target: required
      - since_minutes: int, 5..10080 (default 60)
      - host: optional (filter by reporting host)
      - method: 'ping' | 'traceroute' | 'nslookup' (default 'ping')
    """
    target = request.args.get("target")
    if not target:
        return jsonify({"error": "missing target"}), 400

    since  = _as_int(request.args.get("since_minutes"), 60, lo=5, hi=10080)
    host   = request.args.get("host") or None
    method = request.args.get("method", "ping")

    rows = rs.network_latency_series(target, since, host, method)
    return jsonify(rows)

@api_bp.get("/network/latest")
def api_network_latest():
    """
    Latest traceroute and nslookup for a target (optionally per host).
    Query params:
      - target: required
      - host: optional
    """
    target = request.args.get("target")
    if not target:
        return jsonify({"error": "missing target"}), 400

    host = request.args.get("host") or None
    return jsonify({
        "traceroute": rs.latest_result_for(target, "traceroute", host),
        "nslookup":   rs.latest_result_for(target, "nslookup", host),
    })




































# from flask import request, jsonify
# from . import api_bp
# from .. import read_service as rs
#
# @api_bp.get("/network/events")
# def api_network_events():
#     items = rs.network_events(
#         host=request.args.get("host") or None,
#         target=request.args.get("target") or None,
#         since_minutes=request.args.get("since_minutes") or None,
#         limit=int(request.args.get("limit", 200)),
#         offset=int(request.args.get("offset", 0)),
#         method=request.args.get("method") or None
#     )
#     return jsonify(items)
#
# @api_bp.get("/network/targets")
# def api_network_targets():
#     since = int(request.args.get("since_minutes", 1440))
#     items = rs.network_pairs(since)
#     return jsonify(items)
#
# @api_bp.get("/network/series")
# def api_network_series():
#     target = request.args.get("target")
#     if not target:
#         return jsonify({"error": "missing target"}), 400
#     since  = int(request.args.get("since_minutes", 60))
#     host   = request.args.get("host") or None
#     method = request.args.get("method", "ping")
#     rows = rs.network_latency_series(target, since, host, method)
#     return jsonify(rows)
#
#
# @api_bp.get("/network/latest")
# def api_network_latest():
#     target = request.args.get("target")
#     if not target:
#         return jsonify({"error":"missing target"}), 400
#     host = request.args.get("host") or None
#     return jsonify({
#         "traceroute": rs.latest_result_for(target, "traceroute", host),
#         "nslookup": rs.latest_result_for(target, "nslookup", host)
#     })
