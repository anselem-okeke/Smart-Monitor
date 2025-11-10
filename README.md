## Smart-Monitor  (In Production - live)

![Smart-Monitor Lab – Architecture](docs/overview/smart-monitor.svg)

### Motivation for Developing Smart-Monitor

In many production environments I have worked in, whether in **Site Reliability**, **DevOps**, or **Platform Engineering** 
roles, I have seen the same recurring pattern. Monitoring tools like **Prometheus** or **Grafana** provide excellent
visibility, but they don’t actively *do* anything to fix issues in real time. This often leaves engineers in reactive
mode, receiving alerts at **3 AM** for problems that could have been resolved automatically.

**Smart-Monitor** was created to close that gap.

---

### Why Smart-Monitor?
- **Move from awareness to action**: Traditional monitoring alerts humans, but doesn’t remediate. Smart-Monitor automates recovery.
- **Reduce Mean Time to Recovery (MTTR)**: Automatic fixes for common failures mean less downtime and fewer escalations.
- **Proactive operations**: Detect issues early and apply solutions before they impact users.

---

### Core Goals
1. **Real-time Metrics Collection**  
   Monitor CPU, memory, disk, network, and service status continuously.

2. **Automated Recovery Logic**  
   - Restart failed services.
   - Kill runaway processes under memory pressure.
   - Apply remediation for network connectivity failures.

3. **Modular Architecture**  
   Separate modules for metrics, network, disk, and service recovery.  
   Each can be developed, tested, and extended independently.

4. **Extensibility**  
   Easily add new checks and recovery actions without disrupting existing logic.

---

### Design Philosophy
> **Monitoring is not enough.**  
> Systems should not just *observe* failures, they should attempt to *recover* from them automatically when safe to do so.

By embedding recovery logic directly into the monitoring tool, Smart-Monitor reduces reliance on manual intervention,
keeps systems running longer without human input, and ensures faster problem resolution.

---

### Impact
- **Fewer late-night alerts** for engineers.
- **Improved system resilience** through automated remediation.
- **Lower operational overhead** with self-healing capabilities.

---


### Smart Monitor Container Deployment
This Section explains how to run Smart-Monitor as a containerise application using Docker Compose in two different
environment, dev vs production hardening. It also covers service-state 
collection from the host, database initialization, health checks, observability, security posture, 
and operational runbooks. Smart-Monitor on a single Linux VM comprises:
- GUI (Gunicorn) behind Nginx 
- Postgres database 
- Optional Cloudflare Tunnel 
- Orchestrator (lab profile) that can read host metrics and systemd state via D-Bus (using a small systemctl shim)

---

1) What to expect
- Compose stack: postgres, `gui`, `nginx`, `cloudflared`, and `orchestrator`.

- Two orchestrator modes:

  - lab (privileged): easiest full host visibility (proc/sys/dev, systemd via D-Bus).
  - prod (hardened): read-only mounts + a minimal host helper.

- Host systemd status from inside the container via D-Bus using a tiny systemctl-shim.

- Postgres as single source of truth.

