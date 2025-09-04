import subprocess
import time

import psutil

bounced_tracker = {}

def iface_is_up(iface):
    stats = psutil.net_if_stats().get(iface)
    return stats.isup if stats else False

def iface_has_ip(iface):
    addrs = psutil.net_if_addrs().get(iface, [])
    return any(addr.family.name == 'AF_INET' and addr.address for addr in addrs)


def is_primary_interface(iface):
    try:
        route = subprocess.check_output("ip route get 1.1.1.1", shell=True, text=True)
        return f"dev {iface}" in route
    except Exception as e:
        print(f"[ERROR] Checking primary interface: {e}")
        return False

def has_default_route(iface):
    try:
        result = subprocess.check_output("ip route show default", shell=True, text=True)
        return iface in result
    except Exception as e:
        print(f"[ERROR] Checking default route: {e}")
        return False

def has_recent_rx_tx(iface, threshold_bytes=1024):
    stats1 = psutil.net_io_counters(pernic=True).get(iface)
    time.sleep(1)
    stats2 = psutil.net_io_counters(pernic=True).get(iface)

    if not stats1 or not stats2:
        return False

    delta_rx = stats2.bytes_recv - stats1.bytes_recv
    delta_tx = stats2.bytes_sent - stats1.bytes_sent
    return (delta_rx + delta_tx) > threshold_bytes

def recently_bounced(iface, cooldown=300):
    now = time.time()
    return (now - bounced_tracker.get(iface, 0)) < cooldown

def mark_bounced(iface):
    bounced_tracker[iface] = time.time()

def fails_ping_check(iface, target="8.8.8.8"):
    try:
        result = subprocess.run(
            ["ping", "-I", iface, "-c", "2", "-W", "2", target]
        )
        return result.returncode !=0

    except Exception as e:
        print(f"[ERROR] Could not connect to {iface}: {e}")
        return True

def should_bounce_interface(iface):
    return (
        iface_is_up(iface) and
        iface_has_ip(iface) and
        not is_primary_interface(iface) and
        not has_default_route(iface) and
        not has_recent_rx_tx(iface) and
        not recently_bounced(iface) and
        fails_ping_check(iface)
    )

#NEW ALLOWING leastpriviledge user=smartmonitor
# def bounce_interface_linux(iface: str):
#     """
#     Safely bounce a network interface via the smartmon-netctl wrapper.
#     Requires sudoers: smartmonitor NOPASSWD: /usr/local/bin/smartmon-netctl
#     """
#     try:
#         res = subprocess.run(
#             ["sudo", "-n", "/usr/local/bin/smartmon-netctl", iface, "bounce"],
#             capture_output=True, text=True, timeout=10
#         )
#         if res.returncode == 0:
#             return True, (res.stdout.strip() or f"{iface} bounced")
#         return False, (res.stderr.strip() or res.stdout.strip() or "netctl failed")
#     except subprocess.TimeoutExpired:
#         return False, f"timeout bouncing {iface}"
#     except Exception as e:
#         return False, str(e)


def bounce_interface_linux(iface):
    try:
        subprocess.run(["sudo", "ip", "link", "set", iface, "down"], check=True)
        time.sleep(1)
        subprocess.run(["sudo", "ip", "link", "set", iface, "up"], check=True)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to bounce {iface}: {e}")
        return False

def safe_bounce_all_linux():
    up_ifaces = [
        iface for iface, stats in psutil.net_if_stats().items()
        if stats.isup and iface != "lo"
    ]

    print(f"[INFO] Checking {len(up_ifaces)} UP interfaces: {up_ifaces}")
    for iface in up_ifaces:
        print(f"\n[CHECK] {iface}:")

        if should_bounce_interface(iface):
            print(f"[ACTION] Bouncing {iface} (meets all criteria)")
            success = bounce_interface_linux(iface)
            if success:
                mark_bounced(iface)
        else:
            print(f"[SKIP] {iface} does not meet bounce criteria")
