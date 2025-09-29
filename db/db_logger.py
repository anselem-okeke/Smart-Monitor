#------------------------------------------
"""Author: Anselem Okeke"""
#------------------------------------------

import sqlite3
import os
import json
from datetime import datetime
from pathlib import Path
from db.core import DB_PATH, connect_rw

import logging

# CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config/db_config.json"))
# with open(CONFIG_PATH, "r") as f:
#     config = json.load(f)
#
# DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../" + config["path"]))
# print(f"[DEBUG] Connecting to DB at: {DB_PATH}")



def log_system_metrics(metrics):
    """
    metrics should have keys:
      hostname, os_platform, cpu_usage, memory_usage, disk_usage,
      temperature, uptime, process_count, load_average, inode_usage, swap_usage
    """
    try:
        with connect_rw() as conn:
            conn.execute("""
                INSERT INTO system_metrics (
                    timestamp, hostname, os_platform, cpu_usage, memory_usage,
                    disk_usage, temperature, uptime, process_count, load_average,
                    inode_usage, swap_usage
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                metrics['hostname'],
                metrics['os_platform'],
                metrics['cpu_usage'],
                metrics['memory_usage'],
                metrics['disk_usage'],
                metrics['temperature'],
                metrics['uptime'],
                metrics['process_count'],
                metrics['load_average'],
                metrics['inode_usage'],
                metrics['swap_usage'],
            ))
            # context manager commits on successful block exit
        print(f"[INFO] system_metrics insert OK → {DB_PATH}")
    except Exception as e:
        # Make failures visible to the orchestrator logs
        print(f"[ERROR] log_system_metrics: {e}")
        raise

# # ---------------------------
# # Log system metrics
# # ---------------------------
# def log_system_metrics(metrics):
#     conn = None
#     try:
#         conn = sqlite3.connect(DB_PATH)
#         cursor = conn.cursor()
#
#         print("[DEBUG] Attempting to insert system metrics for host:", metrics.get("hostname"))
#
#         cursor.execute("""
#             INSERT INTO system_metrics (
#                 timestamp, hostname, os_platform, cpu_usage, memory_usage,
#                 disk_usage, temperature, uptime, process_count, load_average, inode_usage, swap_usage
#             ) VALUES (
#                 ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
#             )
#         """, (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
#             metrics['hostname'],
#             metrics['os_platform'],
#             metrics['cpu_usage'],
#             metrics['memory_usage'],
#             metrics['disk_usage'],
#             metrics['temperature'],
#             metrics['uptime'],
#             metrics['process_count'],
#             metrics['load_average'],
#             metrics['inode_usage'],
#             metrics['swap_usage']
#         ))
#
#         conn.commit()
#     except Exception as e:
#         print(f"[ERROR] log_system_metrics: {e}")
#     finally:
#         if conn:
#             conn.close()

# ---------------------------
# Batch log process status
# ---------------------------
def log_process_status_batch(processes):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.executemany("""
            INSERT INTO process_status (
                timestamp, hostname, os_platform, pid, process_name, raw_status, normalized_status, 
                cpu_percent, memory_percent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                proc['timestamp'],
                proc['hostname'],
                proc['os_platform'],
                proc['pid'],
                proc['process_name'],
                proc['raw_status'],
                proc['normalized_status'],
                proc['cpu_percent'],
                proc['memory_percent']
            ) for proc in processes
        ])

        conn.commit()
    except Exception as e:
        print(f"[ERROR] log_process_status_batch: {e}")
    finally:
        if conn:
            conn.close()

# ---------------------------
# Batch log service status
# ---------------------------
def log_service_status_batch(services):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.executemany("""
            INSERT INTO service_status (
                timestamp, hostname, os_platform, service_name, raw_status, normalized_status, 
                sub_state, service_type, unit_file_state, recoverable
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            (
                svc['timestamp'],
                svc['hostname'],
                svc['os_platform'],
                svc['service_name'],
                svc['raw_status'],
                svc['normalized_status'],
                svc['sub_state'],
                svc['service_type'],
                svc['unit_file_state'],
                svc['recoverable']
            ) for svc in services
        ])

        conn.commit()
    except Exception as e:
        print(f"[ERROR] log_service_status_batch: {e}")
    finally:
        if conn:
            conn.close()

# ------------------------------------------
# Batch log recovery log
# ------------------------------------------
def log_recovery(service_name):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.executemany("""
            INSERT INTO recovery_logs (
                timestamp, hostname, os_platform, service_name, result, error_message
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, [
            (
                svc['timestamp'],
                svc['hostname'],
                svc['os_platform'],
                svc['service_name'],
                svc['result'],
                svc['error_message']
            ) for svc in service_name
        ])

        conn.commit()
    except Exception as e:
        print(f"[ERROR] log_recovery_status_batch: {e}")
    finally:
        if conn:
            conn.close()

# ------------------------------------------
# Log network event (ping, traceroute, etc.)
# ------------------------------------------
def log_network_event(event):
    conn = None
    try:
        required_keys = ["hostname", "target", "method", "result", "latency_ms", "packet_loss_percent", "status"]
        for key in required_keys:
            if key not in event:
                raise KeyError(f"Missing required key: '{key}' in event → {event}")

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO network_logs (
                timestamp, hostname, target, method, result,
                latency_ms, packet_loss_percent, status
            ) VALUES (
                CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            event['hostname'],
            event['target'],
            event['method'],
            event['result'],
            event.get('latency_ms'),
            event.get('packet_loss_percent'),
            event['status']
        ))

        conn.commit()
    except Exception as e:
        print(f"[ERROR] log_network_event: {e}")
    finally:
        if conn:
            conn.close()


# ---------------------------
# Log system alert (anomaly, threshold breach)
# ---------------------------
def log_alert(alert):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO alerts (
                timestamp, hostname, severity, source, message
            ) VALUES (
                CURRENT_TIMESTAMP, ?, ?, ?, ?
            )
        """, (
            alert['hostname'],
            alert['severity'],
            alert['source'],
            alert['message']
        ))

        conn.commit()
    except Exception as e:
        print(f"[ERROR] log_alert: {e}")
    finally:
        if conn:
            conn.close()

# ---------------------------
# Log restart attempts
# ---------------------------
def log_restart_attempt(entry):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO restart_attempts (
                timestamp, hostname, service_name
            ) VALUES (?, ?, ?)
        """, (
            entry['timestamp'],
            entry['hostname'],
            entry['service_name']
        ))

        conn.commit()
    except Exception as e:
        print(f"[ERROR] restart_attempts: {e}")
    finally:
        if conn:
            conn.close()

# ---------------------------
# Adding inode_usage into log system metrics
# ---------------------------
def create_inode_usage_column():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE system_metrics ADD COLUMN inode_usage REAL;")
        print("[INFO] Column 'inode_usage' added.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("[INFO] column inode_usage already exits")
        else:
            print(f"[ERROR] {e}")
    finally:
        conn.commit()
        conn.close()

# ---------------------------
# Adding swap_usage into log system metrics
# ---------------------------
def create_swap_usage_column():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE system_metrics ADD COLUMN swap_usage REAL;")
        print("[INFO] Column 'swap_usage' added.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("[INFO] column swap_usage already exits")
        else:
            print(f"[ERROR] {e}")
    finally:
        conn.commit()
        conn.close()

# -------------------------------------
#    SMART health
# -------------------------------------
def log_smart_health(entries):
    """
    Insert one or many SMART results.
    Each entry: {
      "hostname": str,
      "device": str,             # e.g. /dev/sda or \\.\PHYSICALDRIVE0
      "health": str,             # PASSED / FAILED / Unknown
      "model": str | None,
      "temp_c": float | None,
      "output": str | None       # raw smartctl -H/-A snippet (optional)
    }
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        rows = entries if isinstance(entries, list) else [entries]
        cur.executemany("""
            INSERT INTO smart_health
              (timestamp, hostname, device, health, model, temp_c, output)
            VALUES (CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?)
        """, [
            (
                r.get("hostname"),
                r.get("device"),
                r.get("health"),
                r.get("model"),
                r.get("temp_c"),
                r.get("output"),
            )
            for r in rows
        ])
        conn.commit()
    except Exception as e:
        print(f"[ERROR] log_smart_health: {e}")
    finally:
        if conn:
            conn.close()