- Healthchecks, predictable env, and clear mounts for host-level metrics.
```yaml
# ---------- shared defaults ----------
x-env-common: &env_common
  LOG_LEVEL: ${LOG_LEVEL:-INFO}
  DRY_RUN: ${DRY_RUN:-true}

x-env-db: &env_db
  DATABASE_URL: ${DATABASE_URL_INTERNAL}

x-gui-env: &gui_env
  <<: [*env_common, *env_db]
  PORT: ${GUI_PORT:-5003}
  PYTHONPATH: /app
  GUNICORN_CONFIG: /app/gui/gunicorn.conf.py
  SMARTMON_API_KEY: ${SMARTMON_API_KEY:?set in .env}
  SMARTMON_APPROVED_JSON: /app/config/approved_services.json

networks:
  smartnet: {}

volumes:
  pgdata: {}

services:
  # ---------- Postgres ----------
  postgres:
    image: postgres:15
    container_name: sm-postgres
    ports:
      - "${HOST_IP}:${HOST_PORT}:5432"
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD: ${DB_PASS}
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER:-smart} -d ${DB_NAME:-smartdb} -h 127.0.0.1"]
      interval: 5s
      timeout: 3s
      retries: 10
    volumes:
      - pgdata:/var/lib/postgresql/data
    networks: [smartnet]

  # ---------- GUI (Gunicorn inside image) ----------
  gui:
    image: ${GUI_IMAGE:? ghcr.io/smartmon-gui:linux}
    container_name: sm-gui
    depends_on:
      postgres:
        condition: service_healthy
    environment: *gui_env
    volumes:
      # approved services policy (host file → container path)
      - ${APPROVED_JSON_HOST:?abs path on host}:/app/config/approved_services.json:ro
      - ${APP_META_HOST}:/app/config/app_meta.json:ro
    healthcheck:
      test: ["CMD", "/venv/bin/python", "/app/healthcheck.py"]
      interval: 30s
      timeout: 6s
      retries: 5
    networks: [smartnet]

  # ---------- Nginx (fronts GUI only inside network) ----------
  nginx:
    image: nginx:1.27-alpine
    container_name: sm-nginx
    depends_on:
      - gui
    ports:
      - "${HTTP_PORT}:80"
      - "${HTTPS_PORT}:443"
    volumes:
      - ${NGINX_SITE_CONF:?point to site.conf}:/etc/nginx/conf.d/default.conf:ro
      - ${TLS_FULLCHAIN:-/etc/letsencrypt/live/host/fullchain.pem}:/etc/nginx/tls/fullchain.pem:ro
      - ${TLS_PRIVKEY:-/etc/letsencrypt/live/host/privkey.pem}:/etc/nginx/tls/privkey.pem:ro
    networks: [smartnet]

  # ---------- Cloudflared (optional, use when not exposing 80/443) ----------
  cloudflared:
    image: cloudflare/cloudflared:2024.10.0
    container_name: sm-cloudflared
    restart: unless-stopped
    command: tunnel --no-autoupdate run --token ${CF_TUNNEL_TOKEN}
    environment:
      - TUNNEL_TRANSPORT_PROTOCOL=quic
    depends_on:
      - nginx
    networks:
      - smartnet

  # ============================================================
  # PROD profile (locked-down orchestrator: reads systemd state)
  # ============================================================
  orchestrator:
    image: ${ORCH_IMAGE:?e.g. ghcr.io/you/smartmon-orchestrator:linux}
    container_name: sm-orchestrator
    depends_on:
      postgres:
        condition: service_healthy
    profiles: ["prod"]
    user: "1000:1000"                 # non-root in image
    read_only: true
    cap_drop: ["ALL"]
    security_opt:
      - "no-new-privileges:true"
    tmpfs:
      - /tmp:size=32m,mode=1777
      - /run:size=16m,mode=755
    environment:
      <<: [*env_common, *env_db]
      SMARTMON_INIT_PG: ${SMARTMON_INIT_PG:-0}
      # tell code to read host metrics via these roots
      SMARTMON_API_KEY: ${SMARTMON_API_KEY:?set in .env}
      PROCFS_ROOT: /host/proc
      SYSFS_ROOT: /host/sys
      SERVICE_STATUS_MODE: systemd     # read-only systemd introspection
      SMARTCTL: /usr/sbin/smartctl
      SMARTCTL_USE_SUDO: "0"
    volumes:
      # host metrics (read-only)
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      # D-Bus sockets for systemd READ access
      - /run/systemd:/run/systemd:ro
      - /run/dbus/system_bus_socket:/run/dbus/system_bus_socket:ro
      # policy for restart allow-list (still enforced in app)
      - ${APPROVED_JSON_HOST}:/app/config/approved_services.json:ro
    healthcheck:
      test: ["CMD", "python3", "/app/healthcheck.py"]
      interval: 30s
      timeout: 6s
      retries: 5
    networks: [smartnet]

  # NOTE: In PROD, **restarts & smartctl with root** should be done by a tiny host helper (systemd unit)
  # that exposes a UNIX/TCP socket with an API key. The orchestrator calls that helper.
  # (We keep it outside Compose for security — not shown here.)

  # ============================================================
  # LAB profile (privileged orchestrator: restarts & SMART)
  # ============================================================
  orchestrator_lab:
    image: ${ORCH_IMAGE}
    container_name: sm-orchestrator-lab
    entrypoint: [ "bash", "-lc", "unset SMARTMONITOR_DB_PATH; exec /app/entrypoint.sh" ]
    depends_on:
      postgres:
        condition: service_healthy
    profiles: ["lab"]
    privileged: true           # accept full host control in lab
    pid: "host"
    uts: "host"
    user: "0:0"
    environment:
      <<: [*env_common, *env_db]
      SMARTMON_INIT_PG: ${SMARTMON_INIT_PG:-0}
      SMARTMON_API_KEY: ${SMARTMON_API_KEY:?set in .env}
      PROCFS_ROOT: /host/proc
      SYSFS_ROOT: /host/sys
      #SMARTMON_SERVICE_WATCH: ${SMARTMON_SERVICE_WATCH}
      SERVICE_STATUS_MODE: cmd
      SERVICE_STATUS_CMD: /usr/local/bin/systemctl-shim
      SMARTCTL: /usr/sbin/smartctl
      SMARTCTL_USE_SUDO: "0"
      SYSTEMCTL_FORCE_BUS: "1"
      SERVICE_STATUS_DEBUG: "1"
      DBUS_SYSTEM_BUS_ADDRESS: "unix:path=/run/dbus/system_bus_socket"
    volumes:
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
      - /run/systemd:/run/systemd            # writable; systemctl control
      - /run/dbus/system_bus_socket:/run/dbus/system_bus_socket
      - /dev:/dev                            # SMART device access
      - /etc/machine-id:/etc/machine-id:ro
      - ${APPROVED_JSON_HOST}:/app/config/approved_services.json:ro
      #- /vagrant/Smart-Monitor/platform_infra/docker_compose/systemctl-shim:/usr/local/bin/systemctl-shim:ro
    healthcheck:
      test: ["CMD", "python3", "/app/healthcheck.py"]
      interval: 30s
      timeout: 6s
      retries: 5
    networks: [smartnet]
```

