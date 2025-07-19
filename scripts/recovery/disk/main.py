import socket
import sys
import os
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db.db_access import recent_system_metrics
from scripts.db_logger import log_alert
from db.db_access import recent_inode_usage
from scripts.recovery.disk.classifiers_disk_full import is_disk_full, CRIT_TH
from scripts.recovery.disk.remediators_disk_cleanup import cleanup_disk, THROTTLE_MIN
from scripts.recovery.disk.classifiers_fs_readonly import is_root_readonly
from scripts.recovery.disk.remediators_fs_remount import remount_root_rw
from scripts.recovery.disk.classifiers_inode_full import is_inode_exhausted
from scripts.recovery.disk.remediators_inode_cleanup import cleanup_inodes
from datetime import datetime

_last_failure = None
hostname = socket.gethostname()


def handle_disk():
    global _last_failure

    rows = recent_system_metrics(hostname, minutes=5)
    if not rows:
        return

    latest = rows[0]

    # STEP 1: Handle read-only root FS
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

    # STEP 2: Handle inode cleanup separately (run regardless of disk fullness)
    inode_rows = recent_inode_usage(hostname)
    if inode_rows:
        inode_latest = inode_rows[0]
        if is_inode_exhausted(inode_latest):
            inode_usage = inode_latest[1]
            print(f"[INFO] Inode usage @{inode_usage}%. Attempting inode cleanup...")
            clean_inode = cleanup_inodes()

            sev = "warning" if clean_inode else "critical"
            msg = "inode cleanup attempted" if clean_inode else "inode cleanup failed"
            log_alert({
                "hostname": hostname,
                "severity": sev,
                "source": "inode",
                "message": msg
            })
            if not clean_inode:
                return
    else:
        print(f"[INFO] No recent inode data available: skipping inode check...")

    # STEP 3: Only proceed with disk cleanup if disk is full
    if not is_disk_full(latest):
        return

    # STEP 4: Check throttling before cleanup
    if _last_failure and (datetime.utcnow() - _last_failure).total_seconds() < THROTTLE_MIN * 60:
        print("[SKIP] Recently failed cleanup, skipping...")
        return

    # STEP 5: Attempt disk cleanup
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
#     if not is_disk_full(latest):
#         return
#
#     # STEP 1: Check if root filesystem is read-only
#     if is_root_readonly():
#         print("[WARN] Root filesystem is read-only. Attempting remount...")
#         if not remount_root_rw():
#             print("[ERROR] Remount failed. Skipping disk cleanup.")
#             log_alert({
#                 "hostname": hostname,
#                 "severity": "critical",
#                 "source": "disk",
#                 "message": "Root FS is read-only. Remount failed."
#             })
#             return
#         else:
#             print("[INFO] Root filesystem remounted read-write.")
#
#     # STEP 2: Handle inode cleanup if needed
#     inode_rows = recent_inode_usage(hostname)
#     if inode_rows:
#         inode_latest = inode_rows[0]
#         if is_inode_exhausted(inode_latest):
#             inode_usage = inode_latest[1]
#             print(f"[INFO] Inode usage @{inode_usage}%. Attempting inode cleanup...")
#             clean_inode = cleanup_inodes()
#
#             sev = "warning" if clean_inode else "critical"
#             msg = "inode cleanup attempted" if clean_inode else "inode cleanup failed"
#             log_alert({
#                 "hostname": hostname,
#                 "severity": sev,
#                 "source": "inode",
#                 "message": msg
#             })
#     else:
#         print(f"[INFO] No recent {inode_rows} data available: skipping inode check...")
#
#     # STEP 3: Skip if previous failure occurred too recently
#     if _last_failure and (datetime.utcnow() - _last_failure).total_seconds() < THROTTLE_MIN * 60:
#         print("[SKIP] Recently failed cleanup, skipping...")
#         return
#
#     # STEP 4: Attempt disk cleanup
#     success = cleanup_disk(latest, crit_th=CRIT_TH)
#
#     if not success:
#         _last_failure = datetime.utcnow()
#
#     sev = "warning" if success else "critical"
#     after_msg = "cleanup ok" if success else "cleanup failed"
#     log_alert({
#         "hostname": hostname,
#         "severity": sev,
#         "source": "disk",
#         "message": after_msg
#     })







































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