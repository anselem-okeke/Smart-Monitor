LATENCY_THRESHOLD_MS = 300

def is_latency_spike(event) -> bool:
    """
    Detects if ping latency exceeds threshold.
    Works with both Windows and Linux ping outputs.
    """
    _id, _tgt, method, result_txt, latency_ms, _loss = event

    if method != "ping":
        return False

    try:
        if latency_ms is not None and float(latency_ms) > LATENCY_THRESHOLD_MS:
            return True
        return False
    except ValueError:
        return False
