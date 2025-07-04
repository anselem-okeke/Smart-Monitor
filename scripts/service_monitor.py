import platform
import socket
import subprocess
import time

from db_logger import log_service_status_batch

from datetime import datetime

def normalize_service_status(os_platform, raw_status):
    raw_status = raw_status.lower()
    if os_platform == "Windows":
        if raw_status == "running":
            return "active"
        elif raw_status == "stopped":
            return "stopped"
        else:
            return "unknown"
    else:
        active_states = ["running", "exited", "activating", "listening", "waiting", "start"]
        inactive_states = ["dead", "auto-restart", "inactive"]
        failed_states = ["failed"]

        if raw_status in active_states:
            return "active"
        elif raw_status in inactive_states:
            return "stopped"
        elif raw_status in failed_states:
            return "failed"
        else:
            return "unknown"

def collect_service_status():
    os_platform = platform.system()
    hostname = socket.gethostname()
    services = []

    if os_platform == "Windows":
        try:
            output = subprocess.check_output("sc query state= all", shell=True, text=True)
            lines = output.splitlines()
            service_name = None

            for line in lines:
                line = line.strip()
                if line.startswith("SERVICE_NAME:"):
                    service_name = line.split("SERVICE_NAME:")[1].strip()
                elif line.startswith("STATE") and service_name:
                    # Correct parsing: split on ':' first, then split the value part
                    parts = line.split(":", 1)
                    if len(parts) > 1:
                        status_parts = parts[1].strip().split()
                        if len(status_parts) >= 2:
                            state = status_parts[1].strip()  # Should be 'RUNNING', 'STOPPED', etc.
                            normalized = normalize_service_status("Windows", state)
                            services.append({
                                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                                "hostname": socket.gethostname(),
                                "os_platform": os_platform,
                                "service_name": service_name,
                                "raw_status": state,
                                "normalized_status": normalized
                            })
                            service_name = None  # Reset for next
        except Exception as e:
            print(f"[ERROR] Failed to collect Windows services: {e}")


    else:  # Linux
        try:
            output = subprocess.check_output(
                "systemctl list-units --type=service --no-legend --no-pager",
                shell=True, text=True
            )
            for line in output.splitlines():
                parts = line.split(None, 4)  # Split into at most 5 parts
                if len(parts) >= 4:
                    service_name = parts[0]
                    raw_status = parts[3]  # This is the ACTIVE column
                    normalized = normalize_service_status("Linux", raw_status)

                    services.append({
                        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                        "hostname": hostname,
                        "os_platform": os_platform,
                        "service_name": service_name,
                        "raw_status": raw_status,
                        "normalized_status": normalized
                    })
        except Exception as e:
            print(f"[ERROR] Failed to collect Linux services: {e}")

    return services

if __name__ == '__main__':
    print(f"[INFO] Starting Service Monitor...")
    try:
        while True:
            process_data = collect_service_status()
            log_service_status_batch(process_data)
            print("[INFO] Service status logged successfully")
            time.sleep(60)
    except KeyboardInterrupt:
        print("[INFO] Service monitory stopped by user.")
