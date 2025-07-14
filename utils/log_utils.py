import os
from datetime import datetime
logfile_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../logs/unclassified_services.log"))

def log_unclassified_service(service_tuple, reason="Not in approved_services", logfile=logfile_path):
    """
    Log unapproved or skipped services with full context for audit/review.
    Format: timestamp | hostname | service_name | active_state | sub_state | service_type | unit_file_state | reason
    """
    service_name, normalized_status, hostname, sub_state, service_type, unit_file_state, recoverable = service_tuple
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    log_line = f"{timestamp} | {hostname} | {service_name} | {normalized_status} | {sub_state} | {service_type} | {unit_file_state} | {reason}\n"

    try:
        os.makedirs(os.path.dirname(logfile), exist_ok=True)
        with open(logfile, "a") as f:
            f.write(log_line)
    except Exception as e:
        print(f"[ERROR] Failed to write to unclassified log: {e}")
