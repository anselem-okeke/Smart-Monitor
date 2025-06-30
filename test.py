import os
import json
import platform

import psutil

# Absolute path to config/db_config.json from root
# CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "config", "db_config.json"))
#
# with open(CONFIG_PATH, "r") as file:
#     config = json.load(file)
#
# DB_PATH = config["path"]
#
# print(DB_PATH)
MONITORED_SERVICES = [
    "nginx", "docker"
]

# def monitored_services():
#     monitored = set()
#     for proc in psutil.process_iter(['name']):
#         try:
#             if proc.status() in ('running', 'sleeping', 'idle'):
#                 monitored.add(proc.name())
#         except (psutil.NoSuchProcess, psutil.AccessDenied):
#             continue
#     return list(monitored)
#
#
#
#
#
#
def get_service_status(service_name):
    if platform.system() == "Windows":
        import subprocess
        try:
            result = subprocess.check_output(["sc", "query", service_name], text=True)
            if "RUNNING" in result:
                return "running"
            elif "STOPPED" in result:
                return "stopped"
        except subprocess.CalledProcessError:
            return "not found"

    else:
        for proc in psutil.process_iter(['name']):
            if proc.name() == service_name:
                if proc.status() not in ("zombie",):
                    return "running"
        return "stopped"
#
# statuses = []
#
# for i in monitored_services():
#     status = get_service_status(i)
#     statuses.append(status)
# print(statuses)
#
#
# # x = psutil.process_iter(['name'])
# # for i in x:
# #     print(i)
#
# print(monitored_services())



import platform
import psutil
import subprocess
#
# def monitored_services():
#     monitored = set()
#
#     if platform.system() == "Windows":
#         try:
#             # Query all services with their states
#             output = subprocess.check_output("sc query state= all", shell=True, text=True)
#
#             service_name = None
#             for line in output.splitlines():
#                 line = line.strip()
#                 if line.startswith("SERVICE_NAME:"):
#                     service_name = line.split(":", 1)[1].strip()
#                 elif line.startswith("STATE") and "RUNNING" in line:
#                     if service_name:
#                         monitored.add(service_name)
#         except subprocess.CalledProcessError:
#             pass
#
#     else:
#         for proc in psutil.process_iter(['name']):
#             try:
#                 if proc.status() in ('running', 'sleeping', 'idle'):
#                     monitored.add(proc.name())
#             except (psutil.NoSuchProcess, psutil.AccessDenied):
#                 continue
#
#     return list(monitored)
#
# print(monitored_services())

# output = subprocess.check_output("sc query state= all", shell=True, text=True)
# for line in output.splitlines():
#     if line.startswith("SERVICE_NAME:"):
#         service_name = line.split()[1]
#         # print(service_name)
# print(output.splitlines())

import psutil
import platform

def get_load_indicator():
    if platform.system() == "Windows":
        return psutil.cpu_percent(interval=1)  # Alternative metric
    else:
        return psutil.getloadavg()[0]  # 1-minute load avg on Linux
print(get_load_indicator())
