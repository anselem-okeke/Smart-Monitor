WARN_TH = 90    # percent, override via config later
CRIT_TH = 95

def is_disk_full(row) -> bool:
    """
    row = (timestamp, disk_usage)
    :param row:
    :return: bool
    """

    _ts, usage = row
    return usage is not None and usage >= WARN_TH

