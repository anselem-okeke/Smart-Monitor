"""
main_pod_recovery.py

env:
    export DATABASE_URL=postgresql://smart:smartpass@localhost:5432/smartdb
    export K8S_CLUSTER_NAME=kind-smart-monitor
    export K8S_CONTEXT=kind-smart-monitor
    export K8S_POD_RECOVERY_LOOKBACK_MIN=5
    export K8S_POD_RECOVERY_INTERVAL=60

Orchestrates K8s pod recovery:

  - reads recent *unhealthy* pods from k8s_pod_health
  - classifies each row into a decision (severity + action)
  - runs remediation with guardrails

This file does NOT talk to the K8s API directly; that is delegated
to remediator_pods (which enforces guardrails and dry_run).
"""

import os, sys
import time
from typing import Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db.db_access import recent_unhealthy_pods
from scripts.k8s.recovery.classifier_pods import classify_pod_row
from scripts.k8s.recovery.remediator_pods import (
    load_pod_guardrails,
    remediate_pod,
)


def handle_k8s_pod_recovery() -> None:
    """
    Oneshot handler:

      - Reads env for cluster/context/lookback
      - Fetches recent *unhealthy* pod snapshots from k8s_pod_health
      - Classifies each row into a decision
      - Runs remediation for each decision (with guardrails)
    """
    cluster_name = os.getenv("K8S_CLUSTER_NAME", "kind-smart-monitor")
    context: Optional[str] = os.getenv("K8S_CONTEXT") or None
    lookback_min = int(os.getenv("K8S_POD_RECOVERY_LOOKBACK_MIN", "5"))

    # Load guardrails once per run
    guardrails = load_pod_guardrails()

    rows = recent_unhealthy_pods(cluster_name, minutes=lookback_min)
    if not rows:
        print(f"[INFO] k8s_pod_recovery: no unhealthy pods in last {lookback_min} min for cluster={cluster_name}")
        return

    print(f"[INFO] k8s_pod_recovery: found {len(rows)} unhealthy pod snapshot(s) for cluster={cluster_name}")

    handled = 0
    for row in rows:
        decision = classify_pod_row(row)
        if not decision:
            continue

        remediate_pod(decision, guardrails, context=context)
        handled += 1

    print(f"[INFO] k8s_pod_recovery: processed {handled} decision(s)")


if __name__ == "__main__":
    """
    Standalone mode:

      K8S_POD_RECOVERY_INTERVAL   - seconds between sweeps (default: 60)
      K8S_POD_RECOVERY_LOOKBACK_MIN - how far back to look for unhealthy pods (default: 5)
      K8S_CLUSTER_NAME            - logical cluster name (default: kind-smart-monitor)
      K8S_CONTEXT                 - kubeconfig context (optional; can be empty)
    """
    interval = int(os.getenv("K8S_POD_RECOVERY_INTERVAL", "60"))
    print(f"[INFO] Starting K8s pod recovery loop (interval={interval}s) ...")

    try:
        while True:
            handle_k8s_pod_recovery()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("[INFO] K8s pod recovery loop stopped by user.")
