#!/bin/bash
set -e

# Start sqlite-web (read-only if volume is :ro)
sqlite_web "/data/${SQLITE_DATABASE}" --host 0.0.0.0 --port "${PORT}" > /var/log/smartmon/sqliteweb.log 2>&1 &

# Prepare ngrok config on the fly (or mount your own at /etc/ngrok/ngrok.yml)
if [ -n "${NGROK_AUTHTOKEN}" ]; then
  cat > /etc/ngrok/ngrok.yml <<EOF
version: "2"
authtoken: ${NGROK_AUTHTOKEN}
tunnels:
  sqliteweb:
    proto: http
    addr: ${NGROK_ADDR}
EOF
  if [ -n "${NGROK_BASIC_AUTH}" ]; then
    printf "    basic_auth: %s\n" "${NGROK_BASIC_AUTH}" >> /etc/ngrok/ngrok.yml
  fi
  ngrok start --all --config /etc/ngrok/ngrok.yml > /var/log/smartmon/ngrok.log 2>&1 &
fi

# Tail both logs to stdout
exec tail -F /var/log/smartmon/sqliteweb.log /var/log/smartmon/ngrok.log

