# ui/hosts.py
from flask import render_template, request, jsonify, make_response, abort
from . import ui_bp
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

@ui_bp.get("/hosts")
def hosts_list():
    hosts = rs.list_hosts()
    resp = make_response(render_template("hosts_list.html", hosts=hosts))
    resp.headers["Cache-Control"] = "no-store"
    return resp

@ui_bp.get("/hosts/<host>")
def host_detail(host):
    host = (host or "").strip()
    if not host or len(host) > 255:
        abort(400, description="invalid host")
    minutes = _as_int(request.args.get("minutes"), 60, lo=5, hi=10080)
    resp = make_response(render_template("host_detail.html", host=host, minutes=minutes))
    resp.headers["Cache-Control"] = "no-store"
    return resp















# from flask import render_template, request, jsonify
# from . import ui_bp
# from .. import read_service as rs
#
# @ui_bp.get("/hosts")
# def hosts_list():
#     hosts = rs.list_hosts()
#     return render_template("hosts_list.html", hosts=hosts)
#
# @ui_bp.get("/hosts/<host>")
# def host_detail(host):
#     minutes = int(request.args.get("minutes", 60))
#     return render_template("host_detail.html", host=host, minutes=minutes)