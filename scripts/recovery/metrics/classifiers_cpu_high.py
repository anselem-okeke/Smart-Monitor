# def is_cpu_high(rows, warn_thresh, consecutive):
#     """
#     rows: list[(timestamp, cpu_usage)] newest first
#     :param rows:
#     :param warn_thresh:
#     :param consecutive:
#     :return: True if we have atleast consecutive samples
#     and all >= warn_thresh
#
#
#     CPU HIGH VS MEMORY PRESSURE
#     | Aspect                                  | **CPU High**                                                                                             | **Memory Pressure / Swap-in-Use**                                                     |
#     | --------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
#     | **What metric rises**                   | • `cpu_usage %` (instant or averaged)<br>• `load_average` (Linux)                                        | • `memory_usage %` (RSS in use)<br>• `swap_usage %` *or* swap-in/out rate             |
#     | **Hardware resource**                   | CPU cores / cycles                                                                                       | RAM capacity and swap space                                                           |
#     | **Typical root causes**                 | *Compute-bound loops* (infinite loop, crypto hashing, video encoding, runaway thread)                    | *Footprint growth* (memory leak, big dataset load, cache balloon, many JVMs)          |
#     | **Primary symptom**                     | Slow response time but **system stays responsive**; tasks queue on CPU                                   | System begins swapping → dramatic slowdown, OOM-killer, processes exit, kernel stalls |
#     | **Short-term risk**                     | Throughput drops; higher power & heat                                                                    | Kernel may kill critical services or panic; data corruption possible                  |
#     | **SRE first actions**                   | • Identify top CPU PIDs<br>• Throttle or kill runaway processes<br>• Scale horizontally if load is legit | • Restart leak-prone service<br>• Free caches / tmpfs<br>• Add RAM or tune limits     |
#     | **Post-verify success**                 | CPU % falls below warn threshold within seconds                                                          | Memory % and swap fall; OOM events cease                                              |
#     | **Long-term fix**                       | Profile code, optimize algorithms, add CPU cores                                                         | Fix memory leaks, tune heap sizes, add RAM, enable cgroup limits                      |
#     | **Automated remediation in our module** | Optional **kill** of a whitelisted high-CPU process (guard-railed)                                       | Optional **restart** leaky service or kill whitelisted RSS pig; otherwise alert-only  |
#
#     """
#     if len(rows) < consecutive:
#         return False
#     usages = [u for _, u in rows[:consecutive] if u is not None]
#     return len(usages) == consecutive and all(u >= warn_thresh for u in usages)

# scripts/recovery/metrics/classifiers_cpu_high.py
from typing import Any, Iterable, Sequence, Optional


def _to_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def is_cpu_high(rows: Sequence[Iterable[Any]], warn_thresh, consecutive) -> bool:
    """
    rows: sequence of (ts, cpu_percent) where values may be str/float/int/None
    warn_thresh: numeric or str; consecutive: int or str
     rows: list[(timestamp, cpu_usage)] newest first
    :param rows:
    :param warn_thresh:
    :param consecutive:
    :return: True if we have atleast consecutive samples
    and all >= warn_thresh


    CPU HIGH VS MEMORY PRESSURE
    | Aspect                                  | **CPU High**                                                                                             | **Memory Pressure / Swap-in-Use**                                                     |
    | --------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
    | **What metric rises**                   | • `cpu_usage %` (instant or averaged)<br>• `load_average` (Linux)                                        | • `memory_usage %` (RSS in use)<br>• `swap_usage %` *or* swap-in/out rate             |
    | **Hardware resource**                   | CPU cores / cycles                                                                                       | RAM capacity and swap space                                                           |
    | **Typical root causes**                 | *Compute-bound loops* (infinite loop, crypto hashing, video encoding, runaway thread)                    | *Footprint growth* (memory leak, big dataset load, cache balloon, many JVMs)          |
    | **Primary symptom**                     | Slow response time but **system stays responsive**; tasks queue on CPU                                   | System begins swapping → dramatic slowdown, OOM-killer, processes exit, kernel stalls |
    | **Short-term risk**                     | Throughput drops; higher power & heat                                                                    | Kernel may kill critical services or panic; data corruption possible                  |
    | **SRE first actions**                   | • Identify top CPU PIDs<br>• Throttle or kill runaway processes<br>• Scale horizontally if load is legit | • Restart leak-prone service<br>• Free caches / tmpfs<br>• Add RAM or tune limits     |
    | **Post-verify success**                 | CPU % falls below warn threshold within seconds                                                          | Memory % and swap fall; OOM events cease                                              |
    | **Long-term fix**                       | Profile code, optimize algorithms, add CPU cores                                                         | Fix memory leaks, tune heap sizes, add RAM, enable cgroup limits                      |
    | **Automated remediation in our module** | Optional **kill** of a whitelisted high-CPU process (guard-railed)                                       | Optional **restart** leaky service or kill whitelisted RSS pig; otherwise alert-only  |

    """
    # coerce thresholds
    warn = _to_float(warn_thresh) or 85.0
    try:
        need = int(float(consecutive))
    except (TypeError, ValueError):
        need = 3

    if len(rows) < need:
        return False

    vals: list[float] = []
    for pair in rows[:need]:
        # support tuple rows or dict rows
        if isinstance(pair, dict):
            u = pair.get("cpu_percent") or pair.get("cpu")  # adapt if your key differs
        else:
            _, u = pair
        v = _to_float(u)
        if v is None:
            return False  # missing/invalid datapoint → not "high"
        vals.append(v)

    return len(vals) == need and all(v >= warn for v in vals)
