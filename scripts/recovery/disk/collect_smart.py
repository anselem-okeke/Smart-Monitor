import ctypes
import json
import os
import pathlib
import platform
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

repo_root.mkdir(parents=True, exist_ok=True)
default_path = repo_root / "config" / "smartctl_disk.json"

HOST = socket.gethostname()
SMARTCTL = os.environ.get("SMARTCTL", "smartctl")
SCAN_LINE = re.compile(r'^(?P<dev>\S+)\s+-d\s+(?P<drv>[\w,:+\-]+)')

from db.db_logger import log_smart_health

def have_smartctl():
    return shutil.which(SMARTCTL) is not None

def is_root_linux():
    return hasattr(os, "geteuid") and os.geteuid() == 0

def is_admin_windows():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception as e:
        print(f"[ERROR] user has no admin right: {e}")
        return False

def smart_prefix():
    # If already elevated, no prefix
    if (platform.system() == "Linux" and is_root_linux()) or \
       (platform.system() == "Windows" and is_admin_windows()):
        return []
    # Optional: allow passwordless sudo only for smartctl (configure sudoers)
    if platform.system() == "Linux" and os.getenv("SMARTCTL_USE_SUDO", "1").lower() in ("1","true","yes"):
        return ["sudo", "-n"]
    return []

def load_cfg():
    cfg_path = Path(os.getenv("SMART_CONFIG", default_path))

    cfg = {"include": [], "exclude": []}
    try:
        if cfg_path.exists():
            with cfg_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            # shallow overides into defaults
            if isinstance(data, dict):
                cfg.update(data)
    except Exception as e:
        print(f"[WARN] smart_config read failed: {e}")
    return cfg

def scan_devices():
    """
    Discover devices with driver using smartctl.
    Returns: list[(device, driver)]
    """
    if not have_smartctl():
        print("[ERROR] smartctl not found. Install smartmontools or set SMARTCTL=/path/to/smartctl")
        return []

    # Try --scan-open first (preferred), then fall back to --scan.
    outputs = []
    for args in ([SMARTCTL, "--scan-open"], [SMARTCTL, "--scan"]):
        try:
            r = subprocess.run(args, text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=10)
            if r and r.stdout:
                outputs.append(r.stdout)
                if r.stdout.strip():
                    break
        except Exception as e:
            print(f"[WARN] {' '.join(args)} failed: {e}")

    if not outputs:
        print("[WARN] smartctl produced no output.")
        return []

    devices = []
    saw_commented_device = False

    for raw in "\n".join(outputs).splitlines():
        line = raw.strip()
        if not line:
            continue

        if line.startswith("#"):
            # smartctl lists devices but couldn't open them (permissions)
            saw_commented_device = True
            # still strip the comment to check format, but we skip adding it
            line = line[1:].strip()

        # strip trailing inline comment after '#'
        if "#" in line:
            line = line.split("#", 1)[0].strip()

        m = SCAN_LINE.match(line)
        if not m:
            continue

        dev = m.group("dev").strip()
        drv = m.group("drv").strip()

        # only add if it was not a commented line (i.e., openable)
        if not raw.lstrip().startswith("#"):
            devices.append((dev, drv))

    if not devices and saw_commented_device:
        if platform.system() == "Windows":
            print("[WARN] No openable disks found. Run the shell **as Administrator** and try again.")
        else:
            print("[WARN] No openable disks found. Run the command **as root** (e.g., with sudo) and try again.")

    return devices

