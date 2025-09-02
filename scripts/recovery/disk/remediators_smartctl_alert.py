import socket
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db.db_logger import log_alert
from db.db_access import recent_alert_exist
from utils.network_file_logger import net_log

hostname = socket.gethostname()
THROTTLE_MIN = 60 #dont re-alert more than once per hour

def smart_alert(dev_list):
    """
    :param dev_list:
    :return: No auto-fix Raises critical alert once per THROTTLE_MIN
    """
    src = "disk:smartctl"
    if recent_alert_exist(hostname,src, THROTTLE_MIN):
        return
    msg = f"SMART failure on {','.join(dev_list)} – manual replacement required"
    log_alert({
        "hostname": hostname,
        "severity": "critical",
        "source": src,
        "message": msg
    })
    net_log("critical", f"host={hostname} action=smartctl_alert disks={dev_list}")