#!/usr/bin/env bash
# Keep sync_status_to_vps.sh alive forever.
LOG=/workspace/apex-trading-desk/sync_watch.log
SYNC=/workspace/apex-trading-desk/scripts/sync_status_to_vps.sh
log() { echo "$(date -Is) $*" >> "$LOG"; }
log "watchdog starting pid=$$"
while true; do
  if ! pgrep -f '/scripts/sync_status_to_vps.sh' >/dev/null 2>&1; then
    log "sync missing — restarting"
    nohup bash "$SYNC" >> /workspace/apex-trading-desk/sync_vps.log 2>&1 &
    log "sync restarted pid=$!"
  fi
  sleep 15
done