# def parse_health_model_temp(output: str):
#     """
#     Parse smartctl output for:
#       - overall health (passed/failed/unknown/skipped)
#       - model (Device Model / Model Number / Vendor / Product / Model Family / Model Name)
#       - temperature in Celsius (best-effort across SATA/NVMe)
#     """
#     txt = output or ""
#     up  = txt.upper()
#
#     # If the drive was sleeping and the gentle call bailed out, mark as skipped
#     if "DEVICE IS IN STANDBY" in up or "DEVICE IS IN SLEEP" in up:
#         health = "skipped"
#     else:
#         # health
#         if "PASSED" in up:
#             health = "passed"
#         elif "FAILED" in up or "PRE-FAIL" in up:
#             health = "failed"
#         elif "NOT AVAILABLE" in up or "UNSUPPORTED" in up:
#             health = "unknown"
#         else:
#             # e.g. "SMART overall-health self-assessment test result: PASSED"
#             m = re.search(r"overall[- ]?health.*?:\s*([A-Za-z]+)", up)
#             health = (m.group(1).lower() if m else "unknown")
#
#     # model (try multiple keys, first match wins)
#     model = None
#     for key in [
#         "Device Model", "Model Number", "Model Name", "Model",
#         "Vendor", "Product", "Model Family"
#     ]:
#         m = re.search(rf"^{key}\s*:\s*(.+)$", txt, re.MULTILINE)
#         if m:
#             model = m.group(1).strip()
#             break
#
#     # temperature (several formats)
#     temp_c = None
#
#     # 1) ATA attribute 194: Temperature_Celsius
#     m = re.search(r"Temperature_Celsius\s+\d+\s+\d+\s+\d+\s+\d+\s+\w+\s+(\d+)", txt)
#     # 2) ATA attribute 190: Airflow_Temperature_Cel
#     if not m:
#         m = re.search(r"Airflow_Temperature_Cel\s+\d+\s+\d+\s+\d+\s+\d+\s+\w+\s+(\d+)", txt)
#     # 3) Some tools print "Current Drive Temperature: 34 C"
#     if not m:
#         m = re.search(r"Current Drive Temperature:\s*([0-9]+)\s*C", txt, re.IGNORECASE)
#     # 4) NVMe: "Composite Temperature: 34 C" or "Temperature: 34 C" or "Temperature Sensor N: 34 C"
#     if not m:
#         m = re.search(r"(?:Composite Temperature|Temperature(?: Sensor \d+)?):\s*([0-9]+)\s*C",
#                       txt, re.IGNORECASE)
#
#     if m:
#         try:
#             temp_c = float(m.group(1))
#         except Exception:
#             temp_c = None
#
#     return health, model, temp_c

def looks_virtual(txt: str) -> bool:
    # common VM/virtual disk fingerprints
    return bool(re.search(r'\b(VBOX|Virtual|VirtualBox|Msft|Microsoft|QEMU|Hyper-?V|VMware)\b', txt, re.I))

def has_real_smart(txt: str) -> bool:
    # signals that the output actually contains SMART info
    return any([
        re.search(r"SMART support is:\s*Available", txt, re.I),
        re.search(r"SMART support is:\s*Enabled", txt, re.I),
        re.search(r"SMART overall[- ]?health.*?:", txt, re.I),
        re.search(r"SMART Attributes Data Structure", txt, re.I),
        re.search(r"NVMe.*SMART/Health", txt, re.I),
    ])

