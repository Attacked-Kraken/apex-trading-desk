# Cruz Kraken Paper Bot — Cutover to DigitalOcean (apex-trading-desk)

**Status:** PREPARE ONLY — do not execute start/stop until operator approval.  
**Prepared:** 2026-09-22 (America/Chicago)  
**Source (box):** `/workspace/cruzbot_instance_2` — live PID historically `542996` (` .venv/bin/python -u main.py`)  
**Telegram:** `@AlphaPulseNowAlerts_bot` — **ONE** `getUpdates` poller only (never two)  
**Target VPS:** `159.89.91.6` (`apex-trading-desk`)  
**SSH key (box):** `/home/box/.ssh/apex_desk_ed25519`  
**Staged kit:** `/workspace/rebuild-kits/cruz-vps-stage-20260922-1656.tgz`

---

## 0. Hard rules

1. **Never** start `apex-cruz-paper.service` (or any second `main.py`) while the box bot is still polling Telegram.
2. **Never** paste real `.env` secrets into chat, tickets, or this runbook.
3. Cutover order is fixed: **backup → rsync code → copy data → install unit (disabled) → scp `.env` (0600) → start VPS → verify HB+TG → stop box → verify no 409 → point desk at local data → stop sync**.
4. Paper bot listens on **no inbound ports**; only outbound HTTPS (Kraken public + Telegram). Desk stays on `127.0.0.1:8787`.

---

## 1. Inventory — what must land on the VPS

| Item | VPS path | Notes |
|------|----------|--------|
| Application code | `/opt/cruz-paper/` | `main.py`, `trading_bot/`, `scripts/`, `tests/`, docs |
| Dependencies | `/opt/cruz-paper/requirements.txt` + `/opt/cruz-paper/.venv/` | **Rebuild on VPS** (do not copy box `.venv`; box is Python 3.13, VPS is 3.12.3) |
| Runtime data | `/opt/cruz-paper/data/` | `paper_book_2.json`, `bot_heartbeat.json`, DBs, formula memory, etc. Copy **fresh** at cutover (not only stage snapshot) |
| Secrets | `/etc/apex-cruz-paper.env` **and** `/opt/cruz-paper/.env` | Identical content; mode **0600**. App uses dotenv from cwd; systemd `EnvironmentFile` injects process env. |
| Example env only | `/opt/cruz-paper/.env.example` | Placeholders; safe in tarball |
| systemd unit | `/etc/systemd/system/apex-cruz-paper.service` | Template below — **no secrets in unit** |
| Desk data pointer | `TRADING_DATA_DIR=/opt/cruz-paper/data` | After cutover, desk reads local cruz data; box sync scripts stop |

### Explicitly do **not** ship in the code tarball

- `.venv/`
- `.env` / `.env.bak*` (scp later, approved step)
- Large logs (`data/paper_bot.log`, `data/paper_loop.log`) — optional archive separately
- `.git/`

### Live secrets check (box, names only)

- `.env` **exists** at `/workspace/cruzbot_instance_2/.env` (mode `600`, size ~2822 bytes).
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`: present (non-placeholder).
- `KRAKEN_API_KEY` / `KRAKEN_API_SECRET`: still **placeholders** (OK for public paper path; private signed calls incomplete — matches heartbeat `dead_man`).
- `PAPER_TRADING_MODE`: set.

---

## 2. Scrubbed systemd unit template

Install as `/etc/systemd/system/apex-cruz-paper.service` (also in stage kit under `systemd/`):

```ini
[Unit]
Description=Apex Cruz Kraken Paper Bot (ONE Telegram getUpdates poller)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/cruz-paper
EnvironmentFile=/etc/apex-cruz-paper.env
ExecStart=/opt/cruz-paper/.venv/bin/python -u /opt/cruz-paper/main.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
MemoryMax=350M

