import ipaddress
import re
import subprocess
import platform
import pathlib
import shutil

def _linux_reload_firewall() -> bool:
    """
    Reloads Linux firewall using best available method:
    - firewalld: firewall-cmd --reload
    - ufw: ufw reload
    - iptables: iptables-restore from saved rules.v4
    """
    try:
        # firewalld
        if shutil.which("firewall-cmd") and \
           subprocess.call(["systemctl", "is-active", "firewalld"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) == 0:
            print("[INFO] firewalld is active — attempting reload...")
            return subprocess.call(["sudo", "firewall-cmd", "--reload"]) == 0

        # ufw
        if shutil.which("ufw"):
            print("[INFO] ufw found — attempting reload...")
            return subprocess.call(["sudo", "ufw", "reload"]) == 0

        # iptables
        iptables_restore = shutil.which("iptables-restore")
        rules_path = pathlib.Path("/etc/iptables/rules.v4")
        if iptables_restore and rules_path.exists():
            print(f"[INFO] iptables-restore found — restoring from {rules_path}")
            return subprocess.call(["sudo", iptables_restore, str(rules_path)]) == 0

        print("[WARN] No suitable firewall method found (firewalld, ufw, iptables)")
        return False

    except Exception as e:
        print(f"[ERROR] Exception during Linux firewall reload: {e}")
        return False



def _windows_reset_firewall(target_ip: str = None) -> bool:
    """
    Dynamically finds and deletes only block rules related to the given target IP.
    If no target_ip is provided, performs a full firewall reset.
    add_rule: netsh advfirewall firewall add rule name="TestBlock" dir=out action=block remoteip=192.168.56.14
    show_rule: netsh advfirewall firewall show rule name=all
    """
    if platform.system() != "Windows":
        print("[SKIP] Not a Windows system")
        return False

    try:
        netsh = shutil.which("netsh")
        if not netsh:
            print("[ERROR] 'netsh' command not found")
            return False

        if target_ip:
            print(f"[INFO] Searching for firewall block rules targeting {target_ip}...")
            output = subprocess.check_output(
                [netsh, "advfirewall", "firewall", "show", "rule", "name=all"],
                text=True, stderr=subprocess.DEVNULL
            ).lower()

            rules = re.split(r"(?i)^rule name:\s*", output, flags=re.MULTILINE)
            deleted_any = False

            for i, raw_rule in enumerate(rules[1:], 1):  # skip first empty split
                rule_lines = raw_rule.strip().splitlines()
                rule_dict = {}

                for line in rule_lines:
                    if ":" in line:
                        key, val = line.split(":", 1)
                        rule_dict[key.strip().lower()] = val.strip()

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
                                rule_name = rule_lines[0].strip()  # First line is actual rule name
                                print(f"[MATCH] Block rule found: {rule_name} for {target_ip}")
                                subprocess.call([
                                    netsh, "advfirewall", "firewall", "delete", "rule", f"name={rule_name}"
                                ])
                                deleted_any = True
                    except ValueError:
                        continue

            if not deleted_any:
                print(f"[INFO] No matching rule found for {target_ip}")
            return deleted_any

        else:
            print("[INFO] No target IP provided — resetting entire firewall")
            return subprocess.call([netsh, "advfirewall", "reset"]) == 0

    except Exception as e:
        print(f"[ERROR] Failed to reset or clean up Windows firewall: {e}")
        return False


def fix_firewall_block(target_ip: str = None) -> bool:
    """
    Entry point for firewall recovery — OS-aware
    """
    system = platform.system()
    print(f"[INFO] fix_firewall_block triggered on platform: {system}")

    if system == "Linux":
        return _linux_reload_firewall()
    elif system == "Windows":
        return _windows_reset_firewall(target_ip)
    else:
        print(f"[WARN] Unsupported platform: {system}")
        return False
