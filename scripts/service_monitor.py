import platform
import socket
import subprocess
import time

from db_logger import log_service_status_batch

from datetime import datetime

# def normalize_service_status(os_platform, raw_status):
#     raw_status = raw_status.lower()
#     if os_platform == "Windows":
#         if raw_status == "running":
#             return "active"
#         elif raw_status == "stopped":
#             return "stopped"
#         else:
#             return "unknown"
#     else:
#         active_states = ["running", "exited", "activating", "listening", "waiting", "start"]
#         inactive_states = ["dead", "auto-restart", "inactive"]
#         failed_states = ["failed"]
#
#         if raw_status in active_states:
#             return "active"
#         elif raw_status in inactive_states:
#             return "stopped"
#         elif raw_status in failed_states:
#             return "failed"
#         else:
#             return "unknown"
#
# def collect_service_status():
#     os_platform = platform.system()
#     hostname = socket.gethostname()
#     services = []
#
#     if os_platform == "Windows":
#         try:
#             output = subprocess.check_output("sc query state= all", shell=True, text=True)
#             service_name, state = None, None
#
#             for line in output.splitlines():
#                 line = line.strip()
#
#                 # Pick up the current SERVICE_NAME
#                 if line.startswith("SERVICE_NAME:"):
#                     service_name = line.partition(":")[2].strip()
#
#                 # Pick up the STATE numeric + word (e.g. 1  STOPPED)
#                 elif line.startswith("STATE") and service_name:
#                     # after the colon you get “4  RUNNING” or “1  STOPPED”
#                     after_colon = line.partition(":")[2].strip()
#                     # split once → num  word
#                     parts = after_colon.split(None, 1)
#                     if len(parts) == 2:
#                         state = parts[1].strip()  # RUNNING / STOPPED / START_PENDING …
#
#                         normalized = normalize_service_status("Windows", state)
#                         services.append({
#                             "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
#                             "hostname": hostname,
#                             "os_platform": os_platform,
#                             "service_name": service_name,
#                             "raw_status": state,
#                             "normalized_status": normalized
#                         })
#
#                     # reset for next service block
#                     service_name, state = None, None
#
#
#         # if os_platform == "Windows":
#     #     try:
#     #         output = subprocess.check_output("sc query state= all", shell=True, text=True)
#     #         lines = output.splitlines()
#     #         service_name = None
#     #
#     #         for line in lines:
#     #             line = line.strip()
#     #             if line.startswith("SERVICE_NAME:"):
#     #                 service_name = line.split("SERVICE_NAME:")[1].strip()
#     #             elif line.startswith("STATE") and service_name:
#     #                 # Correct parsing: split on ':' first, then split the value part
#     #                 parts = line.split(":", 1)
#     #                 if len(parts) > 1:
#     #                     status_parts = parts[1].strip().split()
#     #                     if len(status_parts) >= 2:
#     #                         state = status_parts[1].strip()  # Should be 'RUNNING', 'STOPPED', etc.
#     #                         normalized = normalize_service_status("Windows", state)
#     #                         services.append({
#     #                             "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
#     #                             "hostname": socket.gethostname(),
#     #                             "os_platform": os_platform,
#     #                             "service_name": service_name,
#     #                             "raw_status": state,
#     #                             "normalized_status": normalized
#     #                         })
#     #                         service_name = None  # Reset for next
#         except Exception as e:
#             print(f"[ERROR] Failed to collect Windows services: {e}")
#
#
#     else:  # Linux
#         try:
#             # Get plain service names first
#             unit_names = subprocess.check_output(
#                 "systemctl list-unit-files --type=service --no-legend --no-pager",
#                 shell=True, text=True
#             ).splitlines()
#
#             for row in unit_names:
#                 # each row: "cron.service   nginx.service     enabled"
#                 svc_name = row.split()[0]  # always first token
#
#                 if '@' in svc_name and not svc_name.rstrip().endswith('.service'):
#                     continue
#                 try:
#                     svc_show = subprocess.check_output(
#                         f"systemctl show {svc_name} --property=ActiveState --value",
#                         shell=True, text=True
#                     ).strip()  # e.g. "active", "inactive", "failed"
#
#                     raw_status = svc_show.lower()
#                     normalized = normalize_service_status("Linux", raw_status)
#
#                     services.append({
#                         "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
#                         "hostname": hostname,
#                         "os_platform": os_platform,
#                         "service_name": svc_name,
#                         "raw_status": raw_status,
#                         "normalized_status": normalized
#                     })
#                 except subprocess.CalledProcessError as svc_err:
#                     print(f"[WARN] Could not query {svc_name}: {svc_err.stderr.strip()}")
#
#         except Exception as e:
#             print(f"[ERROR] Failed to collect Linux services: {e}")
#
#         #     output = subprocess.check_output(
#         #         "systemctl list-units --type=service --no-legend --no-pager",
#         #         shell=True, text=True
#         #     )
#         #     for line in output.splitlines():
#         #         parts = line.split(None, 4)  # Split into at most 5 parts
#         #         if len(parts) >= 4:
#         #             service_name = parts[0]
#         #             raw_status = parts[3]  # This is the ACTIVE column
#         #             normalized = normalize_service_status("Linux", raw_status)
#         #
#         #             services.append({
#         #                 "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
#         #                 "hostname": hostname,
#         #                 "os_platform": os_platform,
#         #                 "service_name": service_name,
#         #                 "raw_status": raw_status,
#         #                 "normalized_status": normalized
#         #             })
#         # except Exception as e:
#         #     print(f"[ERROR] Failed to collect Linux services: {e}")
#
#     return services
#
# if __name__ == '__main__':
#     print(f"[INFO] Starting Service Monitor...")
#     try:
#         while True:
#             process_data = collect_service_status()
#             log_service_status_batch(process_data)
#             print("[INFO] Service status logged successfully")
#             time.sleep(60)
#     except KeyboardInterrupt:
#         print("[INFO] Service monitory stopped by user.")














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
# def collect_windows_services() -> list:
#     services = []
#     try:
#         output = subprocess.check_output("sc.exe query state= all", shell=True, text=True)
#         service_name = None
#         for line in output.splitlines():
#             line = line.strip()
#             if line.startswith("SERVICE_NAME:"):
#                 service_name = line.partition(":")[2].strip()
#             elif line.startswith("STATE") and service_name:
#                 # "STATE              : 1  STOPPED" → split once after ':'
#                 parts = line.partition(":")[2].strip().split(None, 1)
#                 if len(parts) == 2:
#                     raw_state = parts[1].strip()  # e.g. RUNNING / STOPPED / START_PENDING
#                     services.append((service_name, raw_state))
#                 service_name = None
#     except Exception as exc:
#         print(f"[ERROR] Windows service query failed: {exc}")
#     return services
#
#
# def collect_linux_services() -> list:
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
#             # Skip template units without concrete instance
#             if svc_name.endswith("@.service"):
#                 continue
#             res = subprocess.run([
#                 "systemctl", "show", svc_name, "--property=ActiveState", "--value"
#             ], capture_output=True, text=True)
#             if res.returncode != 0:
#                 warn = (res.stderr or res.stdout).strip()
#                 print(f"[WARN] Could not query {svc_name}: {warn}")
#                 continue
#             raw_state = res.stdout.strip()
#             services.append((svc_name, raw_state))
#     except Exception as exc:
#         print(f"[ERROR] Linux service collection failed: {exc}")
#     return services
#
#
# def collect_service_status() -> list:
#     os_platform = platform.system()
#     hostname = socket.gethostname()
#
#     if os_platform == "Windows":
#         collected = collect_windows_services()
#     else:
#         collected = collect_linux_services()
#
#     rows = []
#     for svc_name, raw_state in collected:
#         rows.append({
#             "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
#             "hostname": hostname,
#             "os_platform": os_platform,
#             "service_name": svc_name,
#             "raw_status": raw_state.lower(),
#             "normalized_status": normalize_service_status(os_platform, raw_state),
#         })
#     return rows

















