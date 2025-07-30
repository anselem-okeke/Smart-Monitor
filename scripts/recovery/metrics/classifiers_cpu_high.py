def is_cpu_high(rows, warn_thresh, consecutive):
    """
    rows: list[(timestamp, cpu_usage)] newest first
    :param rows:
    :param warn_thresh:
    :param consecutive:
    :return: True if we have atleast consecutive samples
    and all >= warn_thresh
    """
    if len(rows) < consecutive:
        return False
    usages = [u for _, u in rows[:consecutive] if u is not None]
    return len(usages) == consecutive and all(u >= warn_thresh for u in usages)