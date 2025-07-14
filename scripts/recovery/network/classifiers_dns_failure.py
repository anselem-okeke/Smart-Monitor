def is_dns_failure(event):
    """
    Detects common DNS failure patterns in nslookup output
    :param event: tuple of network events
    :return: bool
    """
    _id, tgt, method, res, latency, _ = event

    if method != "nslookup" or not res:
        return False

    result = res.lower()
    return any(term in result for term in [
        "non-existent domain",
        "can't find",
        "unknown",
        "server failed",
        "no response from server",
        "timed out"
    ])