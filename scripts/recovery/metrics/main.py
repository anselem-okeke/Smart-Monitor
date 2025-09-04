import json
import pathlib
import socket
import sys
import os
import time

import psutil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
print(PROJECT_ROOT)


from db.db_access import recent_cpu_samples, recent_memory_samples, recent_load_samples, recent_alert_exist
from scripts.recovery.metrics.classifiers_cpu_high import is_cpu_high
from scripts.recovery.metrics.classifiers_mem_high import is_memory_high
from scripts.recovery.metrics.classifiers_load_spike import is_load_spike, current_load_and_threshold
from scripts.recovery.metrics.remediators_load_observe import log_load_context
from scripts.recovery.metrics.remediators_cpu_kill import kill_runaway_process, top_cpu_processes
from scripts.recovery.metrics.remediators_mem_cleanup import relieve_memory, top_mem_processes, log_top_mem_contributors
from scripts.recovery.metrics.classifiers_zombie_flood import current_zombie_stats, is_zombie_flood
from scripts.recovery.metrics.remediators_zombie_reap import attempt_reap
from db.db_logger import log_alert
from utils.network_file_logger import net_log

hostname = socket.gethostname()
CFG_PATH = pathlib.Path(__file__).resolve().parents[3] / "config/metrics_recovery.json"
CFG = json.load(open(CFG_PATH))
CPU = CFG["cpu"]
MEM = CFG["memory"]
LOAD = CFG["load"]

def handle_cpu():
    print("[DEBUG] Starting cpu cleanup check...")
    rows = recent_cpu_samples(
        host=hostname,
        samples=CPU['consecutive'],
        minutes=5
    )

    if not is_cpu_high(
        rows=rows,
        warn_thresh=CPU['warn'],
        consecutive=CPU['consecutive']
    ):
        return

    # Log top CPU procs (observability)
    top = top_cpu_processes(verbose=True)

    if top:
        top_proc = top[0]
        print(f"[ALERT] High CPU detected! Top process:")
        print(f"        Name: {top_proc.get('name')}")
        print(f"        PID: {top_proc.get('pid')}")
        print(f"        CPU%: {top_proc.get('cpu_percent')}")

    usages = [u for _,u in rows if u is not None]
    net_log(
        "warning",
        f"host={hostname} cpu_high usages={usages} top={top}"
    )

    # Attempt hybrid process kill
    killed, name, pid = kill_runaway_process()

    # Post verify (optional short wait)
    time.sleep(CPU["post_verify_sleep_sec"])
    rows_after = recent_cpu_samples(hostname, samples=1, minutes=1)
    current_cpu = rows_after[0][1] if rows_after else None

    # Decide severity and alert
    if killed and current_cpu is not None and current_cpu < CPU["warn"]:
        sev = "warning"
        msg = f"CPU high mitigated: killed {name}({pid}), now {current_cpu:.1f}%"
    else:
        sev = "critical" if (current_cpu is None or current_cpu >= CPU["crit"]) else "warning"
        msg = f"CPU high persists ({current_cpu}%) – manual intervention" if current_cpu is not None else "CPU post-check missing"

    log_alert({
        "hostname": hostname,
        "severity": sev,
        "source": "cpu",
        "message": msg
    })

def handle_memory():
    print("[DEBUG] Starting memory cleanup check...")

    rows = recent_memory_samples(
        host=hostname,
        samples=MEM["consecutive"],
        minutes=5
    )
    if not is_memory_high(
        rows=rows,
        warn_th=MEM["warn"],
        swap_th=MEM.get("swap_threshold", 5),
        consecutive=MEM["consecutive"]
    ):
        return

    #---Oberservability: which process is consuming RAM right now-----
    total_mb = psutil.virtual_memory().total / (1024*1024)
    top = top_mem_processes(limit=3, verbose=True)
    if top:
        p = top[0]
        share = (p['rss_mb'] / total_mb) * 100 if total_mb else 0.0
        alert_line = (f"[ALERT] Process with high memory consumption: {p['name']} (PID {p['pid']}) "
                      f"{p['rss_mb']:.1f} MB (~{share:.2f}% of RAM)")
        print(alert_line)

    #-----Optionally log to N RAM contributors
    log_top_mem_contributors(n=5)

    #-----Remediation-----#
    success, action = relieve_memory()
    time.sleep(MEM["post_verify_sleep_sec"])

    mem_after = recent_memory_samples(host=hostname, samples=1, minutes=1)
    cur = mem_after[0][1] if mem_after else None

    sev = ("warning" if success and cur is not None and cur < MEM["warn"]
           else "critical")

    msg = (f"memory cleanup {action} -> {cur:.1f}%"
           if cur is not None else f"memory cleanup {action} - post-verify missing")

    log_alert({
        "hostname": hostname,
        "severity": sev,
        "source": "memory",
        "message": msg
    })

