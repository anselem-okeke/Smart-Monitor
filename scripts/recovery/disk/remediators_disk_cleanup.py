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

VACUUM_MB   = 500      # journalctl target
TMP_DAYS    = 3
LOG_DAYS    = 7
THROTTLE_MIN= 30       # skip if last fail < 30 min
HOST = socket.gethostname()

def has_priv() -> bool:
    return (os.getgid() == 0) if platform.system()=="Linux" else False

def free_disk_space_linux() -> int:
    freed = 0

    #1. journalctl vacuum
    if shutil.which("journalctl"):
        subprocess.call(["journalctl", f"--vacuum-size={VACUUM_MB}M"])

    #2. delete /var/log/*.gz older than LOG_DAYS
    subprocess.call(["find", "/var/log", "-name", "*.gz",
                     "-mtime", str(LOG_DAYS), "-delete"])

    # 3. clean /tmp files older than TMP_DAYS
    subprocess.call(["find", "/tmp", "-type", "f", "-mtime",
                     str(TMP_DAYS), "-delete"])
    time.sleep(1)
    return freed  # size calc skipped for brevity

def free_disk_space_windows() -> int:
    freed = 0
    # Clear %TEMP%
    subprocess.call(["powershell","-Command",
                     "Remove-Item -Path $env:TEMP\\* -Recurse -Force"])
    # Empty recycle bin
    subprocess.call(["powershell","-Command",
                     "Clear-RecycleBin -Force"])
    return freed

def cleanup_disk(row, crit_th=95) -> bool:
    """
    Performs cleanup, logs recovery row, returns True if usage < crit_th.
    """
    _ts, usage_before = row
    if not has_priv():
        log_recovery({"hostname":HOST,"service_name":"disk_cleanup",
                      "result":"fail","error_message":"not_root"})
        return False

    if platform.system()=="Linux":
        free_disk_space_linux()
    else:
        free_disk_space_windows()

    # re-measure
    from shutil import disk_usage
    pct_after = 100 * (disk_usage("/").used / disk_usage("/").total)
    succeeded = pct_after < crit_th

    log_recovery({"hostname":HOST,"service_name":"disk_cleanup",
                  "result":"success" if succeeded else "partial",
                  "error_message":None})
    net_log("warning",
            f"host={HOST} action=disk_cleanup before={usage_before}% after={pct_after:.1f}%")
    return succeeded
