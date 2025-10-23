import json
import os

service_config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config/approved_services.json"))
def load_approved_services(config_path=service_config_path):
    try:
        with open(config_path, "r") as f:
            return set(json.load(f))  # Use set for fast lookup
    except Exception as e:
        print(f"[ERROR] Failed to load approved services: {e}")
        return set()