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

def connect_rw():
    db_path = resolve_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=5.0)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000;")
    try:
        mode = con.execute("PRAGMA journal_mode;").fetchone()[0]
        if mode.lower() != "wal":
            con.execute("PRAGMA journal_mode=WAL;")  # only if needed
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




# def connect_rw():
#     Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
#     con = sqlite3.connect(DB_PATH)
#     con.row_factory = sqlite3.Row
#     con.execute("PRAGMA busy_timeout=5000;")
#     try:
#         con.execute("PRAGMA journal_mode=WAL;")
#     except sqlite3.OperationalError:
#         # fallback when WAL can’t be enabled (permissions/FS)
#         con.execute("PRAGMA journal_mode=DELETE;")
#     return con