[Install]
WantedBy=multi-user.target
```

**Do not** `systemctl enable --now` until Step 7+.

---

## 3. Ordered cutover runbook (execute only when approved)

SSH helper (from box):

```bash
KEY=/home/box/.ssh/apex_desk_ed25519
SSH=(ssh -i "$KEY" -o StrictHostKeyChecking=accept-new root@159.89.91.6)
SCP=(scp -i "$KEY" -o StrictHostKeyChecking=accept-new)
```

### Step A — Backup (box + VPS)

```bash
# Box: snapshot live tree (exclude .venv to save space; include .env in local backup only)
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p /workspace/rebuild-kits/cruz-pre-cutover-$STAMP
tar -C /workspace -czf /workspace/rebuild-kits/cruz-pre-cutover-$STAMP/cruzbot_instance_2-FULL.tgz \
  --exclude='cruzbot_instance_2/.venv' \
  cruzbot_instance_2
# Keep FULL tarball local on box; do not upload .env-bearing archive to chat/Drive casually.

# VPS: snapshot desk + any existing cruz path
"${SSH[@]}" 'mkdir -p /root/backups && tar -C /opt -czf /root/backups/apex-trading-desk-pre-cruz-'$STAMP'.tgz apex-trading-desk && df -h /'
```

### Step B — Rsync / extract code on VPS

```bash
# Option 1: staged sanitized tarball (no .env)
"${SCP[@]}" /workspace/rebuild-kits/cruz-vps-stage-20260922-1656.tgz root@159.89.91.6:/tmp/
"${SSH[@]}" 'mkdir -p /opt && tar -C /opt -xzf /tmp/cruz-vps-stage-20260922-1656.tgz \
  && rm -rf /opt/cruz-paper \
  && mv /opt/cruz-vps-stage-20260922-1656/cruz-paper /opt/cruz-paper \
  && cp /opt/cruz-vps-stage-20260922-1656/systemd/apex-cruz-paper.service /etc/systemd/system/ \
  && rm -rf /opt/cruz-vps-stage-20260922-1656 /tmp/cruz-vps-stage-20260922-1656.tgz'

# Option 2 (fresher code): rsync from box excluding secrets/venv
rsync -az --delete \
  -e "ssh -i $KEY -o StrictHostKeyChecking=accept-new" \
  --exclude '.venv/' --exclude '.env' --exclude '.env.bak*' \
  --exclude '.git/' --exclude '__pycache__/' --exclude '.pytest_cache/' \
  --exclude 'data/paper_bot.log' --exclude 'data/paper_loop.log' \
  /workspace/cruzbot_instance_2/ root@159.89.91.6:/opt/cruz-paper/
```

### Step C — Create venv on VPS (Python 3.12)

```bash
"${SSH[@]}" 'cd /opt/cruz-paper && python3 -m venv .venv \
  && .venv/bin/pip install -U pip \
  && .venv/bin/pip install -r requirements.txt \
  && .venv/bin/python -c "import pydantic, pandas, httpx; print(\"imports_ok\")"'
```

### Step D — Copy live data carefully (box still running OK)

Prefer a quiet moment (or accept that `paper_book_2.json` / heartbeat may race by seconds).

```bash
# Ensure data dir exists; sync state files (not multi-GB logs)
"${SSH[@]}" 'mkdir -p /opt/cruz-paper/data/backups_2'
rsync -az -e "ssh -i $KEY -o StrictHostKeyChecking=accept-new" \
  --exclude 'paper_bot.log' --exclude 'paper_loop.log' \
  /workspace/cruzbot_instance_2/data/ root@159.89.91.6:/opt/cruz-paper/data/
```

### Step E — Install systemd unit (disabled) + **approved** secret scp

```bash
"${SSH[@]}" 'install -m 644 /etc/systemd/system/apex-cruz-paper.service /etc/systemd/system/apex-cruz-paper.service
  systemctl daemon-reload
  systemctl disable apex-cruz-paper.service || true
  systemctl status apex-cruz-paper.service --no-pager || true'

