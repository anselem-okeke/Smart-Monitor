import sys
import os
from typing import Dict, Any, Optional

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from kubernetes import client, config
from scripts.k8s.monitor.monitor_k8s_pods import get_core_v1

from db.db_logger import log_k8s_cluster_health

def env():
    """
    export DATABASE_URL=postgresql://smart:smartpass@localhost:5432/smartdb
    export K8S_CLUSTER_NAME=kind-smart-monitor
    export K8S_CONTEXT=kind-smart-monitor
    export K8S_POD_RECOVERY_LOOKBACK_MIN=5
    export K8S_POD_RECOVERY_INTERVAL=60
    :return:
    """

def collect_k8s_cluster_health(
    cluster_name: str,
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Check if the Kubernetes API is reachable and get its version.

    Returns a dict:
      {
        "cluster_name": "...",
        "api_reachable": True/False,
        "k8s_version": "v1.xx.y" or None
      }
    """
    # type-only declarations (no initial value → no "unused value" warning)
    api_reachable: bool
    version_str: Optional[str]

    try:
        # 1) Get a core client (uses in-cluster config or kubeconfig)
        v1 = get_core_v1(context=context)

        # 2) Simple "ping" to API: try to list 1 namespace
        v1.list_namespace(limit=1)
        api_reachable = True

        # 3) If API is reachable, ask the Version API
        ver_api = client.VersionApi()
        ver_info = ver_api.get_code()          # returns gitVersion, major, minor...
        version_str = ver_info.git_version     # e.g. "v1.34.0"

    except Exception as e:
        # If anything fails, we assume API is down or unreachable
        print(f"[ERROR] collect_k8s_cluster_health: {e}")
        api_reachable = False
        version_str = None

    snapshot = {
        "cluster_name": cluster_name,
        "api_reachable": api_reachable,
        "k8s_version": version_str,
    }

    print(
        f"[INFO] collect_k8s_cluster_health: "
        f"cluster={cluster_name} reachable={api_reachable} version={version_str}"
    )
    return snapshot


def handle_monitor_k8s_cluster():
    """
    Oneshot handler:

      - Builds one cluster/API health snapshot
      - Logs it into k8s_cluster_health
    """
    cluster_name = os.getenv("K8S_CLUSTER_NAME", "kind-smart-monitor")
    context = os.getenv("K8S_CONTEXT") or None

    snapshot = collect_k8s_cluster_health(
        cluster_name=cluster_name,
        context=context,
    )
    log_k8s_cluster_health(snapshot)

if __name__ == "__main__":
    # Standalone, one-shot run for debugging

    cluster_name = os.getenv("K8S_CLUSTER_NAME", "kind-smart-monitor")
    context = os.getenv("K8S_CONTEXT") or None

    snapshot = collect_k8s_cluster_health(
        cluster_name=cluster_name,
        context=context,
    )
    log_k8s_cluster_health(snapshot)
    print("[INFO] k8s_cluster_health snapshot logged once (standalone).")


