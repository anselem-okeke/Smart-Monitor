# import platform
#
#
# def is_load_spike(rows, cores, warn_mult, consecutive):
#     """
#
#     :param rows: list[(timestamp, load_avg)] newest first
#     :param cores:
#     :param warn_mult:
#     :param consecutive:
#     :return:  Return True if we have >= `consecutive` samples AND each sample's load
#     >= cores * warn_mult. On Windows, always False (no real loadavg)
#     """
#
#     if platform.system() == "Windows":
#         return False
#
#     if len(rows) < consecutive or not cores or cores <= 0:
#         return False
#
#     vals = [la for _, la in rows[:consecutive] if la is not None]
#     if len(vals) < consecutive:
#         return False
#
#     threshold = cores * float(warn_mult)
#
#     return all(float(la) >= threshold for la in vals)
#
# def current_load_and_threshold(rows, cores, mult):
#     """
#     Convenience helper to format numbers for messages
#     :param rows:
#     :param cores:
#     :param mult:
#     :return: Returns (current_load, threshold_value) or (None, None)
#     """
#
#     if not rows:
#         return None, None
#     cur = rows[0][1]
#     if cur is None or not cores:
#         return None, None
#     return float(cur), cores * float(mult)

import platform

def is_load_spike(rows, cores, warn_mult, consecutive):
    """
    rows: list of (timestamp, load_avg) tuples, newest first
    Return True iff we have >= `consecutive` samples AND each sample's load
    >= cores * warn_mult. On Windows, always False.
    """
    if platform.system() == "Windows":
        return False

    # Make sure thresholds are numeric
    try:
        c = float(cores)
        mult = float(warn_mult)
    except (TypeError, ValueError):
        return False
    if c <= 0 or len(rows) < consecutive:
        return False

    # Collect the first `consecutive` load values, coercing to float
    vals = []
    for i in range(consecutive):
        try:
            la = rows[i][1]          # expect (ts, load_avg)
        except Exception:
            return False
        if la is None:
            return False
        try:
            vals.append(float(la))
        except (TypeError, ValueError):
            return False

    threshold = c * mult
    return all(v >= threshold for v in vals)


def current_load_and_threshold(rows, cores, mult):
    """
    Convenience helper for messages.
    Returns (current_load_float, threshold_float) or (None, None)
    """
    if not rows:
        return None, None
    try:
        cur = rows[0][1]  # expect (ts, load_avg)
    except Exception:
        return None, None
    if cur is None:
        return None, None
    try:
        c = float(cores)
        m = float(mult)
        return float(cur), c * m
    except (TypeError, ValueError):
        return None, None