2) Environment (.env) — minimal template
```dotenv
# images
GUI_IMAGE=ghcr.io/anselem-okeke/smartmon-gui:latest
ORCH_IMAGE=ghcr.io/anselem-okeke/smartmon-orchestrator:latest

# DB (compose-internal)
DB_NAME=mydb
DB_USER=myuser
DB_PASS=mypass
DATABASE_URL_INTERNAL=postgresql://myuser:mypass@postgres:5432/mydb
SMARTMON_INIT_PG=1
HOST_IP=
HOST_PORT=

# Nginx
HTTP_PORT=8085
HTTPS_PORT=8443
NGINX_SITE_CONF=/etc/nginx/sites-available/smartmon-docker.conf
TLS_FULLCHAIN=/etc/smart-monitor/tls/fullchain.pem
TLS_PRIVKEY=/etc/smart-monitor/tls/privkey.pem

# GUI
SMARTMON_API_KEY=dev-please-change
APPROVED_JSON_HOST=/etc/smart-monitor/approved_services.json
APP_META_HOST=/etc/smart-monitor/app_meta.json
GUI_PORT=5003

# Optional
LOG_LEVEL=INFO
DRY_RUN=true

# optional
SMARTCTL_USE_SUDO=0
SMARTCTL=/usr/sbin/smartctl

#SMARTMON_SERVICE_WATCH=ssh.service,systemd-journald.service,systemd-logind.service,systemd-networkd.service,cron.service,nginx.service,postgresql.service,cloudflared.service,docker.service
SERVICE_STATUS_MODE=cmd
SERVICE_STATUS_CMD=/usr/local/bin/systemctl-shim
CF_TUNNEL_TOKEN=
```

3) Compose services (conceptual)

- postgres
  - Persistent volume `pgdata`. Healthcheck via `pg_isready`.

- gui
  - Talks to Postgres via `DATABASE_URL_INTERNAL`. Consumes `approved_services.json` as policy. Healthcheck uses a Python script.

- nginx
  - Fronts only the GUI inside Compose network `proxy_pass http://gui:${GUI_PORT}`. Exposes `${HTTP_PORT}:80` to host.

- cloudflared (optional)
  - Either token-based `TUNNEL_TOKEN` or file-managed `/etc/cloudflared/config.yml`.

- orchestrator

  - prod profile (hardened): read-only mounts; use a host helper for restarts/SMART where root is required.

  - lab profile (privileged): `privileged: true`, `pid: host`, `uts: host`, `/run/dbus` and `/run/systemd` mounted; uses `systemctl-shim` to query host systemd via D-Bus; SMART works via `/dev`.

- Profiles usage:
```yaml
Lab: docker compose --profile lab up -d

Prod: docker compose --profile prod up -d
```

4) Host metrics mounts — what/why


