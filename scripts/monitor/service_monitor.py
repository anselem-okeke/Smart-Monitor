#------------------------------------------
"""Author: Anselem Okeke
    MIT License
    Copyright (c) 2025 Anselem Okeke
    See LICENSE file in the project root for full license text.
"""
#------------------------------------------
import os
import platform
import socket
import subprocess
import sys
import time
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db.db_logger import log_service_status_batch

# ---------- helpers ----------
import os

def normalize_unit_name(unit: str) -> str:
    u = (unit or "").strip()
    # turn "/etc/systemd/system/foo.service" into "foo.service"
    return os.path.basename(u) if "/" in u else u


def _map_active_to_normalized(active_state: str) -> str:
    s = (active_state or "").strip().lower()
    if s in ("active", "running", "listening"):
        return "running"
    if s in ("inactive", "dead", "exited"):
        return "stopped"
    if s in ("failed",):
        return "failed"
    if s in ("activating", "deactivating", "start", "waiting"):
        return "running"
    return "unknown"

def normalize_service_status(os_platform: str, raw_status: str) -> str:
    if os_platform == "Windows":
        r = (raw_status or "").lower()
        return "running" if r == "running" else ("stopped" if r == "stopped" else "unknown")
    return _map_active_to_normalized(raw_status)


def _is_noisy_unit(name: str, svc_type: str, unit_file_state: str) -> bool:
    n = (name or "").lower()
    if n.endswith("@.service") or n.endswith((".timer", ".path", ".slice", ".scope")):
        return True
    if (svc_type or "").lower() in ("oneshot", "notify"):
        return True
    if (unit_file_state or "").lower() in ("static", "masked"):
        return True
    return False

# ---------- Linux backends ----------

def _linux_list_units_systemctl():
    """List via systemctl (works on host; flaky inside containers)."""
    out = subprocess.check_output(
        ["bash", "-lc", "systemctl list-units --type=service --all --no-legend --no-pager"],
        text=True
    )
    units = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        name = line.split()[0]
        if name.endswith("@.service"):
            continue
        units.append(name)
    return units

def _linux_list_units_cmd():
    """Enumerate via shim (D-Bus) with clean names and observability coverage."""
    cmd = os.getenv("SERVICE_STATUS_CMD", "/usr/local/bin/systemctl-shim")
    names = set()
    try:
        ru = subprocess.check_output([cmd, "list-units-clean"], text=True, timeout=6).splitlines()
        names.update(n.strip() for n in ru if n.strip())
    except Exception:
        pass
    try:
        en = subprocess.check_output([cmd, "list-unit-files-enabled"], text=True, timeout=6).splitlines()
        names.update(n.strip() for n in en if n.strip())
    except Exception:
        pass
    # keep only *.service and drop templates immediately
    return sorted(n for n in names if n.endswith(".service") and not n.endswith("@.service"))


def _linux_show_via_systemctl(unit: str):
    """Details via systemctl show."""
    unit = normalize_unit_name(unit)

    res = subprocess.run(
        ["systemctl", "show", unit, "--property=ActiveState,SubState,Type,UnitFileState"],
        capture_output=True, text=True, timeout=6
    )
    if res.returncode != 0:
        return {"ActiveState": "unknown", "SubState": "unknown", "Type": "unknown", "UnitFileState": "unknown"}
    fields = dict(
        (k.strip(), v.strip())
        for line in res.stdout.splitlines() if "=" in line
        for k, v in [line.split("=", 1)]
    )
    return {
        "ActiveState": fields.get("ActiveState", "unknown"),
        "SubState": fields.get("SubState", "unknown"),
        "Type": fields.get("Type", "unknown"),
        "UnitFileState": fields.get("UnitFileState", "unknown"),
    }

def _linux_show_via_cmd(unit: str):
    """Details via external shim that talks to systemd over D-Bus."""
    cmd = os.getenv("SERVICE_STATUS_CMD", "/usr/local/bin/systemctl-shim")
    unit = normalize_unit_name(unit)

    # quick active state
    try:
        raw = subprocess.check_output([cmd, "is-active", unit], text=True, timeout=4).strip()
    except subprocess.CalledProcessError as e:
        raw = (e.output or "unknown").strip()
    except Exception:
        raw = "unknown"

    sub_state = "unknown"
    svc_type = "unknown"
    ufs = "unknown"
    try:
        out = subprocess.check_output([cmd, "show", unit], text=True, timeout=6)
        kv = dict(
            (k.strip(), v.strip())
            for line in out.splitlines() if "=" in line
            for k, v in [line.split("=", 1)]
        )
        sub_state = kv.get("SubState", sub_state)
        svc_type  = kv.get("Type", svc_type)
        ufs       = kv.get("UnitFileState", ufs)
        if raw in ("", "unknown"):
            raw = kv.get("ActiveState", raw or "unknown")
    except Exception:
        pass

    return raw, sub_state, svc_type, ufs

