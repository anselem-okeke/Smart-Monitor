from flask import render_template, request, jsonify
from . import ui_bp
from .. import read_service as rs

@ui_bp.get("/hosts")
def hosts_list():
    hosts = rs.list_hosts()
    return render_template("hosts_list.html", hosts=hosts)

@ui_bp.get("/hosts/<host>")
def host_detail(host):
    minutes = int(request.args.get("minutes", 60))
    return render_template("host_detail.html", host=host, minutes=minutes)