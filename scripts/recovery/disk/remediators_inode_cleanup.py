import platform
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import socket
import subprocess
from datetime import datetime
from utils.network_file_logger import net_log
from db.db_access import recovery_fail_count
from scripts.db_logger import log_recovery


hostname = socket.gethostname()
THROTLE_MIN = 30   #30
RETRY_LIMIT = 3  #3
TMP_DAYS = 3   #3

def high_node_dirs():
    """
    | Directory                   | Why it's important for inode cleanup                                 |
    | --------------------------- | -------------------------------------------------------------------- |
    | `/tmp`                      | Often has thousands of small temp files from many apps and builds    |
    | `/var/tmp`                  | Similar to `/tmp`, but files persist longer – often overlooked       |
    | `/var/log`                  | Many systems log daily/hourly per-service files (logrotate, etc.)    |
    | `/var/cache`                | App caches (e.g., `apt`, browsers, pip, npm) often create many files |
    | `/var/spool`                | Mail, printing, cron job outputs accumulate here                     |
    | `/var/lib/docker`           | Docker image layers and container metadata – high inode use          |
    | `/var/lib/systemd/coredump` | Core dumps – rare but can be huge and inode-intensive                |

    :return:
    """
    High_INODE_DIRS = [
        "/tmp",
        "/var/tmp",
       # "/var/log",
        "/var/cache",
        "/var/spool",
        "/var/lib/docker",
        "/var/lib/systemd/coredump"
    ]
    return High_INODE_DIRS

NODE_MODULES  = "/var/cache/npm"  # still included for legacy cleanup

def delete_old_files(path, days):
    """
            | Expression  | Matches files modified…    |
        | ----------- | ------------------------------------------ |
        | `-mtime 3`  | Exactly 3–4 days ago                       |
        | `-mtime +3` | More than 3 days ago                       |
        | `-mtime -3` | Less than 3 days ago (e.g., last 72 hours) |

    :param path:
    :param days:
    :return:
    """
    print(f"[INFO] Cleaning up files in {path} older than {days} days...")

    # 1. Delete old files (ignores permission-denied silently)
    subprocess.call([
        "find", path,
        "-type", "f",
        "-mtime", f"{days}",
        "!", "-path", "*/systemd-private-*",
        "!", "-path", "*/snap-private-tmp*",
        "-print", "-delete"
    ], stderr=subprocess.STDOUT)

    # 2. Delete empty dirs (but skip protected dirs)
    subprocess.call([
        "find", path,
        "-type", "d", "-empty",
        "!", "-path", "*/systemd-private-*",
        "!", "-path", "*/snap-private-tmp*",
        "-print", "-delete"
    ], stderr=subprocess.STDOUT)

    print(f"[INFO] {path} cleanup complete...")

def free_inodes_linux() -> bool:
    for path in high_node_dirs():
        if os.path.exists(path):
            try:
                delete_old_files(path, TMP_DAYS)
            except Exception as e:
                print(f"[WARN] Failed to clean {path}: {e}")

        #specfically clean up inode_modules if it exits
        if os.path.isdir(NODE_MODULES):
            try:
                subprocess.call(["rm", "-rf", NODE_MODULES])
            except Exception as e:
                print(f"[WARN] Failed to remove {NODE_MODULES}: {e}")
    return True

def cleanup_inodes():
    if platform.system() != "Linux":
        return False

    if os.geteuid() !=0:
        return False

    if recovery_fail_count(
        host=hostname,
        service_name="inode-clean",
        minutes=THROTLE_MIN
    ) >= RETRY_LIMIT:
        return False

    success = free_inodes_linux()

    log_recovery([{
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": hostname,
        "os_platform": platform.system(),
        "service_name": "inode-clean",
        "result": "success" if success else "fail",
        "error_message": None if success else "inode-clean failed"
    }])

    net_log("warning", f"hostname={hostname} action=inode-clean result={'success' if success else 'fail'}")
    return success

