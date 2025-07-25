#------------------------------------------
"""Author: Anselem Okeke"""
#------------------------------------------

# import os
# import sys
# # sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))
#
# import platform
# import subprocess
# import time
# import traceback
# from datetime import datetime
# import json
# from scripts.db_logger import log_alert, log_recovery
# from db.db_access import db_access_for_service_recovery, count_recent_restart_attempts
#
#
# CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../config/db_config.json"))
# with open(CONFIG_PATH, "r") as f:
#     config = json.load(f)
#
# DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../" + config["path"]))
# MAX_RESTART_ATTEMPTS = 3
# RESTART_INTERVAL_MINUTES = 10
# BACKOFF_BASE_WAIT_SECONDS = 60
#
#
# # def restart_service_windows(service_name):
# #     try:
# #         result = subprocess.run(["sc", "start", service_name], capture_output=True, text=True)
# #         if result.returncode == 0:
# #             return True, result.stdout
# #         return False, result.stderr
# #     except Exception as e:
# #         return False, str(e)
#
# def restart_service_windows(service_name):
#     try:
#         # Attempt to start the service
#         subprocess.run(["sc", "start", service_name], capture_output=True, text=True)
#
#         # Check the service status
#         result = subprocess.run(["sc", "query", service_name], capture_output=True, text=True)
#
#         if result.returncode != 0:
#             return False, result.stderr
#
#         output = result.stdout
#         for line in output.splitlines():
#             if "STATE" in line:
#                 if "RUNNING" in line:
#                     return True, output
#                 else:
#                     return False, output
#         return False, output  # Couldn't find STATE line
#
#     except Exception as e:
#         return False, str(e)
#
#
# def restart_service_linux(service_name):
#     try:
#         result = subprocess.run(["sudo", "systemctl", "restart", service_name], capture_output=True, text=True)
#         if result.returncode == 0:
#             return True, result.stdout
#         return False, result.stderr
#     except Exception as e:
#         return False, str(e)
#
# def attempt_service_recovery():
#     platform_name = platform.system()
#
#     for service_name, status, hostname in db_access_for_service_recovery():
#         if status in ("stopped", "failed"):
#             """Checking how many restart attempts were made in the past 10mins"""
#             recent_attempts = count_recent_restart_attempts(service_name, minutes=RESTART_INTERVAL_MINUTES)
#
#             if recent_attempts >= MAX_RESTART_ATTEMPTS:
#                 print(f"[WARN] Too many restart attempts for {service_name}, skipping...")
#                 continue
#
#             # exponential backoff wait
#             if recent_attempts > 0:
#                 wait_time = BACKOFF_BASE_WAIT_SECONDS * (2 ** (recent_attempts - 1))
#                 print(f"[INFO] Waiting {wait_time} seconds before retrying {service_name}")
#                 time.sleep(wait_time)
#
#             print(f"[INFO] Attempting to restart {service_name} on {hostname}")
#
#             if platform_name == "Windows":
#                 success, msg = restart_service_windows(service_name)
#             else:
#                 success, msg = restart_service_linux(service_name)
#
#             result = "success" if success else "fail"
#
#             log_recovery([{
#                 "timestamp":  datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
#                 "hostname": hostname,
#                 "os_platform": platform_name,
#                 "service_name": service_name,
#                 "result": result,
#                 "error_message": msg
#             }])
#
#             if success:
#                 print(f"[INFO] Successfully restarted {service_name}: {msg}")
#             else:
#                 print(f"[ERROR] Failed to restart {service_name}: {msg}")
#                 log_alert({
#                     "hostname": hostname,
#                     "severity": "warning",
#                     "source": "Service Recovery",
#                     "message":f"Failed recover {service_name}: {msg}"
#                 })
# if __name__ == '__main__':
#     print("[INFO] Starting Service Recovery...")
#     try:
#         while True:
#             try:
#                 attempt_service_recovery()
#                 print("[INFO] Processed Service Recovery successfully")
#             except Exception as e:
#                 print(f"[ERROR] Exception in attempt_service_recovery: {e}")
#                 traceback.print_exc()
#
#             print("[INFO] Waiting 60 seconds before next recovery attempt...")
#             time.sleep(60)
#
#     except KeyboardInterrupt:
#         print("[INFO] Service Recovery stopped by user.")


import os, sys
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


from functools import lru_cache
import platform
import subprocess
import socket
import time
import traceback
from datetime import datetime, timedelta
from db.db_access import*
from scripts.db_logger import log_alert, log_recovery, log_restart_attempt
from utils.config_utils import load_approved_services
from utils.log_utils import log_unclassified_service

# Constants
MAX_RESTART_ATTEMPTS = 3
RESTART_INTERVAL_MINUTES = 10
BACKOFF_BASE_WAIT_SECONDS = 5

def restart_service_windows(service_name):
    """Restart a Windows service safely using sc.exe (PowerShell‐safe)."""
    try:
        start_result = subprocess.run(["sc.exe", "start", service_name], capture_output=True, text=True)
        if "Access is denied" in start_result.stderr:
            return False, "Access denied: Run as Administrator."

        result = subprocess.run(["sc.exe", "query", service_name], capture_output=True, text=True)
        if result.returncode != 0:
            return False, result.stderr.strip()

        for line in result.stdout.splitlines():
            if "STATE" in line and "RUNNING" in line:
                return True, result.stdout.strip()
        return False, result.stdout.strip()
    except Exception as e:
        return False, str(e)


def restart_service_linux(service_name):
    """Restart a systemd service on Linux."""
    try:
        result = subprocess.run(["sudo", "systemctl", "restart", service_name], capture_output=True, text=True)
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)





