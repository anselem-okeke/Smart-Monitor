# api/stream.py
from flask import Response, stream_with_context, request
from . import api_bp
from .. import read_service as rs
import json, time
from datetime import datetime, date, timezone

HEARTBEAT_SEC = 15
POLL_INTERVAL = 1.0  # seconds
MAX_BATCH     = 100

# JSON serializer that handles datetime/date cleanly
def _json_default(o):
    if isinstance(o, datetime):
        # normalize to UTC ISO-8601 (Z)
        if o.tzinfo is None:
            o = o.replace(tzinfo=timezone.utc)
        else:
            o = o.astimezone(timezone.utc)
        return o.isoformat().replace("+00:00", "Z")
    if isinstance(o, date):
        return o.isoformat()
    # final fallback so the stream never crashes
    return str(o)

@api_bp.get("/stream/alerts")
def stream_alerts():
    """
    Server-Sent Events stream of new alerts.
    - Supports Last-Event-ID so the client can resume.
    - Sends a heartbeat every HEARTBEAT_SEC seconds.
    - Ensure nginx/cloudflared disable buffering for this path.
    """
    def gen():
        # Resume support via Last-Event-ID header or ?last_id=123
        last_id_hdr = request.headers.get("Last-Event-ID")
        last_id_qs  = request.args.get("last_id")
        try:
            last_id = int(last_id_hdr or last_id_qs) if (last_id_hdr or last_id_qs) else rs.last_alert_id()
        except Exception:
            last_id = rs.last_alert_id()

        idle_ticks = 0

        # Hint clients to retry after 10s on disconnect
        yield "retry: 10000\n\n"

        try:
            while True:
                try:
                    rows = rs.alerts_after(last_id, max_rows=MAX_BATCH)
                except Exception as e:
                    # Emit a transient error event but keep streaming
                    err = {"error": f"fetch-failed: {str(e)[:120]}"}
                    yield f"event: error\ndata: {json.dumps(err, default=_json_default, separators=(',', ':'))}\n\n"
                    rows = []

                if rows:
                    for r in rows:
                        # safe in case rows are dicts with datetime fields
                        try:
                            last_id = int(r["id"])
                        except Exception:
                            # if id missing/malformed, skip id line but still deliver data
                            pass

                        out = json.dumps(r, default=_json_default, separators=(",", ":"))
                        if isinstance(r.get("id"), int):
                            yield f"id: {r['id']}\n"
                        yield f"event: alert\n"
                        yield f"data: {out}\n\n"
                    idle_ticks = 0
                else:
                    idle_ticks += 1
                    if idle_ticks * POLL_INTERVAL >= HEARTBEAT_SEC:
                        # SSE comment as heartbeat (ignored by EventSource, keeps pipes warm)
                        yield ": keepalive\n\n"
                        idle_ticks = 0

                time.sleep(POLL_INTERVAL)

        except (GeneratorExit, BrokenPipeError):
            return
        except Exception as e:
            # Last-ditch error before closing stream
            msg = {"error": f"stream-crash: {str(e)[:200]}"}
            try:
                yield f"event: error\ndata: {json.dumps(msg, default=_json_default, separators=(',', ':'))}\n\n"
            except Exception:
                pass
            return

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",  # nginx: disable proxy buffering for SSE
        # Add CORS if needed:
        # "Access-Control-Allow-Origin": "https://your-ui.example.com",
    }
    return Response(stream_with_context(gen()), headers=headers)
































