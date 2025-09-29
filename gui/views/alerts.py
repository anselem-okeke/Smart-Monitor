from flask import render_template
from . import ui_bp

@ui_bp.get("/alerts")
def alerts_view():
    return render_template("alerts.html")