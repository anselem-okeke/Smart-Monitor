WARN_INODE = 90
CRIT_INODE = 95

def is_inode_exhausted(row) -> bool:
    """

    :param row: timestamp, inode_usage
    :return: bool
    """
    _ts, inode_pct = row
    return inode_pct is not None and inode_pct >= WARN_INODE