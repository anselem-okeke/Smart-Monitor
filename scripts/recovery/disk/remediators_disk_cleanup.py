import ctypes
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import socket
import platform
import shutil
import subprocess
import time
from scripts.db_logger import log_recovery
from utils.network_file_logger import net_log
from datetime import datetime

#window check if scripts run as admin
def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception as e:
        return False, str(e)
if platform.system() == "Windows" and not is_admin():
    print("[FATAL] Script must be run as Administrator.")
    sys.exit(1)


VACUUM_MB   = 500      # journalctl target
TMP_DAYS    = 0        #3days
LOG_DAYS    = 0        #7days
THROTTLE_MIN= 1       #30 skip if last fail < 30 min
HOST = socket.gethostname()

# def has_priv() -> bool:
#     # for this, python scripts needs to be run with-> sudo python3
#     return (os.getgid() == 0) if platform.system()=="Linux" else False

def has_priv() -> bool:
    #this condition enforces high priviledges
    #Linux: use sudo python3 script
    #Windows: open powershell as adminitrator
    # print(f"[INFO] Running on {platform.system()}, has_priv={has_priv()}")
    if platform.system() == "Linux":
        return os.geteuid() == 0
    elif platform.system() == "Windows":
        return is_admin()
    return False

def has_powershell() -> bool:
    return shutil.which("powershell") is not None

def free_disk_space_linux() -> int:
    freed = 0
    # simulate temporary disk_usage -> sudo dd if=/dev/zero of=/var/log/fillme2.img bs=100M count=20

    try:
        #1. journalctl vacuum
        print("[INFO] Cleaning /var/log/journalctl files...")
        if shutil.which("journalctl"):
            subprocess.call(["sudo","journalctl", f"--vacuum-size={VACUUM_MB}M"])

        #2. delete /var/log/*.gz older than LOG_DAYS
        print("[INFO] Cleaning /var/log files...")
        subprocess.call(["sudo", "find", "/var/log", "-name", "*.gz",
                         "-mtime", str(LOG_DAYS), "-print", "-delete"])

        # 3. clean /tmp files older than TMP_DAYS
        print("[INFO] Cleaning /tmp files...")
        subprocess.call(["sudo", "find", "/tmp",
                         "-type", "f", "-mtime",
                         str(TMP_DAYS), "-print", "-delete"])

        # 4. delete /var/log/*.img older than LOG_DAYS/simulated disk_usage for testing
        print("[INFO] Cleaning /var/log img files...")
        subprocess.call(["sudo", "find", "/var/log", "-name", "*.img",
                         "-mtime", str(LOG_DAYS), "-print", "-delete"])
    except Exception as e:
        print(f"[ERROR] Linux cleanup failed: {e}")
    time.sleep(1)
    return freed  # size calc skipped for brevity


def free_disk_space_windows() -> int:
    #simulate temporay disk_usage
    # $f = "fillme.img"
    # fsutil file createnew $f 54000000000
    if platform.system() != "Windows" or not has_powershell():
        print("[SKIP] not a windows system or powershell not found")
        return 0

    print("[INFO] Starting windows disk cleanup...")
    freed = 0

    try:
        #show what is in %TEMP
        print("[INFO] Show what is in TEMP folder...")
        # Show what's in %TEMP%
        subprocess.call(["powershell", "-Command", "Get-ChildItem -Path $env:TEMP"])

        # Clear %TEMP%
        print("[INFO] Cleaning TEMP folder...")
        subprocess.call(["powershell","-Command",
                         "Remove-Item -Path $env:TEMP\\* -Recurse -Force -ErrorAction SilentlyContinue"
                         ])

        # Empty recycle bin
        subprocess.call(["powershell","-Command",
                         "Clear-RecycleBin -Force -ErrorAction SilentlyContinue"
                         ])
    except Exception as e:
        print(f"[ERROR] Windos cleanup failed: {e}")
    time.sleep(1)
    return freed

def cleanup_disk(row, crit_th=95) -> bool:
    """
    Performs cleanup, logs recovery row, returns True if usage < crit_th.
    """
    _ts, usage_before = row
    if not has_priv():
        log_recovery([{
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "hostname":HOST,
            "os_platform": platform.system(),
            "service_name":"disk_cleanup",
            "result":"fail",
            "error_message":"not_root"
        }])
        return False

    if platform.system()=="Linux":
        free_disk_space_linux()
    else:
        print("[DEBUG] Calling free_disk_space_windows() now...")
        free_disk_space_windows()

    # re-measure
    from shutil import disk_usage
    pct_after = 100 * (disk_usage("/").used / disk_usage("/").total)
    succeeded = pct_after < crit_th

    log_recovery([{
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "hostname":HOST,
        "os_platform": platform.system(),
        "service_name":"disk_cleanup",
        "result":"success" if succeeded else "partial",
        "error_message":None
    }])

    net_log("warning",
            f"host={HOST} action=disk_cleanup before={usage_before}% after={pct_after:.1f}% successful")
    return succeeded
