"""
main_cluster_recovery.py

Orchestrates cluster-level health alerts:

  - reads recent *unhealthy* k8s_cluster_health rows
  - classifies each into a decision
  - alerts via remediator_cluster
"""

import os, sys
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db.db_access import recent_unhealthy_cluster_events
from scripts.k8s.recovery.classifier_cluster import classify_cluster_row
from scripts.k8s.recovery.remediator_cluster import (
    load_cluster_guardrails,
    remediate_cluster,
)


def handle_k8s_cluster_recovery() -> None:
    """
    Oneshot handler:

      - Reads env for cluster + lookback
      - Fetches recent unhealthy cluster snapshots (api_reachable = false)
      - Classifies and alerts with guardrails/cooldown
    """
    cluster_name = os.getenv("K8S_CLUSTER_NAME", "kind-smart-monitor")
    lookback_min = int(os.getenv("K8S_CLUSTER_RECOVERY_LOOKBACK_MIN", "5"))

    guardrails = load_cluster_guardrails()

    rows = recent_unhealthy_cluster_events(cluster_name, minutes=lookback_min)
    if not rows:
        print(f"[INFO] k8s_cluster_recovery: no unhealthy cluster events in last {lookback_min} min for {cluster_name}")
        return

    print(f"[INFO] k8s_cluster_recovery: found {len(rows)} unhealthy cluster snapshot(s) for {cluster_name}")

    handled = 0
    for row in rows:
        decision = classify_cluster_row(row)
        if not decision:
            continue

        remediate_cluster(decision, guardrails)
        handled += 1

    print(f"[INFO] k8s_cluster_recovery: processed {handled} decision(s)")


if __name__ == "__main__":
    interval = int(os.getenv("K8S_CLUSTER_RECOVERY_INTERVAL", "60"))
    print(f"[INFO] Starting K8s cluster recovery loop (interval={interval}s) ...")
    try:
        while True:
            handle_k8s_cluster_recovery()
            time.sleep(interval)
    except KeyboardInterrupt:
        print("[INFO] K8s cluster recovery loop stopped by user.")
