#------------------------------------------
"""Author: Anselem Okeke
    MIT License
    Copyright (c) 2025 Anselem Okeke
    See LICENSE file in the project root for full license text.
"""
#------------------------------------------
import json
import os
import platform
import socket
import subprocess
import sys
import time

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db.db_logger import log_network_event, log_alert

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../config/hosts_config.json"))

def extract_packet_loss(output, system):
    try:
        lines = output.splitlines()
        if system == "Windows":
            for line in lines:
                if "Lost =" in line:
                    if "(" in line and "%" in line:
                        percent = line.split("(")[-1].split("%")[0]
                        return float(percent)
        else:
            for line in lines:
                if "packet loss" in line:
                    # Example: "4 packets transmitted, 3 received, 25% packet loss, time 3002ms"
                    parts = line.split(",")
                    for part in parts:
                        if "packet loss" in part:
                            return float(part.strip().split("%")[0])

    except Exception as e:
        print(f"[ERROR] extract_packet_loss: {e}")
    return None

def extract_latency(output, system):
    try:
        if system == "Windows":
            for line in output.splitlines():
                if "Average =" in line:
                    parts = line.split(",")
                    for part in parts:
                        if part.startswith("Average"):
                            value = float(part.split("=")[-1].strip().replace("ms", ""))
                            return value
        else:
            for line in output.splitlines():
                if "min/avg/max" in line:
                    values = line.split("=")[-1].split("/")
                    if len(values) >= 2:
                        return float(values[1])
    except Exception as e:
        print(f"[ERROR] extract_latency: {e}")
    return None


def check_for_alerts(event, *, loss_warn=10.0, loss_crit=50.0, high_latency_ms=200.0):
    # Only for ping signals
    if event.get("method") != "ping":
        return

    host = event.get("hostname")
    tgt  = event.get("target")
    st   = (event.get("status") or "").lower()
    lat  = event.get("latency_ms")
    loss = event.get("packet_loss_percent")

    alerts = []

    # Down / total failure
    if st in ("error", "fail"):
        msg = f"Ping failed: {tgt} (status={st}, loss={loss})"
        alerts.append({"hostname": host, "severity": "critical",
                       "source": f"ping:{tgt}", "message": msg})

    # Partial loss
    elif st == "degraded" and loss is not None:
        if loss >= loss_crit:
            sev = "critical"
        elif loss >= loss_warn:
            sev = "warning"
        else:
            sev = None
        if sev:
            alerts.append({"hostname": host, "severity": sev,
                           "source": f"ping:{tgt}",
                           "message": f"Packet loss {loss:.1f}% to {tgt}"})

    # High latency (only when otherwise OK)
    if st in ("success", "degraded") and lat is not None and lat > high_latency_ms:
        alerts.append({"hostname": host, "severity": "warning",
                       "source": f"ping:{tgt}",
                       "message": f"High latency {lat:.0f} ms to {tgt}"})

    for a in alerts:
        log_alert(a)
        print(f"[ALERT] {a['severity'].upper()} - {a['message']}")


# def check_for_alerts(event):
#     alerts = []
#
#     # Fallback alert for total failure
#     if event['status'] == "error":
#         alerts.append({
#             "hostname": event["hostname"],
#             "severity": "critical",
#             "source": f"ping:{event['target']}",
#             "message": f"Ping failed entirely: {event['result'][:60]}..."
#         })
#
#     # Latency-based alert
#     if event['latency_ms'] is not None and event['latency_ms'] > 200:
#         alerts.append({
#             "hostname": event["hostname"],
#             "severity": "warning",
#             "source": f"ping:{event['target']}",
#             "message": f"High latency: {event['latency_ms']} ms"
#         })
#
#     # Packet loss alert
#     if event['packet_loss_percent'] is not None and event['packet_loss_percent'] > 10:
#         alerts.append({
#             "hostname": event["hostname"],
#             "severity": "critical",
#             "source": f"ping:{event['target']}",
#             "message": f"Packet loss: {event['packet_loss_percent']}%"
#         })
#
#     for alert in alerts:
#         log_alert(alert)
#         print(f"[ALERT] {alert['severity'].upper()} - {alert['message']}")


