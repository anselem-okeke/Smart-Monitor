from flask import render_template
from . import ui_bp

@ui_bp.get("/network")
def network_view():
    return render_template("network.html")