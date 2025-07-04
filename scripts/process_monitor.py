#------------------------------------------
"""Author: Anselem Okeke"""
#------------------------------------------

import platform
import socket
import time

import psutil
from datetime import datetime
from db_logger import log_process_status_batch

def normalize_status(os_platform, raw_status):
    raw_status = raw_status.lower()

    if os_platform == "Windows":
        if raw_status == "running":
            return "active"
        elif raw_status == "stopped":
            return "stopped"
        else:
            return "unknown"
    elif os_platform == "Linux":
        active_states = ["running", "sleeping", "disk-sleep", "idle"]
        stopped_states = ["stopped"]
        zombie_states = ["zombie", "dead"]

        if raw_status in active_states:
            return "active"
        elif raw_status in stopped_states:
            return "stopped"
        elif raw_status in zombie_states:
            return "zombie"
        else:
            return "unknown"
    return "unknown"

def collect_process_status():
    processes = []
    os_platform = platform.system()

    for proc in psutil.process_iter():
        try:
            proc.cpu_percent(None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    time.sleep(1)

    for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent', 'memory_percent']):
        try:
            raw_status = proc.info['status']
            normalized = normalize_status(os_platform, raw_status)
            processes.append({
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "hostname": socket.gethostname(),
                "os_platform": os_platform,
                "pid": proc.info['pid'],
                "process_name": proc.info['name'],
                "raw_status": raw_status,
                "normalized_status": normalized,
                "cpu_percent": proc.cpu_percent(None),
                "memory_percent": proc.info['memory_percent']
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return processes

if __name__ == '__main__':
    print("[INFO] Starting Process Monitory...")
    try:
        while True:
            process_data = collect_process_status()
            log_process_status_batch(process_data)
            print("[INFO] Process status logged successfully")
            time.sleep(60)
    except KeyboardInterrupt:
        print("[INFO] Process monitory stopped by user.")