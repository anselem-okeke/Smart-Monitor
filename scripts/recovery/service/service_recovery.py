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
import argparse
import os, sys
import shutil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
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
from db.db_logger import log_alert, log_recovery, log_restart_attempt
from utils.config_utils import load_approved_services
from utils.log_utils import log_unclassified_service

# Constants
MAX_RESTART_ATTEMPTS = 3
RESTART_INTERVAL_MINUTES = 10
BACKOFF_BASE_WAIT_SECONDS = 2
MAX_BACKOFF_SECONDS = 8  # cap


def restart_service_windows(service_name: str, timeout_s: int = 25):
    try:
        # Stop (don’t fail if already stopped); cap time spent
        subprocess.run(["sc.exe", "stop", service_name],
                       capture_output=True, text=True, timeout=10)

        # Start with bounded time
        start = subprocess.run(["sc.exe", "start", service_name],
                               capture_output=True, text=True, timeout=10)
        if "Access is denied" in (start.stderr or ""):
            return False, "Access denied: Run as Administrator."

        # Poll RUNNING state with an overall timeout
        deadline = time.time() + timeout_s
        last = None
        while time.time() < deadline:
            q = subprocess.run(["sc.exe", "query", service_name],
                               capture_output=True, text=True, timeout=5)
            last = q.stdout
            line = next((l for l in last.splitlines() if "STATE" in l), "")
            if "RUNNING" in line:
                return True, last
            if "STOPPED" in line:
                break
            time.sleep(1)

        return False, last or "Service didn’t reach RUNNING before timeout"
    except subprocess.TimeoutExpired:
        return False, "sc.exe timed out"
    except Exception as e:
        return False, str(e)


# def restart_service_windows(service_name):
#     """Restart a Windows service safely using sc.exe (PowerShell‐safe)."""
#     try:
#         start_result = subprocess.run(["sc.exe", "start", service_name], capture_output=True, text=True)
#         if "Access is denied" in start_result.stderr:
#             return False, "Access denied: Run as Administrator."
#
#         result = subprocess.run(["sc.exe", "query", service_name], capture_output=True, text=True)
#         if result.returncode != 0:
#             return False, result.stderr.strip()
#
#         for line in result.stdout.splitlines():
#             if "STATE" in line and "RUNNING" in line:
#                 return True, result.stdout.strip()
#         return False, result.stdout.strip()
#     except Exception as e:
#         return False, str(e)

# def restart_service_linux(service_name: str, timeout_s: int = 20):
#     try:
#         # Don’t block on restart; we’ll poll
#         subprocess.run(["systemctl", "reset-failed", service_name],
#                        capture_output=True, text=True, timeout=5)
#         subprocess.run(["systemctl", "restart", "--no-block", service_name],
#                        capture_output=True, text=True, timeout=5)
#
#         # Poll ActiveState with an overall timeout
#         deadline = time.time() + timeout_s
#         last = None
#         while time.time() < deadline:
#             q = subprocess.run(["systemctl", "is-active", service_name],
#                                capture_output=True, text=True, timeout=5)
#             state = (q.stdout or "").strip()
#             if state == "active":
#                 return True, "active"
#             if state in ("failed", "inactive"):
#                 break
#             time.sleep(1)
#
#         # Grab a short journal tail to explain failure
#         j = subprocess.run(["journalctl", "-u", service_name, "-n", "20", "--no-pager"],
#                            capture_output=True, text=True, timeout=5)
#         return False, (j.stdout or "Service didn’t reach active before timeout")[-2000:]
#     except subprocess.TimeoutExpired:
#         return False, "systemctl timed out"
#     except Exception as e:
#         return False, str(e)


