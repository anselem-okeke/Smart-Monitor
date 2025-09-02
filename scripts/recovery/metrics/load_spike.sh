#!/bin/bash
# load_spike.sh — simulate high load average safely, with live WARN/CRIT display
# Usage:
#   ./load_spike.sh <multiplier> <seconds> [warn_mult] [crit_mult]
# Examples:
#   ./load_spike.sh 2 60
#   ./load_spike.sh 3 90 2.0 4.0
# kill the process
#    sudo pkill -KILL -f load_spike.sh

set -euo pipefail

MULT=${1:-2}            # target workers = MULT × cores
DURATION=${2:-60}       # total run seconds
WARN_MULT=${3:-2.0}     # warn if load1 >= WARN_MULT × cores
CRIT_MULT=${4:-4.0}     # crit if load1 >= CRIT_MULT × cores
MAX_MULT=5              # safety cap
CORES=$(nproc)

# Safety cap
if [ "$MULT" -gt "$MAX_MULT" ]; then
  echo "[SAFETY] Multiplier $MULT capped to $MAX_MULT"
  MULT=$MAX_MULT
fi

PROCS=$((CORES * MULT))
WARN_THR=$(awk -v c="$CORES" -v m="$WARN_MULT" 'BEGIN{printf "%.2f", c*m}')
CRIT_THR=$(awk -v c="$CORES" -v m="$CRIT_MULT" 'BEGIN{printf "%.2f", c*m}')

echo "[INFO] Cores=${CORES}  Workers=${PROCS}  Duration=${DURATION}s"
echo "[INFO] Thresholds: warn=${WARN_THR} (=${WARN_MULT}×cores)  crit=${CRIT_THR} (=${CRIT_MULT}×cores)"
echo "[INFO] Initial load: $(uptime)"

# Busy worker
busy_loop() { while :; do :; done; }

# Cleanup on exit/CTRL-C
PIDS=""
cleanup() {
  echo "[INFO] Stopping load spike..."
  # shellcheck disable=SC2015
  [ -n "$PIDS" ] && kill "$PIDS" 2>/dev/null || true
  # shellcheck disable=SC2015
  [ -n "$PIDS" ] && wait "$PIDS" 2>/dev/null || true
  echo "[INFO] Final load: $(uptime)"
}
trap cleanup EXIT INT TERM

# Launch workers
# shellcheck disable=SC2034
for i in $(seq 1 "$PROCS"); do
  busy_loop & PIDS="$PIDS $!"
done

# Live progress (every 5s)
START=$(date +%s)
while [ $(( $(date +%s) - START )) -lt "$DURATION" ]; do
  L1=$(awk '{print $1}' /proc/loadavg)
  # Compare floats:  (L1 >= WARN_THR)? (L1 >= CRIT_THR)?
  GE_WARN=$(awk -v a="$L1" -v b="$WARN_THR" 'BEGIN{print (a>=b)?"1":"0"}')
  GE_CRIT=$(awk -v a="$L1" -v b="$CRIT_THR" 'BEGIN{print (a>=b)?"1":"0"}')
  STATUS=""
  # shellcheck disable=SC2015
  [ "$GE_CRIT" = "1" ] && STATUS="CRIT" || { [ "$GE_WARN" = "1" ] && STATUS="WARN"; }
  printf "[LIVE] load1=%s  thresholds{warn=%s,crit=%s}  status=%s  %s\n" \
         "$L1" "$WARN_THR" "$CRIT_THR" "${STATUS:-OK}" "$(uptime)"
  sleep 5
done

# Cleanup via trap
exit 0
