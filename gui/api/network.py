from flask import request, jsonify
from . import api_bp
from .. import read_service as rs

@api_bp.get("/network/events")
def api_network_events():
    items = rs.network_events(
        host=request.args.get("host") or None,
        target=request.args.get("target") or None,
        since_minutes=request.args.get("since_minutes") or None,
        limit=int(request.args.get("limit", 200)),
        offset=int(request.args.get("offset", 0)),
        method=request.args.get("method") or None
    )
    return jsonify(items)

@api_bp.get("/network/targets")
def api_network_targets():
    since = int(request.args.get("since_minutes", 1440))
    items = rs.network_pairs(since)
    return jsonify(items)

@api_bp.get("/network/series")
def api_network_series():
    target = request.args.get("target")
    if not target:
        return jsonify({"error": "missing target"}), 400
    since  = int(request.args.get("since_minutes", 60))
    host   = request.args.get("host") or None
    method = request.args.get("method", "ping")
    rows = rs.network_latency_series(target, since, host, method)
    return jsonify(rows)


@api_bp.get("/network/latest")
def api_network_latest():
    target = request.args.get("target")
    if not target:
        return jsonify({"error":"missing target"}), 400
    host = request.args.get("host") or None
    return jsonify({
        "traceroute": rs.latest_result_for(target, "traceroute", host),
        "nslookup": rs.latest_result_for(target, "nslookup", host)
    })
