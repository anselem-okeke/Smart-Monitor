import os
import platform
import subprocess
import sys
from scripts.recovery.network.decide_if_should_safe_bounce_nic_linux import safe_bounce_all_linux
from scripts.recovery.network.decide_if_should_safe_bounce_nic_window import safe_bounce_all_window

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# --- Linux helper --------------------------------------------------
def linux_bouce():
    return safe_bounce_all_linux()


    # try:
    #     iface = subprocess.check_output(
    #         ["bash", "-c",
    #          "ip -o link show | awk '$9==\"UP\"{print $2}' | sed 's/://' | head -n1"],
    #         text=True).strip()
    #
    #     if not iface:
    #         return False
    #
    #     subprocess.check_call(["sudo", "ip", "link", "set", iface, "down"])
    #     subprocess.check_call(["sudo", "ip", "link", "set", iface, "up"])
    #     return True
    # except subprocess.CalledProcessError:
    #     return False

# --- Windows helper ------------------------------------------------
def windows_bounce():
    return safe_bounce_all_window()

    # try:
    #     # Get list of "Up" adapters safely without indexing into empty result
    #     iface_list = subprocess.check_output(
    #         ["powershell", "-Command",
    #          "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -First 1 -ExpandProperty Name"],
    #         text=True, stderr=subprocess.STDOUT
    #     ).strip()
    #
    #     if not iface_list:
    #         print("[WARN] No active network interface found")
    #         return False
    #
    #     iface = iface_list
    #
    #     # Disable
    #     disable_cmd = [
    #         "powershell", "-Command",
    #         f"Disable-NetAdapter -Name '{iface}' -Confirm:$false -ErrorAction Stop"
    #     ]
    #     subprocess.check_output(disable_cmd, text=True, stderr=subprocess.STDOUT)
    #
    #     # Enable
    #     enable_cmd = [
    #         "powershell", "-Command",
    #         f"Enable-NetAdapter -Name '{iface}' -Confirm:$false -ErrorAction Stop"
    #     ]
    #     subprocess.check_output(enable_cmd, text=True, stderr=subprocess.STDOUT)
    #
    #     return True
    #
    # except subprocess.CalledProcessError as e:
    #     output = e.output if hasattr(e, 'output') else str(e)
    #
    #     if "Access is denied" in output:
    #         print("[ERROR] Admin privileges required.")
    #     elif "Cannot open" in output or "The exception" in output:
    #         print("[ERROR] Cannot disable this adapter: Protected/virtual device.")
    #     else:
    #         print(f"[ERROR] Unexpected error in windows_bounce: {output}")
    #     return False












# def windows_bounce():
#     try:
#         iface = subprocess.check_output(
#             ["powershell", "-Command",
#              "(Get-NetAdapter | Where-Object {$_.Status -eq 'Up'})[0].Name"],
#             text=True, stderr=subprocess.STDOUT
#         ).strip()
#
#         if not iface:
#             print("[WARN] No active network interface found")
#             return False
#
#         # Disable
#         disable_cmd = [
#             "powershell", "-Command",
#             f"Disable-NetAdapter -Name '{iface}' -Confirm:$false -ErrorAction Stop"
#         ]
#         subprocess.check_output(disable_cmd, text=True, stderr=subprocess.STDOUT)
#
#         # Enable
#         enable_cmd = [
#             "powershell", "-Command",
#             f"Enable-NetAdapter -Name '{iface}' -Confirm:$false -ErrorAction Stop"
#         ]
#         subprocess.check_output(enable_cmd, text=True, stderr=subprocess.STDOUT)
#
#         return True
#
#     except subprocess.CalledProcessError as e:
#         output = e.output if hasattr(e, 'output') else str(e)
#         if "Access is denied" in output:
#             print("[ERROR] Admin privileges required to disable/enable network adapter.")
#         else:
#             print(f"[ERROR] Unexpected error in windows_bounce: {output}")
#         return False


def bounce_suspect_nics():
    if platform.system() == "Windows":
        return windows_bounce()
    elif platform.system() == "Linux":
        return linux_bouce()
    else:
        return False