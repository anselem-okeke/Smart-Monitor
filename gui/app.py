# import os
#
# from flask import Flask
# from .api import api_bp
# from .views import ui_bp
# from datetime import datetime
#
# def _git_sha():
#     try:
#         import subprocess
#         return subprocess.check_output(
#             ["git", "rev-parse", "--short", "HEAD"],
#             stderr=subprocess.DEVNULL,
#         ).decode().strip()
#     except Exception:
#         return None
#
# def create_app():
#     app = Flask(__name__)
#
#     # --- Footer/meta config ---
#     app.config["APP_NAME"] = os.getenv("SMARTMONITOR_APP_NAME", "Smart-Monitor")
#     app.config["APP_VERSION"] = os.getenv("SMARTMONITOR_VERSION", "0.1.0")
#     app.config["COPYRIGHT_OWNER"] = os.getenv("SMARTMONITOR_COPYRIGHT", "Your Company")
#
#     @app.context_processor
#     def inject_footer_meta():
#         return {
#             "app_name": app.config["APP_NAME"],
#             "app_version": app.config["APP_VERSION"],
#             "copyright_owner": app.config["COPYRIGHT_OWNER"],
#             "current_year": datetime.utcnow().year,
#             "git_sha": _git_sha(),
#         }
#
#     # --- Blueprints ---
#     app.register_blueprint(api_bp, url_prefix="/api")
#     app.register_blueprint(ui_bp)
#     return app
#
# if __name__ == "__main__":
#     create_app().run(host="0.0.0.0", port=5000, debug=True)


import os, subprocess, secrets
from datetime import datetime
from flask import Flask
from .api import api_bp
from .views import ui_bp
from dotenv import load_dotenv
from gui import config

# # Load /etc/smart-monitor/env if present; don't override real env
# load_dotenv("/etc/smart-monitor/env", override=False)
# # (optional) also load a local .env during dev
# load_dotenv(".env", override=False)


def _git_sha():
    sha = os.getenv("SMARTMONITOR_GIT_SHA")
    if sha:
        return sha[:7]
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return None

def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = os.getenv('SMARTMON_SECRET_KEY') or secrets.token_hex(32)

    @app.context_processor
    def inject_footer_vars():
        return dict(
            app_name=config.APP_NAME,
            app_version=config.APP_VERSION,
            powered_by=config.POWERED_BY,
            copyright_owner=config.COPYRIGHT_OWNER,
            copyright_year=config.COPYRIGHT_YEAR,
            project_url=config.PROJECT_URL,
            owner_url=config.OWNER_URL,
            flask_url=config.FLASK_URL,
            sqlite_url=config.SQLITE_URL,
        )

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(ui_bp)
    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000, debug=True)