def parse_health_model_temp(output: str):
    """
    Parse smartctl output for:
      - health: 'passed' | 'failed' | 'unknown' | 'skipped'
      - model: best-effort from several id keys
      - temp_c: best-effort across ATA/NVMe formats
    """
    txt = output or ""
    up  = txt.upper()

    # ---------- HEALTH ----------
    health = "unknown"

    # If drive was sleeping and we used -n standby
    if ("DEVICE IS IN STANDBY" in up) or ("DEVICE IS IN SLEEP" in up) or re.search(r'\bexit\(2\)\b', up):
        health = "skipped"
    else:
        # 1) SCSI/SAS style: "SMART Health Status: OK/FAILED"
        m = re.search(r"SMART\s+Health\s+Status:\s*([A-Za-z]+)", txt, re.IGNORECASE)
        if m:
            val = m.group(1).strip().lower()
            if val in ("ok", "good", "passed"):
                health = "passed"
            elif val in ("failed", "fail", "bad"):
                health = "failed"
            else:
                health = "unknown"
        else:
            # 2) ATA/NVMe explicit line:
            m = re.search(r"overall[- ]?health.*?:\s*([A-Za-z]+)", txt, re.IGNORECASE)
            if m:
                val = m.group(1).strip().lower()
                if val in ("passed", "ok", "good"):
                    health = "passed"
                elif val in ("failed", "fail", "bad"):
                    health = "failed"
                else:
                    health = "unknown"
            else:
                # 3) Keywords
                if "PASSED" in up:
                    health = "passed"
                elif ("FAILED" in up) or ("PRE-FAIL" in up):
                    health = "failed"
                elif ("NOT AVAILABLE" in up) or ("UNSUPPORTED" in up):
                    health = "unknown"

    # If SMART is unavailable or this looks like a virtual disk,
    # don't report "passed" based on SCSI OK — clamp to unknown.
    if (not has_real_smart(txt) or looks_virtual(txt)) and health in ("passed", "ok", "good"):
        health = "unknown"

    health = health.lower()  # normalize

    # ---------- MODEL ----------
    model = None
    for key in [
        "Device Model", "Model Number", "Model Name", "Model",
        "Vendor", "Product", "Model Family"
    ]:
        m = re.search(rf"^{key}\s*:\s*(.+)$", txt, re.MULTILINE)
        if m:
            model = m.group(1).strip()
            break

    # ---------- TEMPERATURE ----------
    temp_c = None

    # ATA attr 194: Temperature_Celsius
    m = re.search(r"Temperature_Celsius\s+\d+\s+\d+\s+\d+\s+\d+\s+\w+\s+(\d+)", txt)
    # ATA attr 190: Airflow_Temperature_Cel
    if not m:
        m = re.search(r"Airflow_Temperature_Cel\s+\d+\s+\d+\s+\d+\s+\d+\s+\w+\s+(\d+)", txt)
    # Generic: "Current Drive Temperature: 34 C"
    if not m:
        m = re.search(r"Current Drive Temperature:\s*([0-9]+)\s*C", txt, re.IGNORECASE)
    # NVMe: "Composite Temperature: 34 C" / "Temperature: 34 C" / "Temperature Sensor N: 34 C"
    if not m:
        m = re.search(r"(?:Composite Temperature|Temperature(?: Sensor \d+)?):\s*([0-9]+)\s*C", txt, re.IGNORECASE)

    if m:
        try:
            temp_c = float(m.group(1))
        except Exception:
            temp_c = None

    # Ignore bogus 0°C on virtual/unsupported devices
    if temp_c is not None and temp_c == 0.0 and (looks_virtual(txt) or not has_real_smart(txt)):
        temp_c = None

    return health, model, temp_c


# def parse_health_model_temp(output: str):
#     """
#     Parse smartctl output for:
#       - health: 'passed' | 'failed' | 'unknown' | 'skipped'
#       - model: best-effort from several id keys
#       - temp_c: best-effort across ATA/NVMe formats
#     """
#     txt = output or ""
#     up  = txt.upper()
#
#     # ---------- HEALTH ----------
#     # default
#     health = "unknown"
#
#     # If drive was sleeping and we used -n standby
#     if "DEVICE IS IN STANDBY" in up or "DEVICE IS IN SLEEP" in up:
#         health = "skipped"
#     else:
#         # 1) SCSI/SAS style: "SMART Health Status: OK/FAILED"
#         m = re.search(r"SMART\s+Health\s+Status:\s*([A-Za-z]+)", txt, re.IGNORECASE)
#         if m:
#             val = m.group(1).strip().lower()
#             if val in ("ok", "good"):
#                 health = "passed"
#             elif val in ("failed", "fail", "bad"):
#                 health = "failed"
#             else:
#                 health = "unknown"
#         else:
#             # 2) ATA/NVMe explicit line:
#             #    "SMART overall-health self-assessment test result: PASSED"
#             m = re.search(r"overall[- ]?health.*?:\s*([A-Za-z]+)", txt, re.IGNORECASE)
#             if m:
#                 val = m.group(1).strip().lower()
#                 if val in ("passed", "ok", "good"):
#                     health = "passed"
#                 elif val in ("failed", "fail", "bad"):
#                     health = "failed"
#                 else:
#                     health = "unknown"
#             else:
#                 # 3) Keyword fallbacks
#                 if "PASSED" in up:
#                     health = "passed"
#                 elif "FAILED" in up or "PRE-FAIL" in up:
#                     health = "failed"
#                 elif "NOT AVAILABLE" in up or "UNSUPPORTED" in up:
#                     health = "unknown"
#
#     # ---------- MODEL ----------
#     model = None
#     for key in [
#         "Device Model", "Model Number", "Model Name", "Model",
#         "Vendor", "Product", "Model Family"
#     ]:
#         m = re.search(rf"^{key}\s*:\s*(.+)$", txt, re.MULTILINE)
#         if m:
#             model = m.group(1).strip()
#             break
#
#     # ---------- TEMPERATURE ----------
#     temp_c = None
#
#     # ATA attribute 194
#     m = re.search(r"Temperature_Celsius\s+\d+\s+\d+\s+\d+\s+\d+\s+\w+\s+(\d+)", txt)
#     # ATA attribute 190
#     if not m:
#         m = re.search(r"Airflow_Temperature_Cel\s+\d+\s+\d+\s+\d+\s+\d+\s+\w+\s+(\d+)", txt)
#     # Generic forms
#     if not m:
#         m = re.search(r"Current Drive Temperature:\s*([0-9]+)\s*C", txt, re.IGNORECASE)
#     # NVMe forms
#     if not m:
#         m = re.search(r"(?:Composite Temperature|Temperature(?: Sensor \d+)?):\s*([0-9]+)\s*C",
#                       txt, re.IGNORECASE)
#
#     if m:
#         try:
#             temp_c = float(m.group(1))
#         except Exception:
#             temp_c = None
#
#     return health, model, temp_c

