import os
import platform
import socket
import subprocess
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
from datetime import datetime
from db.db_access import recovery_fail_count
from db.db_logger import log_recovery
from utils.network_file_logger import net_log

hostname = socket.gethostname()
THROTTLE_MIN = 30   # skip if last fail < 30mins
RETRY_LIMIT = 3    #  max fails before give up

MOUNT_TARGET_test = "/mnt/test_ro"
MOUNT_TARGET_sda1 = "/"

def remount_root_rw() -> bool:
    if platform.system() != "Linux":
        return False

    if os.geteuid() != 0:
        return False

    if recovery_fail_count(
        host=hostname,
        service_name="fs-remount",
        minutes=THROTTLE_MIN) >= RETRY_LIMIT:
        return False

    ok = subprocess.call(["sudo", "mount", "-o", "remount,rw", MOUNT_TARGET_test]) == 0
    log_recovery([{
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": hostname,
        "os_platform": platform.system(),
        "service_name": "fs-remount",
        "result": "success" if ok else "fail",
        "error_message": None if ok else "remount failed"
    }])

    net_log("warning", f"hostname={hostname} action=fs-remount result={'success' if ok else 'fail'}")
    return ok

