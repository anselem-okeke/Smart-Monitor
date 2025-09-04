import os, getpass
import sqlite3
from pathlib import Path
# from db.core import DB_PATH


# Tables to be created
REQUIRED_TABLES = [
    "alerts",
    "recovery_logs",
    "service_status",
    "system_metrics",
    "network_logs",
    "process_status",
    "restart_attempts"
]

def default_db_path():
    # repo fallback: Smart-Monitor/db/smart_factory_monitor.db
    return str(Path(__file__).resolve().parent / "smart_factory_monitor.db")
print(default_db_path())

def schema_path():
    return Path(__file__).resolve().parent / "schema.sql"

DB_PATH = os.getenv("SMARTMONITOR_DB_PATH", default_db_path())
print(f"[DEBUG] Using DB: {DB_PATH} (user={getpass.getuser()})")

def ensure_db_initialized():
    """
    Ensure the SQLite DB exists and has the required tables.
    Returns: (db_path, created_new_file, tables_created_or_missing_before)
    """
    db_path = os.getenv("SMARTMONITOR_DB_PATH", default_db_path())
    created = not Path(db_path).exists()

    # Make sure parent directory exists (important for /var/lib/... paths)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(db_path)
    try:
        # Friendly settings for many readers + one writer
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA busy_timeout=5000;")

        # What tables exist now?
        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {row[0] for row in cur.fetchall()}

        missing = [t for t in REQUIRED_TABLES if t not in existing]
        if created or missing:
            with schema_path().open("r", encoding="utf-8") as f:
                con.executescript(f.read())
            con.commit()

            # Re-check after applying schema
            cur2 = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing2 = {row[0] for row in cur2.fetchall()}
            still_missing = [t for t in REQUIRED_TABLES if t not in existing2]

            if still_missing:
                return db_path, created, still_missing
            else:
                # Report what we created/filled
                return db_path, created, missing if not created else REQUIRED_TABLES
        else:
            return db_path, created, []
    finally:
        con.close()