import json, os, socket, platform

def load_approved_services(config_path=None):
    # Prefer env (works for Docker + service), fallback to repo-relative path
    default_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config/approved_services.json"))
    path = config_path or os.getenv("SMARTMON_APPROVED_JSON") or default_path

    host = (platform.node() or socket.gethostname() or "").strip()

    try:
        with open(path, "r") as f:
            data = json.load(f)

        allowed = set()

        # New format: {"allow":[{"host":"BackendServer","service":"nginx.service"}, ...]}
        if isinstance(data, dict) and "allow" in data:
            for rule in data.get("allow", []):
                rhost = (rule.get("host") or "").strip()
                svc   = (rule.get("service") or "").strip()
                if not svc:
                    continue
                if rhost in (host, "*", "ZZZZ-sentinel"):   # keep your sentinel if you want
                    allowed.add(svc)
            return allowed

        # Old format support: ["nginx.service","ssh.service",...]
        if isinstance(data, list):
            return {str(x).strip() for x in data if str(x).strip()}

        return set()

    except Exception as e:
        print(f"[ERROR] Failed to load approved services from {path}: {e}")
        return set()









# import json
# import os
#
# service_config_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../config/approved_services.json"))
# def load_approved_services(config_path=service_config_path):
#     try:
#         with open(config_path, "r") as f:
#             return set(json.load(f))  # Use set for fast lookup
#     except Exception as e:
#         print(f"[ERROR] Failed to load approved services: {e}")
#         return set()