# def check_for_alerts(event):
#     alerts = []
#     if event['latency_ms'] is not None and event['latency_ms'] > 200:
#         alerts.append({
#             "hostname": event['hostname'],
#             "severity": "warning",
#             "source": f"ping:{event['target']}",
#             "message": f"High latency: {event['latency_ms']} ms"
#         })
#     if event['packet_loss_percent'] is not None and event['packet_loss_percent'] > 10:
#         alerts.append({
#             "hostname": event['hostname'],
#             "severity": "critical",
#             "source": f"ping:{event['target']}",
#             "message": f"Packet loss: {event['packet_loss_percent']}%"
#         })
#     for alert in alerts:
#         log_alert(alert)
#         print(f"[Alert] {alert['severity'].upper()} - {alert['message']}")

def run_traceroute(target):
    # system = platform.system()
    # traceroute_cmd = "tracert" if system == "Windows" else "traceroute"
    system = platform.system().lower()
    traceroute_cmd = "tracert" if "windows" in system else "traceroute"

    try:
        result = subprocess.run(
            [traceroute_cmd, target],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )

        status = "success" if result.returncode == 0 else "fail"
        return {
            "hostname": socket.gethostname(),
            "target": target,
            "method": "traceroute",
            "result": result.stdout,
            "latency_ms": extract_latency(result.stdout, system),
            "packet_loss_percent": extract_packet_loss(result.stdout, system),
            "status": status
        }
    except Exception as e:
        return {
            "hostname": socket.gethostname(),
            "target": target,
            "method": "traceroute",
            "result": str(e),
            "latency_ms": None,
            "packet_loss_percent": None,
            "status": "error"
        }