def run_smart(device, driver):
    """
    Run smartctl on a device with the correct -d driver and be gentle with sleeping disks.
    First try: '-n standby' (do not spin up). If it bails out, do one forced read with '-n never'
    to populate fields (this will spin up the disk).
    Returns a dict ready for DB insertion.
    """
    # Base args: driver + permissive tolerance (controllers vary)
    base = [*smart_prefix(), SMARTCTL, "-d", driver, "-T", "permissive", device]

    # 1) Gentle read (won't wake a sleeping drive)
    cmd1 = base + ["-i", "-A", "-H", "-n", "standby"]
    out_parts = []
    try:
        r1 = subprocess.run(cmd1, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=12)
        out1 = r1.stdout or ""
    except subprocess.TimeoutExpired:
        out1 = "timeout"
    except Exception as e:
        out1 = str(e)
    out_parts.append(out1)

    # 2) If the device was sleeping, do ONE forced read to get model/health/temp (optional but useful)
    up1 = (out1 or "").upper()
    if "DEVICE IS IN STANDBY" in up1 or "DEVICE IS IN SLEEP" in up1:
        cmd2 = base + ["-i", "-A", "-H", "-n", "never"]
        try:
            r2 = subprocess.run(cmd2, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=20)
            out2 = r2.stdout or ""
        except subprocess.TimeoutExpired:
            out2 = "timeout"
        except Exception as e:
            out2 = str(e)
        out_parts.append(out2)

    combined = "\n".join(out_parts)
    health, model, temp_c = parse_health_model_temp(combined)

    # normalize health for querying
    health = (health or "unknown").lower()

    return {
        "hostname": HOST,
        "device": device,
        "health": health,   # 'passed' | 'failed' | 'unknown' | 'skipped'
        "model": model,
        "temp_c": temp_c,
        "output": combined[:20000],
    }

