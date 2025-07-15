# Detect if the root filesystem is currently mounted read-only.
# Single responsibility → no DB, no side-effects.
import os
import sys


def is_root_readonly() -> bool:
    """
    Returns True when '/' appears with 'ro' in /proc/self/mounts.
    Works on all modern Linux distros.  Windows returns False.
    """
    try:
        with open("/proc/self/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 4 and parts[1] == "/":
                    opts = parts[3].split(",")
                    return "ro" in opts
    except FileNotFoundError:
        pass  # non-Linux (Windows) → fall through
    return False

with open("/proc/self/mounts") as f:
    for line in f:
        parts = line.split()
        print(parts)