| Host path                     | Purpose                        | Container path                            | Notes                          |
| ----------------------------- | ------------------------------ | ----------------------------------------- | ------------------------------ |
| `/proc`                       | CPU/mem/net per host           | `/host/proc` (ro)                         | psutil reads via `PROCFS_ROOT` |
| `/sys`                        | Disk/IO/sys info               | `/host/sys` (ro)                          | psutil reads via `SYSFS_ROOT`  |
| `/dev`                        | Block devices for SMART health | `/dev`                                    | **Lab only** (full /dev)       |
| `/run/systemd`                | Host systemd private socket    | `/run/systemd`                            | D-Bus transport to PID 1       |
| `/run/dbus/system_bus_socket` | D-Bus system bus to host       | same                                      | Required for busctl calls      |
| `/etc/machine-id`             | Stable machine identity        | same (ro)                                 | Helps certain systemd queries  |
| `approved_services.json`      | Restart allow-list policy      | `/app/config/approved_services.json` (ro) | Consumed by GUI/Orchestrator   |


5) Orchestrator modes & env

- Database selection

  - If `DATABASE_URL` is present, the orchestrator uses Postgres.

  - We unset `SMARTMONITOR_DB_PATH` in entrypoint to avoid SQLite fallback.

- Service status backend

  - `SERVICE_STATUS_MODE=cmd` → use shim (recommended inside container).

  - `SERVICE_STATUS_MODE=systemd` → fallback to systemctl (often unreliable in containers).

- Shim path

  - `SERVICE_STATUS_CMD=/usr/local/bin/systemctl-shim`

- Systemd/D-Bus wiring

  - `DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket`
  - `pid: "host"`, `uts: "host"`, mounts: `/run/systemd`, `/run/dbus/system_bus_socket`

- Host name override

  - In lab we use uts: host so socket.gethostname() resolves to the real host (e.g., BackendServer). If you can’t use UTS, add HOSTNAME_OVERRIDE=BackendServer and read it in code.

6) The systemctl-shim (what it is & how we use it)

A tiny bash utility we bind-mount into the container and build into image at `/usr/local/bin/systemctl-shim`.
It speaks directly to host systemd over D-Bus via `busctl`:
```shell
#!/usr/bin/env bash
set -euo pipefail
cmd="${1:-}"; arg="${2:-}"

normalize_unit() {
  local u="$1"
  [[ -n "$u" && "$u" != *.service ]] && u="${u}.service"
  printf '%s\n' "$u"
}

get_unit_path() {
  local unit="$1"
  local out
  if ! out=$(busctl --system call org.freedesktop.systemd1 \
        /org/freedesktop/systemd1 org.freedesktop.systemd1.Manager \
        GetUnit s "$unit" 2>/dev/null); then
    echo ""
    return 1
  fi
  echo "$out" | awk -F'"' '{print $2}'
}

emit_service_name_if_ok() {
  # args: name load active sub following fields ignored here
  local name="$1" load="$2" active="$3" sub="$4"
  # Filter junk: templates, timers/paths/slices/scopes
  [[ "$name" != *.service ]] && return 0
  [[ "$name" == *@.service ]] && return 0
  [[ "$name" =~ \.(timer|path|slice|scope)$ ]] && return 0
  # We’ll keep running/failed/activating etc.; 'static' gets filtered in show/Type if needed
  printf '%s\n' "$name"
}

case "$cmd" in
  is-active)
    unit="$(normalize_unit "$arg")"
    path="$(get_unit_path "$unit")" || { echo "unknown"; exit 0; }
    state=$(busctl --system get-property org.freedesktop.systemd1 "$path" \
              org.freedesktop.systemd1.Unit ActiveState | awk '{print $2}' | tr -d '"')
    echo "${state:-unknown}"
    ;;

  show)
    unit="$(normalize_unit "$arg")"
    path="$(get_unit_path "$unit")" || {
      printf "ActiveState=unknown\nSubState=unknown\nType=unknown\nUnitFileState=unknown\nLoadState=unknown\n"
      exit 0
    }
    load=$(busctl --system get-property org.freedesktop.systemd1 "$path" \
              org.freedesktop.systemd1.Unit LoadState | awk '{print $2}' | tr -d '"')
    active=$(busctl --system get-property org.freedesktop.systemd1 "$path" \
              org.freedesktop.systemd1.Unit ActiveState | awk '{print $2}' | tr -d '"')
    sub=$(busctl --system get-property org.freedesktop.systemd1 "$path" \
              org.freedesktop.systemd1.Unit SubState | awk '{print $2}' | tr -d '"')
    type=$(busctl --system get-property org.freedesktop.systemd1 "$path" \
              org.freedesktop.systemd1.Service Type 2>/dev/null | awk '{print $2}' | tr -d '"' || true)
    [[ -z "${type:-}" ]] && type="unknown"
    # UnitFileState via Manager.GetUnitFileState (works even if property missing)
    ufs=$(busctl --system call org.freedesktop.systemd1 \
            /org/freedesktop/systemd1 org.freedesktop.systemd1.Manager \
            GetUnitFileState s "$(basename "$unit")" | awk '{print $2}' | tr -d '"' || true)
    [[ -z "${ufs:-}" ]] && ufs="unknown"
    printf "ActiveState=%s\nSubState=%s\nType=%s\nUnitFileState=%s\nLoadState=%s\n" \
           "${active:-unknown}" "${sub:-unknown}" "${type:-unknown}" "${ufs:-unknown}" "${load:-unknown}"
    ;;

  list-units)
    # Emit union: running + failed (names only)
    # Manager.ListUnits returns an array of structures. We’ll parse with busctl --verbose-friendly format.
    busctl --system call org.freedesktop.systemd1 /org/freedesktop/systemd1 \
      org.freedesktop.systemd1.Manager ListUnits \
      | tr -d '\n' \
      | awk -F'[()"]' '
          {
            for (i=1; i<=NF; i++) {
              if ($i ~ /\.service$/) {
                name=$i
                # The next fields (outside quotes) contain load/active/sub later in the tuple; hard to align reliably.
                # We will simply print the name here; filters happen in collector via show().
                print name
              }
            }
          }
        ' \
      | awk '!seen[$0]++'
    ;;

  list-units-clean)
    # Optional cleaner: only running/failed via two filtered queries
    # Running:
    busctl --system call org.freedesktop.systemd1 /org/freedesktop/systemd1 \
      org.freedesktop.systemd1.Manager ListUnits \
      | tr -d '\n' \
      | awk -F'[()"]' '
          { for (i=1; i<=NF; i++) if ($i ~ /\.service$/) { print $i } }
        ' \
      | awk '!seen[$0]++' \
      | while read -r n; do
          # Filter timers/templates/etc.
          [[ "$n" != *.service ]] && continue
          [[ "$n" == *@.service ]] && continue
          [[ "$n" =~ \.(timer|path|slice|scope)$ ]] && continue
          echo "$n"
        done
    ;;

  list-unit-files-enabled)
    # List enabled unit files (to catch stopped-but-should-run)
    busctl --system call org.freedesktop.systemd1 /org/freedesktop/systemd1 \
      org.freedesktop.systemd1.Manager ListUnitFiles \
      | tr -d '\n' \
      | awk -F'[()"]' '
          {
            for (i=1; i<=NF; i++) {
              if ($i ~ /\.service$/) {
                name=$i
                # The state appears later in tuple; do a second pass:
                # For simplicity, we print all *.service here; the collector filters by UnitFileState=enabled via show()
                print name
              }
            }
          }
        ' \
      | awk '!seen[$0]++'
    ;;

  *)
    echo "usage: $0 {is-active|show|list-units|list-units-clean|list-unit-files-enabled} [unit]" >&2
    exit 2
    ;;
esac
```