# === APPROVED SECRETS STEP (do not run in prepare phase) ===
# Live .env must be scp'd with 0600. Never echo/cat contents.
"${SCP[@]}" /workspace/cruzbot_instance_2/.env root@159.89.91.6:/etc/apex-cruz-paper.env
"${SSH[@]}" 'chmod 600 /etc/apex-cruz-paper.env && chown root:root /etc/apex-cruz-paper.env \
  && cp -a /etc/apex-cruz-paper.env /opt/cruz-paper/.env \
  && chmod 600 /opt/cruz-paper/.env \
  && # verify keys exist without printing values:
  python3 - <<"PY"
from pathlib import Path
p=Path("/etc/apex-cruz-paper.env")
keys={"TELEGRAM_BOT_TOKEN","TELEGRAM_CHAT_ID","PAPER_TRADING_MODE","BROKER"}
found={k:False for k in keys}
for line in p.read_text().splitlines():
    if "=" in line and not line.strip().startswith("#"):
        k=line.split("=",1)[0].strip()
        if k in found: found[k]=True
print({k:("present" if v else "MISSING") for k,v in found.items()})
PY'
```

### Step F — Point desk at local cruz data (still before starting cruz, optional prep)

Append to desk env (do **not** print file):

```bash
"${SSH[@]}" 'grep -q "^TRADING_DATA_DIR=" /etc/apex-trading-desk/desk.env 2>/dev/null \
  || echo "TRADING_DATA_DIR=/opt/cruz-paper/data" >> /etc/apex-trading-desk/desk.env
  # Also ensure /opt/apex-trading-desk/.env or Environment= line if desk.env not loaded for that var
  systemctl daemon-reload'
# Restart desk only after cruz data path is populated (can wait until after Step H).
```

### Step G — START on VPS (only after secrets in place) → verify heartbeat + TG

**CRITICAL:** Box bot must still be the **only** poller until Step H. So either:

- **Preferred:** stop box first (Step H-lite), then start VPS; or  
- **Never** start VPS while box `main.py` is alive (will 409).

Recommended sequence (atomic ownership flip):

```bash
# G0. Confirm box is the only poller right now
pgrep -af 'cruzbot_instance_2|.venv/bin/python -u main.py' || true

# G1. STOP box bot FIRST (short Telegram gap)
kill 542996   # or: pkill -f '/workspace/cruzbot_instance_2/.venv/bin/python -u main.py'
sleep 3
kill -0 542996 2>/dev/null && kill -9 542996 || true
# Confirm dead
pgrep -af 'cruzbot_instance_2.*main.py' && echo "ABORT: box still running" || echo "box stopped"

# G2. Final data rsync (catch last paper_book writes)
rsync -az -e "ssh -i $KEY" --exclude 'paper_bot.log' --exclude 'paper_loop.log' \
  /workspace/cruzbot_instance_2/data/ root@159.89.91.6:/opt/cruz-paper/data/

# G3. START VPS unit
"${SSH[@]}" 'systemctl enable --now apex-cruz-paper.service && sleep 2 && systemctl is-active apex-cruz-paper.service'

# G4. Verify heartbeat fresh on VPS
"${SSH[@]}" 'python3 - <<"PY"
import json,time
from pathlib import Path
p=Path("/opt/cruz-paper/data/bot_heartbeat.json")
d=json.loads(p.read_text())
age=time.time()-float(d.get("unix") or 0)
print({"mode":d.get("mode"),"pid":d.get("pid"),"tg_listener":d.get("tg_listener"),"age_s":round(age,1),"open":d.get("open_positions")})
assert age < 60, "heartbeat stale"
assert d.get("tg_listener") in ("ok","OK",True) or str(d.get("tg_listener")).lower()=="ok"
print("HEARTBEAT_OK")
PY'