# ---------- collectors ----------

def collect_windows_services():
    services = []
    try:
        output = subprocess.check_output("sc.exe query state= all", shell=True, text=True)
        service_name = None
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("SERVICE_NAME:"):
                service_name = line.partition(":")[2].strip()
            elif line.startswith("STATE") and service_name:
                parts = line.partition(":")[2].strip().split(None, 1)
                if len(parts) == 2:
                    raw_state = parts[1].strip()
                    services.append((service_name, raw_state, "unknown", "unknown", "unknown", True))
                service_name = None
    except Exception as exc:
        print(f"[ERROR] Windows service query failed: {exc}")
    return services

def collect_linux_services():
    """
    Linux collector that can run in two modes:
      - SERVICE_STATUS_MODE=cmd      → use shim (busctl) inside container
      - SERVICE_STATUS_MODE=systemd  → use systemctl (fallback)
    """
    services = []

    mode = os.getenv("SERVICE_STATUS_MODE", "systemd").lower()
    watch_env = os.getenv("SMARTMON_SERVICE_WATCH", "")
    watch_list = [w.strip() for w in watch_env.split(",") if w.strip()]

    # units to check (from shim/systemctl unless explicit watch)
    units = watch_list if watch_list else (
        _linux_list_units_cmd() if mode == "cmd" else _linux_list_units_systemctl()
    )
    units = [normalize_unit_name(u) for u in units if u and u.strip()]
    units = sorted(set(units))

    for svc_name in units:
        try:
            if mode == "cmd":
                active, sub_state, service_type, unit_file_state = _linux_show_via_cmd(svc_name)

            else:
                info = _linux_show_via_systemctl(svc_name)
                active = info["ActiveState"]
                sub_state = info["SubState"]
                service_type = info["Type"]
                unit_file_state = info["UnitFileState"]

            if active == "unknown" and sub_state == "unknown":
                # likely not loaded / not a real unit
                continue

            # drop noisy units (timers, static, oneshot)
            if _is_noisy_unit(svc_name, service_type, unit_file_state):
                continue

            # # Hard filter: if shim couldn’t resolve it, drop it unless the user asked for it explicitly
            # if not watch_list and (active == "unknown" and sub_state == "unknown"):
            #     continue

            recoverable = (
                    (service_type or "unknown") not in ("oneshot", "notify") and
                    (unit_file_state or "unknown") not in ("static", "masked")
            )
            services.append((svc_name, active, sub_state, service_type, unit_file_state, recoverable))
        except Exception as exc:
            print(f"[WARN] Could not query {svc_name}: {exc}")
    return services

# ---------- main flow ----------

def collect_service_status():
    os_platform = platform.system()
    hostname = socket.gethostname()
    if os_platform == "Windows":
        collected = collect_windows_services()
    else:
        collected = collect_linux_services()

    rows = []
    for svc_name, active_state, sub_state, service_type, unit_file_state, recoverable in collected:
        rows.append({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": hostname,
            "os_platform": os_platform,
            "service_name": svc_name,
            "raw_status": (active_state or "unknown").lower(),
            "normalized_status": normalize_service_status(os_platform, active_state),
            "sub_state": sub_state or "unknown",
            "service_type": service_type or "unknown",
            "unit_file_state": unit_file_state or "unknown",
            "recoverable": 1 if recoverable else 0,
        })
    return rows

def handle_service_monitor():
    batch = collect_service_status()
    if batch:
        log_service_status_batch(batch)
        print(f"[INFO] Logged {len(batch)} service rows → DB; sleeping 60s...")
    else:
        print("[INFO] No services collected this cycle; sleeping 60s...")

if __name__ == "__main__":
    print("[INFO] Service Monitor starting …")
    try:
        while True:
            handle_service_monitor()
            time.sleep(60)
    except KeyboardInterrupt:
        print("[INFO] Service Monitor stopped by user.")





































