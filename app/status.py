"""Read Cruzbot local status files into desk-friendly JSON."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx

from .config import (
    CB_AUTO_RESUME_PATH,
    CB_PHD_BYPASS_PATH,
    HEARTBEAT_FRESH_SEC,
    HEARTBEAT_PATH,
    PAPER_BOOK_PATH,
    xai_api_key_present,
)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _heartbeat_age_s(hb: dict[str, Any] | None) -> float | None:
    if not hb:
        return None
    unix = hb.get("unix")
    if isinstance(unix, (int, float)):
        return max(0.0, time.time() - float(unix))
    ts = hb.get("ts")
    if isinstance(ts, str):
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return max(0.0, time.time() - dt.timestamp())
        except ValueError:
            return None
    return None


def _fetch_marks(symbols: list[str]) -> dict[str, float]:
    """Best-effort Coinbase public spot prices for unrealized PnL."""
    marks: dict[str, float] = {}
    if not symbols:
        return marks
    try:
        with httpx.Client(timeout=3.0) as client:
            for sym in symbols:
                # Coinbase uses BTC-USD style
                try:
                    r = client.get(f"https://api.coinbase.com/v2/prices/{sym}/spot")
                    if r.status_code != 200:
                        continue
                    amount = r.json().get("data", {}).get("amount")
                    if amount is not None:
                        marks[sym] = float(amount)
                except Exception:
                    continue
    except Exception:
        pass
    return marks


def trading_status() -> dict[str, Any]:
    hb = _read_json(HEARTBEAT_PATH)
    book = _read_json(PAPER_BOOK_PATH) or {}
    cb = _read_json(CB_AUTO_RESUME_PATH)
    bypass = _read_json(CB_PHD_BYPASS_PATH)

    age = _heartbeat_age_s(hb)
    online = age is not None and age < HEARTBEAT_FRESH_SEC

    cash = float(book.get("cash") or 0.0)
    positions_raw = book.get("positions") or {}
    if not isinstance(positions_raw, dict):
        positions_raw = {}

    symbols = []
    for key, pos in positions_raw.items():
        if isinstance(pos, dict):
            symbols.append(str(pos.get("symbol") or key))

    marks = _fetch_marks(symbols)

    positions: list[dict[str, Any]] = []
    positions_value = 0.0
    unrealized = 0.0
    any_mark = False

    for key, pos in positions_raw.items():
        if not isinstance(pos, dict):
            continue
        symbol = str(pos.get("symbol") or key)
        qty = float(pos.get("qty") or 0.0)
        entry = float(pos.get("entry") or 0.0)
        side = str(pos.get("side") or "long")
        mark = marks.get(symbol)
        cost = qty * entry
        row: dict[str, Any] = {
            "symbol": symbol,
            "qty": qty,
            "entry": entry,
            "side": side,
            "sl": pos.get("sl"),
            "tp": pos.get("tp"),
            "opened_at": pos.get("opened_at"),
            "mark": mark,
            "pnl": None,
            "pnl_pct": None,
        }
        if mark is not None:
            any_mark = True
            if side.lower() == "short":
                pnl = (entry - mark) * qty
            else:
                pnl = (mark - entry) * qty
            row["pnl"] = pnl
            row["pnl_pct"] = (pnl / cost * 100.0) if cost else None
            unrealized += pnl
            positions_value += qty * mark
        else:
            positions_value += cost
        positions.append(row)

    equity_estimate = cash + positions_value
    # If no marks, equity is cash + cost basis (labeled in UI)

    consec = int(book.get("consecutive_losses") or 0)
    cb_paused = False
    cb_resume_in_s: float | None = None
    if cb:
        cb_paused = bool(cb.get("paused") or cb.get("cb_auto_resume_armed") or cb.get("cb_active"))
        wall = float(cb.get("cb_auto_resume_at_wall") or 0.0)
        if cb_paused and wall > 0:
            cb_resume_in_s = max(0.0, wall - time.time())

    return {
        "bot_id": "cruz_kraken",
        "name": "Cruz Kraken Trading",
        "online": online,
        "heartbeat_age_s": age,
        "mode": (hb or {}).get("mode") or "UNKNOWN",
        "pid": (hb or {}).get("pid"),
        "dead_man": (hb or {}).get("dead_man"),
        "tg_listener": (hb or {}).get("tg_listener"),
        "tg_last_ok_age_s": (hb or {}).get("tg_last_ok_age_s"),
        "open_positions_hb": (hb or {}).get("open_positions"),
        "cash": cash,
        "equity_estimate": equity_estimate,
        "equity_basis": "mark" if any_mark else "cost",
        "unrealized_pnl": unrealized if any_mark else None,
        "consecutive_losses": consec,
        "cb_paused": cb_paused,
        "cb_resume_in_s": cb_resume_in_s,
        "phd_bypass": bypass,
        "positions": positions,
        "day_start_equity": book.get("day_start_equity"),
        "updated_at": book.get("updated_at") or (hb or {}).get("ts"),
        "heartbeat_ts": (hb or {}).get("ts"),
        "files": {
            "heartbeat": HEARTBEAT_PATH.exists(),
            "paper_book": PAPER_BOOK_PATH.exists(),
            "cb_auto_resume": CB_AUTO_RESUME_PATH.exists(),
            "cb_phd_bypass": CB_PHD_BYPASS_PATH.exists(),
        },
    }


def bots_overview() -> dict[str, Any]:
    status = trading_status()
    chat_ok = xai_api_key_present()
    return {
        "bots": [
            {
                "id": "cruz_kraken",
                "name": "Cruz Kraken Trading",
                "kind": "trading",
                "online": status["online"],
                "mode": status["mode"],
                "detail": f"cash ${status['cash']:.2f}" if status["cash"] is not None else "",
                "href": "/#/desk",
            },
            {
                "id": "new_guy",
                "name": "The New Guy",
                "kind": "chat",
                "online": chat_ok,
                "mode": "CHAT",
                "detail": "ready" if chat_ok else "no API key",
                "href": "/#/newguy",
            },
        ],
        "server_time": time.time(),
    }
