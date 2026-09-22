# Apex Trading Desk (local)

Read-only trading office UI for Cruz Kraken status + The New Guy chat. Built to run on this box while Origin/cloud versions are built elsewhere.

## Features

1. **Office floor** — cards for Cruz Kraken Trading and The New Guy  
2. **Trading desk** — mode, cash, equity estimate, open positions (+ mark PnL when public spots resolve), consecutive losses, CB paused?, Telegram listener, timestamps  
3. **New Guy** — multi-turn chat (`POST /api/chat`) using `XAI_API_KEY` from `/workspace/The-New-Guy-Cruz/.env` (default model `grok-4.7`)

No live trading controls. Secrets stay out of git (`.env` is gitignored; key is read from The New Guy path only).

## Data sources (box-local)

| File | Role |
|------|------|
| `/workspace/cruzbot_instance_2/data/bot_heartbeat.json` | Online if updated &lt; 30s; mode, tg_listener |
| `/workspace/cruzbot_instance_2/data/paper_book_2.json` | Cash, positions, consecutive_losses |
| `/workspace/cruzbot_instance_2/data/cb_auto_resume.json` | Circuit-breaker pause (optional) |
| `/workspace/cruzbot_instance_2/data/cb_phd_bypass.json` | Optional PHD bypass flag |
| `/workspace/The-New-Guy-Cruz/.env` | `XAI_API_KEY`, optional `XAI_MODEL` / `TEMPERATURE` |

## Start

```bash
cd /workspace/apex-trading-desk
./start.sh
```

Or manually:

```bash
cd /workspace/apex-trading-desk
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8787
```

## URL

- UI: **http://0.0.0.0:8787/** (or `http://127.0.0.1:8787/`)
- Health: `GET /api/health`
- Bots: `GET /api/bots`
- Trading status: `GET /api/trading/status`
- Chat: `POST /api/chat` with `{ "messages": [ {"role":"user","content":"..."} ], "stream": false }`

## Env

| Variable | Default | Notes |
|----------|---------|-------|
| `APEX_DESK_HOST` | `0.0.0.0` | Bind host |
| `APEX_DESK_PORT` | `8787` | Bind port |
| `XAI_API_KEY` | from New Guy `.env` | Never commit; never log |
| `XAI_MODEL` | `grok-4.7` | Override model |
| `TEMPERATURE` | `0.7` | Chat temperature |

## Notes

- Equity estimate uses Coinbase public spot marks when available; otherwise cash + cost basis.
- Chat key detection is reported as present/absent only — the key value is never logged.
