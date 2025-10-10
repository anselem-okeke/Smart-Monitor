#!/usr/bin/env bash
set -euo pipefail

### ====== CONFIG (override with env vars) ======
APP_NAME="${APP_NAME:-Smart-Monitor}"
APP_USER="${APP_USER:-smartmon}"
APP_GROUP="${APP_GROUP:-smartmon}"
APP_ROOT="${APP_ROOT:-/opt/Smart-Monitor}"
GUI_DIR="${GUI_DIR:-$APP_ROOT/gui}"
DB_DIR="${DB_DIR:-/var/lib/smart-monitor}"
DB_PATH="${DB_PATH:-$DB_DIR/smart_factory_monitor.db}"
ETC_DIR="${ETC_DIR:-/etc/smart-monitor}"
ENV_FILE="${ENV_FILE:-$ETC_DIR/env}"

# Nginx
NGINX_SITE="${NGINX_SITE:-/etc/nginx/sites-available/smart-monitor.conf}"
NGINX_LINK="${NGINX_LINK:-/etc/nginx/sites-enabled/smart-monitor.conf}"
HOST_HEADER="${HOST_HEADER:-smart-monitor.example.tld}"   # used only for tests/headers
LISTEN_LOOPBACK="${LISTEN_LOOPBACK:-yes}"                 # "yes" (Cloudflare Tunnel) or "no" (direct exposure)

# Cloudflared (optional): set these if you want the script to write config
CF_WRITE_CONFIG="${CF_WRITE_CONFIG:-no}"                  # "yes" to write config.yml
CF_TUNNEL_UUID="${CF_TUNNEL_UUID:-}"                      # required if CF_WRITE_CONFIG=yes
CF_HOSTNAME="${CF_HOSTNAME:-}"                            # e.g., smart-monitor.yourdomain.tld

### ====== PRE-FLIGHT ======
if [[ $EUID -ne 0 ]]; then
  echo "Please run as root (sudo $0)"; exit 1
fi

### ====== SYSTEMD UNITS ======
echo "==> Installing systemd units"

# GUI via Gunicorn (venv)
install -m 0644 /dev/stdin /etc/systemd/system/smart-monitor-gui.service <<UNIT
[Unit]
Description=Smart Monitor GUI (Gunicorn)
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$APP_ROOT
EnvironmentFile=-$ENV_FILE
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONPATH=$APP_ROOT
ExecStart=$GUI_DIR/.venv/bin/gunicorn -c $GUI_DIR/gunicorn.conf.py 'gui.app:create_app()'
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$DB_DIR

[Install]
WantedBy=multi-user.target
UNIT

# Orchestrator / collectors
install -m 0644 /dev/stdin /etc/systemd/system/smart-monitor-orchestrator.service <<UNIT
[Unit]
Description=Smart Monitor Orchestrator (collectors & jobs)
After=network-online.target
Wants=network-online.target

[Service]
User=$APP_USER
Group=$APP_GROUP
WorkingDirectory=$APP_ROOT
EnvironmentFile=-$ENV_FILE
Environment=DB_PATH=$DB_PATH
ExecStart=/usr/bin/python3 $APP_ROOT/main.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
ReadWritePaths=$DB_DIR

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now smart-monitor-gui smart-monitor-orchestrator

### ====== NGINX SITE ======
echo "==> Writing nginx site: $NGINX_SITE"

if [[ "$LISTEN_LOOPBACK" == "yes" ]]; then
  # Cloudflare Tunnel mode — listen only on loopback
  install -m 0644 /dev/stdin "$NGINX_SITE" <<NGINX
server {
  listen 127.0.0.1:80 default_server;
  server_name $HOST_HEADER _;

  add_header X-Debug "smart-monitor-proxy" always;
  add_header X-Frame-Options "SAMEORIGIN" always;
  add_header X-Content-Type-Options "nosniff" always;
  add_header Referrer-Policy "strict-origin-when-cross-origin" always;
  add_header Content-Security-Policy "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'" always;

  location /whoami { add_header Content-Type text/plain; return 200 "smart-monitor vhost\\n"; }

  location / {
    proxy_pass         http://127.0.0.1:5003;
    proxy_set_header   Host              \$host;
    proxy_set_header   X-Real-IP         \$remote_addr;
    proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
    proxy_set_header   X-Forwarded-Proto \$scheme;
    proxy_http_version 1.1;
    proxy_set_header   Connection "";
    proxy_buffering    off;
    proxy_read_timeout 1h;
  }
}
NGINX
else
  # Direct public mode — listen on 80 and redirect to HTTPS (you'll run certbot afterward)
  install -m 0644 /dev/stdin "$NGINX_SITE" <<'NGINX'
server {
  listen 80;
  listen [::]:80;
  server_name _;
  return 301 https://$host$request_uri;
}
# After certbot: it will create the 443 server block with cert paths
NGINX
fi

ln -sf "$NGINX_SITE" "$NGINX_LINK"
# remove default site to avoid welcome page
rm -f /etc/nginx/sites-enabled/default || true

nginx -t
systemctl reload nginx

### ====== LOCAL PROBES ======
echo "==> Probing locally"
curl -I -H "Host: ${HOST_HEADER}" http://127.0.0.1/whoami || true
curl -I -H "Host: ${HOST_HEADER}" http://127.0.0.1/ || true

### ====== CLOUDFLARE (optional) ======
if [[ "$CF_WRITE_CONFIG" == "yes" ]]; then
  if [[ -z "$CF_TUNNEL_UUID" || -z "$CF_HOSTNAME" ]]; then
    echo "WARN: CF_WRITE_CONFIG=yes but CF_TUNNEL_UUID/CF_HOSTNAME not set; skipping cloudflared config."
  else
    echo "==> Writing /etc/cloudflared/config.yml for $CF_HOSTNAME"
    mkdir -p /etc/cloudflared
    install -m 0644 /dev/stdin /etc/cloudflared/config.yml <<YML
tunnel: $CF_TUNNEL_UUID
credentials-file: /etc/cloudflared/$CF_TUNNEL_UUID.json

ingress:
  - hostname: $CF_HOSTNAME
    service: http://localhost:80
  - service: http_status:404
YML

    echo "NOTE: Ensure /etc/cloudflared/$CF_TUNNEL_UUID.json exists (copy from ~/.cloudflared/)."
    echo "Then: systemctl enable --now cloudflared"
  fi
fi

echo "==> enable-services complete."
