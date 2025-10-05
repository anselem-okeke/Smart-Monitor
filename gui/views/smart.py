from flask import render_template, request
from . import ui_bp
from .. import read_service as rs

@ui_bp.get("/smart")
def smart_view():
    host = request.args.get("host") or ""
    hosts = rs.hosts_for_smart()
    return render_template("smart.html", hosts=hosts, host=host)

