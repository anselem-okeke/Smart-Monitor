import os, sys
import platform
import socket
import subprocess
import time
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from db.db_access import recent_failed_network_events
from scripts.db_logger import log_alert, log_recovery

from scripts.recovery.network.classifiers_packet_loss import is_packet_loss_100
from scripts.recovery.network.remediators_nic_bounce import bounce_suspect_nics
from scripts.recovery.network.remediators_latency import noop_latency_fix
from scripts.recovery.network.classifiers_latency import is_latency_spike
from scripts.recovery.network.classifiers_dns_failure import is_dns_failure
from scripts.recovery.network.remediators_dns_fix import restart_dns_service
from utils.network_file_logger import net_log
from utils.build_msg import build_msg
from scripts.recovery.network.utils import ping_host, can_resolve_dns
from scripts.recovery.network.classifiers_firewall_block import is_firewall_block, should_fix_firewall
from scripts.recovery.network.remediators_firewall_block import fix_firewall_block
hostname = socket.gethostname()

def handle_event(ev):
    _id, tgt, method, result, latency, loss = ev
    print(f"[DEBUG] Raw event: {ev}")

    # -------------------------------
    # Step 1: Classify all conditions
    # -------------------------------
    classifications = {
        "firewall_block": is_firewall_block(ev),
        "dns_failure": is_dns_failure(ev),
        "packet_loss_100": is_packet_loss_100(ev),
        "latency_spike": is_latency_spike(ev),
    }
    print(f"[DEBUG] Classifications: {classifications}")

    # -------------------------------
    # Step 2: Priority = FIREWALL
    # -------------------------------
    if classifications["firewall_block"]:
        print("[DEBUG] Detected firewall block")
        if should_fix_firewall(ev):
            fixed = fix_firewall_block(target_ip=tgt)
            msg = build_msg(ev, action="firewall_reload", result="reloaded" if fixed else "reload_failed")
            sev = "warning" if fixed else "critical"

            log_alert({
                "hostname": hostname,
                "severity": sev,
                "source": f"{method}:{tgt}",
                "message": msg
            })

            log_recovery([{
                "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "hostname": hostname,
                "os_platform": platform.system(),
                "service_name": "firewall",
                "result": "success" if fixed else "fail",
                "error_message": None if fixed else "firewall fix failed"
            }])

            net_log("warning", msg)
            return  # Highest priority

    # -------------------------------
    # Step 3: Priority = DNS failure
    # -------------------------------
    if classifications["dns_failure"]:
        print("[DEBUG] Detected DNS failure")
        fixed = restart_dns_service()
        recovered = can_resolve_dns(tgt) if fixed else False
        status = "dns_fixed" if recovered else "DNS-restart failed"
        severity = "warning" if recovered else "critical"

        msg = build_msg(ev, action="dns_fix", result=status)
        log_alert({
            "hostname": hostname,
            "severity": severity,
            "source": f"nslookup:{tgt}",
            "message": msg
        })

        log_recovery([{
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": hostname,
            "os_platform": platform.system(),
            "service_name": "dns-service",
            "result": status,
            "error_message": None if recovered else "DNS restart failed"
        }])

        net_log("warning", msg)
        return

    # -------------------------------
    # Step 4: Packet Loss = 100%
    # -------------------------------
    if classifications["packet_loss_100"]:
        print("[DEBUG] Detected 100% packet loss")
        fixed = bounce_suspect_nics()
        recovered = ping_host(tgt) if fixed else False
        status = "fixed" if recovered else "still_down"
        error_message = None if recovered else "NIC bounce failed"

        msg = build_msg(ev, action="nic_bounce", result=status)
        log_alert({
            "hostname": hostname,
            "severity": "critical",
            "source": f"ping:{tgt}",
            "message": msg
        })

        log_recovery([{
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            "hostname": hostname,
            "os_platform": platform.system(),
            "service_name": "nic-bounce",
            "result": status,
            "error_message": error_message
        }])

        net_log("warning", msg)
        return

    # -------------------------------
    # Step 5: Latency Spike
    # -------------------------------
    if classifications["latency_spike"]:
        print("[DEBUG] Detected latency spike")
        noop_latency_fix()
        msg = build_msg(ev, action="latency-spike", result="alerted")
        log_alert({
            "hostname": hostname,
            "severity": "critical",
            "source": f"ping:{tgt}",
            "message": msg
        })
        net_log("warning", msg)
        return