# import os
# import platform
# import socket
# import subprocess
# import sys
# import time
#
# PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
# if PROJECT_ROOT not in sys.path:
#     sys.path.insert(0, PROJECT_ROOT)
#
# from db.db_logger import log_service_status_batch
#
# from datetime import datetime
#
#
# def normalize_service_status(os_platform: str, raw_status: str) -> str:
#     raw_status = raw_status.lower()
#
#     if os_platform == "Windows":
#         return "active" if raw_status == "running" else "stopped" if raw_status == "stopped" else "unknown"
#
#     # Linux mapping
#     active_states = {"active", "running", "exited", "listening", "waiting", "start", "activating"}
#     inactive_states = {"dead", "inactive", "auto-restart"}
#     failed_states = {"failed"}
#
#     if raw_status in active_states:
#         return "active"
#     if raw_status in inactive_states:
#         return "stopped"
#     if raw_status in failed_states:
#         return "failed"
#     return "unknown"
#
#
# def collect_windows_services():
#     services = []
#     try:
#         output = subprocess.check_output("sc.exe query state= all", shell=True, text=True)
#         service_name = None
#         for line in output.splitlines():
#             line = line.strip()
#             if line.startswith("SERVICE_NAME:"):
#                 service_name = line.partition(":")[2].strip()
#             elif line.startswith("STATE") and service_name:
#                 parts = line.partition(":")[2].strip().split(None, 1)
#                 if len(parts) == 2:
#                     raw_state = parts[1].strip()
#                     # Dummy values for unsupported metadata on Windows
#                     services.append((service_name, raw_state, "unknown", "unknown", "unknown", True))
#                 service_name = None
#     except Exception as exc:
#         print(f"[ERROR] Windows service query failed: {exc}")
#     return services
#
# def collect_linux_services():
#     services = []
#     try:
#         unit_rows = subprocess.check_output(
#             "systemctl list-unit-files --type=service --no-legend --no-pager",
#             shell=True, text=True
#         ).splitlines()
#
#         for row in unit_rows:
#             row = row.strip()
#             if not row:
#                 continue
#             svc_name = row.split()[0]
#             if svc_name.endswith("@.service"):
#                 continue
#
#             res = subprocess.run([
#                 "systemctl", "show", svc_name,
#                 "--property=ActiveState,SubState,Type,UnitFileState"
#             ], capture_output=True, text=True)
#
#             if res.returncode != 0:
#                 warn = (res.stderr or res.stdout).strip()
#                 print(f"[WARN] Could not query {svc_name}: {warn}")
#                 continue
#
#             parsed = dict(
#                 (key.strip(), value.strip())
#                 for line in res.stdout.strip().splitlines() if "=" in line
#                 for key, value in [line.split("=", 1)]
#             )
#
#             active_state = parsed.get("ActiveState", "unknown")
#             sub_state = parsed.get("SubState", "unknown")
#             service_type = parsed.get("Type", "unknown")
#             unit_file_state = parsed.get("UnitFileState", "unknown")
#
#             recoverable = (
#                 service_type not in ["oneshot", "notify"] and
#                 unit_file_state not in ["static", "masked"]
#             )
#
#             services.append((svc_name, active_state, sub_state, service_type, unit_file_state, recoverable))
#     except Exception as exc:
#         print(f"[ERROR] Linux service collection failed: {exc}")
#     return services
#
# def collect_service_status():
#     os_platform = platform.system()
#     hostname = socket.gethostname()
#
#     if os_platform == "Windows":
#         collected = collect_windows_services()
#     else:
#         collected = collect_linux_services()
#
#     rows = []
#     for svc_name, active_state, sub_state, service_type, unit_file_state, recoverable in collected:
#         rows.append({
#             "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
#             "hostname": hostname,
#             "os_platform": os_platform,
#             "service_name": svc_name,
#             "raw_status": active_state.lower(),
#             "normalized_status": normalize_service_status(os_platform, active_state),
#             "sub_state": sub_state,
#             "service_type": service_type,
#             "unit_file_state": unit_file_state,
#             "recoverable": 1 if recoverable else 0
#         })
#     return rows
#
# def handle_service_monitor():
#     batch = collect_service_status()
#     if batch:
#         log_service_status_batch(batch)
#         print(f"[INFO] Logged {len(batch)} service rows → DB; sleeping 60s...")
#     else:
#         print("[INFO] No services collected this cycle; sleeping 60s...")
#
# if __name__ == "__main__":
#     print("[INFO] Service Monitor starting …")
#     try:
#         while True:
#             handle_service_monitor()
#             time.sleep(60)
#     except KeyboardInterrupt:
#         print("[INFO] Service Monitor stopped by user.")















