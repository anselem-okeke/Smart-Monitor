from flask import render_template
from . import ui_bp

@ui_bp.get("/")
@ui_bp.get("/overview")
def overview():
    return render_template("overview.html")