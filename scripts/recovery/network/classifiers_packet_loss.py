def is_packet_loss_100(event):
    """Return True when ping loss 100% of packets
    event tuple =(id, target, method, result, packet_loss_percent)"""
    _, tgt, method, res, _, loss = event
    if method == "ping" and loss is not None and loss >= 100.0:
        return True
    if method in {"ping", "traceroute"} and isinstance(res, str) and "timed out" in res.lower():
        return True
    return False