def restart_service_linux(service_name: str, timeout_s: int = 20):
    WRAPPER = "/usr/local/bin/smartmon-restart-service"
    unit = service_name if service_name.endswith(".service") else f"{service_name}.service"

    # If we're root, don't use sudo or the wrapper—just call systemctl directly.
    if os.geteuid() == 0:
        cmd = ["/bin/systemctl", "restart", unit]
        check = ["/bin/systemctl", "is-active", "--quiet", unit]
    else:
        if shutil.which(WRAPPER):
            cmd = ["sudo", "-n", WRAPPER, unit]
            check = ["sudo", "-n", "/bin/systemctl", "is-active", "--quiet", unit]
        else:
            # Fallback: try sudo systemctl directly (requires sudoers permission)
            cmd = ["sudo", "-n", "/bin/systemctl", "restart", unit]
            check = ["sudo", "-n", "/bin/systemctl", "is-active", "--quiet", unit]

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        if r.returncode != 0:
            msg = (r.stderr or r.stdout or "restart failed").strip()
            if "a password is required" in msg.lower():
                msg = "sudo needs a password (add NOPASSWD or run orchestrator as root)."
            if "command not found" in msg.lower() and WRAPPER in " ".join(cmd):
                msg = f"wrapper missing on host: {WRAPPER}"
            return False, msg

        # verify it came back up
        rc = subprocess.run(check, capture_output=True, text=True, timeout=5).returncode
        return (rc == 0), ("restart requested" if rc == 0 else "service not active after restart")
    except subprocess.TimeoutExpired:
        return False, "restart timed out"
    except Exception as e:
        return False, str(e)
#
# def restart_service_linux(service_name: str, timeout_s: int = 20):
#     try:
#         # DO NOT call "systemctl reset-failed" here
#         r = subprocess.run(
#             ["sudo", "-n", "/usr/local/bin/smartmon-restart-service", service_name],
#             capture_output=True, text=True, timeout=10
#         )
#         if r.returncode != 0:
#             return False, r.stderr.strip() or "Restart failed"
#         # (poll is-active for up to timeout_s if you want)
#         return True, "restart requested"
#     except subprocess.TimeoutExpired:
#         return False, "systemctl timed out"
#     except Exception as e:
#         return False, str(e)

# def restart_service_linux(service_name: str):
#     """Restart a systemd service on Linux via safe wrapper (no password prompts)."""
#     try:
#         result = subprocess.run(
#             ["sudo", "-n", "/usr/local/bin/smartmon-restart-service", service_name],
#             capture_output=True, text=True
#         )
#         if result.returncode == 0:
#             return True, result.stdout.strip() or f"{service_name} restarted successfully"
#         return False, result.stderr.strip() or f"Failed to restart {service_name}"
#     except Exception as e:
#         return False, str(e)

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
        # if recent_attempts > 0:
        #     wait_time = BACKOFF_BASE_WAIT_SECONDS * (2 ** (recent_attempts - 1))
        #     print(f"[INFO] Waiting {wait_time}s before retrying {service_name}")
        #     time.sleep(wait_time)

        if recent_attempts > 0:
            wait_time = min(BACKOFF_BASE_WAIT_SECONDS * (2 ** (recent_attempts - 1)), MAX_BACKOFF_SECONDS)
            print(f"[INFO] Backoff {wait_time}s for {service_name} (attempts={recent_attempts})", flush=True)
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

def handle_service_recovery():
    try:
        attempt_service_recovery()
    except Exception as exc:
        print(f"[ERROR] attempt_service_recovery crashed: {exc}")
        traceback.print_exc()
        # wait before next service check
    print("[INFO] Sleeping 60s …")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process one recovery sweep and exit")
    args = parser.parse_args()

    print("[INFO] Starting Service Recovery …", flush=True)
    try:
        if args.once:
            handle_service_recovery()
        else:
            while True:
                handle_service_recovery()
                time.sleep(60)
    except KeyboardInterrupt:
        print("[INFO] Service Recovery stopped by user.")


# -------------------------
# Main scheduler loop
# -------------------------
if __name__ == "__main__":
    main()
    # print("[INFO] Starting Service Recovery …")
    # try:
    #     while True:
    #         handle_service_recovery()
    #         time.sleep(60)
    # except KeyboardInterrupt:
    #     print("[INFO] Service Recovery stopped by user.")




