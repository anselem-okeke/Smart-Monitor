import platform
import socket

import psutil
import subprocess

def monitored_services():
    monitored = set()

    if platform.system() == "Windows":
        try:
            output = subprocess.check_output("sc query state= all", shell=True, text=True)
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("SERVICE_NAME:"):
                    service_name = line.split()[1].strip()
                    monitored.add(service_name)
        except subprocess.CalledProcessError:
            pass
    else:
        for proc in psutil.process_iter(['name']):
            try:
                monitored.add(proc.name())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    return list(monitored)

def get_service_status(service_name):
    if platform.system() == "Windows":
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
            try:
                if proc.name() == service_name:
                    if proc.status() not in ("zombie",):
                        return "running"
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return "stopped"

def check_services():
    services_checked = []
    for svc in monitored_services():
        status = get_service_status(svc)
        services_checked.append({
            "service_name": svc,
            "status": status,
            "hostname": socket.gethostname()
        })
    return services_checked

