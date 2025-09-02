import ctypes
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import os, platform, psutil, subprocess, socket, time, json, pathlib
from db.db_logger import log_recovery
from utils.network_file_logger import net_log
from db.db_access import recovery_fail_count
from datetime import datetime


HOST = socket.gethostname()
CFG  = json.load(open(pathlib.Path(__file__).resolve().parents[3] / "config/metrics_recovery.json"))
CPU  = CFG["cpu"]
OS   = platform.system()
WHITELIST = [p.lower() for p in CPU.get("kill_whitelist", [])]
BLACKLIST = [p.lower() for p in CPU.get("kill_blacklist", {}).get(OS, [])]

def _is_admin():
    if platform.system() == "Windows":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() != 0
        except Exception as e:
            return False, str(e)
    return os.geteuid() == 0

def top_cpu_processes(limit=10, refresh_delay=0.1, verbose=False):
    # First we pass to initialize the CPU percent measurement
    for p in psutil.process_iter(['pid', 'name']):
        try:
            p.cpu_percent(interval=None)
        except psutil.NoSuchProcess:
            continue

    # Wait for a short delay to capture actual CPU usage
    time.sleep(refresh_delay)

    procs = []
    for p in psutil.process_iter(['pid','name','cpu_percent', 'cmdline']):
        try:
            info = p.info
            if verbose:
                cmd = info.get('cmdline')
                info['cmdline'] = ' '.join(cmd) if isinstance(cmd, list) else str(cmd)
            procs.append(info)
        except psutil.Error:
            pass

    procs.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
    return procs[:limit]

# def top_cpu_processes_filtered(limit=10):
#     procs = []
#     for p in psutil.process_iter(['pid', 'name', 'cpu_percent']):
#         try:
#             info = p.info
#             if info['name'].lower() not in BLACKLIST:
#                 procs.append(info)
#         except psutil.Error:
#             pass
#     procs.sort(key=lambda x: x['cpu_percent'] or 0, reverse=True)
#     return procs[:limit]

def kill(pid, name, mode="unknown"):
    print(f"[INFO] Killing process NAME={name} PID={pid} MODE={mode}")
    try:
        if OS == "Windows":
            subprocess.check_call(["taskkill", "/PID", str(pid), "/F"],
                                  stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, 9)

        log_recovery([{
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": HOST,
            "os_platform": OS,
            "service_name": f"cpu-kill",
            "result": "success",
            "error_message": None
        }])
        net_log("warning", f"host={HOST} action=cpu_kill_{mode} pid={pid} name={name}")
        return True, name, pid

    except Exception as e:
        print(f"[ERROR] Failed to kill NAME={name} PID={pid} : {e}")
        log_recovery([{
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": HOST,
            "os_platform": OS,
            "service_name": f"cpu-kill",
            "result": "fail",
            "error_message": f"kill failed (mode={mode}): {str(e)}"
        }])
        net_log("error", f"host={HOST} action=cpu_kill_{mode}_fail pid={pid} err={e}")
        return False, name, pid

def kill_runaway_process():
    """
    | `dry_run` Value                    | Meaning                                                                | When to Use                                   |
    | ---------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------- |
    | `true` *(default in safe rollout)* | Don’t actually kill processes — just simulate/log what would happen    | Initial phase (1–2 weeks of log-only testing) |
    | `false`                            | Actively kill the process if safe                                      | After confirming logs show safe behavior      |


    Here we want to kill a high-CPU process safely using an hybrid logic
    - Phase 1: Kill only if on whitelist
    - Phase 2: if none killed, fallback to killing safe candidate:
        - Not in blacklist
        - Not SYSTEM/root user
        - Uptime > 60s

    | Metric Source                       | Meaning                                        | Scope           |
    | ----------------------------------- | ---------------------------------------------- | --------------- |
    | `psutil.boot_time()`                | How long has the machine been up               | **Global**      |
    | `psutil.Process(pid).create_time()` | How long has this proc(PID=124) been runnging  | **Per-process** |
    | DB field: `uptime`                  | System uptime (i.e. `time.time() - boot_time`) | **Global**      |

    :return:
    """

    if CPU["dry_run"]:
        return False, None, None

    if not _is_admin():
        return False, None, None

    if recovery_fail_count(
        host=HOST,
        service_name="cpu-kill",
        minutes= CPU["throttle_minutes"]
    )  >= CPU["max_actions_in_window"]:
        return False, None, None

    top = top_cpu_processes()

    #Phase 1: Whitelist-only kill
    for p in top:
        name = (p["name"] or "").lower()
        if name in WHITELIST:
            return kill(pid=p['pid'], name=name, mode="whitelist")

    # Phase 2: Fallback kill with safety checks
    for p in top:
        name = (p["name"] or "").lower()
        try:
            proc = psutil.Process(pid=p['pid'])
            user = proc.username().lower()
            uptime = time.time() - proc.create_time() #secs
        except psutil.Error:
            continue

        if any(bl in name for bl in BLACKLIST):
            continue

        # if name in BLACKLIST:
        #     continue

        if user in ("system", "root", "local system", "nt authority\\system"):
            continue

        if uptime < 60:
            continue

        return kill(pid=p['pid'], name=name, mode="fallback")

    return False, None, None
