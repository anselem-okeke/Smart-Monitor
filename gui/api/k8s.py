# api/k8s.py
from flask import request, jsonify
from . import api_bp
from .. import read_service as rs

from datetime import datetime, date, timezone

MAX_LIMIT_JSON = 2000

def _as_int(v, default, lo=None, hi=None):
    try:
        n = int(v)
    except (TypeError, ValueError):
        n = default
    if lo is not None: n = max(lo, n)
    if hi is not None: n = min(hi, n)
    return n

def _as_bool(v, default=False):
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")

def _jsonable(obj):
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(v, datetime):
                v = (v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc))
                out[k] = v.isoformat().replace("+00:00", "Z")
            elif isinstance(v, date):
                out[k] = v.isoformat()
            else:
                out[k] = v
        return out
    return obj

@api_bp.get("/k8s/pods")
def api_k8s_pods():
    cluster = request.args.get("cluster") or None
    namespace = request.args.get("namespace") or None
    problem_type = request.args.get("problem_type") or None
    only_unhealthy = _as_bool(request.args.get("only_unhealthy"), default=False)

    since = _as_int(request.args.get("since_minutes"), 10, lo=1, hi=7*24*60)
    limit = _as_int(request.args.get("limit"), 200, lo=1, hi=MAX_LIMIT_JSON)
    offset = _as_int(request.args.get("offset"), 0, lo=0)

    items = rs.k8s_pods_latest(
        cluster=cluster,
        namespace=namespace,
        problem_type=problem_type,
        only_unhealthy=only_unhealthy,
        since_minutes=since,
        limit=limit,
        offset=offset,
    )
    total = rs.count_k8s_pods_latest(
        cluster=cluster,
        namespace=namespace,
        problem_type=problem_type,
        only_unhealthy=only_unhealthy,
        since_minutes=since,
    )

    return jsonify({
        "items": _jsonable(items),
        "total": total,
        "limit": limit,
        "offset": offset,
    })

@api_bp.get("/k8s/clusters")
def api_k8s_clusters():
    cluster = request.args.get("cluster") or None
    since = _as_int(request.args.get("since_minutes"), 60, lo=1, hi=7*24*60)
    limit = _as_int(request.args.get("limit"), 50, lo=1, hi=MAX_LIMIT_JSON)
    offset = _as_int(request.args.get("offset"), 0, lo=0)

    items = rs.k8s_clusters_latest(
        cluster=cluster,
        since_minutes=since,
        limit=limit,
        offset=offset,
    )
    total = rs.count_k8s_clusters_latest(
        cluster=cluster,
        since_minutes=since,
    )

    return jsonify({
        "items": _jsonable(items),
        "total": total,
        "limit": limit,
        "offset": offset,
    })
