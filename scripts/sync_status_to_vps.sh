#!/usr/bin/env bash
# Auto-reconnect: never exits on SSH/SCP failure; backs off then retries forever.
KEY=/home/box/.ssh/apex_desk_ed25519
HOST=root@159.89.91.6
SRC=/workspace/cruzbot_instance_2/data
DST=/opt/apex-trading-desk/data
LOG=/workspace/apex-trading-desk/sync_vps.log
FILES=(bot_heartbeat.json paper_book_2.json cb_auto_resume.json cb_phd_bypass.json)
SSH_OPTS=(-i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -o BatchMode=yes)
fail=0
mkdir -p "$(dirname "$LOG")"
log() { echo "$(date -Is) $*" >> "$LOG"; }
log "sync starting pid=$$"
while true; do
  ok=1
  for f in "${FILES[@]}"; do
    if [[ -f "$SRC/$f" ]]; then
      if ! scp "${SSH_OPTS[@]}" -q "$SRC/$f" "$HOST:$DST/$f" 2>>"$LOG"; then
        ok=0
      fi
    fi
  done
  if [[ $ok -eq 1 ]]; then
    fail=0
    sleep 3
  else
    fail=$((fail + 1))
    # backoff 5s, 10s, 20s ... cap 60s
    delay=$(( fail < 5 ? fail * 5 : 60 ))
    log "scp failed streak=$fail; reconnect in ${delay}s"
    sleep "$delay"
  fi
done
