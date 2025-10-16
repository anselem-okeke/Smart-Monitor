# def is_memory_high(rows, warn_th, swap_th, consecutive):
#     """
#     rows = list[(timestamp, mem%, swap%)] newest first
#     Trigger if at least `consecutive` samples have:
#       • memory_usage >= warn_th  AND
#       • swap_usage    >=  swap_th
#
#     | Concept                          | Explanation                                                                                                                                                                                                                           |
#     | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
#     | **Swap space**                   | A reserved area on disk (Linux `swap partition` / `swapfile`, Windows **pagefile.sys**) that the OS uses as *overflow* for inactive memory pages when physical RAM is full.                                                           |
#     | **Memory pressure**              | When `memory_usage %` (actual RAM in use) climbs so high that the kernel starts paging data out to swap to create free RAM frames.                                                                                                    |
#     | **Swap-in / swap-out**           | • **Swap-out**: move a RAM page → disk (slow but frees RAM)<br>• **Swap-in**: bring it back when accessed (slower, causes latency spike).                                                                                             |
#     | **Why swap > 0 % is a red flag** | • Indicates RAM was *already* exhausted.<br>• Disk I/O is orders of magnitude slower than RAM → response times degrade.<br>• Heavy swapping can lead to “thrashing,” where CPU time is spent just paging data, not doing useful work. |
#     | **Kernel escalation**            | If swap + RAM both fill, Linux invokes the **OOM-killer**; Windows raises “low memory” and may terminate processes—both disruptive.                                                                                                   |
#     | **Good practice**                | • Keep swap **mostly idle** in normal operation (0–2 %).<br>• Alert when it rises (e.g., > 0 % *and* RAM ≥ 85 %).                                                                                                                     |
#     | **SRE remediation**              | 1. Identify leak or runaway process.<br>2. Restart/kill it or scale out.<br>3. Long term: add RAM, tune swappiness, set cgroup/Job limits.                                                                                            |
#
#     """
#     if len(rows) < consecutive:
#         return False
#
#     count = 0
#
#     for _, mem, swap in rows[:consecutive]:
#         if mem is None or swap is None:
#             continue
#         if mem >= warn_th and swap >= swap_th:
#             count += 1
#
#     return count >= consecutive


# scripts/recovery/metrics/classifiers_mem_high.py
from typing import Any, Iterable, Sequence, Optional


def _to_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

def _to_int(x: Any, default: int) -> int:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return default

def is_memory_high(rows: Sequence[Iterable[Any]], warn_th, swap_th, consecutive) -> bool:
    """
    rows: sequence of (ts, mem_pct, swap_pct) or dicts with keys like
          {'ts_epoch': ..., 'mem_pct': ..., 'swap_pct': ...}
    warn_th, swap_th: numeric or str thresholds
    consecutive: int or str
    """
    warn = _to_float(warn_th) or 85.0
    swap_req = _to_float(swap_th) or 10.0
    need = _to_int(consecutive, 3)

    if len(rows) < need:
        return False

    hits = 0
    for r in rows[:need]:
        if isinstance(r, dict):
            mem = _to_float(r.get("mem_pct") or r.get("memory_pct") or r.get("mem"))
            swp = _to_float(r.get("swap_pct") or r.get("swap"))
        else:
            # tuple/iterable: (ts, mem, swap)
            try:
                _, mem_raw, swp_raw = r
            except Exception as e:
                print(f"{e}")
                return False
            mem = _to_float(mem_raw)
            swp = _to_float(swp_raw)

        if mem is None or swp is None:
            return False  # missing datapoint → treat as not-high (safer)
        if mem >= warn and swp >= swap_req:
            hits += 1

    return hits >= need

