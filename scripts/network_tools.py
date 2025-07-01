#------------------------------------------
"""Author: Anselem Okeke"""
#------------------------------------------
import json
import os
import platform
import socket
import subprocess
import time

from db_logger import log_network_event, log_alert

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config/hosts_config.json"))

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

def check_for_alerts(event):
    alerts = []

    # Fallback alert for total failure
    if event['status'] == "error":
        alerts.append({
            "hostname": event["hostname"],
            "severity": "critical",
            "source": f"ping:{event['target']}",
            "message": f"Ping failed entirely: {event['result'][:60]}..."
        })

    # Latency-based alert
    if event['latency_ms'] is not None and event['latency_ms'] > 200:
        alerts.append({
            "hostname": event["hostname"],
            "severity": "warning",
            "source": f"ping:{event['target']}",
            "message": f"High latency: {event['latency_ms']} ms"
        })

    # Packet loss alert
    if event['packet_loss_percent'] is not None and event['packet_loss_percent'] > 10:
        alerts.append({
            "hostname": event["hostname"],
            "severity": "critical",
            "source": f"ping:{event['target']}",
            "message": f"Packet loss: {event['packet_loss_percent']}%"
        })

    for alert in alerts:
        log_alert(alert)
        print(f"[ALERT] {alert['severity'].upper()} - {alert['message']}")


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
        status = "success" if result.returncode == 0 else "fail"
        latency = extract_latency(result.stdout, system)
        packet_loss = extract_packet_loss(result.stdout, system)
        return {
            "hostname": socket.gethostname(),
            "target": target,
            "method": "ping",
            "result": result.stdout,
            "latency_ms": latency,
            "packet_loss_percent": packet_loss,
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
        print(f"[INFO] Logged {method} to {target}: {data['status']}")

if __name__ == "__main__":
    try:
        while True:
            print("[INFO] Starting network monitoring...")
            run_network_checks()
            time.sleep(60)  # run every 60 seconds
    except KeyboardInterrupt:
        pass