def normalize_service_status(os_platform: str, raw_status: str) -> str:
    raw_status = raw_status.lower()

    if os_platform == "Windows":
        return "active" if raw_status == "running" else "stopped" if raw_status == "stopped" else "unknown"

    # Linux mapping
    active_states = {"active", "running", "exited", "listening", "waiting", "start", "activating"}
    inactive_states = {"dead", "inactive", "auto-restart"}
    failed_states = {"failed"}

    if raw_status in active_states:
        return "active"
    if raw_status in inactive_states:
        return "stopped"
    if raw_status in failed_states:
        return "failed"
    return "unknown"


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
                    # Dummy values for unsupported metadata on Windows
                    services.append((service_name, raw_state, "unknown", "unknown", "unknown", True))
                service_name = None
    except Exception as exc:
        print(f"[ERROR] Windows service query failed: {exc}")
    return services

def collect_linux_services():
    services = []
    try:
        unit_rows = subprocess.check_output(
            "systemctl list-unit-files --type=service --no-legend --no-pager",
            shell=True, text=True
        ).splitlines()

        for row in unit_rows:
            row = row.strip()
            if not row:
                continue
            svc_name = row.split()[0]
            if svc_name.endswith("@.service"):
                continue

            res = subprocess.run([
                "systemctl", "show", svc_name,
                "--property=ActiveState,SubState,Type,UnitFileState"
            ], capture_output=True, text=True)

            if res.returncode != 0:
                warn = (res.stderr or res.stdout).strip()
                print(f"[WARN] Could not query {svc_name}: {warn}")
                continue

            parsed = dict(
                (key.strip(), value.strip())
                for line in res.stdout.strip().splitlines() if "=" in line
                for key, value in [line.split("=", 1)]
            )

            active_state = parsed.get("ActiveState", "unknown")
            sub_state = parsed.get("SubState", "unknown")
            service_type = parsed.get("Type", "unknown")
            unit_file_state = parsed.get("UnitFileState", "unknown")

            recoverable = (
                service_type not in ["oneshot", "notify"] and
                unit_file_state not in ["static", "masked"]
            )

            services.append((svc_name, active_state, sub_state, service_type, unit_file_state, recoverable))
    except Exception as exc:
        print(f"[ERROR] Linux service collection failed: {exc}")
    return services

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
            "raw_status": active_state.lower(),
            "normalized_status": normalize_service_status(os_platform, active_state),
            "sub_state": sub_state,
            "service_type": service_type,
            "unit_file_state": unit_file_state,
            "recoverable": str(recoverable)
        })
    return rows

if __name__ == "__main__":
    print("[INFO] Service Monitor starting …")
    try:
        while True:
            batch = collect_service_status()
            if batch:
                log_service_status_batch(batch)
                print(f"[INFO] Logged {len(batch)} service rows → DB; sleeping 60s...")
            else:
                print("[INFO] No services collected this cycle; sleeping 60s...")
            time.sleep(60)
    except KeyboardInterrupt:
        print("[INFO] Service Monitor stopped by user.")