if __name__ == '__main__':
    print("[INFO] Network-recovery loop running...")

    try:
        while True:
            failed_events = recent_failed_network_events(hostname)

            if not failed_events:
                print("[INFO] No failed network events at this time.")
            else:
                print(f"[INFO] Found {len(failed_events)} failed event(s)")

            for event in failed_events:
                handle_event(event)
                print(f"[INFO] Network event handling succeeded")

            # Wait before next check
            time.sleep(60)

    except KeyboardInterrupt:
        print("[INFO] Network-recovery stopped by user")
























# def handle_event(ev):
#     _id, tgt, method, result, latency, loss = ev
#
#     """Pair A - 100% packet loss"""
#     if is_packet_loss_100(ev):
#         fixed = bounce_suspect_nics()
#
#         recovered = ping_host(tgt) if fixed else False
#         status = "fixed" if recovered else "still_down"
#
#         print(f"[RECOVERY] Bounce attempt result: {'Success' if fixed else 'Failed'}")
#         print(f"[RECOVERY] Ping after bounce: {'Recovered' if recovered else 'Unreachable'}")
#
#         error_message = None if recovered else "Bounce failed or target still unreachable"
#
#         msg = build_msg(ev, action="nic_bounce", result=status)
#
#         log_alert({
#             "hostname": hostname,
#             "severity": "critical",
#             "source": f"ping:{tgt}",
#             "message":msg
#         })
#
#         log_recovery([{
#             "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
#             "hostname": hostname,
#             "os_platform": platform.system(),
#             "service_name": "nic-bounce",
#             "result": status,
#             "error_message": error_message
#         }])
#
#         net_log(level="warning", msg=msg)
#         return
#
#     """Pair B - latency spike (> 300ms)"""
#     if is_latency_spike(ev):
#         noop_latency_fix()
#         msg = build_msg(ev, action="latency-spike", result="alerted")
#
#         log_alert({
#             "hostname": hostname,
#             "severity": "critical",
#             "source": f"ping:{tgt}",
#             "message": msg
#         })
#         net_log(level="warning", msg=msg)
#         return
#
#     """Pair C - DNS resolution"""
#     if is_dns_failure(ev):
#         fixed = restart_dns_service()
#
#         recovered = can_resolve_dns(tgt) if fixed else False
#         status = "dns_fixed" if recovered else "DNS-restart failed"
#         msg = build_msg(ev, action="dns_fix", result=status)
#         severity = "warning" if recovered else "critical"
#         log_alert({
#             "hostname": hostname,
#             "severity": severity,
#             "source":f"nslookup:{ev[1]}",
#             "message": msg
#         })
#
#         log_recovery([{
#             "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
#             "hostname": hostname,
#             "os_platform": platform.system(),
#             "service_name": "dns-service",
#             "result": status,
#             "error_message": None if recovered else "restart failed"
#         }])
#
#         net_log("warning", msg)
#         return
#
#     """Pair D - Firewall resolution"""
#     if is_firewall_block(ev):
#         if should_fix_firewall(ev):
#             fixed = fix_firewall_block(target_ip=tgt)
#             msg = build_msg(ev, action="firewall_reload",
#                             result="reloaded" if fixed else "reload_failed")
#             sev = "warning" if fixed else "critical"
#
#             log_alert({
#                 "hostname": hostname,
#                 "severity": sev,
#                 "source": f"{ev[2]}:{ev[1]}",
#                 "message": msg
#             })
#
#             log_recovery([{
#                 "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
#                 "hostname": hostname,
#                 "os_platform": platform.system(),
#                 "service_name": "firewall",
#                 "result": "success" if fixed else "fail",
#                 "error_message": None if fixed else "restart failed"
#             }])
#             net_log("warning", msg)
#             return
#
#
# if __name__ == '__main__':
#     print("[INFO] Network-recovery loop running...")
#     try:
#         while True:
#             for event in recent_failed_network_events(hostname):
#                 print(f"[DEBUG] Raw event: {event}")
#                 handle_event(event)
#                 print(f"[INFO] Network event handling succeeded")
#             time.sleep(120)
#     except KeyboardInterrupt:
#         print("[INFO] Network-recovery stopped by user")

