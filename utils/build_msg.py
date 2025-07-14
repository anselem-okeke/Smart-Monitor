import socket

def build_msg(event, action, result):
    _id, tgt, mtd, res, latency, loss = event
    parts = [
        f"hostname={socket.gethostname()},"
        f"target={tgt},"
        f"method={mtd},"
        f"action={action},"
        f"latency={latency},"
        f"result={result}"
    ]
    if loss is not None:
        parts.append(f"loss={loss}")
    return " ".join(parts)