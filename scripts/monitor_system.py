#------------------------------------------
"""Author: Anselem Okeke"""
#------------------------------------------

import platform
import socket
import time

import psutil
import subprocess
from db_logger import log_system_metrics

def collect_system_metrics():
    hostname = socket.gethostname()
    os_platform = platform.system()
    cpu_usage = psutil.cpu_percent(interval=1)
    memory_usage = psutil.virtual_memory().percent
    disk_usage = get_disk_usage()
    temperature = get_temperature()
    uptime = int(time.time() - psutil.boot_time())
    process_count = len(psutil.pids())
    load_avg = get_load_average()

    return {
        "hostname": hostname,
        "os_platform": os_platform,
        "cpu_usage": cpu_usage,
        "memory_usage": memory_usage,
        "disk_usage": disk_usage,
        "temperature": temperature,
        "uptime": uptime,
        "process_count": process_count,
        "load_average": load_avg
    }

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
    return f"Not Available" if platform.system() == "Windodows" else psutil.getloadavg()[0]

def get_disk_usage():
    if platform.system() == "Windows":
        return psutil.disk_usage("C:\\").percent
    return psutil.disk_usage('/').percent

if __name__ == "__main__":
    print("[INFO] Starting Smart Factory Monitor...")
    try:
        while True:
            # System metrics
            metrics = collect_system_metrics()
            log_system_metrics(metrics)

            print("[INFO] Sytem Metrics logged successfully.")
            time.sleep(60)
    except KeyboardInterrupt:
        print("[INFO] Smart Factory Monitor stopped by user.")





