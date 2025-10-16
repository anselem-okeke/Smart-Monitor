WARN_TH = 90    # percent, override via config later
CRIT_TH = 95

# def is_disk_full(row) -> bool:
#     """
#     row = (timestamp, disk_usage)
#     :param row:
#     :return: bool
#     """
#
#     _ts, usage = row
#     return usage is not None and usage >= WARN_TH


from typing import Any, Iterable, Tuple, Union, Optional


def _to_float(x: Any) -> Optional[float]:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


Row = Union[Tuple[Any, Any], Iterable[Any], dict]

def is_disk_full(row: Row) -> bool:
    """
    row: (ts, usage_pct) or {'ts_epoch': ..., 'usage_pct': ...}
    returns True if usage_pct >= WARN_TH
    """
    # support tuple/iterable or dict rows
    if isinstance(row, dict):
        usage_raw = row.get("usage_pct") or row.get("disk_usage") or row.get("usage")
    else:
        try:
            _, usage_raw = row  # tuple-like
        except Exception as e:
            print(f"{e}")
            return False

    usage = _to_float(usage_raw)
    return usage is not None and usage >= WARN_TH

def is_disk_critical(row: Row) -> bool:
    if isinstance(row, dict):
        usage_raw = row.get("usage_pct") or row.get("disk_usage") or row.get("usage")
    else:
        try:
            _, usage_raw = row
        except Exception as e:
            print(f"{e}")
            return False
    usage = _to_float(usage_raw)
    return usage is not None and usage >= CRIT_TH


