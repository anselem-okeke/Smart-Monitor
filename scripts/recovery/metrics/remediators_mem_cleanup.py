import ctypes
import json
import pathlib
import platform
import socket
import subprocess
import sys
import os
import time

import psutil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from datetime import datetime
from utils.network_file_logger import net_log
from scripts.db_logger import log_recovery
from db.db_access import recovery_fail_count


hostname = socket.gethostname()
CFG = json.load(open(pathlib.Path(__file__).resolve().parents[3] / "config/metrics_recovery.json"))
MEM = CFG["memory"]
OS  = platform.system()

# Precompute lowercase lists for matching
WHITELIST = [n.lower() for n in MEM.get("kill_whitelist", [])]
BLACKLIST = [n.lower() for n in MEM.get("kill_blacklist", {}).get(OS, [])]
RSS_MIN_MB = MEM.get("rss_kill_threshold_mb", 50)

def _is_admin():
    if OS == "Windows":
        try:
            return ctypes.windll.shell32.IsUserAnAdmin() !=0
        except Exception as e:
            return False, str(e)
    return os.geteuid() == 0

if OS == "Windows" and not _is_admin():
    print("[FATAL] Script must be run as Administrator.")
    sys.exit(1)

def restart_service(name):
    print(f"[INFO] Restarting service NAME={name}")
    try:
        if OS == "Windows":
            subprocess.check_call(
                [
                    "powershell", "-Command", f"Restart-Service -Name '{name}' -ErrorAction Stop"
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        else:
            subprocess.check_call(
                [
                    "sudo", "systemctl", "restart", name
                ],stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        return True
    except subprocess.CalledProcessError:
        return False

def is_blacklisted(proc_name):
    name = (proc_name or "").lower()
    return any(bl in name for bl in BLACKLIST)

def top_mem_processes(limit=10, verbose=False, min_rss_mb=0):
    procs = []
    for p in psutil.process_iter([
        'pid', 'name', 'username', 'memory_info', 'cmdline', 'create_time'
    ]):
        try:
            info = p.info
            rss = info['memory_info'].rss if info['memory_info'] else 0
            if rss <= 0:
                continue

            rec = {
                'pid': info['pid'],
                'name': info['name'],
                'rss_mb': rss / (1024 * 1024),
                'username': (info.get('username') or '').lower(),
                'create_time': info.get('create_time')
            }
            if verbose:
                cmd = info.get('cmdline')
                rec['cmdline']=''.join(cmd) if isinstance(cmd, list) else str(cmd)

            if rec['rss_mb'] >= min_rss_mb:
                procs.append(rec)
        except psutil.Error:
            continue

    procs.sort(key=lambda x: x['rss_mb'], reverse=True)
    return procs[:limit]

def terminate_then_kill(name, pid):
    print(f"[INFO] Killing process NAME={name} PID={pid}")
    """Try graceful terminate, then force kill"""
    try:
        p = psutil.Process(pid)
        p.terminate()
        p.wait(timeout=3)
    except Exception:
        try:
            if OS == "Windows":
                subprocess.check_call(["taskkill", "/PID", str(pid), "/F"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                psutil.Process(pid).kill()
        except Exception:
            pass

def kill_whitelisted_rss():
    """
    Pick the highest RSS process that is in the whitelist and safe to kill
    :return: (ok, name, pid) - always 3-tuple
    """
    for p in top_mem_processes(limit=10, verbose=False, min_rss_mb=RSS_MIN_MB):
        name = (p['name'] or "").lower()
        user = p['username']
        pid = p['pid']
        uptime_ok = True
        try:
            proc = psutil.Process(pid)
            uptime_ok = (time.time() - proc.create_time()) >= 60
        except psutil.Error:
            pass

        if name not in WHITELIST:
            continue
        if is_blacklisted(name):
            continue
        if user in ("system", "root", "local system", "nt authority\\system"):
            continue
        if not uptime_ok:
            continue

        try:
            terminate_then_kill(name, pid)
            return True, name, pid
        except Exception:
            return False, name, pid
    return False, None, None

#-----Optional log for observability-------#
def log_top_mem_contributors(n=5):
    total_mb = psutil.virtual_memory().total / (1024*1024)
    top = top_mem_processes(limit=n, verbose=True)
    lines = []
    for p in top:
        share = (p['rss_mb'] / total_mb) * 100 if total_mb else 0.0
        lines.append(f"{p['name']} (PID {p['pid']}) {p['rss_mb']:.1f} MB ~ {share:.2f}% RAM")
    if lines:
        msg = "[ALERT] Top memory contributors:\n  " + "\n  ".join(lines)
        print(msg)
        net_log("warning", f"host={hostname} mem_top={lines}")
        # Optional observability row in recovery table
        log_recovery([{
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": hostname,
            "os_platform": platform.system(),
            "service_name": "mem-observe",
            "result": "info",
            "error_message": "; ".join(lines)
        }])

def relieve_memory():
    """
    Memory pressure occurs when:
       - RAM usage is consistently high (e.g. ≥ 80%)
       - The system is forced to use swap, which is significantly slower than RAM

    This often leads to:
       - System lag
       - Sluggish application performance
       - Swap storms (excessive paging)

    Why is Swap Usage a Red Flag?
       - Swap (virtual memory) is disk-based memory
       - It’s ~100x slower than RAM
       - when swap usage rises while memory is already high, it's a sign the system is out of physical memory

    If left unchecked, it can cause:
       - Application crashes
       - Failed service launches
       - Kernel OOM (Out-Of-Memory) killer intervention

    What Causes It?
       - Memory leaks (e.g. apps that allocate memory but never release)
       - Misconfigured services (e.g. Java heap too large)
       - Multiple heavy services running in parallel (e.g. DB + webserver + batch job)
       - Long-running background jobs (e.g. analytics, backup)

    How Do We Recover?
       - Automated memory cleanup
       - Monitors memory_usage and swap_usage
       - triggers only if both cross safe thresholds for consecutive samples
       - restart leaky services (configurable list)
       - If that fails, kill known leaky apps (from kill_whitelist)
       - with throttling, dry-run, logging, and safety nets

    Safety Mechanisms:
       - Avoids critical system services (kill_blacklist)
       - Uses recovery throttle to avoid rapid-fire restarts
       - Supports dry-run/testing mode
    :return:
    """

    # Dry-run logging
    if MEM.get("dry_run", True):
        net_log(
            "info", f"host={hostname} dry_run=true - skipping memory cleanup"
        )
        log_recovery([{
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": hostname,
            "os_platform": OS,
            "service_name": f"mem-fix",
            "result": "skipped",
            "error_message": "dry_run"
        }])
        return False, "dry_run"

    if not _is_admin():
        return False, "no_privileges"

    if recovery_fail_count(
        host=hostname,
        service_name="mem-fix",
        minutes=MEM["throttle_minutes"]
    ) >= MEM["max_actions_in_window"]:
        return False, "throttled"

    # step 1: Try to restart known leaky services
    for svc in MEM.get("restart_services", []):
        if restart_service(svc):
            log_recovery([{
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "hostname": hostname,
                "os_platform": OS,
                "service_name": f"mem-fix",
                "result": "success",
                "error_message": None
            }])
            net_log(
                "info", f"host={hostname} action=mem_restart service={svc}"
            )
            return True, f"restart: {svc}"

    # step 2: kill whitelisted RSS-heavy processes
    ok, name, pid = kill_whitelisted_rss()
    if ok:
        log_recovery([{
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": hostname,
            "os_platform": OS,
            "service_name": f"mem-fix",
            "result": "success",
            "error_message": None
        }])
        net_log(
            "info", f"host={hostname} action=mem_kill pid={pid} name={name}"
        )
        return True, f"kill:{name}({pid})"

    # step 3: Fallback - no action taken
    log_recovery([{
        "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "hostname": hostname,
        "os_platform": OS,
        "service_name": f"mem-fix",
        "result": "fail",
        "error_message": "no_target"
    }])
    return False, "no_target"
