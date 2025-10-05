import json
import logging
import os
import sqlite3
from pathlib import Path

log = logging.getLogger("smart-monitor")

PROJ_ROOT = Path(__file__).resolve().parents[1]

def resolve_db_path() -> str:
    # 1) ENV first (systemd injects this)
    env_db = os.getenv("SMARTMONITOR_DB_PATH")
    if env_db:
        return env_db

    # 2) config next
    cfg_path = PROJ_ROOT / "config" / "db_config.json"
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)
        p = cfg.get("path")
        if p:
            p = Path(p).expanduser()
            if not p.is_absolute():
                p = (PROJ_ROOT / p).resolve()
            return str(p)

    # 3) repo fallback
    return str((PROJ_ROOT / "db" / "smart_factory_monitor.db").resolve())

DB_PATH = resolve_db_path()

# def connect_rw():
#     db_path = resolve_db_path()
#     Path(db_path).parent.mkdir(parents=True, exist_ok=True)
#     con = sqlite3.connect(db_path, timeout=5.0)
#     con.row_factory = sqlite3.Row
#     con.execute("PRAGMA busy_timeout=5000;")
#     try:
#         mode = con.execute("PRAGMA journal_mode;").fetchone()[0]
#         if mode.lower() != "wal":
#             con.execute("PRAGMA journal_mode=WAL;")  # only if needed
#     except sqlite3.OperationalError:
#         con.execute("PRAGMA journal_mode=DELETE;")
#     return con

def connect_rw():
    db_path = resolve_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path, timeout=5.0)  # <— use db_path here
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000;")

    # Allow environment to choose journal mode
    # - default WAL for local ext4/xfs
    # - set SMARTMON_SQLITE_JOURNAL=DELETE on SMB/vboxsf
    mode = os.getenv("SMARTMON_SQLITE_JOURNAL", "WAL").upper()
    try:
        if mode == "WAL":
            con.execute("PRAGMA journal_mode=WAL;")
        else:
            con.execute("PRAGMA journal_mode=DELETE;")
            con.execute("PRAGMA locking_mode=EXCLUSIVE;")  # safer on shares
    except sqlite3.OperationalError:
        con.execute("PRAGMA journal_mode=DELETE;")
    return con


# core.py
def _to_sqlite_ro_uri(path: str) -> str:
    p = Path(path).resolve().as_posix()
    # On Windows, 'file:C:/...' works; avoid extra leading slash.
    return f"file:{p}?mode=ro&cache=shared"

def connect_ro(timeout_s: float = 1.5):
    db_path = resolve_db_path()
    uri = _to_sqlite_ro_uri(db_path)
    conn = sqlite3.connect(uri, uri=True, timeout=timeout_s, isolation_level=None)
    conn.row_factory = sqlite3.Row          # or your _dict_factory if you prefer dicts
    conn.execute(f"PRAGMA busy_timeout={int(timeout_s*1000)};")
    conn.execute("PRAGMA query_only=ON;")
    return conn




# ---------DB CORE TO BE IMPLEMENTED AND IMPORTED EVERYWHERE----------
# db/core.py

# import os, sqlite3
# from pathlib import Path
#
# PROJ_ROOT = Path(__file__).resolve().parents[1]
#
# def resolve_db_path() -> str:
#     env_db = os.getenv("SMARTMONITOR_DB_PATH")
#     if env_db:
#         return env_db
#     cfg = PROJ_ROOT / "config" / "db_config.json"
#     if cfg.exists():
#         import json
#         j = json.loads(cfg.read_text(encoding="utf-8"))
#         p = j.get("path")
#         if p:
#             p = Path(p).expanduser()
#             if not p.is_absolute():
#                 p = (PROJ_ROOT / p).resolve()
#             return str(p)
#     return str((PROJ_ROOT / "db" / "smart_factory_monitor.db").resolve())
#
# def _to_sqlite_ro_uri(path: str) -> str:
#     p = Path(path).resolve().as_posix()
#     return f"file:{p}?mode=ro&cache=shared"
#

# def connect_ro(*, dicts: bool = False, timeout_s: float = 1.5, check_same_thread: bool = True):
#     db_path = resolve_db_path()
#     uri = _to_sqlite_ro_uri(db_path)  # "file:/abs/path?mode=ro&cache=shared"
#     conn = sqlite3.connect(
#         uri, uri=True,
#         timeout=timeout_s,
#         isolation_level=None,          # autocommit / no implicit txn
#         check_same_thread=check_same_thread
#     )
#     conn.row_factory = (
#         (lambda c, r: {col[0]: r[i] for i, col in enumerate(c.description)}) if dicts
#         else sqlite3.Row
#     )
#     conn.execute(f"PRAGMA busy_timeout={int(timeout_s*1000)};")
#     conn.execute("PRAGMA query_only=ON;")
#     return conn


#
# def connect_rw(*, timeout_s: float = 5.0) -> sqlite3.Connection:
#     db_path = resolve_db_path()
#     Path(db_path).parent.mkdir(parents=True, exist_ok=True)
#     conn = sqlite3.connect(db_path, timeout=timeout_s)
#     conn.row_factory = sqlite3.Row
#     conn.execute(f"PRAGMA busy_timeout={int(timeout_s*1000)};")
#     # If your DB lives on SMB/VirtualBox shared folders, WAL can be flaky.
#     # Honor an override env; default to WAL.
#     mode = os.getenv("SMARTMON_SQLITE_JOURNAL", "WAL").upper()
#     try:
#         conn.execute(f"PRAGMA journal_mode={mode};")
#     except sqlite3.OperationalError:
#         conn.execute("PRAGMA journal_mode=DELETE;")
#     return conn



# UI / JSON / templates (prefer dicts → easy to serialize & template):
# with connect_ro(dicts=True) as conn:
#     rows = conn.execute("SELECT ...").fetchall()   # list[dict]
#
# db_access / internal logic (Rows are fine):
# with connect_ro() as conn:
#     rows = conn.execute("SELECT ...").fetchall()   # list[sqlite3.Row]
#
# Writers must use your existing connect_rw():
# with connect_rw() as conn:
#     conn.execute("INSERT ...", params)


