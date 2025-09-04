# Detect if the root filesystem is currently mounted read-only.
# Single responsibility → no DB, no side-effects.
import os
import subprocess
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

# with open("/proc/self/mounts") as f:
#     for line in f:
#         parts = line.split()
#         print(parts)

THROTLE_MIN = 1   #30
RETRY_LIMIT = 0  #3
TMP_DAYS = 0   #3

def delete_old_files(path, days):

    print(f"[INFO] Cleaning up files in {path} older than {days} days...")

    # 1. Delete old files (ignores permission-denied silently)
    subprocess.call([
        "find", path,
        "-type", "f",
        "-mtime", f"{-1}",
        "!", "-path", "*/systemd-private-*",
        "!", "-path", "*/snap-private-tmp*",
        "-print", "-delete"
    ])

    # 2. Delete empty dirs (but skip protected dirs)
    subprocess.call([
        "find", path,
        "-type", "d", "-empty",
        "!", "-path", "*/systemd-private-*",
        "!", "-path", "*/snap-private-tmp*",
        "-print", "-delete"
    ])

    print(f"[INFO] {path} cleanup complete...")

def high_node_dirs():

    High_INODE_DIRS = [
        "/tmp"
    ]
    return High_INODE_DIRS



for path in high_node_dirs():
    if os.path.exists(path):
        delete_old_files(path, TMP_DAYS)



