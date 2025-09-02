import json
import os
import pathlib
import platform
import signal
import socket
import subprocess
import sys
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from scripts.db_logger import log_recovery
from utils.network_file_logger import net_log
from db.db_access import recovery_fail_count

HOST = socket.gethostname()
CFG  = json.load(open(pathlib.Path(__file__).resolve().parents[3] / "config/metrics_recovery.json"))
ZB   = CFG["zombies"]
OS = platform.system()

def is_admin():
    return False if OS == "Windows" else (os.geteuid()==0)

def restart_service(unit):
    try:
        subprocess.check_call(["sudo","systemctl","restart", unit],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        return True
    except Exception:
        return False

def attempt_reap(by_ppid, parent_names):
    """
    Try to mitigate by restarting a known parent systemd unit or terminating
    a whitelisted parent process. Returns (success_bool, action_str).
    """
    if platform.system() == "Windows" or ZB["dry_run"] or not is_admin():
        return False, "dry_run_or_no_priv"

    if recovery_fail_count(HOST, "zombie-reap", ZB["throttle_minutes"]) >= 2:
        return False, "throttled"

    # Pick parent PID with most zombies
    if not by_ppid:
        return False, "no_parent"

    ppid = max(by_ppid, key=by_ppid.get)
    pname = (parent_names.get(ppid) or "").lower()

    # 1) restart service if parent name matches a systemd unit in config
    for unit in ZB["restart_services"]:
        if pname == unit.lower():
            ok = restart_service(unit)

            log_recovery([{
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "hostname":HOST,
                "os_platform": OS,
                "service_name":"zombie-reap",
                "result":"success" if ok else "fail",
                "error_message":None if ok else f"restart {unit} failed"
            }])

            net_log("warning", f"host={HOST} action=zombie_reap restart={unit} parent={pname}({ppid})")
            return ok, f"restart:{unit}"

    # 2) last resort: TERM the parent if explicitly whitelisted
    for allowed in ZB["kill_parent_whitelist"]:
        if pname == allowed.lower():
            try:
                os.kill(ppid, signal.SIGTERM)
                log_recovery([{
                    "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    "hostname":HOST,
                    "os_platform": OS,
                    "service_name":"zombie-reap",
                    "result":"success",
                    "error_message":None
                }])

                net_log("warning", f"host={HOST} action=zombie_reap term_parent={pname}({ppid})")
                return True, f"term:{pname}({ppid})"
            except Exception as e:
                log_recovery([{
                    "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                    "hostname":HOST,
                    "os_platform": OS,
                    "service_name":"zombie-reap",
                    "result":"fail",
                    "error_message":str(e)
                }])

                net_log("error", f"host={HOST} action=zombie_reap_term_fail parent={pname}({ppid}) err={e}")
                return False, f"term_fail:{pname}({ppid})"

    return False, f"no_action_for_parent:{pname}({ppid})"