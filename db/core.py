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
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=5000;")
    try:
        con.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError:
        # fallback when WAL can’t be enabled (permissions/FS)
        con.execute("PRAGMA journal_mode=DELETE;")
    return con