# # api/stream.py
# from flask import Response, stream_with_context, request
# from . import api_bp
# from .. import read_service as rs
# import json, time, sys
# from datetime import datetime, date, timezone
#
# HEARTBEAT_SEC = 15
# POLL_INTERVAL = 1.0  # seconds
# MAX_BATCH     = 100
#
# def _json_default(o):
#     if isinstance(o, datetime):
#         # normalize to UTC ISO-8601
#         if o.tzinfo is None:
#             o = o.replace(tzinfo=timezone.utc)
#         else:
#             o = o.astimezone(timezone.utc)
#         return o.isoformat().replace("+00:00", "Z")
#     if isinstance(o, date):
#         return o.isoformat()
#     # fallback so we never crash the stream
#     return str(o)
#
# @api_bp.get("/stream/alerts")
# def stream_alerts():
#     """
#     Server-Sent Events stream of new alerts.
#     - Supports Last-Event-ID so the client can resume.
#     - Sends a heartbeat every HEARTBEAT_SEC seconds.
#     - Set proxy_buffering off in nginx for this path.
#     """
#     def gen():
#         # Allow resume via Last-Event-ID header or query (?last_id=123)
#         last_id = request.headers.get("Last-Event-ID") or request.args.get("last_id")
#         try:
#             last_id = int(last_id) if last_id is not None else rs.last_alert_id()
#         except Exception:
#             last_id = rs.last_alert_id()
#
#         idle_ticks = 0
#
#         # Hint clients to retry after 10s on disconnect
#         yield "retry: 10000\n\n"
#
#         try:
#             while True:
#                 try:
#                     rows = rs.alerts_after(last_id, max_rows=MAX_BATCH)
#                 except Exception as e:
#                     # Surface a transient error to the client, then keep going
#                     err = {"error": f"fetch-failed: {str(e)[:120]}"}
#                     yield f"event: error\ndata: {json.dumps(err, separators=(',', ':'))}\n\n"
#                     rows = []
#
#                 if rows:
#                     for r in rows:
#                         last_id = int(r["id"])
#                         # Include id so clients can resume with Last-Event-ID
#                         yield f"id: {last_id}\n" \
#                               f"event: alert\n" \
#                               f"data: {json.dumps(r, separators=(',', ':'))}\n\n"
#                     idle_ticks = 0
#                 else:
#                     idle_ticks += 1
#                     if idle_ticks * POLL_INTERVAL >= HEARTBEAT_SEC:
#                         # Comment line = heartbeat (ignored by EventSource, keeps connection warm)
#                         yield ": keepalive\n\n"
#                         idle_ticks = 0
#
#                 time.sleep(POLL_INTERVAL)
#         except GeneratorExit:
#             # Client disconnected — end generator quietly
#             return
#         except BrokenPipeError:
#             return
#         except Exception as e:
#             # Last-ditch: emit an error event before closing
#             msg = {"error": f"stream-crash: {str(e)[:200]}"}
#             try:
#                 yield f"event: error\ndata: {json.dumps(msg, separators=(',', ':'))}\n\n"
#             except Exception:
#                 pass
#             return
#
#     headers = {
#         "Content-Type": "text/event-stream",
#         "Cache-Control": "no-cache, no-transform",
#         "X-Accel-Buffering": "no",  # nginx: disable proxy buffering for SSE
#         # "Access-Control-Allow-Origin": "https://your-ui.example.com",  # if you ever expose cross-origin
#     }
#     return Response(stream_with_context(gen()), headers=headers)




























# from flask import Response, stream_with_context
# from . import api_bp
# from .. import read_service as rs
# import json, time
#
# @api_bp.get("/stream/alerts")
# def stream_alerts():
#     """Server-Sent Events stream of new alerts. Heartbeat keeps proxies alive."""
#     def gen():
#         last_id = rs.last_alert_id()
#         idle = 0
#         while True:
#             rows = rs.alerts_after(last_id, max_rows=100)
#             if rows:
#                 for r in rows:
#                     last_id = r["id"]
#                     yield f"event: alert\n" \
#                           f"data: {json.dumps(r)}\n\n"
#                 idle = 0
#             else:
#                 # heartbeat every ~15s to keep the connection alive through proxies
#                 idle += 1
#                 if idle % 15 == 0:
#                     yield ": keepalive\n\n"
#             time.sleep(1.0)
#
#     headers = {
#         "Content-Type": "text/event-stream",
#         "Cache-Control": "no-cache",
#         "X-Accel-Buffering": "no",   # nginx: disable proxy buffering
#     }
#     return Response(stream_with_context(gen()), headers=headers)