- `systemctl-shim is-active <unit>` → prints `active|inactive|failed|unknown`

- `systemctl-shim show <unit>` → prints:
- `systemctl-shim list-units` → one *.service per line
```shell
ActiveState=...
SubState=...
Type=...
UnitFileState=...
```

Why: containerized `systemctl` is usually “offline” and lies about host services. The shim skips `systemctl` and hits systemd directly (PID 1) using the sockets mounted.

- Ensure the shim file is LF line endings and executable:
  - `chmod +x platform_infra/docker_compose/systemctl-shim`

7) Healthcheck (orchestrator)

- The container is considered healthy if it can connect to Postgres and run `SELECT 1`;.
We adjusted the healthcheck to use `python3 /app/healthcheck.py`. If base image doesn’t have a venv at `/venv`, don’t point to `/venv/bin/python`.

- Common cause of “unhealthy”:

  - Healthcheck command points to a non-existent python path.

  - Container can’t resolve `postgres` DNS name.

  - Wrong credentials in `.env`.

8) Quick verifications

- A. D-Bus + systemd visible inside the orchestrator (lab)
```shell
docker compose exec orchestrator_lab bash -lc '
  stat /run/dbus/system_bus_socket /run/systemd/private || true
  env | egrep "SERVICE_STATUS_MODE|SERVICE_STATUS_CMD|DBUS_SYSTEM_BUS_ADDRESS"
  /usr/local/bin/systemctl-shim show ssh.service
  /usr/local/bin/systemctl-shim is-active ssh.service
  /usr/local/bin/systemctl-shim list-units | head
'
```
- should see `ActiveState=active` and `active` for real services, and a list of services.

