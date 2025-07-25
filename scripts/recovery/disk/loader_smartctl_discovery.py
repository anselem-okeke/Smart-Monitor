import json
import pathlib
import platform

import subprocess

def load_disk_config():
    # Load config (include/exclude)
    config_path = pathlib.Path(__file__).resolve().parents[3] / "config/smartctl_disk.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to load config: {e}")
        return {"include": [], "exclude": []}


def _linux_candidate_disks():
    """
    Discover all usable disk-like devices using lsblk.
    Return list of dicts with 'device', 'type', and 'size'.
    """
    cfg = load_disk_config()
    exclude_set = set(cfg.get("exclude", []))
    include_set = set(cfg.get("include", []))

    disks = []

    try:
        # lsblk to list all block devices with name, type, size
        output = subprocess.check_output(
            ["lsblk", "-ndo", "NAME,TYPE,SIZE"], text=True
        )

        for line in output.splitlines():
            if not line.strip():
                continue

            parts = line.strip().split()
            if len(parts) != 3:
                continue

            name, dev_type, size = parts
            dev_path = f"/dev/{name}"

            # Only consider meaningful types
            if dev_type in {"disk", "raid0", "raid1", "lvm", "crypt"}:
                if dev_path not in exclude_set:
                    disks.append({
                        "device": dev_path,
                        "type": dev_type,
                        "size": size
                    })

        # Add manually included devices (even if they weren't in lsblk)
        for manual in include_set:
            if manual not in [d["device"] for d in disks]:
                disks.append({
                    "device": manual,
                    "type": "manual",
                    "size": "unknown"
                })

    except Exception as e:
        print(f"[ERROR] Disk discovery failed: {e}")

    return disks

def _windows_candidate_disks():
    cfg = load_disk_config()
    exclude_set = set(cfg.get("exclude", []))
    include_set = set(cfg.get("include", []))
    discovered = []

    try:
        output = subprocess.check_output(["smartctl", "--scan-open"], text=True)
        for line in output.splitlines():
            if line.strip().startswith("#"):
                continue  # skip commented lines

            parts = line.strip().split()
            if len(parts) >= 3 and parts[1] == "-d":
                dev_path = parts[0]
                driver_type = parts[2]
                if dev_path not in exclude_set:
                    discovered.append({
                        "device": dev_path,
                        "type": driver_type,
                        "size": "unknown"
                    })

        for manual in include_set:
            if manual not in [d["device"] for d in discovered]:
                discovered.append({
                    "device": manual,
                    "type": "manual",
                    "size": "unknown"
                })

    except Exception as e:
        print(f"[ERROR] Windows disk discovery failed: {e}")

    return discovered

def failing_disks():
    """
    check SMART health of all discovered disks.
    :return: a list of devices where SMART health check failed
    """
    system = platform.system()
    bad_disks = []

    #here we chose platform specific candidates
    if system == "Linux":
        candidates = _linux_candidate_disks()
    elif system == "Windows":
        candidates = _windows_candidate_disks()
    else:
        print(f"[ERROR] Unsupported platform: {system}")
        return bad_disks

    for disk in candidates:
        print(f"[INFO] {disk['device']}  |  type: {disk['type']}  |  size: {disk['size']}")
        device = disk["device"]
        driver = disk.get("type", "")

        # Building smartctl args
        # Always user permissive mode for resilience
        driver_args = ["-d", driver] if system == "Windows" else []
        smart_args =  ["smartctl", "-H", *driver_args, "-T", "permissive", device]

        try:
            res = subprocess.run(smart_args, capture_output=True, text=True)
            output = res.stdout + res.stderr

            if "SMART support is: Unavailable" in output:
                print(f"[INFO] Skipping {device}: No SMART support.")
                continue

            if "SMART Disabled" in output:
                print(f"[INFO] SMART is disabled on {device}. Attempting to enable...")
                enable_args = ["smartctl", "-s", "on", *driver_args, device]
                enable_res = subprocess.run(enable_args, capture_output=True, text=True)

                if enable_res.returncode != 0:
                    print(f"[WARN] Failed to enable SMART on {device}. Skipping.")
                    continue

                # Retry the health check
                res = subprocess.run(smart_args, capture_output=True, text=True)
                output = res.stdout + res.stderr

            if "SMART Enable failed" in output or "Input/output error" in output:
                print(f"[WARN] Skipping {device}: Cannot enable or access SMART.")
                continue

            if res.returncode & 0x01:
                print(f"[ALERT] {device} reports SMART health FAILED.")
                bad_disks.append(device)
            else:
                print(f"[OK] {device} passed SMART health check.")

        except Exception as e:
            print(f"[ERROR] SMART check failed on {device}: {e}")

    return bad_disks
    # #Simulating bad disk
    # return ["/dev/sdfake0", "/dev/sdfake1"]


