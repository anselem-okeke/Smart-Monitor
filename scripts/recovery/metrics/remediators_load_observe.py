# import json
import os
# import pathlib
import socket
import sys

import psutil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.network_file_logger import net_log

hostname = socket.gethostname()
# CFG = json.load(open(pathlib.Path(__file__).resolve().parents[3] / "config/metrics_recovery.json"))
# LOAD = CFG["load"]

def snapshot_hotspots(top_n=5):
    """
    :param top_n:
    :return:  Returns a small dict with top CPU processes, run queue size,
    and (if Linux) %iowait, for observability
    """

    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'num_threads']):
        try:
            procs.append(p.info)
        except psutil.Error:
            pass

    procs.sort(key=lambda x: x.get('cpu_percent') or 0.0, reverse=True)
    top = [
        {
            "pid":p["pid"], "name":p["name"], "cpu%":p["cpu_percent"], "threads":p["num_threads"]
        }
           for p in procs[:top_n]
    ]

    ctx = {
        "top": top
    }

    try:
        cpu_times = psutil.cpu_times_percent(interval=0.5)
        if hasattr(cpu_times, "iowait"):
            ctx["iowait%"] = cpu_times.iowait
    except Exception as e:
        print(f"Error as: {e}")

    try:
        ctx["run_queue_len"] = len(psutil.pids())
    except Exception as e:
        print(f"Error as: {e}")
    return ctx

def log_load_context(current_load, threshold, severity="warning"):
    ctx = snapshot_hotspots()
    msg = (
        f"hostname={hostname} load={current_load:.2f} threshold={threshold:.2f}"
        f"top={ctx.get('top')} iowait%={ctx.get('iowait%', 'na')}"
        f"rqlen={ctx.get('run_queue_len', 'na')}"
    )

    net_log(severity, msg) #alert-only, nothing to fix automatically
    return False