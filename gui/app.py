#------------------------------------------
"""Author: Anselem Okeke
    MIT License
    Copyright (c) 2025 Anselem Okeke
    See LICENSE file in the project root for full license text.
"""
#------------------------------------------

import os, json, secrets
from pathlib import Path
from datetime import datetime
from flask import Flask
from .api import api_bp
from .views import ui_bp
from . import config

def _resolve_meta_from_env_and_json() -> dict:
    # 1) start from ENV (fallback to config defaults)
    meta = {
        "app_name":        os.getenv("SMARTMON_APP_NAME", config.APP_NAME),
        "app_version":     os.getenv("SMARTMON_APP_VERSION", config.APP_VERSION),
        "powered_by":      os.getenv("SMARTMON_POWERED_BY", config.POWERED_BY),
        "copyright_owner": os.getenv("SMARTMON_COPYRIGHT_OWNER", config.COPYRIGHT_OWNER),
        "copyright_year":  os.getenv("SMARTMON_COPYRIGHT_YEAR", config.COPYRIGHT_YEAR or str(datetime.utcnow().year)),
        "project_url":     os.getenv("SMARTMON_PROJECT_URL", config.PROJECT_URL),
        "owner_url":       os.getenv("SMARTMON_OWNER_URL", config.OWNER_URL),
        "flask_url":       os.getenv("FLASK_URL", config.FLASK_URL),
        "postgres_url":    os.getenv("POSTGRES_URL", "https://www.postgresql.org/docs/"),
        "sqlite_url":      os.getenv("SQLITE_URL",   "https://www.sqlite.org"),
    }

    # 2) merge JSON for any missing values (does not override explicit ENV)
    json_path = Path("/app/config/app_meta.json")
    if json_path.is_file():
        try:
            with json_path.open() as f:
                data = json.load(f) or {}

            # flat keys
            for k in ("app_name","app_version","powered_by","copyright_owner",
                      "copyright_year","project_url","owner_url"):
                env_key = f"SMARTMON_{k.upper()}"
                if not os.getenv(env_key) and data.get(k):
                    meta[k] = data[k]

            # docs: flask / postgres / sqlite (all optional)
            docs = data.get("docs") or {}
            if docs.get("flask") and not os.getenv("FLASK_URL"):
                meta["flask_url"] = docs["flask"]
            if docs.get("postgres") and not os.getenv("POSTGRES_URL"):
                meta["postgres_url"] = docs["postgres"]
            if docs.get("sqlite") and not os.getenv("SQLITE_URL"):
                meta["sqlite_url"] = docs["sqlite"]

        except Exception as e:
            print(f"[WARN] app_meta.json not applied: {e}")

    return meta

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SMARTMON_SECRET_KEY') or secrets.token_hex(32)

    APP_META = _resolve_meta_from_env_and_json()
    app.config["APP_META"] = APP_META

    @app.context_processor # type: ignore[attr-defined]
    def inject_footer_vars():
        return dict(
            app_name=APP_META["app_name"],
            app_version=APP_META["app_version"],
            powered_by=APP_META["powered_by"],
            copyright_owner=APP_META["copyright_owner"],
            copyright_year=APP_META["copyright_year"],
            project_url=APP_META["project_url"],
            owner_url=APP_META["owner_url"],
            flask_url=APP_META["flask_url"],
            postgres_url=APP_META["postgres_url"],
            sqlite_url=APP_META["sqlite_url"],
        )

    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(ui_bp)
    return app

if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5000, debug=True)





























# import os, subprocess, secrets
# from datetime import datetime
# from flask import Flask
# from .api import api_bp
# from .views import ui_bp
# from dotenv import load_dotenv
# from gui import config
#
# # # Load /etc/smart-monitor/env if present; don't override real env
# # load_dotenv("/etc/smart-monitor/env", override=False)
# # # (optional) also load a local .env during dev
# # load_dotenv(".env", override=False)
#
#
# def create_app():
#     app = Flask(__name__)
#
#     app.config['SECRET_KEY'] = os.getenv('SMARTMON_SECRET_KEY') or secrets.token_hex(32)
#
#     @app.context_processor
#     def inject_footer_vars():
#         return dict(
#             app_name=config.APP_NAME,
#             app_version=config.APP_VERSION,
#             powered_by=config.POWERED_BY,
#             copyright_owner=config.COPYRIGHT_OWNER,
#             copyright_year=config.COPYRIGHT_YEAR,
#             project_url=config.PROJECT_URL,
#             owner_url=config.OWNER_URL,
#             flask_url=config.FLASK_URL,
#             sqlite_url=config.SQLITE_URL,
#         )
#
#     app.register_blueprint(api_bp, url_prefix="/api")
#     app.register_blueprint(ui_bp)
#     return app
#
#
# if __name__ == "__main__":
#     create_app().run(host="0.0.0.0", port=5000, debug=True)
