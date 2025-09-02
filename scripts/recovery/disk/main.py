import socket
import sys
import os
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db.db_access import recent_system_metrics
from db.db_logger import log_alert
from db.db_access import recent_inode_usage
from scripts.recovery.disk.classifiers_disk_full import is_disk_full, CRIT_TH
from scripts.recovery.disk.remediators_disk_cleanup import cleanup_disk, THROTTLE_MIN
from scripts.recovery.disk.classifiers_fs_readonly import is_root_readonly
from scripts.recovery.disk.remediators_fs_remount import remount_root_rw
from scripts.recovery.disk.classifiers_inode_full import is_inode_exhausted
from scripts.recovery.disk.remediators_inode_cleanup import cleanup_inodes
from scripts.recovery.disk.loader_smartctl_discovery import failing_disks
from scripts.recovery.disk.classifiers_smartctl_fail import is_smart_failure
from scripts.recovery.disk.remediators_smartctl_alert import smart_alert
from datetime import datetime

_last_failure = None
hostname = socket.gethostname()

def handle_disk():
    global _last_failure

    rows = recent_system_metrics(hostname, minutes=5)
    if not rows:
        return

    latest = rows[0]

    #STEP 1: SMARTCTL / I-O error spike
    bad_disk = failing_disks()
    if is_smart_failure(bad_disk):
        print(f"[WARN] Smartctl failures on {bad_disk}: performing smart alert...")
        smart_alert(bad_disk)
        return

    # STEP 2: Handle read-only root FS
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

    # STEP 3: Handle inode cleanup separately (run regardless of disk fullness)
    inode_rows = recent_inode_usage(hostname)
    if inode_rows:
        inode_latest = inode_rows[0]
        if is_inode_exhausted(inode_latest):
            inode_usage = inode_latest[1]
            print(f"[INFO] Inode usage @{inode_usage}%. Attempting inode cleanup...")
            clean_inode = cleanup_inodes()

            sev = "warning" if clean_inode else "critical"
            msg = "inode cleanup success" if clean_inode else "inode cleanup failed"
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

    # STEP 4: Only proceed with disk cleanup if disk is full
    if not is_disk_full(latest):
        return

    # STEP 5: Check throttling before cleanup
    if _last_failure and (datetime.utcnow() - _last_failure).total_seconds() < THROTTLE_MIN * 60:
        print("[SKIP] Recently failed cleanup, skipping...")
        return

    # STEP 6: Attempt disk cleanup
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

if __name__ == "__main__":
    print("[INFO] Disk-recovery loop running …")
    try:
        while True:
            handle_disk()
            print("[INFO] Disk-recovery loop succeeded …")
            time.sleep(300)          # every 5 min
    except KeyboardInterrupt:
        print("[INFO] Disk-recovery stopped")