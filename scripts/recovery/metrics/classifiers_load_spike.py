import platform


def is_load_spike(rows, cores, warn_mult, consecutive):
    """

    :param rows: list[(timestamp, load_avg)] newest first
    :param cores:
    :param warn_mult:
    :param consecutive:
    :return:  Return True if we have >= `consecutive` samples AND each sample's load
    >= cores * warn_mult. On Windows, always False (no real loadavg)
    """

    if platform.system() == "Windows":
        return False

    if len(rows) < consecutive or not cores or cores <= 0:
        return False

    vals = [la for _, la in rows[:consecutive] if la is not None]
    if len(vals) < consecutive:
        return False

    threshold = cores * float(warn_mult)

    return all(float(la) >= threshold for la in vals)

def current_load_and_threshold(rows, cores, mult):
    """
    Convenience helper to format numbers for messages
    :param rows:
    :param cores:
    :param mult:
    :return: Returns (current_load, threshold_value) or (None, None)
    """

    if not rows:
        return None, None
    cur = rows[0][1]
    if cur is None or not cores:
        return None, None
    return float(cur), cores * float(mult)

