# import os, getpass
# import sqlite3
# from pathlib import Path
# # from db.core import DB_PATH
#
#
# # Tables to be created
# REQUIRED_TABLES = [
#     "alerts",
#     "recovery_logs",
#     "service_status",
#     "system_metrics",
#     "network_logs",
#     "process_status",
#     "restart_attempts",
#     "smart_health"
# ]
#
# def default_db_path():
#     # repo fallback: Smart-Monitor/db/smart_factory_monitor.db
#     return str(Path(__file__).resolve().parent / "smart_factory_monitor.db")
#
# def schema_path():
#     return Path(__file__).resolve().parent / "schema.sql"
#
# DB_PATH = os.getenv("SMARTMONITOR_DB_PATH", default_db_path())
# print(f"[DEBUG] Using DB: {DB_PATH} (user={getpass.getuser()})")
#
# def ensure_db_initialized():
#     """
#     Ensure the SQLite DB exists and has the required tables.
#     Returns: (db_path, created_new_file, tables_created_or_missing_before)
#     """
#     db_path = os.getenv("SMARTMONITOR_DB_PATH", default_db_path())
#     created = not Path(db_path).exists()
#
#     # Make sure parent directory exists (important for /var/lib/... paths)
#     Path(db_path).parent.mkdir(parents=True, exist_ok=True)
#
#     con = sqlite3.connect(db_path)
#     try:
#         # Friendly settings for many readers + one writer
#         con.execute("PRAGMA journal_mode=WAL;")
#         con.execute("PRAGMA synchronous=NORMAL;")
#         con.execute("PRAGMA busy_timeout=5000;")
#
#         # What tables exist now?
#         cur = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
#         existing = {row[0] for row in cur.fetchall()}
#
#         missing = [t for t in REQUIRED_TABLES if t not in existing]
#         if created or missing:
#             with schema_path().open("r", encoding="utf-8") as f:
#                 con.executescript(f.read())
#             con.commit()
#
#             # Re-check after applying schema
#             cur2 = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
#             existing2 = {row[0] for row in cur2.fetchall()}
#             still_missing = [t for t in REQUIRED_TABLES if t not in existing2]
#
#             if still_missing:
#                 return db_path, created, still_missing
#             else:
#                 # Report what we created/filled
#                 return db_path, created, missing if not created else REQUIRED_TABLES
#         else:
#             return db_path, created, []
#     finally:
#         con.close()




import os, getpass, sqlite3, logging
from pathlib import Path

log = logging.getLogger("smart-monitor")

REQUIRED_TABLES = [
    "alerts",
    "recovery_logs",
    "service_status",
    "system_metrics",
    "network_logs",
    "process_status",
    "restart_attempts",
    "smart_health",
]

def default_db_path():
    # repo fallback: Smart-Monitor/db/smart_factory_monitor.db
    return str(Path(__file__).resolve().parent / "smart_factory_monitor.db")

def schema_path_sqlite():
    return Path(__file__).resolve().parent / "schema.sql"

def schema_path_pg():
    # New file with PG DDL (see below)
    return Path(__file__).resolve().parent / "schema_pg.sql"

DB_PATH = os.getenv("SMARTMONITOR_DB_PATH", default_db_path())
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
INIT_PG = os.getenv("SMARTMON_INIT_PG", "").strip() in ("1", "true", "yes", "y")

def _using_pg() -> bool:
    return DATABASE_URL.startswith(("postgres://", "postgresql://"))

print(f"[DEBUG] Using backend: {'Postgres' if _using_pg() else 'SQLite'} (user={getpass.getuser()})")

# -------------------- SQLite init --------------------

def ensure_sqlite_initialized():
    """
    Ensure the SQLite DB exists and has the required tables using schema.sql.
    Returns: (db_path, created_new_file, tables_created_or_missing_before)
    """
    db_path = os.getenv("SMARTMONITOR_DB_PATH", default_db_path())
    created = not Path(db_path).exists()

    # Ensure parent dir exists (important for /var/lib/... paths)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(db_path)
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        con.execute("PRAGMA busy_timeout=5000;")

        cur = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {row[0] for row in cur.fetchall()}

        missing = [t for t in REQUIRED_TABLES if t not in existing]
        if created or missing:
            with schema_path_sqlite().open("r", encoding="utf-8") as f:
                con.executescript(f.read())
            con.commit()

            cur2 = con.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing2 = {row[0] for row in cur2.fetchall()}
            still_missing = [t for t in REQUIRED_TABLES if t not in existing2]

            if still_missing:
                return db_path, created, still_missing
            else:
                return db_path, created, missing if not created else REQUIRED_TABLES
        else:
            return db_path, created, []
    finally:
        con.close()

# -------------------- Postgres init/check --------------------

def _pg_conn():
    import psycopg  # pip install "psycopg[binary]"
    return psycopg.connect(DATABASE_URL)

def _pg_existing_tables(conn):
    """
    Return lowercase table names that exist in the 'public' schema.
    """
    sql = """
      SELECT tablename
      FROM pg_catalog.pg_tables
      WHERE schemaname = 'public'
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        return {r[0].lower() for r in cur.fetchall()}

def _pg_apply_schema(conn, path: Path):
    sql = path.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()

def ensure_postgres_ready():
    """
    If SMARTMON_INIT_PG=1, apply schema_pg.sql (idempotent: IF NOT EXISTS).
    Otherwise, only check tables and report what's missing.
    Returns: (DATABASE_URL, created:bool, missing_or_created:list)
    """
    created = False
    with _pg_conn() as conn:
        existing = _pg_existing_tables(conn)
        missing = [t for t in REQUIRED_TABLES if t.lower() not in existing]

        if INIT_PG:
            # Apply schema regardless; it's idempotent due to IF NOT EXISTS.
            _pg_apply_schema(conn, schema_path_pg())
            existing2 = _pg_existing_tables(conn)
            still_missing = [t for t in REQUIRED_TABLES if t.lower() not in existing2]
            if still_missing:
                return DATABASE_URL, created, still_missing
            else:
                # If there were any missing before, we can say we created/fixed them.
                created = bool(missing)
                return DATABASE_URL, created, missing if created else []
        else:
            # No init; just report missing.
            return DATABASE_URL, created, missing

# -------------------- public entry point --------------------

def ensure_db_initialized():
    """
    Dual backend dispatcher.
    - SQLite: same behavior as before.
    - Postgres: optional auto-init if SMARTMON_INIT_PG=1, else just check.
    Returns a triple:
       (target, created_flag, list_of_missing_or_created)
    Where 'target' is a path for SQLite or the DATABASE_URL for Postgres.
    """
    if _using_pg():
        return ensure_postgres_ready()
    else:
        return ensure_sqlite_initialized()
