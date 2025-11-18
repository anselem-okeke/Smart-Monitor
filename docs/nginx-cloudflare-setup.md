### Smart-Monitor: Nginx + Cloudflare Tunnel (Token) + Local HTTPS

Architecture (at a glance)
- sm-gui (Flask/Gunicorn) listens internally on port 5003 (Docker network only). 
- sm-nginx listens inside the container on:
  - 80 → reverse proxies to sm-gui:5003 (used by Cloudflare Tunnel), 
  - 443 → reverse proxies to sm-gui:5003 with local TLS.

- Host ports are published as:
  - 8085 → container:80 (local HTTP), 
  - 8443 → container:443 (local HTTPS).

- sm-cloudflared runs with a Tunnel Token, and Zero Trust adds a Public Hostname → Service: http://sm-nginx:80.

This guide sets up:

- Nginx (reverse proxy) in Docker → proxies to sm-gui:5003 
- Local HTTP on http://<VM-IP>:8085 
- Local HTTPS on https://<VM-IP>:8443 (self-signed cert)
- Cloudflare Tunnel (token mode) → public hostname → sm-nginx:80 (no open ports required)
- Works with docker compose, official nginx:alpine, and cloudflare/cloudflared.

---

1) Structure & Prereqs 

- Docker network: smartnet 
- Containers:
  - sm-gui (Flask/Gunicorn) → listens on 5003 
  - sm-nginx → listens on 80 (HTTP) and 443 (HTTPS), proxies to sm-gui:5003 
  - sm-postgres 
  - sm-cloudflared (Cloudflare Tunnel connector)
  - VM has a host-only IP (e.g., 192.168.56.11) or use your server IP.

2) `.env`

- Create/update .env at the compose root:
```dotenv
# Images
GUI_IMAGE=ghcr.io/anselem-okeke/smartmon-gui:latest
ORCH_IMAGE=ghcr.io/anselem-okeke/smartmon-orchestrator:latest

# DB (compose-internal)
DB_NAME=
DB_USER=
DB_PASS=
DATABASE_URL_INTERNAL=postgresql://smart:smartpass@postgres:5432/smartdb
SMARTMON_INIT_PG=1

# Nginx host ports
HTTP_PORT=8085
HTTPS_PORT=8443

# Paths (absolute on host)
NGINX_SITE_CONF=/etc/nginx/sites-available/smartmon-docker.conf
TLS_FULLCHAIN=/etc/smart-monitor/tls/fullchain.pem
TLS_PRIVKEY=/etc/smart-monitor/tls/privkey.pem

# GUI
SMARTMON_API_KEY=dev-please-change
APPROVED_JSON_HOST=/etc/smart-monitor/approved_services.json
APP_META_HOST=/etc/smart-monitor/app_meta.json

# Optional
LOG_LEVEL=INFO
DRY_RUN=true

# Cloudflare Tunnel (token mode)
CF_TUNNEL_TOKEN=eyJ...<your-long-token>...
```
- CF_TUNNEL_TOKEN comes from Zero Trust → Networks → Tunnels → Create → Docker (copy the --token value)

3) Nginx site file (mounted into container)

- Create /etc/nginx/sites-available/smartmon-docker.conf on the host:
````nginx configuration
# /etc/nginx/sites-available/smartmon-docker.conf

upstream smartgui {
  server sm-gui:5003;     # Docker DNS: container name + port
  keepalive 32;
}

# --- HTTPS (local TLS on host HTTPS_PORT→443) ---
server {
  listen 443 ssl;
  server_name _;

  ssl_certificate     /etc/nginx/tls/fullchain.pem;
  ssl_certificate_key /etc/nginx/tls/privkey.pem;
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_session_cache shared:TLS:10m;
  ssl_session_timeout 1d;

  add_header X-Debug "smart-monitor-proxy" always;

  # Health probe (via HTTPS)
  location = /whoami {
    add_header Content-Type text/plain;
    return 200 "smart-monitor vhost\n";
  }

  # SSE: disable buffering + long timeouts
  location /api/stream/alerts {
    proxy_pass http://smartgui;

    proxy_http_version 1.1;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;

    proxy_buffering off;
    proxy_request_buffering off;
    proxy_cache off;
    gzip off;
    chunked_transfer_encoding off;

    add_header X-Accel-Buffering no;
    add_header Cache-Control "no-cache, no-transform";
    add_header Content-Type "text/event-stream";

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
  }

  # Everything else → GUI
  location / {
    proxy_pass http://smartgui;
    proxy_http_version 1.1;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_buffering off;
    proxy_read_timeout 1h;
    proxy_set_header Connection "";
  }
}

