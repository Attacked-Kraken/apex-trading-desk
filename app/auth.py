"""Password gate + signed session cookies + password reset for Apex Trading Desk."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import Request, Response
from starlette.requests import Request as StarletteRequest

from .config import ROOT

log = logging.getLogger("apex_desk.auth")

COOKIE_NAME = "desk_session"
MAX_AGE_SEC = 30 * 24 * 60 * 60  # ~30 days
RESET_TTL_SEC = 30 * 60  # 30 minutes
SECRET_FILE = ROOT / "data" / "desk_auth_secret"
PASSWORD_FILE = ROOT / "data" / "desk_password.txt"
RESET_STATE_FILE = ROOT / "data" / "desk_reset_state.json"
LAST_RESET_FILE = ROOT / "data" / "desk_last_reset.txt"
DEFAULT_AUTH_EMAIL = "apexsignalsnow@gmail.com"
SMTP_ENV_FILE = ROOT / "data" / "desk_smtp.env"


def load_desk_smtp_env() -> None:
    """Load data/desk_smtp.env into os.environ without overriding existing values."""
    if not SMTP_ENV_FILE.is_file():
        return
    try:
        text = SMTP_ENV_FILE.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def auth_user() -> str:
    return (os.environ.get("DESK_AUTH_USER") or "apex").strip() or "apex"


def auth_email() -> str:
    return (
        os.environ.get("DESK_AUTH_EMAIL") or DEFAULT_AUTH_EMAIL
    ).strip() or DEFAULT_AUTH_EMAIL


def auth_password() -> Optional[str]:
    """Prefer local password file (survives reset), else env."""
    try:
        if PASSWORD_FILE.is_file():
            pw = PASSWORD_FILE.read_text(encoding="utf-8").strip()
            if pw:
                return pw
    except OSError:
        pass
    pw = (os.environ.get("DESK_AUTH_PASSWORD") or "").strip()
    return pw or None


def auth_enforced() -> bool:
    """Gate is on only when a password is configured."""
    return auth_password() is not None


def set_password(new_password: str) -> None:
    """Persist new gate password (file 0600 + process env)."""
    new_password = (new_password or "").strip()
    if not new_password:
        raise ValueError("empty password")
    PASSWORD_FILE.parent.mkdir(parents=True, exist_ok=True)
    PASSWORD_FILE.write_text(new_password + "\n", encoding="utf-8")
    os.chmod(PASSWORD_FILE, 0o600)
    os.environ["DESK_AUTH_PASSWORD"] = new_password
    log.info("Desk password updated (file + process env)")


_warned_open = False


def warn_if_open() -> None:
    global _warned_open
    if auth_enforced() or _warned_open:
        return
    _warned_open = True
    log.warning(
        "DESK_AUTH_PASSWORD unset — desk auth gate is OPEN (dev only). "
        "Set DESK_AUTH_PASSWORD on VPS before sharing the tunnel URL."
    )


def _load_or_create_secret() -> bytes:
    env = (os.environ.get("DESK_AUTH_SECRET") or "").strip()
    if env:
        return env.encode("utf-8")
    try:
        if SECRET_FILE.is_file():
            raw = SECRET_FILE.read_bytes().strip()
            if raw:
                return raw
    except OSError:
        pass
    secret = secrets.token_urlsafe(48).encode("utf-8")
    try:
        SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
        SECRET_FILE.write_bytes(secret + b"\n")
        os.chmod(SECRET_FILE, 0o600)
        log.info("Generated DESK_AUTH_SECRET into %s", SECRET_FILE)
    except OSError as e:
        log.warning("Could not write desk_auth_secret (%s); using in-memory secret", e)
    return secret


_SECRET: Optional[bytes] = None


def get_secret() -> bytes:
    global _SECRET
    if _SECRET is None:
        _SECRET = _load_or_create_secret()
    return _SECRET


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def sign_session(username: str, max_age: int = MAX_AGE_SEC) -> str:
    exp = int(time.time()) + int(max_age)
    payload = f"{username}:{exp}".encode("utf-8")
    sig = hmac.new(get_secret(), payload, hashlib.sha256).digest()
    return f"{_b64url(payload)}.{_b64url(sig)}"


def verify_session_token(token: str | None) -> Optional[str]:
    if not token or "." not in token:
        return None
    try:
        payload_b64, sig_b64 = token.rsplit(".", 1)
        payload = _b64url_decode(payload_b64)
        expected = hmac.new(get_secret(), payload, hashlib.sha256).digest()
        got = _b64url_decode(sig_b64)
        if not hmac.compare_digest(expected, got):
            return None
        text = payload.decode("utf-8")
        user, exp_s = text.rsplit(":", 1)
        if int(exp_s) < int(time.time()):
            return None
        if not user:
            return None
        return user
    except (ValueError, OSError, UnicodeDecodeError):
        return None


def password_ok(provided: str) -> bool:
    expected = auth_password()
    if expected is None:
        return True
    return hmac.compare_digest(
        provided.encode("utf-8"),
        expected.encode("utf-8"),
    )


def username_ok(provided: str) -> bool:
    """Username optional on form; if blank, accept. If set, must match."""
    provided = (provided or "").strip()
    if not provided:
        return True
    return hmac.compare_digest(
        provided.encode("utf-8"),
        auth_user().encode("utf-8"),
    )


def recovery_email_ok(provided: str) -> bool:
    provided = (provided or "").strip().lower()
    expected = auth_email().strip().lower()
    return hmac.compare_digest(
        provided.encode("utf-8"),
        expected.encode("utf-8"),
    )


def request_is_https(request: Request | StarletteRequest) -> bool:
    if request.url.scheme == "https":
        return True
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return proto == "https"


def set_session_cookie(response: Response, request: Request, username: str) -> None:
    token = sign_session(username or auth_user())
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=MAX_AGE_SEC,
        expires=MAX_AGE_SEC,
        path="/",
        httponly=True,
        samesite="lax",
        secure=request_is_https(request),
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        key=COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=request_is_https(request),
    )


def session_user(request: Request) -> Optional[str]:
    return verify_session_token(request.cookies.get(COOKIE_NAME))


def is_public_path(path: str) -> bool:
    if path in ("/login", "/logout", "/forgot", "/reset"):
        return True
    if path == "/api/health":
        return True
    if path in ("/favicon.ico", "/robots.txt"):
        return True
    return False


def _hash_token(token: str) -> str:
    return hmac.new(get_secret(), token.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_reset_token() -> tuple[str, int]:
    """Create one-time reset token; returns (raw_token, exp_unix)."""
    raw = secrets.token_urlsafe(32)
    exp = int(time.time()) + RESET_TTL_SEC
    state = {"token_hash": _hash_token(raw), "exp": exp}
    RESET_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESET_STATE_FILE.write_text(json.dumps(state) + "\n", encoding="utf-8")
    os.chmod(RESET_STATE_FILE, 0o600)
    return raw, exp


def consume_reset_token(raw: str) -> bool:
    """Validate and invalidate one-time reset token."""
    raw = (raw or "").strip()
    if not raw or not RESET_STATE_FILE.is_file():
        return False
    try:
        state = json.loads(RESET_STATE_FILE.read_text(encoding="utf-8"))
        exp = int(state.get("exp") or 0)
        stored = str(state.get("token_hash") or "")
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    if exp < int(time.time()):
        try:
            RESET_STATE_FILE.unlink(missing_ok=True)
        except OSError:
            pass
        return False
    ok = hmac.compare_digest(stored, _hash_token(raw))
    if ok:
        try:
            RESET_STATE_FILE.unlink(missing_ok=True)
        except OSError:
            pass
    return ok


def public_base_url(request: Request) -> str:
    """Build absolute origin, honoring Cloudflare/proxy headers."""
    proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    if not proto:
        proto = request.url.scheme or "http"
    if not host:
        host = request.url.netloc
    return f"{proto}://{host}".rstrip("/")


def smtp_configured() -> bool:
    load_desk_smtp_env()
    host = (os.environ.get("DESK_SMTP_HOST") or "").strip()
    user = (os.environ.get("DESK_SMTP_USER") or "").strip()
    password = (os.environ.get("DESK_SMTP_PASSWORD") or "").strip().replace(" ", "")
    return bool(host and user and password)


def send_reset_email(to_addr: str, reset_url: str) -> tuple[bool, str]:
    """
    Send reset link via DESK_SMTP_* (Gmail-friendly).
    Returns (ok, detail). Never logs the SMTP password.
    """
    load_desk_smtp_env()
    host = (os.environ.get("DESK_SMTP_HOST") or "smtp.gmail.com").strip()
    try:
        port = int((os.environ.get("DESK_SMTP_PORT") or "587").strip() or "587")
    except ValueError:
        port = 587
    user = (os.environ.get("DESK_SMTP_USER") or "").strip()
    # Gmail app passwords are often shown with spaces — strip them
    password = (os.environ.get("DESK_SMTP_PASSWORD") or "").strip().replace(" ", "")
    from_addr = (os.environ.get("DESK_SMTP_FROM") or user or auth_email()).strip()
    if not (host and user and password):
        return False, "SMTP not configured"

    msg = EmailMessage()
    msg["Subject"] = "Apex Trading Desk — password reset"
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.set_content(
        "Apex Trading Desk password reset\n\n"
        f"Open this link within {RESET_TTL_SEC // 60} minutes to set a new password:\n\n"
        f"{reset_url}\n\n"
        "If you did not request this, ignore this email.\n"
    )

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            if port != 465:
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(msg)
        return True, "sent"
    except Exception as e:  # noqa: BLE001 — surface class name only
        log.warning("SMTP send failed: %s", type(e).__name__)
        return False, type(e).__name__


def write_last_reset_link(reset_url: str, emailed: bool, note: str = "") -> None:
    """Ops fallback when SMTP is missing or failed."""
    LAST_RESET_FILE.parent.mkdir(parents=True, exist_ok=True)
    body = (
        f"issued_at={time.strftime('%Y-%m-%dT%H:%M:%S%z')}\n"
        f"emailed={emailed}\n"
        f"to={auth_email()}\n"
        f"note={note}\n"
        f"url={reset_url}\n"
    )
    LAST_RESET_FILE.write_text(body, encoding="utf-8")
    os.chmod(LAST_RESET_FILE, 0o600)
    log.warning(
        "Password reset link written to %s (emailed=%s)",
        LAST_RESET_FILE,
        emailed,
    )


def build_reset_url(request: Request, token: str) -> str:
    return f"{public_base_url(request)}/reset?token={quote(token, safe='')}"


def start_password_reset(request: Request) -> dict[str, object]:
    """
    Issue token, try SMTP to DESK_AUTH_EMAIL, always write ops file if email fails.
    Returns non-sensitive status for UI.
    """
    token, exp = issue_reset_token()
    reset_url = build_reset_url(request, token)
    emailed = False
    note = ""
    if smtp_configured():
        ok, detail = send_reset_email(auth_email(), reset_url)
        emailed = ok
        note = detail if not ok else "smtp_ok"
        if not ok:
            write_last_reset_link(reset_url, emailed=False, note=f"smtp_fail:{detail}")
        else:
            # Still keep a copy for ops audit (no extra secret beyond the link)
            write_last_reset_link(reset_url, emailed=True, note="smtp_ok")
    else:
        note = "smtp_missing"
        write_last_reset_link(reset_url, emailed=False, note="smtp_missing")
    return {
        "emailed": emailed,
        "exp": exp,
        "smtp_configured": smtp_configured(),
        "note": note,
    }
