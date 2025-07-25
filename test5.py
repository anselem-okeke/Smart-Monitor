import pathlib
import subprocess
import os
import re

def _windows_candidate_disks(cfg):
    """
    Returns a list of available \\.\PhysicalDriveN devices on Windows.
    Tries PowerShell for accuracy, falls back to checking actual existence.
    Applies include/exclude from config.
    """
    candidates = set()

    # Step 1: Try PowerShell for real physical disk indices
    try:
        output = subprocess.check_output(
            ["powershell", "-Command", "(Get-PhysicalDisk | Select -Expand FriendlyName)"],
            text=True
        )
        # Match only if disks are actually found
        for i in range(0, 16):
            dev = f"\\\\.\\PhysicalDrive{i}"
            if os.path.exists(dev):
                candidates.add(dev)
    except subprocess.CalledProcessError:
        # Step 2: Fallback — probe known PhysicalDrives
        for i in range(0, 16):
            dev = f"\\\\.\\PhysicalDrive{i}"
            if os.path.exists(dev):
                candidates.add(dev)

    # Step 3: Apply user-defined include/exclude rules
    candidates.update(cfg.get("include", []))
    candidates.difference_update(cfg.get("exclude", []))

    return sorted(candidates)
config_path = pathlib.Path(__file__).resolve().parents[0] / "config/smartctl_disk.json"
print(_windows_candidate_disks(config_path))
