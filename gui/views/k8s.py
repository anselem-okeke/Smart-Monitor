from flask import render_template
from . import ui_bp

@ui_bp.get("/k8s")
def k8s_view():
    return render_template("k8s.html")
