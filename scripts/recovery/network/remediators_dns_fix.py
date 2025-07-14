import platform
import subprocess

def restart_windows_dns_service():
    try:
        """First check: if Dnscache is running"""
        status = subprocess.check_output(
            ["powershell", "-Command", "(Get-Service -Name 'Dnscache').Status"],
            text=True
        ).strip()

        if status.lower() != "running":
            print("[WARN] Dnscache is not running.")
            return False

        """Now attempt restart (may faill"""
        # Now attempt restart (may fail)
        subprocess.check_output(
            ["powershell", "-Command", "Restart-Service -Name 'Dnscache' -ErrorAction Stop"],
            text=True, stderr=subprocess.STDOUT
        )
        print("[INFO] Dnscache restarted successfully.")
        return True

    except subprocess.CalledProcessError as e:
        output = e.output if hasattr(e, 'output') else str(e)
        if "Cannot open Dnscache service" in output:
            print("[WARN] Dnscache cannot be restarted on this system (restricted service).")
        else:
            print(f"[ERROR] Failed to restart Dnscache: {output}")
        return False

def restart_linux_dns_service():
    CANDIDATES = ["NetworkManager", "systemd-resolved"]

    for unit in CANDIDATES:
        try:
            # Check if the service is active/loaded
            status_check = subprocess.run(
                ["systemctl", "status", f"{unit}.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            if status_check.returncode != 0:
                continue  # Skip this candidate

            # Try to restart it
            subprocess.check_output(
                ["sudo", "systemctl", "restart", f"{unit}.service"],
                text=True,
                stderr=subprocess.STDOUT
            )

            print(f"[INFO] Restarted DNS service: {unit}")
            return True

        except subprocess.CalledProcessError as e:
            output = e.output if hasattr(e, 'output') else str(e)
            print(f"[ERROR] Failed to restart {unit}: {output}")

    print("[WARN] No suitable DNS service could be restarted.")
    return False


def restart_dns_service():
    """
    Try to restart the local DNS-caching service
        windows -> Dnscache
        linux -> prefer NetworkManager, fall back to systemd-resolved
    :return: True if restart succeeded
    """

    if platform.system() == "Windows":
        return restart_windows_dns_service()
    elif platform.system() == "Linux":
        return restart_linux_dns_service()
    else:
        return False