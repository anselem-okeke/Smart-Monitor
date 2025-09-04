#!/usr/bin/env python3
"""
    Smart-Monitor Orchestrator (root entrypoint)
        - Runs handlers on per-handler cadence with jitter
        - Graceful shutdown (SIGINT/SIGTERM)
        - Env overrides: DRY_RUN, RUN_ONCE, ONLY

        HOW TO RUN IT
          run everything, continuous
            python main.py

          run only zombies once (debugging)
            ONLY=metrics:zombies RUN_ONCE=1 python main.py

          override config (skip remediation)
            DRY_RUN=true python main.py

"""

# === Import handlers ===
import json
import logging
import os
import pathlib
import random
import signal
import socket
import time
import traceback

from db.auto_init import ensure_db_initialized
from scripts.monitor.monitor_system import handle_monitor_system
from scripts.monitor.network_tools import handle_network_tools
from scripts.monitor.process_monitor import handle_process_monitor
from scripts.monitor.service_monitor import handle_service_monitor
from scripts.recovery.service.service_recovery import handle_service_recovery
from scripts.recovery.disk.main import handle_disk_recovery
from scripts.recovery.metrics.main import handle_metric_recovery
from scripts.recovery.network.main import handle_network_recovery

HOSTNAME = socket.gethostname()
CFG_PATH = pathlib.Path(__file__).resolve().parents[0] / "config/metrics_recovery.json"
CFG = json.load(open(CFG_PATH))

class SafeExtraFormatter(logging.Formatter):
    def format(self, record):
        # make sure fields used in format string exist
        if not hasattr(record, "host"):
            record.host = HOSTNAME
        return super().format(record)

class HostFilter(logging.Filter):
    def filter(self, record):
        # ensure 'host' exists for the formatter
        if not hasattr(record, "host"):
            record.host = HOSTNAME
        return True

#----------------logging--------------------
def setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()

    handler = logging.StreamHandler()
    handler.setFormatter(SafeExtraFormatter(
        "%(asctime)s %(levelname)s host=%(host)s msg=%(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    # also add filter at handler-level (covers records bypassing root logger)
    handler.addFilter(HostFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level, logging.INFO))
    # keep filter on root too (belt & suspenders)
    root.addFilter(HostFilter())

class HostAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        kwargs["extra"] = {**kwargs.get("extra", {}), "host": HOSTNAME}
        return msg, kwargs

setup_logging()
log = HostAdapter(logging.getLogger("smart-monitor"), {})

# ---------- signals ----------
_SHUTDOWN = False
def _signal_handler(signum, frame):
    global _SHUTDOWN
    log.info(f"received signal {signum}; shutting down after current cycle…")
    _SHUTDOWN = True

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# ---------- env overrides ----------
def apply_env_overrides():
    val = os.getenv("DRY_RUN")
    if val is None:
        return
    on = str(val).strip().lower() in ("1", "true", "yes", "y")
    try:
        CFG["zombies"]["dry_run"] = on
        log.info(f"override: zombies.dry_run={on}")
    except Exception as e:
        log.warning(f"could not apply DRY_RUN override: {e}")

HANDLERS = [
    {
        "name": "metrics:system",
        "fn": handle_monitor_system,
        "interval": 60,  # run every 60s
        "jitter": 0.10,
        "next": 0.0,
    },

    {
        "name": "metrics:network",
        "fn": handle_network_tools,
        "interval": 60,  # run every 60s
        "jitter": 0.10,
        "next": 0.0,
    },

    {
        "name": "metrics:process",
        "fn": handle_process_monitor,
        "interval": 60,  # run every 60s
        "jitter": 0.10,
        "next": 0.0,
    },

    {
        "name": "metrics:service",
        "fn": handle_service_monitor,
        "interval": 60,  # run every 60s
        "jitter": 0.10,
        "next": 0.0,
    },

    {
        "name": "recovery:service",
        "fn": handle_service_recovery,
        "interval": 60,  # run every 60s
        "jitter": 0.10,
        "next": 0.0,
    },

    {
        "name": "recovery:disk",
        "fn": handle_disk_recovery,
        "interval": 300,  # run every 5min
        "jitter": 0.10,
        "next": 0.0,
    },

    {
        "name": "recovery:metrics",
        "fn": handle_metric_recovery,
        "interval": 60,  # run every 60s
        "jitter": 0.10,
        "next": 0.0,
    },

    {
        "name": "recovery:network",
        "fn": handle_network_recovery,
        "interval": 60,  # run every 60s
        "jitter": 0.10,
        "next": 0.0,
    }

]

def _with_jitter(base, frac):
    if not frac or frac <= 0: return base
    span = base * frac
    val = base + random.uniform(-span, span)
    return max(0.5 * base, val)

def run_handler(name, fn):
    start = time.time()
    try:
        fn()
        dur = time.time() - start
        log.info(f"{name} OK ({dur:.2f}s)")
    except Exception as e:
        dur = time.time() - start
        log.error(f"{name} FAILED ({dur:.2f}s) err={e}\n{traceback.format_exc()}")

def main():
    db_path, created, filled = ensure_db_initialized()
    if created:
        log.info(f"DB created and initialized at {db_path}")
    elif filled:
        log.info(f"DB at {db_path} was missing tables; created: {filled}")
    else:
        log.info(f"DB ready at {db_path}")

    apply_env_overrides()
    log.info("orchestrator starting… (Ctrl+C to stop)")

    # filter by ONLY (e.g., ONLY=metrics:zombies)
    only = os.getenv("ONLY")
    handlers = [h for h in HANDLERS if (not only or h["name"] == only)]

    # initialize next-run with stagger
    now = time.time()
    for h in handlers:
        h["next"] = now + random.uniform(0, _with_jitter(h["interval"], h["jitter"]))

    run_once = os.getenv("RUN_ONCE", "").lower() in ("1","true","yes","y")
    idle_sleep = 0.5

    while not _SHUTDOWN:
        now = time.time()
        did_any = False
        for h in handlers:
            if now >= h["next"]:
                did_any = True
                run_handler(h["name"], h["fn"])
                h["next"] = time.time() + _with_jitter(h["interval"], h["jitter"])
        if run_once:
            break
        if not did_any:
            time.sleep(idle_sleep)

    log.info("orchestrator stopped. bye.")

if __name__ == "__main__":
    main()