# def parse_health_model_temp(output):
#     """
#     Parse a variety of smartctl outputs for:
#       - overall health (PASSED/FAILED/Unknown)
#       - model (Device Model / Model Family / Model Number / Vendor)
#       - temperature (best effort)
#     """
#     txt = output or ""
#     up = txt.upper()
#
#     # health
#     if "PASSED" in up:
#         health = "PASSED"
#     elif "FAILED" in up or "PRE-FAIL" in up:
#         health = "FAILED"
#     elif "NOT AVAILABLE" in up or "UNSUPPORTED" in up:
#         health = "Unknown"
#     else:
#         # NVMe sometimes prints "SMART overall-health self-assessment test result: PASSED"
#         m = re.search(r"overall[- ]?health.*?:\s*(\w+)", up)
#         health = (m.group(1) if m else "Unknown").capitalize()
#
#     # model (try multiple keys)
#     model = None
#     for key in ["Device Model", "Model Number", "Model", "Vendor", "Product", "Model Family"]:
#         m = re.search(rf"^{key}\s*:\s*(.+)$", txt, re.MULTILINE)
#         if m:
#             model = m.group(1).strip()
#             break
#
#     # temperature
#     temp_c = None
#     # smartctl -A attribute-style line (SATA)
#     m = re.search(r"Temperature_Celsius\s+\d+\s+\d+\s+\d+\s+\d+\s+\w+\s+(\d+)", txt)
#     if m:
#         try: temp_c = float(m.group(1))
#         except: pass
#
#     if temp_c is None:
#         # NVMe-style: "Temperature: 34 Celsius"
#         m = re.search(r"Temperature:\s*([0-9]+)\s*C", txt, re.IGNORECASE)
#         if m:
#             try: temp_c = float(m.group(1))
#             except: pass
#
#     return health, model, temp_c
#
# def run_smart(device, driver):
#     """
#     Run smartctl on a device with the correct -d driver
#     :param device: variable for the device
#     :param driver: variable for the device driver
#     :return: Returns dict entry for Database
#     """
#
#     # Base args: driver + be gentle/persion for all the pattern
#     base = [*smart_prefix(), SMARTCTL, "-d", driver, "-n", "standby", "-T", "permissive", device]
#
#     cmds = [
#         base + ["-H"],  # overall health
#         base + ["-A"],  # attributes (for temp)
#     ]
#
#     outs = []
#     for cmd in cmds:
#         try:
#             r = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=12)
#             outs.append(r.stdout)
#         except subprocess.TimeoutExpired:
#             outs.append("timeout")
#         except Exception as e:
#             outs.append(str(e))
#
#     combined = "\n".join(outs)
#     health, model, temp_c = parse_health_model_temp(combined)
#
#     # normalize health (easier queries later)
#     health = (health or "").lower()  # 'passed'/'failed'/'unknown'
#
#     return {
#         "hostname": HOST,
#         "device": device,
#         "health": health,
#         "model": model,
#         "temp_c": temp_c,
#         "output": combined[:20000]
#     }

def filtered(dev_list, cfg):
    inc = cfg.get("include") or []
    exc = cfg.get("exclude") or []
    if inc:
        dev_list = [d for d in dev_list if any(p in d[0] for p in inc)]
    if exc:
        dev_list = [d for d in dev_list if all(p not in d[0] for p in exc)]
    return dev_list


def collect_smart_once(ensure_schema: bool = False) -> int:
    """
    Collect SMART health for discovered disks once and write to DB.
    Returns the number of rows inserted (0 on no-op/error).

    - In the orchestrator: call collect_smart_once()  (ensure_schema=False).
    - Ad-hoc/manual run:   call collect_smart_once(ensure_schema=True).
    """
    # (A) Optional: schema init only for ad-hoc usage
    if ensure_schema:
        try:
            from db.auto_init import ensure_db_initialized
        except ImportError:
            print("[INFO] Skipping schema init: db.auto_init not on PYTHONPATH (orchestrator usually handles this).")
        else:
            try:
                ensure_db_initialized()
            except Exception as e:
                print(f"[WARN] ensure_db_initialized failed: {e}")

    # (B) Tool present?
    if not have_smartctl():
        print("[ERROR] smartctl not found. Install smartmontools and/or set SMARTCTL.")
        return 0

    # (C) Discover -> filter (policy via config)
    cfg   = load_cfg()                 # {"include": [...], "exclude": [...]}
    cand  = scan_devices()             # list[(device, driver)]
    devs  = filtered(cand, cfg)

    if not devs:
        print("[INFO] No SMART-capable devices discovered (or filtered out).")
        return 0

    # (D) Collect rows (be resilient per-device)
    rows = []
    for dev, drv in devs:
        try:
            rows.append(run_smart(dev, drv))
        except Exception as e:
            print(f"[WARN] SMART read failed for {dev} ({drv}): {e}")

    if not rows:
        print("[INFO] Nothing to log.")
        return 0

    # (E) Write to DB (precise errors)
    try:
        inserted = log_smart_health(rows)  # prefer to have this return the count
    except sqlite3.OperationalError as e:
        msg = str(e).lower()
        if "no such table" in msg and "smart_health" in msg:
            print("[ERROR] Table smart_health is missing. Run auto-init or apply schema.sql first.")
            return 0
        print(f"[ERROR] DB write failed: {e}")
        return 0
    except Exception as e:
        print(f"[ERROR] DB write failed: {e}")
        return 0

    # (F) Report how many inserted (fallback to len(rows) if function returns None)
    if isinstance(inserted, int) and inserted >= 0:
        print(f"[INFO] SMART logged: {inserted} devices")
        return inserted

    print(f"[INFO] SMART logged: {len(rows)} devices")
    return len(rows)