# @lru_cache(maxsize=512)
# def restart_candidate_linux(unit: str, norm_status: str) -> bool:
#     """
#     Return True only for daemons we expect to stay up and whose
#     normalised status says 'stopped' or 'failed'.
#     """
#     if norm_status not in {"stopped", "failed"}:
#         return False                       # still running / oneshot completed
#
#     show = subprocess.run(
#         ["systemctl", "show", unit,
#          "--property=Type,UnitFileState,SubState", "--value", "--no-pager"],
#         capture_output=True, text=True
#     )
#     if show.returncode:
#         return False                       # unknown unit – be safe, skip
#
#     unit_type, enabled_state, sub_state = (
#         show.stdout.strip().splitlines() + ["", "", ""])[:3]
#
#     return (
#         enabled_state == "enabled" and
#         unit_type.lower() in {"simple", "forking"} and
#         sub_state in {"dead", "failed", "auto-restart"}
#     )



# @lru_cache(maxsize=256)
# def restart_candidate_linux(unit: str, norm_status: str) -> bool:
#     if norm_status not in {"stopped", "failed"}:
#         return False
#
#     show = subprocess.run(
#         ["systemctl", "show", unit,
#          "--property=Type,UnitFileState,SubState",
#          "--no-pager"],
#         capture_output=True, text=True
#     )
#     if show.returncode:
#         return False            # unknown unit → skip
#
#     if "Type=oneshot" in show.stdout:
#         return False            # completed helper → never restart
#
#     props = {}
#     for line in show.stdout.splitlines():
#         if "=" in line:
#             k, v = line.split("=", 1)
#             props[k] = v.lower()
#
#     return (
#         props.get("UnitFileState") == "enabled" and
#         props.get("Type") in {"simple", "forking"} and
#         props.get("SubState") in {"dead", "failed", "auto-restart"}
#     )

def is_passive_or_oneshot_service(service_name):
    """Detects services that are timer-triggered, oneshot, or auto-dead after success."""
    try:
        # Check if the service is tied to a timer
        result_timer = subprocess.run(
            ["systemctl", "show", service_name, "--property=TriggeredBy"],
            capture_output=True, text=True
        )
        if "apt-daily.timer" in result_timer.stdout:
            return True  # timer-based service

        # Check type
        result_type = subprocess.run(
            ["systemctl", "show", service_name, "--property=Type"],
            capture_output=True, text=True
        )
        service_type = result_type.stdout.strip().split("=")[-1]
        return service_type in ("oneshot", "simple")

    except Exception as e:
        print(f"[WARN] Couldn't determine nature of {service_name}: {e}")
        return False  # Assume recoverable if unknown







def attempt_service_recovery():
    """Attempt to recover **one** failed service per call (sequential processing)."""
    platform_name = platform.system()
    approved_services = load_approved_services()

    for service_name, status, hostname, sub_state, service_type, unit_file_state, recoverable in db_access_for_service_recovery():

        if status not in ("stopped", "failed"):
            continue  # skip healthy services

        if service_name not in approved_services:
            log_unclassified_service(
                (service_name, status, hostname, sub_state, service_type, unit_file_state, recoverable),
                reason="Not in approved_services"
            )
            continue

        if not recoverable:
            print(f"[SKIP] {service_name}: not recoverable")
            continue

        # --- rate‑limit check (DB‑based) ----------------------------------
        recent_attempts = count_recent_restart_attempts(service_name, minutes=RESTART_INTERVAL_MINUTES)
        if recent_attempts >= MAX_RESTART_ATTEMPTS:
            print(f"[WARN] Too many restart attempts for {service_name}, skipping this cycle …")
            return  # process only one service per run

        # --- exponential back‑off ----------------------------------------
        if recent_attempts > 0:
            wait_time = BACKOFF_BASE_WAIT_SECONDS * (2 ** (recent_attempts - 1))
            print(f"[INFO] Waiting {wait_time}s before retrying {service_name}")
            time.sleep(wait_time)

        print(f"[INFO] Attempting to restart {service_name} on {hostname}")
        if platform_name == "Windows":
            success, msg = restart_service_windows(service_name)
        else:
            success, msg = restart_service_linux(service_name)

        # --- logging ------------------------------------------------------
        result = "success" if success else "fail"

        log_restart_attempt({
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": hostname,
            "service_name": service_name
        })

        log_recovery([{  # batch format
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": hostname,
            "os_platform": platform_name,
            "service_name": service_name,
            "result": result,
            "error_message": msg
        }])

        if success:
            print(f"[INFO] Successfully restarted {service_name}: {msg}")
            mark_service_running(service_name, hostname, platform_name)
        else:
            print(f"[ERROR] Failed to restart {service_name}: {msg}")
            log_alert({
                "hostname": hostname,
                "severity": "warning",
                "source": "Service Recovery",
                "message": f"Failed to recover {service_name}: {msg}"
            })

        return  # process only ONE service this cycle

    # If no services needed recovery
    print("[INFO] No stopped/failed services detected in this cycle.")


# -------------------------
# Main scheduler loop
# -------------------------
if __name__ == "__main__":
    print("[INFO] Starting Service Recovery …")
    try:
        while True:
            try:
                attempt_service_recovery()
            except Exception as exc:
                print(f"[ERROR] attempt_service_recovery crashed: {exc}")
                traceback.print_exc()
            # wait before next service check
            print("[INFO] Sleeping 60s …")
            time.sleep(60)
    except KeyboardInterrupt:
        print("[INFO] Service Recovery stopped by user.")




