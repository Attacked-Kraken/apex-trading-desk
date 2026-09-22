#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
HOST="${APEX_DESK_HOST:-0.0.0.0}"
PORT="${APEX_DESK_PORT:-8787}"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

# Stop any previous desk on this port (best-effort)
if command -v fuser >/dev/null 2>&1; then
  fuser -k "${PORT}/tcp" >/dev/null 2>&1 || true
fi

exec uvicorn app.main:app --host "$HOST" --port "$PORT"