# --- HTTP (host HTTP_PORT→80; used by Cloudflare Tunnel) ---
server {
  listen 80;
  server_name _;

  add_header X-Debug "smart-monitor-proxy" always;

  location = /whoami {
    add_header Content-Type text/plain;
    return 200 "smart-monitor vhost\n";
  }

  location /api/stream/alerts {
    proxy_pass http://smartgui;

    proxy_http_version 1.1;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;

    proxy_buffering off;
    proxy_request_buffering off;
    proxy_cache off;
    gzip off;
    chunked_transfer_encoding off;

    add_header X-Accel-Buffering no;
    add_header Cache-Control "no-cache, no-transform";
    add_header Content-Type "text/event-stream";

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Connection "";
  }

  location / {
    proxy_pass http://smartgui;
    proxy_http_version 1.1;

    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    proxy_buffering off;
    proxy_read_timeout 1h;
    proxy_set_header Connection "";
  }
}
````

4) Self-signed TLS (local only)

- Create certs on the host:
```shell
sudo mkdir -p /etc/smart-monitor/tls
sudo openssl req -x509 -newkey rsa:2048 -sha256 -days 365 -nodes \
  -keyout /etc/smart-monitor/tls/privkey.pem \
  -out /etc/smart-monitor/tls/fullchain.pem \
  -subj "/CN=smartmon.local" \
  -addext "subjectAltName=DNS:smartmon.local,IP:192.168.56.11"

sudo chmod 644 /etc/smart-monitor/tls/fullchain.pem
sudo chmod 640 /etc/smart-monitor/tls/privkey.pem
sudo chgrp root /etc/smart-monitor/tls/privkey.pem
```
- Replace 192.168.56.11 with your VM IP.

5) docker-compose.yml (relevant services)
```yaml
networks:
  smartnet: {}

volumes:
  pgdata: {}

services:
  postgres:
    image: postgres:15
    container_name: sm-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASS}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME:-smartdb} -h 127.0.0.1"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks: [smartnet]

  gui:
    image: ${GUI_IMAGE}
    container_name: sm-gui
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      LOG_LEVEL: ${LOG_LEVEL:-INFO}
      DRY_RUN: ${DRY_RUN:-true}
      DATABASE_URL: ${DATABASE_URL_INTERNAL}
      PORT: ${GUI_PORT:-5003}
      PYTHONPATH: /app
      GUNICORN_CONFIG: /app/gui/gunicorn.conf.py
      SMARTMON_API_KEY: ${SMARTMON_API_KEY}
      SMARTMON_APPROVED_JSON: /app/config/approved_services.json
    volumes:
      - ${APPROVED_JSON_HOST}:/app/config/approved_services.json:ro
      - ${APP_META_HOST}:/app/config/app_meta.json:ro
    healthcheck:
      test: ["CMD", "/venv/bin/python", "/app/healthcheck.py"]
      interval: 30s
      timeout: 6s
      retries: 5
    networks: [smartnet]

  nginx:
    image: nginx:1.27-alpine
    container_name: sm-nginx
    depends_on:
      - gui
    ports:
      - "${HTTP_PORT}:80"      # e.g., 8085:80
      - "${HTTPS_PORT}:443"    # e.g., 8443:443
    volumes:
      - ${NGINX_SITE_CONF}:/etc/nginx/conf.d/default.conf:ro
      - ${TLS_FULLCHAIN}:/etc/nginx/tls/fullchain.pem:ro
      - ${TLS_PRIVKEY}:/etc/nginx/tls/privkey.pem:ro
    networks: [smartnet]

  cloudflared:
    image: cloudflare/cloudflared:2024.10.0
    container_name: sm-cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${CF_TUNNEL_TOKEN}
    environment:
      - TUNNEL_TRANSPORT_PROTOCOL=quic   # or http2 if QUIC is flaky
    depends_on:
      - nginx
    networks:
      - smartnet
```

6) Cloudflare Tunnel (Token mode)

- Cloudflare Dashboard → Zero Trust → Networks → Tunnels → Create a tunnel → pick Docker → copy the --token value → paste into .env as CF_TUNNEL_TOKEN=....

- In the tunnel, add a Public Hostname:
  - Hostname: smartmon.<your-domain>
  - Service (URL): http://sm-nginx:80 (Tunnel connects within Docker network; TLS at edge handled by Cloudflare.)
