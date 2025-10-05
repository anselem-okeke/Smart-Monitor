from flask import render_template
from . import ui_bp

@ui_bp.get("/services")
def services_view():
    # Pure template; page fetches via /api/services
    return render_template("services.html")
