#!/usr/bin/env python3
#------------------------------------------
"""Author: Anselem Okeke
    MIT License
    Copyright (c) 2025 Anselem Okeke
    See LICENSE file in the project root for full license text.



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
#------------------------------------------

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
from asyncio import QueueEmpty
from multiprocessing import Queue, Process

from db.auto_init import ensure_db_initialized
from scripts.monitor.monitor_system import handle_monitor_system
from scripts.monitor.network_tools import handle_network_tools
from scripts.monitor.process_monitor import handle_process_monitor
from scripts.monitor.service_monitor import handle_service_monitor
from scripts.recovery.service.service_recovery import handle_service_recovery
from scripts.recovery.disk.main import handle_disk_recovery
from scripts.recovery.metrics.main import handle_metric_recovery
from scripts.recovery.network.main import handle_network_recovery
from scripts.recovery.disk.collect_smart import collect_smart_once
from scripts.k8s.monitor.monitor_k8s_pods import handle_monitor_k8s_pods
from scripts.k8s.monitor.monitor_k8s_cluster import handle_monitor_k8s_cluster
from scripts.k8s.recovery.main_pod_recovery import handle_k8s_pod_recovery
from scripts.k8s.recovery.main_cluster_recovery import handle_k8s_cluster_recovery

monotonic = time.monotonic
HOSTNAME = socket.gethostname()
CFG_PATH = pathlib.Path(__file__).resolve().parents[0] / "config/metrics_recovery.json"
CFG = json.load(open(CFG_PATH))

import os, sys
if os.name == "nt":
    try:
        # Prefer robust UTF-8 output; avoid crashes on odd consoles
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception as e:
        print(f"{e}")
        pass

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
        "timeout": 120,
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
    },

    {
        "name": "metrics:smart",
        "fn": collect_smart_once,
        "interval": 6*3600,   # every 6 hours 6*3600
        "jitter": 0.10,
        "timeout": 180,
        "next": 0.0,
    },

    {
        "name": "k8s:pod_health",
        "fn": handle_monitor_k8s_pods,
        "interval": 60,
        "jitter": 0.10,
        "next": 0.0,
    },

    {
        "name": "k8s:cluster_health",
        "fn": handle_monitor_k8s_cluster,
        "interval": 60,
        "jitter": 0.10,
        "next": 0.0,
    },

    {
        "name": "k8s:cluster_recovery",
        "fn": handle_k8s_cluster_recovery,
        "interval": 60,
        "jitter": 0.10,
        "next": 0.0,
    },

    {
        "name": "k8s:pod_recovery",
        "fn": handle_k8s_pod_recovery,
        "interval": 60,   # run every 60s in normal mode
        "jitter": 0.10,
        "next": 0.0,
    }
]

def _with_jitter(base, frac):
    if not frac or frac <= 0:
        return base
    span = base * frac
    val = base + random.uniform(-span, span)
    return max(0.5 * base, val)

def run_fn(fn, q):
    try:
        fn()
        q.put(("ok", None))
    except Exception as a:
        print(f"{a}")
        q.put(("err", traceback.format_exc()))

def run_handler_with_timeout(name, fn, timeout_sec):
    q = Queue()
    p = Process(target=run_fn, args=(fn, q), daemon=True)
    p.start()
    p.join(timeout=timeout_sec)
    if p.is_alive():
        p.terminate()
        p.join(1)
        log.error(f"{name} TIMEOUT after {timeout_sec}...")
        return False
    try:
        status, err = q.get_nowait()
    except QueueEmpty:
        log.error(f"{name} exited without status (crash?)")
        return False
    if status == "ok":
        log.info(f"{name} OK...")
        return True
    else:
        log.error(f"{name} FAILED\n{err}...")
        return False

def run_handler(name, fn):
    start = time.time()
    try:
        fn()
        dur = time.time() - start
        log.info(f"{name} OK ({dur:.2f}s)")
    except Exception as e:
        dur = time.time() - start
        log.error(f"{name} FAILED ({dur:.2f}s) err={e}\n{traceback.format_exc()}")

def _using_pg():
    dsn = os.getenv("DATABASE_URL", "")
    return dsn.startswith(("postgres://", "postgresql://"))


def main():
    # db_path, created, filled = ensure_db_initialized()
    # if created:
    #     log.info(f"DB created and initialized at {db_path}")
    # elif filled:
    #     log.info(f"DB at {db_path} was missing tables; created: {filled}")
    # else:
    #     log.info(f"DB ready at {db_path}")

    # only initialize (or check) when starting; safe for both backends
    target, created, info = ensure_db_initialized()
    if _using_pg():
        if created:
            log.info(f"Postgres schema applied at {target}")
        if info:
            log.info(f"PG tables created/missing before: {info}")
    else:
        if created:
            log.info(f"SQLite DB created at {target}")
        elif info:
            log.info(f"SQLite tables created: {info}")
        else:
            log.info(f"SQLite DB ready at {target}")

    apply_env_overrides()
    log.info("orchestrator starting… (Ctrl+C to stop)")

    # filter by ONLY (e.g., ONLY=metrics:zombies)
    only = os.getenv("ONLY")
    handlers = [h for h in HANDLERS if (not only or h["name"] == only)]

    # initialize next-run with stagger
    now = monotonic()
    for h in handlers:
        h["next"] = now + random.uniform(0, _with_jitter(h["interval"], h["jitter"]))

    run_once = os.getenv("RUN_ONCE", "").lower() in ("1","true","yes","y")
    IDLE_MIN = 0.05
    IDLE_MAX = 2.0

    while not _SHUTDOWN:
        now = monotonic()
        next_due = now + 3600.0  # far future

        for h in handlers:
            if now >= h["next"]:
                # handlers must be single-pass (no inner while True)
                run_handler_with_timeout(h["name"], h["fn"], h.get("timeout", 30))
                h["next"] = monotonic() + _with_jitter(h["interval"], h["jitter"])

            # track ealiest next run
            if h["next"] < next_due:
                next_due = h["next"]

        if run_once:
            break
        # sleep exactly until something is due (with clamps)
        sleep_for = min(IDLE_MAX, max(IDLE_MIN, next_due - monotonic()))
        time.sleep(sleep_for)

    log.info("orchestrator stopped. bye.")

if __name__ == "__main__":
    main()

# vagrant ssh web01 -- -N -L 5000:127.0.0.1:5000
# python3 -m flask --app gui.app run --debug --host 0.0.0.0 --port 5050