import json
import pathlib
import socket
import sys
import os
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
print(PROJECT_ROOT)


from db.db_access import recent_cpu_samples
from scripts.recovery.metrics.classifiers_cpu_high import is_cpu_high
from scripts.recovery.metrics.remediators_cpu_kill import kill_runaway_process, top_cpu_processes
from scripts.db_logger import log_alert
from utils.network_file_logger import net_log

hostname = socket.gethostname()
CFG_PATH = pathlib.Path(__file__).resolve().parents[3] / "config/metrics_recovery.json"
CFG = json.load(open(CFG_PATH))
CPU = CFG["cpu"]

def handle_cpu():
    print(f"[DEBUG] Attempting Metrics-recovery (CPU) for host: {hostname}")
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

if __name__ == '__main__':
    print(f"[INFO] Metrics-recovery (CPU) loop running...")
    try:
        while True:
            handle_cpu()
            print(f"[INFO] Metrics-recovery (CPU) loop succeeded...")
            time.sleep(60)  # run every minute
    except KeyboardInterrupt:
        print("[INFO] Metrics-recovery stopped by user")