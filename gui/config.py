from datetime import datetime
import os

APP_NAME        = os.getenv("SMARTMON_APP_NAME", "Smart Monitor Console")
APP_VERSION     = os.getenv("SMARTMON_APP_VERSION", "v0.1.0")
COPYRIGHT_OWNER = os.getenv("SMARTMON_COPYRIGHT_OWNER", "Anselem Okeke")
COPYRIGHT_YEAR  = os.getenv("SMARTMON_COPYRIGHT_YEAR", str(datetime.utcnow().year))
POWERED_BY      = os.getenv("SMARTMON_POWERED_BY", "Flask & SQLite")

PROJECT_URL     = os.getenv("SMARTMON_PROJECT_URL", "https://github.com/anselem-okeke/Smart-Monitor")
OWNER_URL       = os.getenv("SMARTMON_OWNER_URL", "https://www.linkedin.com/in/anselem-okeke/")
FLASK_URL       = os.getenv("FLASK_URL", "https://flask.palletsprojects.com")
SQLITE_URL      = os.getenv("SQLITE_URL", "https://www.sqlite.org")
POSTGRES_URL    = os.getenv("POSTGRES_URL", "https://www.postgresql.org/docs/")