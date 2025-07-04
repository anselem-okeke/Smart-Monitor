#------------------------------------------
"""Author: Anselem Okeke"""
#------------------------------------------
import json
import os
import platform
import socket
import sqlite3
import subprocess
import time

from datetime import datetime, timedelta
from db_logger import log_alert


CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config/db_config.json"))
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", config['path']))

hostname = socket.gethostname()

def get_valid_sytemd_services():
    try:
        result = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--no-pager"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        services = set()
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts:
                svcc = parts[0]
                if svcc.endswith(".service"):
                    services.add(svcc.replace(".service",""))
        return services
    except Exception as e:
        print(f"[ERROR] get_valid_systemd_services: {e}")
        return set()
def get_valid_window_services():
    try:
        result = subprocess.run(
            ["powershell", "-Command", "Get-Service | Select-Object -ExpandProperty Name"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return set(line.strip() for line in result.stdout.splitlines() if line.strip())
        else:
            print(f"[ERROR] Failed to get windows services: {result.stderr.strip()}")
            return set()
    except Exception as e:
        print(f"[ERROR] get_valid_windows_services: {e}")
        return set()

def get_stopped_services():
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT service_name
            FROM service_status
            WHERE status = 'stopped' AND host = ?
            ORDER BY timestamp DESC
        """, (hostname,))
        rows = cursor.fetchall()
        conn.close()
        return [row[0] for row in rows]
    except Exception as e:
        print(f"[ERROR] Fetching stopped services: {e}")
        return []

# def log_recovery(service_name, result, error=None):
def log_recovery(entry):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO recovery_logs (timestamp, hostname, service_name, result, error_message)
            VALUES (?, ?, ?, ?, ?)
        """, (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
              entry["hostname"],
              entry["service_name"],
              entry["result"],
              entry["error_message"]
              ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ERROR] Logging recovery attempt: {e}")

def too_many_failures(service_name, limit=3, within_minutes=1440):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        time_threshold = datetime.utcnow() - timedelta(minutes=within_minutes)
        cursor.execute("""
            SELECT COUNT(*) FROM recovery_logs
            WHERE hostname = ? AND service_name = ? AND result = 'fail' AND timestamp > ?
        """, (hostname, service_name, time_threshold.isoformat()))
        count = cursor.fetchone()[0]
        conn.close()
        return count >= limit
    except Exception as e:
        print(f"[WARN] Failed to check failure count: {e}")
        return False

def attempt_recovery(service_name):
    try:
        if platform.system() == "Windows":
            #check if windows service already running
            status_check = subprocess.run(
                ["powershell", "-Command", f"(Get-Service -Name '{service_name}').Status"],
                capture_output=True, text=True
            )
            if "Running" in status_check.stdout:
                print(f"[INFO] Already running: {service_name}")
                result = "already_running"
            else:
                result = subprocess.run(
                    ["powershell", "-Command", f"Start-Service -Name '{service_name}'"],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    result = "sucess"
                else:
                    raise Exception(result.stderr.strip())
        else:
            res = subprocess.run(
                ["sudo", "systemctl", "start", service_name],
                capture_output=True, text=True
            )
            if res.returncode == 0:
                result = "success"
            else:
                raise Exception(res.stderr.strip())
        print(f"[INFO] Recovered service: {service_name}")

        log_recovery({
            "hostname": hostname,
            "service_name": service_name,
            "result": result,
            "error_message": None
        })

    except Exception as e:
        print(f"[ERROR] Restart failed: {e}")
        log_recovery({
            "hostname": hostname,
            "service_name": service_name,
            "result": "fail",
            "error_message ": str(e)
        })

        log_alert({
            "hostname": hostname,
            "severity": "critical",
            "source": f"recovery:{service_name}",
            "message": f"Recovery failed: {e}"
        })

# def restart_service(service_name):
#     if too_many_failures(service_name):
#         print(f"[SKIP] Too many failed attempts for: {service_name}")
#         return
#
#     system = platform.system()
#     try:
#         if system == "Windows":
#             subprocess.run(["sc", "start", service_name], check=True)
#         else:
#             subprocess.run(["sudo", "systemctl", "start", service_name], check=True)
#         print(f"[INFO] Restarted service: {service_name}")
#         log_recovery(service_name, "success")
#     except subprocess.CalledProcessError as e:
#         error_msg = f"Restart failed: {e}"
#         print(f"[ERROR] {error_msg}")
#         log_recovery(service_name, "fail", error_msg)
#         log_alert({
#             "hostname": hostname,
#             "severity": "critical",
#             "source": f"recovery:{service_name}",
#             "message": f"Failed to restart service: {service_name}"
#         })
#     except Exception as e:
#         error_msg = f"Unexpected error: {e}"
#         print(f"[ERROR] {error_msg}")
#         log_recovery(service_name, "fail", error_msg)


if __name__ == "__main__":
    print("[INFO] Smart Recovery Tool started...")
    try:
        while True:
            failed_services = get_stopped_services()

            #determine valid services
            if platform.system() == "Windows":
                valid_services = get_valid_window_services()
            else:
                valid_services = get_valid_sytemd_services()

            for svc in failed_services:
                if svc not in valid_services:
                    print(f"[SKIP] {svc} not found in system-manged services.")
                    continue

                if too_many_failures(svc):
                    print(f"[WARN] Skipping recovery for {svc} due to repeated failures.")
                    continue

                attempt_recovery(svc)
            time.sleep(60)
    except KeyboardInterrupt:
        print("[INFO] Recovery tool stopped by user.")
