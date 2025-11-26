"""
classifier_cluster.py

Pure classification logic for cluster health rows from k8s_cluster_health.
"""

from typing import Any, Dict, Optional, Tuple


def _row_to_record(row: Tuple[Any, ...]) -> Dict[str, Any]:
    """
    Expected tuple order:
      0: id
      1: timestamp
      2: cluster_name
      3: api_reachable
      4: k8s_version
    """
    return {
        "id": row[0],
        "timestamp": row[1],
        "cluster_name": row[2],
        "api_reachable": row[3],
        "k8s_version": row[4],
    }


def _build_decision(
    rec: Dict[str, Any],
    severity: str,
    action: str,
    kind: str,
    message: str,
) -> Dict[str, Any]:
    """
    Standard decision dict for cluster remediation.
    """
    return {
        "id": rec["id"],
        "timestamp": rec["timestamp"],
        "cluster_name": rec["cluster_name"],
        "api_reachable": rec["api_reachable"],
        "k8s_version": rec["k8s_version"],

        "severity": severity,   # e.g. "critical"
        "action": action,       # e.g. "alert_only"
        "kind": kind,           # e.g. "APIDown"
        "message": message,
    }


def classify_cluster_row(row: Any) -> Optional[Dict[str, Any]]:
    """
    Classify one k8s_cluster_health row.

    v1 logic:
      - api_reachable = False → critical "APIDown", alert_only
      - api_reachable = True  → ignore (no decision)
    """
    rec = _row_to_record(row)

    if rec["api_reachable"]:
        # Cluster is fine; no remediation needed
        return None

    # Simple v1 classification: API is down
    msg = (
        f"K8s API appears unreachable for cluster={rec['cluster_name']} "
        f"(version={rec['k8s_version'] or 'unknown'})"
    )
    return _build_decision(
        rec=rec,
        severity="critical",
        action="alert_only",
        kind="APIDown",
        message=msg,
    )