- B. Postgres is being used
```shell
docker compose exec orchestrator_lab bash -lc 'echo "DB=$DATABASE_URL"'
docker compose exec postgres psql -U smart -d smartdb -c "SELECT COUNT(*) FROM service_status;"
```

- C. Recent service rows from host
```shell
SELECT service_name, raw_status, sub_state, service_type, unit_file_state
FROM service_status
WHERE hostname='BackendServer'
ORDER BY ts_epoch DESC
LIMIT 20;
```
9) Security & hardening notes

- Lab profile is intentionally over-privileged to validate end-to-end logic. Don’t use in production.

- In prod:
  - Drop `privileged`, avoid `/dev` mount unless segmented.
  - Don’t give /run/systemd write access; if you must read, keep read-only. 
  - Implement a tiny host helper (systemd service) that exposes a protected local socket for restart/smartctl actions; orchestrator calls it with an API key. Keep that helper on the host, outside Compose. 
  - Use Docker secrets for API keys and DB credentials. 
  - Restrict Nginx exposure or put Cloudflare Tunnel/Access in front. 
  - Turn on GUI rate-limits and auth (Basic Auth or SSO) before going public.

10) Windows collector (note)
- On Windows we don’t containerize for host metrics. Run the orchestrator as a service (e.g., with NSSM), writing into the same Postgres on your Linux VM. It uses sc.exe query for service states and logs to the same schema.


11) Key env glossary

| Var                              | Meaning / Example                                                         |
| -------------------------------- | ------------------------------------------------------------------------- |
| `DATABASE_URL`                   | `postgresql://smart:smartpass@postgres:5432/smartdb` (or the Linux VM IP) |
| `SMARTMON_INIT_PG`               | `1` to auto-apply schema on first run                                     |
| `SERVICE_STATUS_MODE`            | `cmd` (shim via D-Bus) or `systemd` (fallback)                            |
| `SERVICE_STATUS_CMD`             | `/usr/local/bin/systemctl-shim`                                           |
| `DBUS_SYSTEM_BUS_ADDRESS`        | `unix:path=/run/dbus/system_bus_socket`                                   |
| `PROCFS_ROOT` / `SYSFS_ROOT`     | `/host/proc`, `/host/sys` to read host metrics                            |
| `SMARTCTL` / `SMARTCTL_USE_SUDO` | `/usr/sbin/smartctl` and `0/1`                                            |
| `SMARTMON_API_KEY`               | API key for protected endpoints                                           |
| `APPROVED_JSON_HOST`             | Host path to restart allow-list JSON                                      |
| `DRY_RUN`                        | `true/false` to suppress actual remediation                               |

12) Minimal runbook (lab)
```shell
# 1) Prepare files
sudo mkdir -p /etc/smart-monitor
sudo cp config/approved_services.json /etc/smart-monitor/
sudo cp config/app_meta.json /etc/smart-monitor/   # optional

# 2) Ensure shim is executable
chmod +x platform_infra/docker_compose/systemctl-shim

# 3) Bring up
docker compose --profile lab up -d

# 4) Verify
docker compose ps
docker compose logs -f orchestrator_lab
docker compose exec orchestrator_lab bash -lc '/usr/local/bin/systemctl-shim show ssh.service'
docker compose exec postgres psql -U smart -d smartdb -c \
  "SELECT normalized_status, COUNT(*) FROM service_status WHERE hostname='BackendServer' GROUP BY 1;"
```

13) What to change when hardening (prod)

- Switch to --profile prod.

- Remove privileged options, /dev mount, and writable /run/systemd.

- Replace shim access with a host helper for restart/SMART; keep orchestrator read-only.

- Move secrets to Docker secrets or external secret manager.

- Put Cloudflare Access/SSO in front of Nginx (no unauthenticated public access).


