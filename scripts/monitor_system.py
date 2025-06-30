import platform
import socket
import time

import psutil
import subprocess
from db_logger import log_system_metrics, log_service_status

def collect_system_metrics():
    hostname = socket.gethostname()
    cpu_usage = psutil.cpu_percent(interval=1)
    memory_usage = psutil.virtual_memory().percent
    disk_usage = psutil.disk_usage('/').percent
    temperature = get_temperature()
    uptime = int(time.time() - psutil.boot_time())
    process_count = len(psutil.pids())
    load_avg = get_load_average()

    return {
        "hostname": hostname,
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "disk_usage": disk_usage,
        "temperature": temperature,
        "uptime": uptime,
        "process_count": process_count,
        "load_average": load_avg
    }


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

def get_temperature():
    if hasattr(psutil, "sensors_temperature"):
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                if entries:
                    return entries[0].current
        else:
            print("No temperature data available (likely running in a VM)")
    return None

def get_load_average():
    return None if platform.system() == "Windodows" else psutil.getloadavg()[0]

def check_services():
    services_checked = []
    for svc in monitored_services():
        status = get_service_status(svc)
        services_checked.append({
            "service_name": svc,
            "status": status,
            "host": socket.gethostname()
        })
    return services_checked

if __name__ == "__main__":
    print("[INFO] Starting Smart Factory Monitor...")
    while True:
        try:
            # System metrics
            metrics = collect_system_metrics()
            log_system_metrics(metrics)

            # Services
            services = check_services()
            for service in services:
                log_service_status(service)

            print("[INFO] Metrics + services logged successfully.")

        except Exception as e:
            print(f"[ERROR] Monitoring loop failed: {e}")

        time.sleep(60)  # Wait for 60 seconds before next cycle





