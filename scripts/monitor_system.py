#------------------------------------------
"""Author: Anselem Okeke"""
#------------------------------------------
import os
import platform
import socket
import time

import psutil
import subprocess
from db_logger import log_system_metrics, create_inode_usage_column

def collect_system_metrics():
    """
    | Metric          | Source                             | Type        | Units            | Example                 |
    | --------------- | ---------------------------------- | ----------- | ---------------- | ----------------------- |
    | `hostname`      | `socket.gethostname()`             | string      | –                | `"web01"`               |
    | `os_platform`   | `platform.system()`                | string      | –                | `"Windows"` / `"Linux"` |
    | `cpu_usage`     | `psutil.cpu_percent(interval=1)`   | float       | **%**            | `27.5`                  |
    | `memory_usage`  | `psutil.virtual_memory().percent`  | float       | **%**            | `43.1`                  |
    | `disk_usage`    | `get_disk_usage()`                 | float       | **%**            | `68.2`                  |
    | `temperature`   | `get_temperature()`                | float       | **°C** (or None) | `47.5`                  |
    | `uptime`        | `time.time() - psutil.boot_time()` | float → int | **seconds**      | `86400` (1 day)         |
    | `process_count` | `len(psutil.pids())`               | int         | **count**        | `97`                    |
    | `load_avg`      | `get_load_average()`               | tuple       | system-dependent | `(0.1, 0.2, 0.3)`       |

    :return:
    """
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
        "load_average": load_avg,
        "inode_usage": get_inode_usage()
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

def get_inode_usage():
    """
    Each file or directory on a Linux filesystem has an inode that contains:
     - File type (regular file, directory, symlink, etc.)
     - Permissions (read/write/execute)
     - Owner and group
     - File size
     - Timestamps (created, modified, accessed)
     - Number of hard links
     - Disk block pointers (where the actual data is stored)
    Why are inodes important in disk recovery?
      - Even if your disk has free space, if you run out of inodes, you can't create new files.
    Symptoms of inode exhaustion:
      - You can't create files despite having free space (No space left on device)
      - Heavy logging systems stop writing logs
      - df -h shows free space, but df -i shows 100% inode usage
    Causes:
      - Millions of small files (e.g., logs, temp files, cache)
      - Backup scripts that create many files without cleanup
      - Misconfigured apps writing excessive files (especially in /tmp, /var/log, or /var/cache)
    :return:
      st.f_files = total number of inodes
      st.f_ffree = free inodes
      st.f_files - st.f_ffree = used inodes
      the formula returns: (used inodes / total inodes) * 100 as a percentage
    """
    if platform.system() != "Linux":
        return None
    st = os.statvfs("/")
    return round(100 * (st.f_files - st.f_ffree) / st.f_files, 2)


if __name__ == "__main__":
    print("[INFO] Starting Smart Factory Monitor...")
    # creating inode_usage
    create_inode_usage_column()
    try:
        while True:
            # System metrics
            metrics = collect_system_metrics()
            log_system_metrics(metrics)

            print("[INFO] System Metrics logged successfully.")
            time.sleep(60)
    except KeyboardInterrupt:
        print("[INFO] Smart Factory Monitor stopped by user.")





