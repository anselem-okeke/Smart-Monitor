import subprocess

def is_virtual_or_loopback(iface_name):
    virtual_keywords = ['loopback', 'virtual', 'vEthernet', 'TAP', 'VPN', 'WAN Miniport']
    return any(keyword.lower() in iface_name.lower() for keyword in virtual_keywords)

def get_primary_windows_interface():
    try:
        route = subprocess.check_output(
            ["powershell", "-Command", "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1).InterfaceAlias"],
            text=True
        ).strip()
        return route
    except Exception as e:
        print(f"[ERROR] Could not determine primary interface: {e}")
        return None

def safe_bounce_all_window():
    try:
        # Get all UP interfaces
        iface_list = subprocess.check_output(
            ["powershell", "-Command",
             "Get-NetAdapter | Where-Object {$_.Status -eq 'Up'} | Select-Object -ExpandProperty Name"],
            text=True).strip().splitlines()

        if not iface_list:
            print("[WARN] No active network interfaces found.")
            return False

        primary_iface = get_primary_windows_interface()
        bounced_any = False

        for iface in iface_list:
            iface = iface.strip()
            if iface == primary_iface:
                print(f"[SKIP] {iface} is the primary interface.")
                continue
            if is_virtual_or_loopback(iface):
                print(f"[SKIP] {iface} is virtual or loopback.")
                continue

            print(f"[INFO] Attempting to bounce {iface}")
            try:
                subprocess.check_output(
                    ["powershell", "-Command",
                     f"Disable-NetAdapter -Name '{iface}' -Confirm:$false -ErrorAction Stop"],
                    text=True
                )
                subprocess.check_output(
                    ["powershell", "-Command",
                     f"Enable-NetAdapter -Name '{iface}' -Confirm:$false -ErrorAction Stop"],
                    text=True
                )
                print(f"[SUCCESS] Bounced interface {iface}")
                bounced_any = True
            except subprocess.CalledProcessError as e:
                output = e.output if hasattr(e, 'output') else str(e)
                print(f"[ERROR] Failed to bounce {iface}: {output}")

        return bounced_any

    except Exception as e:
        print(f"[ERROR] General failure in bounce logic: {e}")
        return False
