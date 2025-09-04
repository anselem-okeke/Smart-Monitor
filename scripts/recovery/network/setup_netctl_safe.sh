#!/bin/bash
# setup_netctl_safe.sh
set -euo pipefail

SMART_USER=smartmonitor
WRAPPER=/usr/local/bin/smartmon-netctl
ALLOW=/etc/smart-monitor/approved_ifaces.txt
SUDOERS=/etc/sudoers.d/92-smartmonitor-netctl

# Edit this list to your environment (interfaces you allow to bounce):
IFACES="enp0s8
enp0s9"

install -d -m 0755 /etc/smart-monitor
printf "%s\n" $IFACES | sort -u | tee "$ALLOW" >/dev/null

cat > "$WRAPPER" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
IFACE="${1:-}"
ACTION="${2:-bounce}"   # down | up | bounce
ALLOW=/etc/smart-monitor/approved_ifaces.txt
IPBIN="$(command -v ip)"

if [[ -z "$IFACE" ]]; then
  echo "usage: smartmon-netctl <iface> [down|up|bounce]" >&2; exit 2
fi

# exact match only (one iface per line)
grep -Fxq "$IFACE" "$ALLOW"

case "${ACTION}" in
  down)   exec "$IPBIN" link set "$IFACE" down ;;
  up)     exec "$IPBIN" link set "$IFACE" up ;;
  bounce) "$IPBIN" link set "$IFACE" down && exec "$IPBIN" link set "$IFACE" up ;;
  *) echo "invalid action: ${ACTION}" >&2; exit 3 ;;
esac
SH

chmod 0755 "$WRAPPER"
chown root:root "$WRAPPER"

echo "${SMART_USER} ALL=(root) NOPASSWD: ${WRAPPER}" > "$SUDOERS"
chmod 0440 "$SUDOERS"
visudo -cf "$SUDOERS" >/dev/null

# quick non-interactive test (will bounce the first iface)
first_iface="$(head -n1 "$ALLOW")"
if id -u "$SMART_USER" >/dev/null 2>&1; then
  sudo -u "$SMART_USER" sudo -n "$WRAPPER" "$first_iface" bounce && echo "[OK] wrapper works"
else
  echo "[INFO] user '$SMART_USER' not found; skipping self-test."
fi

echo "[DONE] Safe netctl wrapper installed."
