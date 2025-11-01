#!/usr/bin/env bash
set -euo pipefail

echo "[GUI] starting Flask GUI/API via gunicorn"
echo "[GUI] user=$(id -u -n) uid=$(id -u) gid=$(id -g)"
echo "[GUI] app=${GUNICORN_APP:-gui.app:create_app} bind=${GUNICORN_BIND:-0.0.0.0:5003}"

# Ensure log/instance dirs exist
mkdir -p "${APP_HOME:-/app}/logs" "${APP_HOME:-/app}/instance" || true

exec /venv/bin/gunicorn \
  --config "${GUNICORN_CONFIG:-/app/gunicorn.conf.py}" \
  --factory \
  "${GUNICORN_APP:-gui.app:create_app}"

