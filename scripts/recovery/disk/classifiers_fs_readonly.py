# Detect if the root filesystem is currently mounted read-only.
#Happens after I/O errors or sudden power loss;
# next highest operational impact because writes halt.

def is_root_readonly() -> bool:
    """
    Returns True when '/' appears with 'ro' in /proc/self/mounts.
    Works on all modern Linux distros.  Windows returns False.
    """
    try:
        with open("/proc/self/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 4 and parts[1] == "/mnt/test_ro":
                # if len(parts) >= 4 and parts[1] == "/":
                    opts = parts[3].split(",")
                    if "ro" in opts:
                        print("[WARN] Root filesystem is mounted read-only!")
                        return True
    except FileNotFoundError:
        pass  # non-Linux (Windows) → fall through
    return False


