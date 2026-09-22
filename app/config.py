"""Paths and env for the local Apex Trading Desk."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Prefer TRADING_DATA_DIR (VPS / portable); fall back to box cruzbot path.
_data = (os.environ.get("TRADING_DATA_DIR") or "").strip()
CRUZ_DATA = Path(_data) if _data else Path("/workspace/cruzbot_instance_2/data")
HEARTBEAT_PATH = CRUZ_DATA / "bot_heartbeat.json"
PAPER_BOOK_PATH = CRUZ_DATA / "paper_book_2.json"
CB_AUTO_RESUME_PATH = CRUZ_DATA / "cb_auto_resume.json"
CB_PHD_BYPASS_PATH = CRUZ_DATA / "cb_phd_bypass.json"

# Prefer desk-local .env on VPS; fall back to New Guy env on the box.
_desk_env = ROOT / ".env"
_box_env = Path("/workspace/The-New-Guy-Cruz/.env")
NEW_GUY_ENV = _desk_env if _desk_env.is_file() else _box_env

HOST = os.environ.get("APEX_DESK_HOST", "0.0.0.0")
PORT = int(os.environ.get("APEX_DESK_PORT", "8787"))

HEARTBEAT_FRESH_SEC = 30.0
DEFAULT_MODEL = "grok-4.7"
XAI_CHAT_URL = "https://api.x.ai/v1/chat/completions"

SYSTEM_PROMPT = (
    "You are The New Guy — a high-drive, intelligent Apex Signals assistant. "
    "You help with trading ops awareness, strategy thinking, and crisp decision support. "
    "Be direct, sharp, and useful. No fluff. You do not place trades or claim live control."
)


def load_new_guy_env() -> dict[str, str]:
    """Load key=value pairs from env file without printing secrets."""
    out: dict[str, str] = {}
    if not NEW_GUY_ENV.is_file():
        return out
    try:
        text = NEW_GUY_ENV.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def xai_api_key_present() -> bool:
    env = load_new_guy_env()
    key = (env.get("XAI_API_KEY") or os.environ.get("XAI_API_KEY") or "").strip()
    return bool(key)



# Cloud backup / Connect panel (no secrets — public folder URL + mailto only)
DEFAULT_DRIVE_ATTACK_FOLDER_URL = (
    "https://drive.google.com/drive/folders/1yOA3dDrPIbFRobQpvD3ApsUhl6v8m_5n"
)
DEFAULT_BACKUP_EMAIL = "apexsignalsnow@gmail.com"
DEFAULT_BACKUP_EMAIL_SUBJECT = "Apex desk backup"
DEFAULT_ICLOUD_HELP = (
    "iCloud has no login from this desk. Download the Attack suitcase / briefcase zip "
    "from Google Drive (or chat), then save it into Files → iCloud Drive on your phone or Mac."
)


def connect_settings() -> dict[str, str]:
    """Public Connect panel targets; overridable via env (no secrets)."""
    drive = (
        os.environ.get("DRIVE_ATTACK_FOLDER_URL") or DEFAULT_DRIVE_ATTACK_FOLDER_URL
    ).strip()
    email = (os.environ.get("APEX_BACKUP_EMAIL") or DEFAULT_BACKUP_EMAIL).strip()
    subject = (
        os.environ.get("APEX_BACKUP_EMAIL_SUBJECT") or DEFAULT_BACKUP_EMAIL_SUBJECT
    ).strip()
    help_text = (os.environ.get("APEX_ICLOUD_HELP") or DEFAULT_ICLOUD_HELP).strip()
    return {
        "drive_folder_url": drive,
        "email": email,
        "email_subject": subject,
        "icloud_help": help_text,
    }


def get_xai_settings() -> tuple[str | None, str, float]:
    env = load_new_guy_env()
    key = (env.get("XAI_API_KEY") or os.environ.get("XAI_API_KEY") or "").strip() or None
    model = (
        env.get("XAI_MODEL")
        or os.environ.get("XAI_MODEL")
        or DEFAULT_MODEL
    ).strip() or DEFAULT_MODEL
    try:
        temp = float(env.get("TEMPERATURE") or os.environ.get("TEMPERATURE") or 0.7)
    except ValueError:
        temp = 0.7
    return key, model, temp
