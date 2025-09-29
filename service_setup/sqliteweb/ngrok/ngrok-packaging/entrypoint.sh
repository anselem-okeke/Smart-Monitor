#!/usr/bin/env bash
set -Eeuo pipefail

# --- defaults ---
: "${PORT:=8080}"
: "${SQLITE_DATABASE:=smart_factory_monitor.db}"
: "${NGROK_ADDR:=127.0.0.1:8080}"          # can be host:port or full http(s):// URL
: "${NGROK_AUTHTOKEN:=}"                   # pass at docker run time
: "${NGROK_BASIC_AUTH:=}"                  # comma-separated "user:pass,user2:pass2"

mkdir -p /var/log/smartmon
DB="/data/${SQLITE_DATABASE}"

# Validate DB is readable
if [[ ! -r "$DB" ]]; then
  echo "[ERROR] DB not readable at: $DB" >&2
  ls -l /data || true
  exit 1
fi

# Normalize upstream to a full URL for ngrok v3
if [[ "$NGROK_ADDR" =~ ^https?:// ]]; then
  UPSTREAM="$NGROK_ADDR"
else
  UPSTREAM="http://$NGROK_ADDR"
fi

# Start sqlite-web (read-only UI)
sqlite_web --read-only --host 0.0.0.0 --port "$PORT" "$DB" \
  > /var/log/smartmon/sqliteweb.log 2>&1 &
SQLITE_PID=$!

# Build ngrok v3 config if we have a token (the agent also accepts NGROK_AUTHTOKEN from env)
NGROK_LOG="/var/log/smartmon/ngrok.log"
: > "$NGROK_LOG"

if [[ -n "$NGROK_AUTHTOKEN" ]]; then
  {
    echo 'version: "3"'
    echo 'endpoints:'
    echo '  - name: sqliteweb'
    echo '    upstream:'
    echo "      url: \"$UPSTREAM\""
    # optional Basic Auth via traffic policy
    if [[ -n "$NGROK_BASIC_AUTH" ]]; then
      echo '    traffic_policy:'
      echo '      on_http_request:'
      echo '        - actions:'
      echo '            - type: basic-auth'
      echo '              config:'
      echo '                credentials:'
      IFS=',' read -ra CREDS <<< "$NGROK_BASIC_AUTH"
      for c in "${CREDS[@]}"; do
        echo "                  - \"${c}\""
      done
    fi
  } > /etc/ngrok/ngrok.yml

  # Start v3 agent: reads NGROK_AUTHTOKEN from env; config defines the endpoint
  ngrok start --all --config /etc/ngrok/ngrok.yml > "$NGROK_LOG" 2>&1 &
  NGROK_PID=$!
else
  NGROK_PID=""
fi

# Graceful shutdown
trap '[[ -n "${NGROK_PID}" ]] && kill "$NGROK_PID" 2>/dev/null || true; kill "$SQLITE_PID" 2>/dev/null || true' INT TERM

## Stream logs
#tail -F /var/log/smartmon/sqliteweb.log "$NGROK_LOG" &
#TAIL_PID=$!
## Wait on children
#wait -n "$SQLITE_PID" ${NGROK_PID:+$NGROK_PID} "$TAIL_PID"

tail -F /var/log/smartmon/sqliteweb.log "$NGROK_LOG" &
wait "$SQLITE_PID"



























##!/bin/bash
#set -e
#
## Start sqlite-web (read-only if volume is :ro)
#sqlite_web "/data/${SQLITE_DATABASE}" --host 0.0.0.0 --port "${PORT}" > /var/log/smartmon/sqliteweb.log 2>&1 &
#
## Prepare ngrok config on the fly (or mount your own at /etc/ngrok/ngrok.yml)
#if [ -n "${NGROK_AUTHTOKEN}" ]; then
#  cat > /etc/ngrok/ngrok.yml <<EOF
#version: "2"
#authtoken: ${NGROK_AUTHTOKEN}
#tunnels:
#  sqliteweb:
#    proto: http
#    addr: ${NGROK_ADDR}
#EOF
#  if [ -n "${NGROK_BASIC_AUTH}" ]; then
#    printf "    basic_auth: %s\n" "${NGROK_BASIC_AUTH}" >> /etc/ngrok/ngrok.yml
#  fi
#  ngrok start --all --config /etc/ngrok/ngrok.yml > /var/log/smartmon/ngrok.log 2>&1 &
#fi
#
## Tail both logs to stdout
#exec tail -F /var/log/smartmon/sqliteweb.log /var/log/smartmon/ngrok.log

