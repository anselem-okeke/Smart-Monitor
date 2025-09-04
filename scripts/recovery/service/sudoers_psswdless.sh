#!/bin/bash

# allow-list
echo -e "nginx.service\ntelegraf.service" | sudo tee /etc/smart-monitor/approved_services.txt

# wrapper
sudo tee /usr/local/bin/smartmon-restart-service >/dev/null <<'SH'
#!/usr/bin/env bash
set -euo pipefail
svc="${1:-}"
grep -Fxq "$svc" /etc/smart-monitor/approved_services.txt
exec /bin/systemctl restart "$svc"
SH
sudo chmod 0755 /usr/local/bin/smartmon-restart-service
sudo chown root:root /usr/local/bin/smartmon-restart-service

# sudoers rule
echo 'smartmonitor ALL=(root) NOPASSWD: /usr/local/bin/smartmon-restart-service' | \
  sudo tee /etc/sudoers.d/90-smartmonitor >/dev/null
sudo chmod 0440 /etc/sudoers.d/90-smartmonitor
sudo visudo -cf /etc/sudoers.d/90-smartmonitor  # should say "parsed OK"
