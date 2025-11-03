#!/usr/bin/env bash
set -euo pipefail

echo "[GUI] starting Flask GUI/API via gunicorn"
echo "[GUI] user=$(id -u -n) uid=$(id -u) gid=$(id -g)"
echo "[GUI] app=${GUNICORN_APP:-gui.app:create_app} bind=${GUNICORN_BIND:-0.0.0.0:5003}"

# Ensure log/instance dirs exist
mkdir -p "${APP_HOME:-/app}/logs" "${APP_HOME:-/app}/instance" || true

/venv/bin/python - <<'PY'
import importlib, sys, os
spec = os.environ.get("GUNICORN_APP", "gui.app:create_app")
mod, func = spec.split(":")
f = getattr(importlib.import_module(mod), func.split("(")[0], None)
if not callable(f):
    print(f"[FATAL] GUNICORN_APP {spec} not resolvable to a callable.", file=sys.stderr)
    sys.exit(1)
print(f"[OK] factory callable resolved: {spec}")
PY

unset GUNICORN_CMD_ARGS

exec /venv/bin/gunicorn \
  --config "${GUNICORN_CONFIG:-/app/gunicorn.conf.py}"
#  "${GUNICORN_APP:-gui.app:create_app()}"

