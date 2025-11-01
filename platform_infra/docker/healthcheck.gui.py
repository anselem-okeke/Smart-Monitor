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