# def collect_smart_once():
#     # 0) ensure schema when run ad-hoc (or do nothing if the helper isn't available)
#     try:
#         from db.auto_init import ensure_db_initialized
#         ensure_db_initialized()
#     except Exception as e:
#         print(f"orchestrator already does this; ad-hoc may not have the module path:{e}")
#         pass
#
#     # 1) tool present?
#     if not have_smartctl():
#         print("[ERROR] smartctl not found. Install smartmontools and/or set SMARTCTL.")
#         return 0
#
#     # 2) discover + filter
#     cfg = load_cfg()                 # your include/exclude loader
#     cand = scan_devices()            # your working scanner (with the root/Admin hint)
#     devs = filtered(cand, cfg)
#
#     if not devs:
#         print("[INFO] No SMART-capable devices discovered (or filtered out).")
#         return 0
#
#     # 3) collect
#     rows = [run_smart(dev, drv) for dev, drv in devs]
#     if not rows:
#         print("[INFO] Nothing to log.")
#         return 0
#
#     # 4) write to DB, with precise error handling
#     try:
#         log_smart_health(rows)
#         print(f"[INFO] SMART logged: {len(rows)} devices")
#         return len(rows)
#     except sqlite3.OperationalError as e:
#         msg = str(e).lower()
#         if "no such table" in msg and "smart_health" in msg:
#             print("[ERROR] Table smart_health is missing. Run auto-init or apply schema.sql first.")
#             return 0
#         print(f"[ERROR] DB write failed: {e}")
#         return 0


# def collect_smart_once():
#     if not have_smartctl():
#         print("[ERROR] smartctl not found. Install smartmontools and ensure SMARTCTL is set if needed.")
#         return 0
#
#     cfg = load_cfg()  # your existing include/exclude loader
#     cand = scan_devices()
#     devs = filtered(cand, cfg)
#
#     if not devs:
#         print("[INFO] No SMART-capable devices discovered (or filtered out).")
#         return 0
#
#     rows = []
#     for dev, drv in devs:
#         rows.append(run_smart(dev, drv))
#
#     if rows:
#         log_smart_health(rows)
#         print(f"[INFO] SMART logged: {len(rows)} devices")
#         return len(rows)
#     return 0

if __name__ == "__main__":
    # One-off run for testing
    collect_smart_once(ensure_schema=True)
















# def scan_devices():
#     """
#     Discover devices with driver using smartctl.
#     Returns: list[(device, driver)]
#     """
#     if not have_smartctl():
#         print("[ERROR] smartctl not found. Install smartmontools or set SMARTCTL=/path/to/smartctl")
#         return []
#
#     # Try --scan-open first (preferred), then fallback to --scan.
#     outputs = []
#     for args in ([SMARTCTL, "--scan-open"], [SMARTCTL, "--scan"]):
#         try:
#             r = subprocess.run(args, text=True, stdout=subprocess.PIPE,
#                                stderr=subprocess.STDOUT, timeout=10)
#             if r and r.stdout:
#                 outputs.append(r.stdout)
#                 if r.stdout.strip():
#                     break
#         except Exception as e:
#             print(f"[WARN] {' '.join(args)} failed: {e}")
#
#     if not outputs:
#         return []
#
#     devices = []
#     for raw in "\n".join(outputs).splitlines():
#         line = raw.strip()
#         if not line:
#             continue
#         if line.startswith("#"):
#             # commented lines mean "not openable" or informational -> skip
#             continue
#         # strip trailing inline comment after '#'
#         if "#" in line:
#             line = line.split("#", 1)[0].strip()
#         m = SCAN_LINE.match(line)
#         if not m:
#             continue
#         dev = m.group("dev").strip()
#         drv = m.group("drv").strip()
#         devices.append((dev, drv))
#     return devices