14) Security Posture (what “good” looks like)
```yaml
# /etc/nginx/conf.d/default.conf  (mounted into the container)

upstream smartgui {
  server sm-gui:5003;
  keepalive 32;
}

# --- HTTPS (local TLS) ---
server {
  listen 443 ssl;
  server_name smartmon-docker.anselemokeke.dpdns.org _;

  ssl_certificate     /etc/nginx/tls/fullchain.pem;
  ssl_certificate_key /etc/nginx/tls/privkey.pem;
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_session_cache shared:TLS:10m;
  ssl_session_timeout 1d;

  add_header X-Debug "smart-monitor-proxy" always;

  location = /whoami {
    add_header Content-Type text/plain;
    return 200 "smart-monitor vhost\n";
  }

  # SSE stream
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

# --- HTTP (local + for Cloudflare Tunnel) ---
server {
  listen 80;
  server_name _;

  # If you want HTTP→HTTPS redirect for local browsing, use:
  # return 301 https://$host:8443$request_uri;

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
    proxy_buffering off; proxy_request_buffering off; proxy_cache off; gzip off; chunked_transfer_encoding off;
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
```
- GUI & Nginx 
  - GUI never binds to host network; expose it only through Nginx. 
  - Add basic headers (X-Frame-Options, X-Content-Type-Options, CSP). 
  - Keep SSE buffering disabled in the proxy location for streaming endpoints. 
  - Authentication at the edge:
    - Cloudflare Access (SSO) is best, 
    - or Basic Auth at Nginx when you don’t have SSO. 
- Orchestrator (prod)
  - Run non-root, read-only filesystem, drop all capabilities, no-new-privileges. 
  - Mount systemd sockets read-only only if you absolutely need state introspection. 
  - Restart & smartctl go through the host helper (local socket + API key). The container cannot mutate the host on its own.
- Orchestrator (lab)
  - OK to be privileged with /dev and host namespaces to speed up development, but:
    - Treat the box as ephemeral. 
    - Don’t use this on shared or sensitive hosts.
- Secrets 
  - Don’t inline secrets in Compose. 
  - Use Compose secrets or env files outside of VCS. 
  - At minimum: API key, DB password, session secret.


---
### Run Smart-Monitor as a Service (Linux & Windows)
This guide shows how to run Smart-Monitor as a background service on Linux (systemd) and Windows. It assumes your 
project root contains the Python entrypoint (e.g., `main.py`) and a `.env` file for configuration. Otherwise clone project
dir.

---


1) Linux (systemd)
- Prerequisites 
- Python 3.10+ installed 
- A dedicated user (non-root) to run the service 
- Project cloned at /opt/smart-monitor 
- Virtualenv recommended at /opt/smart-monitor/.venv
```shell
# Create service user (no shell login)
sudo useradd --system --home /opt/smart-monitor --shell /usr/sbin/nologin smartmon

# Prepare directories
sudo mkdir -p /opt/smart-monitor
sudo chown -R smartmon:smartmon /opt/smart-monitor

# Clone code (example)
sudo -u smartmon git clone https://yourgit/Smart-Monitor.git /opt/smart-monitor

# Python venv + deps
sudo -u smartmon python3 -m venv /opt/smart-monitor/.venv
sudo -u smartmon /opt/smart-monitor/.venv/bin/pip install --upgrade pip wheel
sudo -u smartmon /opt/smart-monitor/.venv/bin/pip install -r /opt/smart-monitor/requirements.txt
```
Environment variables

Create an environment file and restrict permissions:
```shell
sudo tee /etc/smart-monitor.env >/dev/null <<'EOF'
# --- core ---
MODE=collector          # or control
LOG_LEVEL=INFO
# DB
DB_HOST=
DB_PORT=
DB_NAME=
DB_USER=
DB_PASSWORD=supersecret
# other app-specific vars...
EOF

sudo chown root:root /etc/smart-monitor.env
sudo chmod 0640 /etc/smart-monitor.env
```
systemd unit

Create `/etc/systemd/system/smart-monitor.service`:
```shell
[Unit]
Description=Smart-Monitor Orchestrator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=smartmon
Group=smartmon
WorkingDirectory=/opt/smart-monitor
EnvironmentFile=/etc/smart-monitor.env
ExecStart=/opt/smart-monitor/.venv/bin/python -m smart_monitor.main
Restart=on-failure
RestartSec=5

# Logging
StandardOutput=append:/var/log/smart-monitor/smart-monitor.log
StandardError=append:/var/log/smart-monitor/smart-monitor.err

# Hardening (optional but recommended)
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=true
PrivateTmp=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true

[Install]
WantedBy=multi-user.target
```
Create log directory and set permissions:
```shell
sudo mkdir -p /var/log/smart-monitor
sudo chown smartmon:smartmon /var/log/smart-monitor
```
Start & enable
```shell
sudo systemctl daemon-reload
sudo systemctl enable --now smart-monitor.service
sudo systemctl status smart-monitor.service
```
Logs & troubleshooting
```shell
# If using journald instead of file append:
journalctl -u smart-monitor.service -e -f

# Restart after code or env changes
sudo systemctl restart smart-monitor.service
```
Tip: If your entrypoint is a script (e.g., `python main.py`), set `ExecStart=/opt/smart-monitor/.venv/bin/python` `/opt/smart-monitor/main.py`.

