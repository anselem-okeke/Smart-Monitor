#!/usr/bin/env bash
# ──────────────────────────────────────────────
# Smart-Monitor Orchestrator — Linux Entrypoint
# - Waits for DB
# - Logs startup info
# - Launches orchestrator main process
# ──────────────────────────────────────────────

set -euo pipefail

# Timestamped log helper
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

log "Starting Smart-Monitor Orchestrator (Linux mode)"
log "User: $(whoami) | Host: $(hostname)"

# Optional environment verification
: "${DATABASE_URL:?DATABASE_URL not set}"
: "${SMARTMON_API_KEY:?SMARTMON_API_KEY not set}"

# Wait for database connectivity
log "Waiting for database..."
max_retries=10
until python3 - <<'PYCODE'
import os, time, sys, psycopg
url = os.getenv("DATABASE_URL")
try:
    psycopg.connect(url).close()
except Exception as e:
    print(f"[WARN] DB not ready: {e}")
    sys.exit(1)
PYCODE
do
  ((max_retries--))
  if [ "$max_retries" -le 0 ]; then
    log "Database not reachable after multiple attempts, exiting."
    exit 1
  fi
  sleep 5
done

log "Database reachable."

# Launch orchestrator main script
log "Running main orchestrator loop..."
exec python3 /app/main.py

