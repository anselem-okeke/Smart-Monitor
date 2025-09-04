import sqlite3
import socket
import json
import os
from datetime import datetime

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "./config/db_config.json"))

with open(CONFIG_PATH, "r") as f:
    config = json.load(f)
    print(config)

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), config["path"]))
print(DB_PATH)
def insert_event(event):
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO network_logs (
                timestamp, hostname, target, method, result,
                latency_ms, packet_loss_percent, status
            ) VALUES (
                CURRENT_TIMESTAMP, :hostname, :target, :method, :result,
                :latency_ms, :packet_loss_percent, :status
            )
        """, event)
        conn.commit()
        conn.close()
        print(f"[INSERTED] {event['target']} ({event['status']})")
    except Exception as e:
        print(f"[ERROR] Insert failed for {event['target']}: {e}")


def simulate_all_events():
    hostname = socket.gethostname()

    test_events = [
        # DNS failure
        {
            "hostname": hostname,
            "target": "fake9876543210notrealexample.com",
            "method": "ping",
            "result": "Ping request could not find host fake9876543210notrealexample.com. Please check the name and try again.",
            "latency_ms": None,
            "packet_loss_percent": None,
            "status": "fail"
        },
        # Firewall block
        {
            "hostname": hostname,
            "target": "192.168.56.14",
            "method": "ping",
            "result": "Command '['ping', '-n', '4', '192.168.56.14']' timed out after 4000ms",
            "latency_ms": 1000,
            "packet_loss_percent": 100.0,
            "status": "fail"
        },
        # Latency spike
        {
            "hostname": hostname,
            "target": "8.8.8.8",
            "method": "ping",
            "result": "Reply from 8.8.8.8: bytes=32 time=600ms TTL=117",
            "latency_ms": 600,
            "packet_loss_percent": 0.0,
            "status": "success"
        },
        # Normal success
        {
            "hostname": hostname,
            "target": "8.8.4.4",
            "method": "ping",
            "result": "Reply from 8.8.4.4: bytes=32 time=25ms TTL=117",
            "latency_ms": 25,
            "packet_loss_percent": 0.0,
            "status": "success"
        }
    ]

    for event in test_events:
        insert_event(event)


if __name__ == "__main__":
    simulate_all_events()
