import ipaddress
import pathlib
import re
import shutil
import socket
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


# output = subprocess.check_output("sc query state= all", shell=True, text=True)
# lines = output.splitlines()
# service_name = None
# for line in lines:
#     if line.startswith("STATE:"):
#         print(line)
#         service_name = line.split("SERVICE_NAME:")[1].strip()
#     elif line.startswith("STATE") and service_name:
#         print(f"{service_name}={line}")


# CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "./scripts/checkservice.txt"))
#
# with open(CONFIG_PATH, "r") as f:
#     for line in f:
#         x = line.strip().splitlines()
#         print(x.__str__())


# unit_names = subprocess.check_output(
#             "systemctl list-unit-files --type=service --no-legend --no-pager",
#             shell=True, text=True
#         ).splitlines()
#
# for i in unit_names:
#     print(i.split()[0])



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
# def collect_linux_services():
#     raw_state = None
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
#             services.append(raw_state)
#     except Exception as exc:
#         print(f"[ERROR] Linux service collection failed: {exc}")
#     return services
#
# print(collect_linux_services())

def collect_linux_services() -> list:
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

            # Get detailed properties
            props = subprocess.run([
                "systemctl", "show", svc_name,
                "--property=ActiveState,SubState,Type,UnitFileState"
            ], capture_output=True, text=True)

            if props.returncode != 0:
                print(f"[WARN] Could not query {svc_name}")
                continue

            parsed = dict(
                (key.strip(), value.strip())
                for line in props.stdout.strip().splitlines()
                if "=" in line
                for key, value in [line.split("=", 1)]
            )
            raw_state = parsed.get("ActiveState", "unknown")
            sub_state = parsed.get("SubState", "unknown")
            service_type = parsed.get("Type", "unknown")
            unit_state = parsed.get("UnitFileState", "unknown")

            # Determine if service is recoverable
            recoverable = (
                service_type not in ["oneshot", "notify"] and
                unit_state not in ["static", "masked"]
            )

            services.append((svc_name, raw_state, sub_state, service_type, unit_state, recoverable))
    except Exception as exc:
        print(f"[ERROR] Linux service collection failed: {exc}")
    return services

iface = subprocess.check_output(
            ["bash", "-c",
             "ip -o link show | awk '$9==\"UP\"{print $2}' | sed 's/://' | head -n1"],
            text=True).strip()


def get_primary_interface_linux() -> str:

    try:
        out = subprocess.check_output(["ip", "route", "get", "1.1.1.1"], text=True)
        parts = out.split()
        if "dev" in parts:
            return parts[parts.index("dev") + 1]
    except Exception as e:
        print(f"[ERROR] Primary interface detection failed: {e}")
    return str(None)


def get_primary():

    try:
        out = subprocess.check_output(["ip", "route", "get", "1.1.1.1"], text=True)
        parts = out.split()
        return parts[4]
    except Exception as e:
        print(f"[ERROR] Primary interface detection failed: {e}")
    return str(None)




def get_all_up_interfaces() -> list:
    try:
        output = subprocess.check_output(
            ["ip", "-o", "link", "show", "up"], text=True)
        interfaces = []
        for line in output.splitlines():
            parts = line.split(":")
            if len(parts) >= 2:
                iface = parts[1].strip()
                if iface != "lo":
                    interfaces.append(iface)
        return interfaces
    except Exception as e:
        print(f"[ERROR] Failed to get interfaces: {e}")
        return []


def is_target_blocked_by_windows_firewall(target_ip: str) -> bool:
    """
    Checks if any enabled Windows Firewall rule blocks the given IP,
    including CIDR ranges (e.g., 192.168.56.0/24).
    """
    if platform.system() != "Windows":
        return False

    try:
        output = subprocess.check_output(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=all"],
            text=True,
            stderr=subprocess.DEVNULL
        ).lower()

        # rules = output.split("rule name:")
        rules = re.split(r"(?i)^rule name:\s*", output, flags=re.MULTILINE)

        for raw_rule in rules:
            rule_lines = raw_rule.strip().splitlines()
            rule_dict = {}

            for line in rule_lines:
                if ":" in line:
                    key, val = line.split(":", 1)
                    rule_dict[key.strip()] = val.strip()

            if (
                rule_dict.get("enabled") == "yes" and
                rule_dict.get("action") == "block"
            ):
                remoteip = rule_dict.get("remoteip", "any")
                try:
                    if remoteip == "any":
                        continue
                    for cidr in remoteip.split(","):
                        if ipaddress.ip_address(target_ip) in ipaddress.ip_network(cidr.strip(), strict=False):
                            print(f"[MATCH] Block rule found for {target_ip} in {cidr}")
                            return True
                except ValueError:
                    continue

        return False

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to check firewall rules: {e}")
        return False

