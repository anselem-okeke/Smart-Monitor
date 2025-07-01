#------------------------------------------
"""Author: Anselem Okeke"""
#------------------------------------------

import sqlite3
import os
import json

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config/db_config.json"))
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../" + config["path"]))
print(f"[DEBUG] Connecting to DB at: {DB_PATH}")

# ---------------------------
# Log system metrics
# ---------------------------
def log_system_metrics(metrics):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        print("[DEBUG] Attempting to insert system metrics for host:", metrics.get("hostname"))

        cursor.execute("""
            INSERT INTO system_metrics (
                timestamp, hostname, cpu_usage, memory_usage,
                disk_usage, temperature, uptime, process_count, load_average
            ) VALUES (
                CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?
            )
        """, (
            metrics['hostname'],
            metrics['cpu_usage'],
            metrics['memory_usage'],
            metrics['disk_usage'],
            metrics['temperature'],
            metrics['uptime'],
            metrics['process_count'],
            metrics['load_average']
        ))

        conn.commit()
    except Exception as e:
        print(f"[ERROR] log_system_metrics: {e}")
    finally:
        conn.close()

# ---------------------------
# Log service status
# ---------------------------
def log_service_status(service):
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO service_status (
                timestamp, host, service_name, status,
                start_time, exit_code, error_message
            ) VALUES (
                CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?
            )
        """, (
            service['host'],
            service['service_name'],
            service['status'],
            service.get('start_time'),
            service.get('exit_code'),
            service.get('error_message')
        ))

        conn.commit()
    except Exception as e:
        print(f"[ERROR] log_service_status: {e}")
    finally:
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
        conn.close()

