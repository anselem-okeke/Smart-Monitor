import ipaddress
import platform
import re
import socket
import subprocess
OS = platform.system()


def is_firewall_block(event):
    SUSPECT_WORDS = (
        "connection refused",
        "blocked by firewall",
        "administratively prohibited",
        "destination host prohibited",
        "destination net unreachable",
        "no route to host",
        "request timed out",
        "timed out after",
        "filtered"
    )

    _id, tgt, method, result_txt, latency, _ = event
    if not result_txt:
        return False

    result = result_txt.lower()
    for word in SUSPECT_WORDS:
        if word in result:
            print(f"[MATCH] Firewall suspect keyword matched: {word}")
            return True

    # result = result_txt.lower()
    # print(f"[DEBUG] Evaluating result: {result}")
    # match = any(word in result for word in SUSPECT_WORDS)
    # print(f"[DEBUG] is_firewall_block = {match}")
    # return match

"""Detect DNS issues"""
def has_dns_issue(target="google.com"):
    try:
        socket.gethostbyname(target)
        return False
    except socket.gaierror:
        return True

def no_default_route():
    try:
        result = subprocess.check_output(
            "ip rout show default",
            shell=True, text=True
        )
        return not result.strip()
    except Exception as e:
        return True, str(e)

def fails_ping_check(target, count=2, timeout=2) -> bool:
    """
       Works on both Linux and Windows.
    :param target:
    :param count:
    :param timeout:
    :return: Returns True if ping to target fails.
    """
    if OS == "Windows":
        cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), target]
    else:
        cmd = ["ping", "-c", str(count), "-W", str(timeout), target]

    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode != 0  # True if ping fails
    except Exception as e:
        print(f"[ERROR] Ping failed: {e}")
        return True  # Treat as failure if an exception occurs


def should_fix_firewall_linux(event):
    _id, tgt, method, result_txt, latency, _ = event

    if not is_firewall_block(event):
        return False

    if not fails_ping_check(tgt):
        print("[SKIP] Target is reachable - not firewall fix needed")
        return False

    if has_dns_issue():
        print("[SKIP] Target failed DNS resolution - not a firewall issue")
        return False

    if no_default_route():
        print("[SKIP] Nod default route, likely routing issue not firewall")
        return False

    return True


def should_fix_firewall_window(target_ip: str) -> bool:
    """
    Checks if any enabled Windows Firewall rule blocks the given IP,
    including CIDR ranges (e.g., 192.168.56.0/24).
    """
    if OS != "Windows":
        return False

    try:
        output = subprocess.check_output(
            ["netsh", "advfirewall", "firewall", "show", "rule", "name=all"],
            text=True,
            stderr=subprocess.DEVNULL
        ).lower()

        # rules = output.split("rule name:")
        rules = re.split(r"(?i)^rule name:\s*", output, flags=re.MULTILINE)

        for raw_rule in rules:
            rule_lines = raw_rule.strip().splitlines()
            rule_dict = {}

            for line in rule_lines:
                if ":" in line:
                    key, val = line.split(":", 1)
                    rule_dict[key.strip()] = val.strip()

            if (
                    rule_dict.get("enabled") == "yes" and
                    rule_dict.get("action") == "block"
            ):
                remoteip = rule_dict.get("remoteip", "any")
                try:
                    if remoteip == "any":
                        continue
                    for cidr in remoteip.split(","):
                        if ipaddress.ip_address(target_ip) in ipaddress.ip_network(cidr.strip(), strict=False):
                            print(f"[MATCH] Block rule found for {target_ip} in {cidr}")
                            return True
                except ValueError:
                    continue

        return False

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Failed to check firewall rules: {e}")
        return False

def should_fix_firewall(event):
    _id, tgt, method, result_txt, latency, _ = event

    print(f"[DEBUG] Checking Windows firewall rules for {tgt}")

    if OS == "Linux":
        return should_fix_firewall_linux(event)
    elif OS == "Windows":
        print(f"[DEBUG] Called: should_fix_firewall_window{tgt} ")
        return should_fix_firewall_window(tgt)
    else:
        print("[INFO] NO matching platform found...")
        return False
