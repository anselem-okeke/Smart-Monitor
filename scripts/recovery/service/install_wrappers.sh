#!/bin/bash
# install once per host
cat <<'EOF' | sudo tee /usr/local/bin/smartmon-restart-service >/dev/null
#!/usr/bin/env bash
set -euo pipefail
svc="$1"
[[ "$svc" =~ ^[A-Za-z0-9@._+-]+(\.service)?$ ]] || { echo "invalid"; exit 2; }
unit="$svc"; [[ "$unit" != *.service ]] && unit="$unit.service"
/bin/systemctl restart -- "$unit"
/bin/systemctl is-active --quiet "$unit"
echo "ok: $unit restarted"
EOF
sudo chown root:root /usr/local/bin/smartmon-restart-service
sudo chmod 0755 /usr/local/bin/smartmon-restart-service
sudo restorecon -v /usr/local/bin/smartmon-restart-service 2>/dev/null || true