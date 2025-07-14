import platform
import subprocess

def ping_host(target, count=2, timeout=2):
    """
    Ping target IP or hostname to verify connectivity
    returns True if ping succeeds, False if unreachable
    :param target: hostname
    :param count: ping counts
    :param timeout: expected time
    :return: bool
    """
    if platform.system() == "Windows":
        cmd = ["ping", "-n", str(count), "-w", str(timeout * 1000), target]
    else:
        cmd = ["ping", "-c", str(count), "-W", str(timeout), target]

    try:
        subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def can_resolve_dns(test_domain="google.com"):
    try:
        test_output = subprocess.check_output(
            ["nslookup", test_domain],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5
        )
        lower = test_output.lower()
        return not any(bad in lower for bad in [
            "non-existent domain",
            "can't find",
            "unknown",
            "server failed",
            "no response from server",
            "timed out"
        ])
    except Exception as e:
        print(f"[ERROR] Post-DNS-restart check failed: {e}")
        return False