from flask import render_template
from . import ui_bp
import os, urllib.parse, requests
from flask import request, redirect, url_for, flash

API_KEY = os.getenv("SMARTMON_API_KEY")
INTERNAL_API = os.getenv("SMARTMON_INTERNAL_API", "")  # <— settable, safe default

def api_base():
    """
    | Setting                 | Where requests go                          | Pros                                      | Cons                                     |
    | ----------------------- | ------------------------------------------ | ----------------------------------------- | ---------------------------------------- |
    | unset (same-origin)     | Public hostname → Cloudflare Tunnel → back | Simple; matches browser path              | Hairpin out & back; slower; needs egress |
    | `http://127.0.0.1`      | Nginx (local) → Gunicorn                   | Local, fast; keeps Nginx logs/rate-limits | None for your setup                      |
    | `http://127.0.0.1:5003` | Gunicorn direct                            | Local, fastest                            | Skips Nginx protections/logs             |

    :return:
    """
    if INTERNAL_API:
        return INTERNAL_API.rstrip("/")
    # build from the incoming request (http(s)://host[:port])
    return request.host_url.rstrip("/")


@ui_bp.get("/services")
def services_view():
    # Pure template; page fetches via /api/services
    return render_template("services.html")


@ui_bp.post("/services/<host>/<path:service>/restart")
def service_restart_ui(host, service):
    service = urllib.parse.unquote(service)
    minutes = request.args.get("minutes", 1440)
    url = f"{api_base()}/api/services/restart"

    try:
        r = requests.post(
            url,
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json={"host": host, "service": service},
            timeout=20,
        )
        # Parse defensively
        try:
            data = r.json()
        except ValueError:
            data = {"ok": False, "error": (r.text or f"HTTP {r.status_code}")[:200]}

        ok = isinstance(data, dict) and bool(data.get("ok"))

        if r.ok and ok:
            msg = f"Restart {data.get('result')} for {service} on {host}"
            if data.get("dry_run"): msg += " (dry-run)"
            flash(msg, "success")
        else:
            # err = ""
            if isinstance(data, dict):
                err = data.get("error") or data.get("stderr") or f"HTTP {r.status_code}"
            else:
                err = f"Unexpected response: {str(data)[:200]}"
            flash(f"Restart failed/blocked: {err}", "error")
    except Exception as e:
        flash(f"Restart request error: {e}", "error")

    return redirect(url_for(".service_detail", host=host, service=service, minutes=minutes))


# @ui_bp.post("/services/<host>/<path:service>/restart")
# def service_restart_ui(host, service):
#     service = urllib.parse.unquote(service)
#     minutes = request.args.get("minutes", 1440)
#
#     url = f"{INTERNAL_API.rstrip('/')}/api/services/restart"
#     try:
#         r = requests.post(
#             url,
#             headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
#             json={"host": host, "service": service},
#             timeout=15,
#         )
#         data = r.json()
#         if r.ok and data.get("ok"):
#             msg = f"Restart {data.get('result')} for {service} on {host}"
#             if data.get("dry_run"): msg += " (dry-run)"
#             flash(msg, "success")
#         else:
#             err = (data.get("error") or data.get("stderr") or f"HTTP {r.status_code}")
#             flash(f"Restart failed/blocked: {err}", "error")
#     except Exception as e:
#         # now that SECRET_KEY is set, this will show instead of crashing
#         flash(f"Restart request error: {e}", "error")
#
#     return redirect(url_for("ui.service_detail", host=host, service=service, minutes=minutes))