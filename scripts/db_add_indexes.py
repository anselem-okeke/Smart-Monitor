#!/usr/bin/env python3
# scripts/db_add_indexes.py
import os, sys, sqlite3
from pathlib import Path

try:
    # prefer the function, not the constant
    from db.core import resolve_db_path
except Exception:
    def resolve_db_path():
        return "/var/lib/smart-monitor/smart_factory_monitor.db"

def pick_db() -> str:
    # 1) --db /path/to.db
    if "--db" in sys.argv:
        arg = sys.argv[sys.argv.index("--db") + 1]
        return str(Path(arg).expanduser().resolve())
    # 2) ENV
    env = os.getenv("SMARTMONITOR_DB_PATH")
    if env:
        return str(Path(env).expanduser().resolve())
    # 3) repo resolution
    return str(Path(resolve_db_path()).expanduser().resolve())

DB = pick_db()
print(f"[db_add_indexes] Using DB: {DB}", flush=True)

# OPEN READ-WRITE (no URI, no mode=ro)
con = sqlite3.connect(DB, timeout=30)
con.row_factory = sqlite3.Row
cur = con.cursor()
cur.execute("PRAGMA foreign_keys=ON")

# Ensure table exists
row = cur.execute(
    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='service_status'"
).fetchone()
if not row:
    raise SystemExit("[db_add_indexes] Table 'service_status' not found in this DB.")

# Add ts_epoch if missing
cols = {r["name"] for r in cur.execute("PRAGMA table_info(service_status)")}
if "ts_epoch" not in cols:
    cur.execute("ALTER TABLE service_status ADD COLUMN ts_epoch INTEGER")
    cur.execute("UPDATE service_status SET ts_epoch = strftime('%s', timestamp)")
    print("[db_add_indexes] Added ts_epoch and backfilled.", flush=True)
else:
    print("[db_add_indexes] ts_epoch already exists.", flush=True)

# Indexes
cur.execute("""
CREATE INDEX IF NOT EXISTS idx_ss_host_os_svc_ts
ON service_status(hostname, os_platform, service_name, ts_epoch DESC)
""")
cur.execute("""
CREATE INDEX IF NOT EXISTS idx_ss_status_ts
ON service_status(normalized_status, ts_epoch DESC)
""")

con.commit()
con.close()
print("OK: ts_epoch + indexes ready.", flush=True)









# # scripts/db_add_indexes.py
# import os
# import sqlite3, json
# import sys
# from pathlib import Path
#
# ROOT = Path(__file__).resolve().parents[1]
# if str(ROOT) not in sys.path:
#     sys.path.insert(0, str(ROOT))
#
# from db.core import DB_PATH
#
#
# con = sqlite3.connect(DB_PATH)
# cur = con.cursor()
#
# # Add ts_epoch if missing
# cols = {c[1] for c in cur.execute("PRAGMA table_info(service_status);").fetchall()}
# if "ts_epoch" not in cols:
#     cur.execute("ALTER TABLE service_status ADD COLUMN ts_epoch INTEGER;")
#     cur.execute("UPDATE service_status SET ts_epoch = strftime('%s', timestamp);")
#     con.commit()
#
# # Indexes
# cur.execute("""
# CREATE INDEX IF NOT EXISTS idx_ss_host_os_svc_ts
# ON service_status(hostname, os_platform, service_name, ts_epoch DESC);
# """)
# cur.execute("""
# CREATE INDEX IF NOT EXISTS idx_ss_status_ts
# ON service_status(normalized_status, ts_epoch DESC);
# """)
#
# con.commit()
# con.close()
# print("OK: ts_epoch + indexes ready.")
