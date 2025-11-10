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


10) Key env glossary

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

11) Minimal runbook (lab)
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

12) What to change when hardening (prod)

- Switch to --profile prod.

- Remove privileged options, /dev mount, and writable /run/systemd.

- Replace shim access with a host helper for restart/SMART; keep orchestrator read-only.

- Move secrets to Docker secrets or external secret manager.

- Put Cloudflare Access/SSO in front of Nginx (no unauthenticated public access).