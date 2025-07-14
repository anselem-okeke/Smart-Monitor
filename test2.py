
import json
import os
import socket
import sqlite3
from datetime import datetime
from scripts.recovery.network.main import handle_event

CONFIG_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "./config/db_config.json"))

with open(CONFIG_PATH, "r") as f:
    config = json.load(f)
    print(config)

DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), config["path"]))
print(DB_PATH)

def simulate_firewall_block_event(target_ip: str):
    event = {
        "hostname": socket.gethostname(),
        "target": target_ip,
        "method": "ping",
        "result": "Request timed out",  # Suspicious result
        "latency_ms": 100000000,             # <- corrected key
        "packet_loss_percent": 10000000.0,
        "status": "fail"
    }

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
        print(f"[SIMULATION] Inserted simulated firewall block event for {target_ip}")
    except Exception as e:
        print(f"[ERROR] Inserting simulated event: {e}")




test_event = (
    999,                                # _id
    "192.168.56.14",                    # tgt
    "ping",                             # method
    "Request timed out",               # result_txt (suspicious for firewall block)
    1000,                               # latency
    100.0                               # packet loss
)

handle_event(test_event)

#python test2.py --simulate-firewall == run the code

if __name__ == '__main__':
    import sys
    if len(sys.argv) == 2 and sys.argv[1] == "--simulate-firewall":
        simulate_firewall_block_event("192.168.56.14")

