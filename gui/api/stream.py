from flask import Response, stream_with_context
from . import api_bp
from .. import read_service as rs
import json, time

@api_bp.get("/stream/alerts")
def stream_alerts():
    """Server-Sent Events stream of new alerts. Heartbeat keeps proxies alive."""
    def gen():
        last_id = rs.last_alert_id()
        idle = 0
        while True:
            rows = rs.alerts_after(last_id, max_rows=100)
            if rows:
                for r in rows:
                    last_id = r["id"]
                    yield f"event: alert\n" \
                          f"data: {json.dumps(r)}\n\n"
                idle = 0
            else:
                # heartbeat every ~15s to keep the connection alive through proxies
                idle += 1
                if idle % 15 == 0:
                    yield ": keepalive\n\n"
            time.sleep(1.0)

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",   # nginx: disable proxy buffering
    }
    return Response(stream_with_context(gen()), headers=headers)