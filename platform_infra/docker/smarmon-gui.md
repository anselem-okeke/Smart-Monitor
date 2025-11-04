### Smart-Monitor GUI — Containerization & Deployment
This doc captures the decisions and working setup for running the Smart-Monitor GUI on both Linux (Gunicorn) and
Windows (Waitress), plus CI builds and DB connectivity. It’s a knowledge base for the future

---

1) Final approach (what we ship)
   - WSGI style: object (no factory ambiguity).
   - Entry module: gui.wsgi:app.
   - Gunicorn config: gui/gunicorn.conf.py points to the object.
   - Entrypoint: starts Gunicorn with only --config (no app on CLI).

2) Minimal code snippets (canonical)
   - gui/wsgi.py (Linux path)
```shell
from gui.app import create_app
app = create_app()  # instantiate once at import

```
- gui/gunicorn.conf.py
```shell
import os, multiprocessing

wsgi_app = "gui.wsgi:app"      # object style (no factory needed)

PORT = os.getenv("PORT", "5003")
bind = os.getenv("GUNICORN_BIND", f"0.0.0.0:{PORT}")
workers = int(os.getenv("WORKERS", os.getenv("WEB_CONCURRENCY",
               max(2, multiprocessing.cpu_count() // 2))))
threads = int(os.getenv("THREADS", 4))
timeout = int(os.getenv("GUNICORN_TIMEOUT", 60))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", 30))
keepalive = int(os.getenv("GUNICORN_KEEPALIVE", 30))
worker_class = os.getenv("WORKER_CLASS", "gthread")
accesslog = "-"
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOGLEVEL", "info")
preload_app = os.getenv("GUNICORN_PRELOAD", "false").lower() == "true"

```
- platform_infra/docker/healthcheck.gui.py
```shell
# healthcheck.py
import os, sys, urllib.request, urllib.error

PORT = int(os.environ.get("PORT", "5003"))
HOST = os.environ.get("HEALTH_HOST", "127.0.0.1")
PATH = os.environ.get("HEALTH_PATH", "/")  # set to "/healthz" if you have one
TIMEOUT = float(os.environ.get("HEALTH_TIMEOUT", "5"))

URL = f"http://{HOST}:{PORT}{PATH}"

try:
    with urllib.request.urlopen(URL, timeout=TIMEOUT) as r:
        # Treat any 2xx/3xx as healthy
        if 200 <= r.status < 400:
            sys.exit(0)
        else:
            sys.exit(1)
#
except (urllib.error.URLError, urllib.error.HTTPError, Exception):
    sys.exit(1)

```
3) Building & pushing images (CI summary)
- Workflow (build-push-gui.yml) does:
  - Linux: build multi-arch (linux/amd64, linux/arm64) from gui.linux.Dockerfile.

  - Windows: build win-ltsc2022 and win-ltsc2025 from gui.windows.Dockerfile.

  - Push to GHCR and Docker Hub with simple tags:

    - :amd64-arm64-linux

    - :win-ltsc2022, :win-ltsc2025

  - Create a multi-OS/arch :latest manifest referencing the above.

  - This lets users docker pull ...:latest on any supported platform and get the correct variant.


4) Running locally
- Linux container, ensure to include the necessary env
```shell
docker run -d --name gui-linux -p 5003:5003 \
  -e PORT=5003 \
  -e PYTHONPATH=/app \
  -e GUNICORN_CONFIG=/app/gui/gunicorn.conf.py \
  -e HEALTH_HOST=127.0.0.1 \
  -e HEALTH_PATH=/ \
  -e SMARTMON_APPROVED_JSON=/app/config/approved_services.json \
  -v /etc/smart-monitor:/app/config \
  -e "DATABASE_URL=postgresql://smart:smartpass@192.168.56.11:5432/smartdb" \
  ghcr.io/anselem-okeke/smartmon-gui:latest
```

- Windows container, ensure to incldue the necesssary env
```shell
docker run -d --name gui-win -p 5003:5003 `
  -e PORT=5003 `
  -e GUNICORN_APP=gui.app:create_app `
  -e HEALTH_PATH=/ `
  -e "DATABASE_URL=postgresql://smart:smartpass@192.168.56.11:5432/smartdb" `
  -e SMARTMON_APPROVED_JSON="C:\app\config\approved_services.json" `
  -v C:\ProgramData\SmartMonitor:C:\app\config `
  ghcr.io/anselem-okeke/smartmon-gui:latest
```

5) Postgres connectivity (pg_hba.conf realities)
   - On Linux Docker, outbound connections originate from the default bridge (often 172.17.0.0/16).
     - Postgres sees 172.17.x.y as the client.
     - Add in pg_hba.conf on the DB host:
```shell
host  smartdb  smart  172.17.0.0/16  md5
```
- Reload Postgres: sudo systemctl reload postgresql
- On Windows Docker, WinNAT usually SNATs to the host IP; Postgres sees the host’s 192.168.56.x


- Also ensure:

  - listen_addresses='*' or host IP in postgresql.conf
  