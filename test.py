import time
from datetime import timedelta,datetime
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
# MONITORED_SERVICES = [
#     "nginx", "docker"
# ]

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
# def get_service_status(service_name):
#     if platform.system() == "Windows":
#         import subprocess
#         try:
#             result = subprocess.check_output(["sc", "query", service_name], text=True)
#             if "RUNNING" in result:
#                 return "running"
#             elif "STOPPED" in result:
#                 return "stopped"
#         except subprocess.CalledProcessError:
#             return "not found"
#
#     else:
#         for proc in psutil.process_iter(['name']):
#             if proc.name() == service_name:
#                 if proc.status() not in ("zombie",):
#                     return "running"
#         return "stopped"
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

# import psutil
# import platform
#
# def get_load_indicator():
#     if platform.system() == "Windows":
#         return psutil.cpu_percent(interval=1)  # Alternative metric
#     else:
#         return psutil.getloadavg()[0]  # 1-minute load avg on Linux
# print(get_load_indicator())

# result = subprocess.run(
#     ["ping", "-n", "4", "192.168.56.11"],
#     stdout=subprocess.PIPE,
#     stderr=subprocess.PIPE,
#     text=True,
#     timeout=10
# )
# new_val = []
# x = result.stdout.splitlines()
# for line in x:
#     if "Average =" in line:
#         parts = line.split(",")
#         for part in parts:
#             part = part.strip()
#             print(part)
#             if part.startswith("Average"):
#                 value = float(part.split("=")[-1].strip().replace("ms", ""))
#                 print(value)
#         parts = line.strip().split(" ")
#         print(parts)
#         for part in parts:
#             if "Average" in part:
#                 continue
#             if "ms" in part:
#                 ms_val = float(part.replace("ms", "").replace(",", ""))
#                 new_val.append(ms_val)
#
# print(new_val[2])

# system = platform.system().lower()
# print(system)
# traceroute_cmd = "tracert" if system == "windows" else "traceroute"
#
# result = subprocess.run(
#     [traceroute_cmd, "192.168.56.11"],
#     stdout=subprocess.PIPE,
#     stderr=subprocess.PIPE,
#     text=True,
#     timeout=30
# )


# import sqlite3
# conn = sqlite3.connect("db/smart_factory_monitor.db")
# cursor = conn.cursor()
# cursor.execute("SELECT DISTINCT hostname FROM system_metrics")
# # print(cursor.fetchall())


#
# CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "config", "db_config.json"))
# with open(CONFIG_PATH, "r") as f:
#     config = json.load(f)
#     print(config)
# print(CONFIG_PATH)
#
# DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "./" + config["path"]))

# resulti = subprocess.run(
#     ["systemctl", "list-units", "--type=service", "--no-legend", "--all"],
#     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
# )

# result = subprocess.run(
#     ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--no-pager"],
#     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
# )
# services = set()
# for line in result.stdout.splitlines():
#     parts = line.split()
#     if parts:
#         svcc = parts[0]
#         if svcc.endswith(".service"):
#             services.add(svcc.replace(".service", ""))



import psutil
import platform

# def monitored_processes():
#     processes = []
#
#     for proc in psutil.process_iter(['cpu_percent', 'memory_percent']):
#         try:
#             processes.append({
#                 "cpu_percent": proc.info['cpu_percent'],
#                 "memory_percent": proc.info['memory_percent']
#             })
#         except (psutil.NoSuchProcess, psutil.AccessDenied):
#             continue
#
#     return processes
# print(monitored_processes())

def monitored_processes():
    processes = []

    # First call primes internal CPU counters
    for proc in psutil.process_iter():
        try:
            proc.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    time.sleep(1)  # Allow CPU measurement to accumulate

    # Second call gives meaningful values
    for proc in psutil.process_iter(['cpu_percent', 'memory_percent']):
        try:
            processes.append({
                "cpu_percent": proc.cpu_percent(interval=None),  # now this gives a real %
                "memory_percent": proc.info['memory_percent']
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return processes

# output = subprocess.check_output("sc query state= all", shell=True, text=True)
# x =output.splitlines()
# for i in x:
#     print(i)
# output = subprocess.check_output("systemctl list-units --type=service --no-pager", shell=True, text=True)
# x = output.splitlines()[1:]
# for i in x:
#     print(i.split()[0])
# for procc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_percent']):
#     print(procc)


output = subprocess.check_output("sc query state= all", shell=True, text=True)
lines = output.splitlines()
service_name = None
for line in lines:
    if line.startswith("STATE:"):
        print(line)
        service_name = line.split("SERVICE_NAME:")[1].strip()
    elif line.startswith("STATE") and service_name:
        print(f"{service_name}={line}")