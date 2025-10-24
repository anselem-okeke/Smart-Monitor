#!/usr/bin/env python3
"""
Smart-Monitor Orchestrator Healthcheck
Checks:
  - DB connectivity
  - Last heartbeat file (optional)
  - Main loop still responsive (optional)
Exits 0 if healthy, 1 otherwise.
"""
import os, sys, psycopg

db_url = os.getenv("DATABASE_URL")
if not db_url:
    print("[WARN] DATABASE_URL not set")
    sys.exit(1)

try:
    with psycopg.connect(db_url, connect_timeout=3) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
except Exception as e:
    print(f"[ERROR] DB not reachable: {e}")
    sys.exit(1)
#
print("[OK] Orchestrator healthy")
sys.exit(0)