def handle_load():
    cores = psutil.cpu_count(logical=True) or 1
    rows = recent_load_samples(
        host=hostname,
        samples=CFG["load"]["consecutive"],
        minutes=5
    )

    if not is_load_spike(
        rows=rows,
        cores=cores,
        warn_mult=CFG["load"]["warn_multiplier"],
        consecutive=CFG["load"]["consecutive"]
    ):
        return

    cur, warn_thr = current_load_and_threshold(
        rows=rows,
        cores=cores,
        mult=CFG["load"]["warn_multiplier"]
    )

    _, crit_thr = current_load_and_threshold(
        rows=rows,
        cores=cores,
        mult=CFG["load"]["crit_multiplier"]
    )

    # --- Observability: show top CPU contributors during load spike ---
    top = top_cpu_processes(limit=3, verbose=True)
    if top:
        print("[ALERT] Load spike detected!")
        print(f"         Current load={cur:.2f}, Warn threshold={warn_thr:.2f}, Critical threshold={crit_thr:.2f}")
        for p in top:
            print(f"         PID {p['pid']} | {p['name']} | CPU={p['cpu_percent']}% | cmd={p.get('cmdline', '')}")

    # throttle duplicate alerts
    if recent_alert_exist(
        host=hostname,
        source="load",
        minutes=CFG["load"]["throttle_minutes"]
    ):
        # still log to file for local trail
        if cur is not None and warn_thr is not None:
            log_load_context(
                current_load=cur,
                threshold=warn_thr,
                severity="warning"
            )
        return

    # context log (top processes etc)
    if cur is not None and warn_thr is not None:
        log_load_context(
            current_load=cur,
            threshold=warn_thr,
            severity="warning"
        )

    # quick post-verify
    time.sleep(CFG["load"]["post_verify_sleep_sec"])

    rows_after = recent_load_samples(
        host=hostname,
        samples=1,
        minutes=3
    )

    cur_after, _ = current_load_and_threshold(
        rows=rows_after,
        cores=cores,
        mult=CFG["load"]["warn_multiplier"]
    )

    # severity decision
    severity = "critical" if (cur_after is not None and crit_thr is not None and cur_after >= crit_thr) else "warning"
    msg_val = f"load {cur_after:.2f}" if cur_after is not None else f"load {cur:.2f}" if cur is not None else "load spike"

    log_alert({
        "hostname": hostname,
        "severity": severity,
        "source": "load",
        "message": msg_val
    })

def handle_zombies():
    eff = CFG['zombies']
    total, zombies, ratio, by_ppid, pname = current_zombie_stats()

    print(f"\t---- Zombie Check ----")
    print(f"\tTotal processes: {total}")
    print(f"\tZombie count: {zombies}")
    print(f"\tZombie ratio: {ratio:.3f}")
    print("\tZombies by parent:", by_ppid)
    for ppid, count in by_ppid.items():
        pname_parent = pname.get(ppid, "unknown")
        print(f"\t  Parent {ppid} ({pname_parent}) → {count} zombies")
    print(f"\t----------------------")

    if not hasattr(handle_zombies, "history"):
        handle_zombies.history = []

    handle_zombies.history.append((total, zombies, ratio))
    handle_zombies.history = handle_zombies.history[-eff["consecutive"]:]

    if len(handle_zombies.history) < eff["consecutive"]:
        return

    if not all(is_zombie_flood(t, z, r, eff) != 'none' for t, z, r in handle_zombies.history):
        return

    severity = is_zombie_flood(total, zombies, ratio, eff)
    print(f"[{severity.upper()}] host={hostname} zombies={zombies}/{total} ratio={ratio:.3f} parents={by_ppid}")
    # Always write a detailed context line

    net_log("warning", f"host={hostname} zombies={zombies}/{total} ratio={ratio:.3f} parents={by_ppid} parents={pname}")

    if eff.get("dry_run"):
        print("[INFO] zombie_reap skipped: dry_run=true")
        net_log("info", "zombie_reap skipped: dry_run=true")
        return

    # Throttle DB alerts
    if recent_alert_exist(hostname, "zombie", eff["throttle_minutes"]):
        return

    # Optional mitigation
    fixed, action = attempt_reap(by_ppid, pname)
    print(f"[INFO] Attempting {action}")

    time.sleep(eff["post_verify_sleep_sec"])
    total2, zombies2, ratio2, *_ = current_zombie_stats()

    if fixed and ratio2 < eff["ratio_warn"]:
        print(f"[INFO] zombies mitigated via {action} → {zombies2}/{total2} ({ratio2:.3f})")
        log_alert({
            "hostname": hostname,
            "severity": "warning",
            "source": "zombie",
            "message": f"zombies mitigated via {action} → {zombies2}/{total2} ({ratio2:.3f})"})
    else:
        print(f"[ERROR] zombies persist {zombies2}/{total2} ({ratio2:.3f}); action={action}")
        log_alert({
            "hostname": hostname,
            "severity": ("critical" if severity == 'critical' else "warning"),
            "source": "zombie",
            "message": f"zombies persist {zombies2}/{total2} ({ratio2:.3f}); action={action}"})

def handle_metric_recovery():
    handle_cpu()
    print(f"[INFO] Metrics-recovery (CPU) loop succeeded...")
    handle_memory()
    print(f"[INFO] Metrics-recovery (MEM) loop succeeded...")
    handle_load()
    print(f"[INFO] Metrics-recovery (LOAD) loop succeeded...")
    handle_zombies()
    print(f"[INFO] Metrics-recovery (ZOMBIES) loop succeeded...")


if __name__ == '__main__':
    print(f"[INFO] Metrics-recovery (CPU/MEM) loop running...")
    try:
        while True:
            handle_metric_recovery()
            time.sleep(60)  # run every minute
    except KeyboardInterrupt:
        print("[INFO] Metrics-recovery stopped by user")