def ping_host(target):
    system = platform.system()
    count_flag = "-n" if system == "Windows" else "-c"
    try:
        result = subprocess.run(
            ["ping", count_flag, "4", target],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        # parse first
        latency = extract_latency(result.stdout, system)
        loss    = extract_packet_loss(result.stdout, system)

        # derive state from both rc and loss
        rc = result.returncode
        if loss is not None:
            if loss >= 100.0:
                status = "fail"        # total loss
            elif loss > 0.0:
                status = "degraded"    # partial loss, still got replies
            else:
                status = "success" if rc == 0 else "fail"
        else:
            # no loss parsed -> fall back to rc
            status = "success" if rc == 0 else "fail"

        return {
            "hostname": socket.gethostname(),
            "target": target,
            "method": "ping",
            "result": result.stdout,
            "latency_ms": latency,
            "packet_loss_percent": loss,
            "status": status
        }
    except Exception as e:
        return {
            "hostname": socket.gethostname(),
            "target": target,
            "method": "ping",
            "result": str(e),
            "latency_ms": None,
            "packet_loss_percent": None,
            "status": "error"
        }

# def ping_host(target):
#     system = platform.system()
#     count_flag = "-n" if system == "Windows" else "-c"
#     try:
#         result = subprocess.run(
#             ["ping", count_flag, "4", target],
#             stdout=subprocess.PIPE,
#             stderr=subprocess.PIPE,
#             text=True,
#             timeout=10
#         )
#         status = "success" if result.returncode == 0 else "fail"
#         latency = extract_latency(result.stdout, system)
#         packet_loss = extract_packet_loss(result.stdout, system)
#         return {
#             "hostname": socket.gethostname(),
#             "target": target,
#             "method": "ping",
#             "result": result.stdout,
#             "latency_ms": latency,
#             "packet_loss_percent": packet_loss,
#             "status": status
#         }
#     except Exception as e:
#         return {
#             "hostname": socket.gethostname(),
#             "target": target,
#             "method": "ping",
#             "result": str(e),
#             "latency_ms": None,
#             "packet_loss_percent": None,
#             "status": "error"
#         }

def run_nslook(target):
    system = platform.system()
    try:
        result = subprocess.run(
            ["nslookup", target],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        output = result.stdout.strip().lower()
        status = "success"
        message = ""

        if result.returncode != 0 or "can't find" in output or "non-existent domain" in output:
            #try Fall back local resolution
            try:
                socket.gethostbyname(target)
                status = "local"
                message = "Resolved locally (not in public DNS)"
            except socket.error:
                status = "fail"
                message = "Unresolved (NXDOMAIN in DNS and local)"
        return {
            "hostname": socket.gethostname(),
            "target": target,
            "method": "nslookup",
            "result": result.stdout.strip() + f"\n\n[INFO] {message}" if message else result.stdout,
            "latency_ms": extract_latency(result.stdout, system),
            "packet_loss_percent": extract_packet_loss(result.stdout, system),
            "status": status
        }
    except Exception as e:
        return {
            "hostname": socket.gethostname(),
            "target": target,
            "method": "nslookup",
            "result": str(e),
            "latency_ms": None,
            "packet_loss_percent": None,
            "status": "error"
        }


#NEW ADDING timeout in other not stuck handlers
# def run_network_checks():
#     from concurrent.futures import ThreadPoolExecutor, as_completed
#     with open(CONFIG_PATH, "r", encoding="utf-8") as f:
#         targets = json.load(f)
#
#     def dispatch(entry):
#         m, t = entry["method"], entry["target"]
#         if m == "ping":
#             return ping_host(t)
#         if m == "traceroute":
#             return run_traceroute(t)
#         if m == "nslookup":
#             return run_nslook(t)
#         return {"method": m, "target": t, "status": "error", "result": "unsupported"}
#
#     # Limit concurrency so we don’t overwhelm the host/DNS
#     results = []
#     with ThreadPoolExecutor(max_workers=4) as ex:
#         futs = [ex.submit(dispatch, e) for e in targets]
#         for fut in as_completed(futs):
#             data = fut.result()
#             log_network_event(data)
#             if data["method"] == "ping":
#                 check_for_alerts(data)
#             elif data["method"] == "nslookup" and data["status"] in ("fail", "error"):
#                 log_alert({
#                     "hostname": data['hostname'],
#                     "severity": "warning",
#                     "source": f"nslookup:{data['target']}",
#                     "message": f"DNS failure: {data['result'][:60]}..."
#                 })
#             print(f"[INFO] Logged {data['method']} to {data['target']}: {data['status']}")
#             results.append(data)
#     return results



def run_network_checks():
    with open(CONFIG_PATH, "r") as f:
        targets = json.load(f)

    for entry in targets:
        method = entry['method']
        target = entry['target']

        if method == "ping":
            data = ping_host(target)
        elif method == "traceroute":
            data = run_traceroute(target)
        elif method == "nslookup":
            data = run_nslook(target)
        else:
            print(f"[WARN] Unsupported method: {method}")
            continue

        log_network_event(data)
        if method == "ping":
            check_for_alerts(data)
        elif method == "nslookup" and data['status'] in ['fail', 'error']:
            log_alert({
                "hostname": data['hostname'],
                "severity": "warning",
                "source": f"nslookup:{data['target']}",
                "message": f"DNS failure: {data['result'][:60]}..."
            })
        elif method == "traceroute" and data['status'] in ['fail', 'error']:
            log_alert({
                "hostname": data['hostname'],
                "severity": "warning",  # traceroute is often noisy; keep warning
                "source": f"traceroute:{data['target']}",
                "message": f"Traceroute {data['status']} to {data['target']}: {str(data['result'])[:120]}..."
            })
        print(f"[INFO] Logged {method} to {target}: {data['status']}")

def handle_network_tools():
    """
        Handler for network tools..
    :return:
    """
    run_network_checks()

if __name__ == "__main__":
    try:
        while True:
            print("[INFO] Starting network monitoring...")
            handle_network_tools()
            time.sleep(60)  # run every 60 seconds
    except KeyboardInterrupt:
        pass