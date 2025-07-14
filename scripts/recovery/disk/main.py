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
from scripts.recovery.disk.remediators_disk_cleanup import cleanup_disk
hostname = socket.gethostname()

def handle_disk():
    rows = recent_system_metrics(hostname, minutes=5)
    if not rows: return
    latest = rows[0]
    if not is_disk_full(latest):
        return

    success = cleanup_disk(latest, crit_th=CRIT_TH)
    sev = "warning" if success else "critical"
    after_msg = "cleanup ok" if success else "cleanup failed"
    log_alert({"hostname":hostname, "severity":sev,
               "source":"disk", "message":after_msg})

if __name__ == "__main__":
    print("[INFO] Disk-recovery loop running …")
    try:
        while True:
            handle_disk()
            print("[INFO] Disk-recovery loop succeeded …")
            time.sleep(300)          # every 5 min
    except KeyboardInterrupt:
        print("[INFO] Disk-recovery stopped")