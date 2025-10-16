# WARN_INODE = 90
# CRIT_INODE = 95
#
# def is_inode_exhausted(row) -> bool:
#     """
#
#     :param row: timestamp, inode_usage
#     :return: bool
#     """
#     _ts, inode_pct = row
#     return inode_pct is not None and inode_pct >= WARN_INODE

from typing import Any, Iterable, Tuple, Union, Optional

WARN_INODE: float = 90.0
CRIT_INODE: float = 95.0

Number = Union[int, float]

def _to_float(x: Any) -> Optional[float]:
    try:
        # handle "92", "92.0", Decimal, etc.
        return float(x)
    except (TypeError, ValueError):
        return None

def is_inode_exhausted(row: Union[Tuple[Any, Any], Iterable[Any]]) -> bool:
    """
    row: (timestamp, inode_usage_pct)  -- values may be str/float/int/None
    returns True if inode_usage_pct >= WARN_INODE
    """
    try:
        _ts, inode_pct_raw = row  # tuple-like
    except Exception as e:
        print(f"{e}")
        return False

    inode_pct = _to_float(inode_pct_raw)
    return inode_pct is not None and inode_pct >= WARN_INODE