# G5. Telegram: send /status to @AlphaPulseNowAlerts_bot — expect PAPER status, no Conflict errors in journal
"${SSH[@]}" 'journalctl -u apex-cruz-paper.service -n 80 --no-pager | grep -iE "409|Conflict|getUpdates|error" || echo "no 409 in recent journal"'
```

### Step H — Confirm box remains stopped + no dual poller

```bash
pgrep -af 'cruzbot_instance_2.*main.py' || echo "box clear"
"${SSH[@]}" 'systemctl is-active apex-cruz-paper.service; pgrep -af "/opt/cruz-paper/.venv/bin/python"'
```

### Step I — Verify no Telegram 409

- `/status` works once.
- VPS journal has **no** `Conflict: terminated by other getUpdates request`.
- If 409 appears: **immediately** `systemctl stop apex-cruz-paper` and hunt any other poller (box process, second unit, old screen/tmux).

### Step J — Desk reads local data; stop box sync

```bash
# Restart desk so TRADING_DATA_DIR takes effect
"${SSH[@]}" 'systemctl restart apex-trading-desk.service && systemctl is-active apex-trading-desk.service'

# On box: stop sync_status_to_vps.sh / watch_sync.sh loops
pkill -f 'sync_status_to_vps.sh' || true
pkill -f 'watch_sync.sh' || true
# Confirm
pgrep -af 'sync_status_to_vps|watch_sync' || echo "sync stopped"
```

Desk should show cruz heartbeat/book from `/opt/cruz-paper/data` without SCP sync.

### Step K — Post-cutover hygiene

- Leave box tree intact as rollback for 24–48h.
- Do **not** restart box `main.py` unless VPS unit is stopped first.
- Optional: truncate or rotate old `paper_bot.log` on box only (not required for VPS).

---

## 4. Rollback (if VPS fails)

```bash
"${SSH[@]}" 'systemctl disable --now apex-cruz-paper.service'
# On box:
cd /workspace/cruzbot_instance_2 && bash scripts/start_paper.sh
# Verify single poller + /status; re-enable sync scripts if desired
```

---

## 5. VPS resource snapshot (read-only check at prepare time)

| Resource | Value |
|----------|--------|
| Host | `apex-trading-desk` |
| RAM | 961 MiB total; ~594 MiB available; **no swap** |
| Disk `/` | 24G total, ~21G avail (~11% used) |
| Python | **3.12.3** (`python3-venv` present, pip 24.0) |
| Existing services | `apex-trading-desk` (~52 MiB RSS), `apex-desk-tunnel` (cloudflared), ssh |
| Listening | `:22`, desk `127.0.0.1:8787` only |

**Headroom:** Disk OK. RAM tight on 1 GiB droplet with no swap — unit sets `MemoryMax=350M`; cruz paper historically ~60 MiB RSS on box. Soft blocker: consider 1–2 GiB swapfile before cutover if desk+bot+cloudflared spike.

---

## 6. Blockers / watch-outs (prepare-time)

| Item | Severity | Note |
|------|----------|------|
| Dual Telegram poller | **Critical** | Never start VPS unit while box PID alive |
| Python 3.13 (box) vs 3.12.3 (VPS) | Low | Rebuild venv on VPS; pin via requirements |
| No swap on VPS | Medium | 961 MiB shared with desk+tunnel; add swapfile recommended |
| Kraken key placeholders | Info | Paper public path OK; private/dead-man incomplete |
| Live `.env` not in tarball | Expected | Must scp with 0600 in approved Step E |
| Desk `TRADING_DATA_DIR` | Required post-cutover | Default still box path `/workspace/...` which does not exist on VPS |
| Ports | None | Bot needs no inbound ports |

---

## 7. Prepare-phase checklist (this document’s scope)

- [x] Inventory code / requirements / data / unit template
- [x] Sanitized tarball staged (no `.venv`, no `.env`)
- [x] VPS `free -h` / `df -h` checked via SSH
- [x] Confirmed live `.env` exists locally (secrets not reported)
- [x] Live paper bot **left running** (PID ~542996) — **not stopped**
- [ ] Operator approval to execute Steps A–K
- [ ] Approved scp of `.env` to VPS
- [ ] Actual stop box → start VPS → verify no 409
