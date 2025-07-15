import socket
import sys
import os
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db.db_access import recent_system_metrics
from scripts.db_logger import log_alert
from scripts.recovery.disk.classifiers_disk_full import is_disk_full, CRIT_TH
from scripts.recovery.disk.remediators_disk_cleanup import cleanup_disk, THROTTLE_MIN
from scripts.recovery.disk.classifiers_fs_readonly import is_root_readonly
from scripts.recovery.disk.remediators_fs_remount import remount_root_rw
from datetime import datetime

_last_failure = None
hostname = socket.gethostname()


def handle_disk():
    global _last_failure

    rows = recent_system_metrics(hostname, minutes=5)
    if not rows:
        return

    latest = rows[0]
    if not is_disk_full(latest):
        return

    # Check if root filesystem is read-only
    if is_root_readonly():
        print("[WARN] Root filesystem is read-only. Attempting remount...")
        if not remount_root_rw():
            print("[ERROR] Remount failed. Skipping disk cleanup.")
            log_alert({
                "hostname": hostname,
                "severity": "critical",
                "source": "disk",
                "message": "Root FS is read-only. Remount failed."
            })
            return
        else:
            print("[INFO] Root filesystem remounted read-write.")

    # Skip if previous failure occurred too recently
    if _last_failure and (datetime.utcnow() - _last_failure).total_seconds() < THROTTLE_MIN * 60:
        print("[SKIP] Recently failed cleanup, skipping...")
        return

    success = cleanup_disk(latest, crit_th=CRIT_TH)

    if not success:
        _last_failure = datetime.utcnow()

    sev = "warning" if success else "critical"
    after_msg = "cleanup ok" if success else "cleanup failed"
    log_alert({
        "hostname": hostname,
        "severity": sev,
        "source": "disk",
        "message": after_msg
    })

# def handle_disk():
#     global _last_failure
#
#     rows = recent_system_metrics(hostname, minutes=5)
#     if not rows:
#         return
#
#     latest = rows[0]
#
#     #1. check for disk full
#     if not is_disk_full(latest):
#         return
#
#     if _last_failure and (datetime.utcnow() - _last_failure).total_seconds() < THROTTLE_MIN * 60:
#         print("[SKIP] Recently failed cleanup, skipping...")
#         return
#
#     success = cleanup_disk(latest, crit_th=CRIT_TH)
#
#     if not success:
#         print("[FAILURE] Cleanup failed, setting throttle...")
#         _last_failure = datetime.utcnow()
#
#     sev = "warning" if success else "critical"
#     after_msg = "cleanup ok" if success else "cleanup failed"
#     log_alert({
#         "hostname":hostname,
#         "severity":sev,
#         "source":"disk",
#         "message":after_msg
#     })
#
#     #2. check for read-only root FS
#     if is_root_readonly():
#         print("[WARN] Detected root FS as read-only. Attempting remount...")
#         success = remount_root_rw()
#
#         log_alert({
#             "hostname": hostname,
#             "severity": "warning" if success else "critical",
#             "source": "fs-remount",
#             "message": "remount ok" if success else "remount failed"
#         })

if __name__ == "__main__":
    print("[INFO] Disk-recovery loop running …")
    try:
        while True:
            handle_disk()
            print("[INFO] Disk-recovery loop succeeded …")
            time.sleep(60)          # every 5 min
    except KeyboardInterrupt:
        print("[INFO] Disk-recovery stopped")