- Save. Cloudflare auto-creates the DNS record (if your domain is on Cloudflare DNS). If your domain is not on Cloudflare DNS, manually create a CNAME to <tunnel-id>.cfargotunnel.com at your DNS provider, then add the same hostname in the tunnel’s Public Hostnames.

7) Bring it up 
- From the directory containing your compose file:
```shell
docker compose up -d --force-recreate postgres gui nginx cloudflared
```

8) Sanity checks

- Inside the Nginx container:
```shell
docker exec -it sm-nginx nginx -t
docker exec -it sm-nginx sh -lc 'apk add --no-cache curl >/dev/null 2>&1 || true; curl -i localhost/whoami'
# Expect 200 + "smart-monitor vhost"

docker exec -it sm-nginx sh -lc 'curl -i sm-gui:5003/'
# Expect 200 OK (your app homepage)

docker exec -it sm-nginx ss -lntp | grep -E ':80|:443'
# Should show listeners on 80 and 443
```
- From the VM:
```shell
curl -i  http://127.0.0.1:8085/whoami
curl -ik https://127.0.0.1:8443/whoami   # -k to ignore self-signed
```
- From your laptop (replace IP):
```shell
http://192.168.56.11:8085/
https://192.168.56.11:8443/
```
- Cloudflare Tunnel:
  - Check logs:
```shell
docker logs -f sm-cloudflared
```

- Look for “Registered tunnel connection …”. 
  - Open:
```shell
https://smartmon.<your-domain>/
```

9) Troubleshooting

- I can’t reach the app from my browser 
  - Use the VM IP directly: http://<VM-IP>:8085/ 
  - Confirm port mapping:
```shell
docker ps --format 'table {{.Names}}\t{{.Ports}}' | grep sm-nginx
# Expect 0.0.0.0:8085->80/tcp and 0.0.0.0:8443->443/tcp
```

- VM firewall:
```shell
sudo ufw status
sudo ufw allow 8085/tcp
sudo ufw allow 8443/tcp
```
- Host-only network: confirm the correct 192.168.56.x IP:
```shell
ip -4 addr show | grep '192\.168\.56\.'
```
- HTTPS (8443) says “Connection refused” 
  - Container not listening on 443:
```shell
docker exec -it sm-nginx ss -lntp | grep ':443'
```
- If empty: confirm the HTTPS server block and cert mounts; then:
```shell
docker compose up -d --force-recreate nginx
docker exec -it sm-nginx nginx -t && docker exec -it sm-nginx nginx -s reload
docker logs --since=10m sm-nginx   # look for SSL errors
```

- Cloudflared shows QUIC timeouts 
  - Switch transport:
```yaml
environment:
  - TUNNEL_TRANSPORT_PROTOCOL=http2
```

- Recreate the container. 
- DNS NXDOMAIN for your hostname 
  - If using Cloudflare DNS: ensure the zone is onboarded. 
  - If using another DNS: create CNAME host.yourdomain -> <tunnel-id>.cfargotunnel.com, then add the same hostname in the tunnel’s Public Hostnames.

- SSE flickers / buffering 
  - Ensure proxy_buffering off; and add_header X-Accel-Buffering no; in the SSE location. 
  - Keep long proxy_read_timeout and proxy_send_timeout.

10) Optional hardening (later)
- HTTP→HTTPS local redirect:
```nginx configuration
# inside the HTTP server block
return 301 https://$host:8443$request_uri;
```
- ACME/Let’s Encrypt for trusted certs (requires public 80/443). 
- Cloudflare Access (SSO) for the tunnel hostname. 
- Origin certs with verify (Cloudflare→Nginx mTLS).

11) Quick reference (copy/paste tests)
```shell
# Nginx config loaded?
docker exec -it sm-nginx nginx -T | sed -n '1,200p'

# Nginx listeners?
docker exec -it sm-nginx ss -lntp | grep -E ':80|:443'

# Internal path OK?
docker exec -it sm-nginx sh -lc 'curl -i sm-gui:5003/'

# Local host ports OK?
curl -i  http://127.0.0.1:8085/whoami
curl -ik https://127.0.0.1:8443/whoami
```

**Notes & options**
- HTTP→HTTPS redirect (local): If you want local HTTP to force HTTPS, add a 301 redirect in your HTTP server block (remember to keep the port in the Location if you’re using a non-standard 8443).

- Let’s Encrypt (publicly trusted): Requires the server to be reachable on 80/443 from the internet; otherwise stick with self-signed (or Cloudflare origin certs for CF→origin TLS).

- Cloudflare Access (SSO): Protect your public hostname with identity policies in Zero Trust → Access → Applications.