# print(is_target_blocked_by_windows_firewall("192.168.56.14"))
# def _windows_reset_firewall() -> bool:
#     """
#     Resets Windows firewall using dynamically resolved netsh
#     """
#     try:
#         netsh = shutil.which("netsh")
#         if not netsh:
#             print("[ERROR] 'netsh' command not found")
#             return False
#
#         print("[INFO] Resetting Windows firewall using netsh...")
#         return subprocess.call(["netsh", "advfirewall", "firewall", "delete", "rule", "name=TestBlock"]) == 0
#
#         # return subprocess.call([netsh, "advfirewall", "reset"]) == 0
#
#     except Exception as e:
#         print(f"[ERROR] Failed to reset Windows firewall: {e}")
#         return False

# def _windows_reset_firewall(target_ip: str = None) -> bool:
#     """
#     Dynamically finds and deletes only block rules related to the given target IP.
#     If no target_ip is provided, performs a full firewall reset (fallback).
#     """
#     if platform.system() != "Windows":
#         print("[SKIP] Not a Windows system")
#         return False
#
#     try:
#         netsh = shutil.which("netsh")
#         if not netsh:
#             print("[ERROR] 'netsh' command not found")
#             return False
#
#         if target_ip:
#             print(f"[INFO] Searching for firewall block rules targeting {target_ip}...")
#             output = subprocess.check_output(
#                 [netsh, "advfirewall", "firewall", "show", "rule", "name=all"],
#                 text=True, stderr=subprocess.DEVNULL
#             ).lower()
#
#             rules = output.split("rule name:")
#             deleted_any = False
#
#             for rule in rules:
#                 lines = rule.strip().splitlines()
#                 rule_data = {}
#
#                 for line in lines:
#                     if ":" in line:
#                         key, val = line.split(":", 1)
#                         rule_data[key.strip()] = val.strip()
#
#                 if (
#                     rule_data.get("enabled") == "yes" and
#                     rule_data.get("action") == "block" and
#                     target_ip in rule_data.get("remoteip", "")
#                 ):
#                     rule_name = rule_data.get("rule name")
#                     if rule_name:
#                         print(f"[ACTION] Deleting rule: {rule_name}")
#                         subprocess.call([
#                             netsh, "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"
#                         ])
#                         deleted_any = True
#
#             if not deleted_any:
#                 print(f"[INFO] No matching rule found for {target_ip}")
#             return deleted_any
#
#         else:
#             print("[INFO] No target IP provided — resetting entire firewall")
#             return subprocess.call([netsh, "advfirewall", "reset"]) == 0
#
#     except Exception as e:
#         print(f"[ERROR] Failed to reset or clean up Windows firewall: {e}")
#         return False

def _windows_reset_firewall(target_ip: str = None) -> bool:
    """
    Dynamically finds and deletes only block rules related to the given target IP.
    If no target_ip is provided, performs a full firewall reset.
    """
    if platform.system() != "Windows":
        print("[SKIP] Not a Windows system")
        return False

    try:
        netsh = shutil.which("netsh")
        if not netsh:
            print("[ERROR] 'netsh' command not found")
            return False

        if target_ip:
            print(f"[INFO] Searching for firewall block rules targeting {target_ip}...")
            output = subprocess.check_output(
                [netsh, "advfirewall", "firewall", "show", "rule", "name=all"],
                text=True, stderr=subprocess.DEVNULL
            ).lower()

            rules = re.split(r"(?i)^rule name:\s*", output, flags=re.MULTILINE)
            deleted_any = False

            for i, raw_rule in enumerate(rules[1:], 1):  # skip first empty split
                rule_lines = raw_rule.strip().splitlines()
                rule_dict = {}

                for line in rule_lines:
                    if ":" in line:
                        key, val = line.split(":", 1)
                        rule_dict[key.strip().lower()] = val.strip()

                if (
                        rule_dict.get("enabled") == "yes" and
                        rule_dict.get("action") == "block"
                ):
                    remoteip = rule_dict.get("remoteip", "any")
                    try:
                        if remoteip == "any":
                            continue
                        for cidr in remoteip.split(","):
                            if ipaddress.ip_address(target_ip) in ipaddress.ip_network(cidr.strip(), strict=False):
                                rule_name = rule_lines[0].strip()  # First line is actual rule name
                                print(f"[MATCH] Block rule found: {rule_name} for {target_ip}")
                                subprocess.call([
                                    netsh, "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"
                                ])
                                deleted_any = True
                    except ValueError:
                        continue

            if not deleted_any:
                print(f"[INFO] No matching rule found for {target_ip}")
            return deleted_any

        else:
            print("[INFO] No target IP provided — resetting entire firewall")
            return subprocess.call([netsh, "advfirewall", "reset"]) == 0

    except Exception as e:
        print(f"[ERROR] Failed to reset or clean up Windows firewall: {e}")
        return False


# print(_windows_reset_firewall("192.168.56.14"))
print(is_target_blocked_by_windows_firewall("192.168.56.14"))