2) Windows (Service)

You can install Smart-Monitor as a Windows Service using either NSSM (simple & popular) or built-in sc.exe.
NSSM is recommended because it handles working directories, restarts, and stdout/stderr better.

- Common prerequisites 
  - Python 3.11+ installed (e.g., `C:\Python311\python.exe`)
  - Project at `C:\smart-monitor` 
  - Virtual environment at `C:\smart-monitor\.venv`
  - `.env` file at `C:\smart-monitor\.env` (Smart-Monitor should load it)
```shell
# Run in an elevated PowerShell
New-Item -ItemType Directory -Force C:\smart-monitor | Out-Null
# Clone your repo (example using git)
git clone https://your.git/Smart-Monitor.git C:\smart-monitor

# Python venv + deps
C:\Python311\python.exe -m venv C:\smart-monitor\.venv
C:\smart-monitor\.venv\Scripts\pip.exe install --upgrade pip wheel
C:\smart-monitor\.venv\Scripts\pip.exe install -r C:\smart-monitor\requirements.txt
```

Create `C:\smart-monitor\.env`:
```MODE=collector
LOG_LEVEL=INFO
DB_HOST=127.0.0.1
DB_PORT=
DB_NAME=
DB_USER=
DB_PASSWORD=supersecret
```

Option A — NSSM (Recommended)

- Download NSSM (you can use chocolatey) and place nssm.exe in C:\Windows\System32 or keep its folder in PATH. 
- Install the service:
```# Paths
$AppPath = "C:\smart-monitor\.venv\Scripts\python.exe"
$Args    = "-m smart_monitor.main"
$SrvName = "SmartMonitor"
$WorkDir = "C:\smart-monitor"
$OutLog  = "C:\smart-monitor\logs\smart-monitor.out.log"
$ErrLog  = "C:\smart-monitor\logs\smart-monitor.err.log"

New-Item -ItemType Directory -Force "C:\smart-monitor\logs" | Out-Null

nssm install $SrvName $AppPath $Args
nssm set $SrvName AppDirectory $WorkDir
nssm set $SrvName AppStdout    $OutLog
nssm set $SrvName AppStderr    $ErrLog
nssm set $SrvName AppRotateFiles 1
nssm set $SrvName AppRotateOnline 1
nssm set $SrvName Start SERVICE_AUTO_START
nssm set $SrvName AppEnvironmentExtra "MODE=collector" "LOG_LEVEL=INFO"
# If your app reads .env itself, AppEnvironmentExtra is optional

nssm start $SrvName
```
- Manage:
```shell
nssm status SmartMonitor
nssm restart SmartMonitor
nssm stop SmartMonitor
```

Option B — Built-in sc.exe (no external tools)

Note: sc.exe doesn’t handle working directories or logging as nicely. Use full paths and consider a wrapper .bat to set cd first.

Create a simple wrapper `C:\smart-monitor\run-smartmon.bat`:
```shell
@echo off
cd /d C:\smart-monitor
C:\smart-monitor\.venv\Scripts\python.exe -m smart_monitor.main
```

Then install the service:
```shell
$SrvName = "SmartMonitor"
sc.exe create $SrvName binPath= "C:\smart-monitor\run-smartmon.bat" start= auto
sc.exe description $SrvName "Smart-Monitor Orchestrator"
sc.exe start $SrvName
```
To update/restart:
```shell
sc.exe stop SmartMonitor
sc.exe start SmartMonitor
```
Logs & troubleshooting (Windows)

- NSSM: check `C:\smart-monitor\logs\smart-monitor.*.log` 
- Event Viewer: `Windows Logs → Application` for service errors 
- Quick check:
```shell
Get-Service SmartMonitor
```

Health checks & verification

- Confirm the process is running (Linux: systemctl status; Windows: Get-Service). 
- Validate expected ports or endpoints (if applicable). 
- Tail logs to ensure successful startup and DB connectivity.

Upgrades & deployments

Linux
```shell
sudo systemctl stop smart-monitor
sudo -u smartmon git -C /opt/smart-monitor pull
sudo -u smartmon /opt/smart-monitor/.venv/bin/pip install -r /opt/smart-monitor/requirements.txt
sudo systemctl start smart-monitor
```

Windows (NSSM)
```shell
nssm stop SmartMonitor
git -C C:\smart-monitor pull
C:\smart-monitor\.venv\Scripts\pip.exe install -r C:\smart-monitor\requirements.txt
nssm start SmartMonitor
```