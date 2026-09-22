"""Apex Trading Desk — FastAPI entrypoint."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from .auth import (
    auth_email,
    auth_enforced,
    auth_user,
    clear_session_cookie,
    consume_reset_token,
    is_public_path,
    password_ok,
    recovery_email_ok,
    session_user,
    set_password,
    set_session_cookie,
    smtp_configured,
    start_password_reset,
    username_ok,
    warn_if_open,
)
from .chat import chat_completion
from .config import connect_settings, xai_api_key_present
from .status import bots_overview, trading_status

STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Apex Trading Desk", version="1.0.0")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list)
    stream: bool = False


class AuthGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        warn_if_open()
        path = request.url.path
        if is_public_path(path):
            return await call_next(request)
        if not auth_enforced():
            return await call_next(request)
        if session_user(request):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return RedirectResponse(url="/login", status_code=303)


app.add_middleware(AuthGateMiddleware)


def _esc(s: str) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


_AUTH_CSS = """
    :root {
      --bg: #0b0f14;
      --panel: #161d28;
      --border: #2a3545;
      --text: #e8eef7;
      --muted: #8b9bb0;
      --accent: #3d9cf0;
      --danger: #f07178;
      --good: #3dd68c;
      --shadow: 0 12px 40px rgba(0, 0, 0, 0.45);
      --sans: "Inter", "Segoe UI", system-ui, -apple-system, sans-serif;
    }
    * { box-sizing: border-box; }
    html, body {
      margin: 0; min-height: 100%;
      background: radial-gradient(1200px 600px at 10% -10%, #152033 0%, transparent 55%),
                  radial-gradient(900px 500px at 90% 0%, #13241f 0%, transparent 50%),
                  var(--bg);
      color: var(--text); font-family: var(--sans);
    }
    .wrap {
      max-width: 400px; margin: 0 auto; padding: 48px 20px;
      min-height: 100vh; display: flex; flex-direction: column;
      justify-content: center;
    }
    .card {
      background: linear-gradient(180deg, #1c2533, var(--panel));
      border: 1px solid var(--border); border-radius: 16px;
      padding: 28px 22px; box-shadow: var(--shadow);
    }
    .brand { display: flex; align-items: center; gap: 12px; margin-bottom: 22px; }
    .logo {
      width: 40px; height: 40px; border-radius: 10px;
      background: linear-gradient(145deg, #2d6cdf, #1a9c7a);
      display: grid; place-items: center; font-weight: 800;
      box-shadow: var(--shadow);
    }
    h1 { margin: 0; font-size: 1.15rem; }
    .sub { margin: 2px 0 0; color: var(--muted); font-size: 0.8rem; }
    label { display: block; font-size: 0.78rem; color: var(--muted);
      text-transform: uppercase; letter-spacing: 0.04em; margin: 14px 0 6px; }
    input {
      width: 100%; background: #0f151e; border: 1px solid var(--border);
      border-radius: 12px; color: var(--text); padding: 12px 14px;
      font-size: 1rem; outline: none;
    }
    input:focus { border-color: var(--accent); }
    button {
      margin-top: 20px; width: 100%;
      background: linear-gradient(145deg, #2d6cdf, #1f8f6e);
      border: none; color: white; font-weight: 700; font-size: 0.95rem;
      border-radius: 12px; padding: 14px; cursor: pointer;
    }
    button:hover { filter: brightness(1.06); }
    .err {
      margin: 0 0 12px; color: var(--danger); font-size: 0.88rem;
      background: #2a1618; border: 1px solid #5a3036;
      border-radius: 10px; padding: 10px 12px;
    }
    .ok {
      margin: 0 0 12px; color: var(--good); font-size: 0.88rem;
      background: #13241f; border: 1px solid #245743;
      border-radius: 10px; padding: 10px 12px;
    }
    .hint { margin-top: 16px; color: var(--muted); font-size: 0.75rem; text-align: center; }
    .hint a { color: var(--accent); text-decoration: none; }
    .hint a:hover { text-decoration: underline; }
    .links { margin-top: 14px; text-align: center; font-size: 0.85rem; }
    .links a { color: var(--accent); text-decoration: none; }
    .links a:hover { text-decoration: underline; }
"""


def _shell(title: str, body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{_esc(title)} · Apex Trading Desk</title>
  <style>{_AUTH_CSS}</style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div class="brand">
        <div class="logo">A</div>
        <div>
          <h1>Apex Trading Desk</h1>
          <p class="sub">Private access · Apex Signals</p>
        </div>
      </div>
      {body}
    </div>
  </div>
</body>
</html>"""


def _login_page(error: str | None = None, username: str = "") -> str:
    err_html = f'<p class="err">{_esc(error)}</p>' if error else ""
    user_val = _esc(username or auth_user())
    body = f"""
      {err_html}
      <form method="post" action="/login" autocomplete="on">
        <label for="username">Username</label>
        <input id="username" name="username" type="text" value="{user_val}"
               autocomplete="username" placeholder="apex" />
        <label for="password">Password</label>
        <input id="password" name="password" type="password" required
               autocomplete="current-password" autofocus placeholder="••••••••" />
        <button type="submit">Unlock desk</button>
      </form>
      <p class="links"><a href="/forgot">Forgot password?</a></p>
      <p class="hint">Session cookie · ~30 days · HttpOnly</p>
    """
    return _shell("Login", body)


def _forgot_page(error: str | None = None, ok: str | None = None) -> str:
    err_html = f'<p class="err">{_esc(error)}</p>' if error else ""
    ok_html = f'<p class="ok">{_esc(ok)}</p>' if ok else ""
    email_hint = _esc(auth_email())
    body = f"""
      {err_html}{ok_html}
      <p class="sub" style="margin-bottom:12px">
        Enter the recovery email to receive a short-lived reset link.
      </p>
      <form method="post" action="/forgot" autocomplete="on">
        <label for="email">Recovery email</label>
        <input id="email" name="email" type="email" required
               autocomplete="email" autofocus placeholder="{email_hint}" />
        <button type="submit">Send reset link</button>
      </form>
      <p class="links"><a href="/login">Back to login</a></p>
      <p class="hint">Link expires in 30 minutes · sent only to the configured recovery address</p>
    """
    return _shell("Forgot password", body)


def _reset_page(token: str, error: str | None = None) -> str:
    err_html = f'<p class="err">{_esc(error)}</p>' if error else ""
    tok = _esc(token)
    body = f"""
      {err_html}
      <p class="sub" style="margin-bottom:12px">Choose a new desk password.</p>
      <form method="post" action="/reset" autocomplete="on">
        <input type="hidden" name="token" value="{tok}" />
        <label for="password">New password</label>
        <input id="password" name="password" type="password" required minlength="8"
               autocomplete="new-password" autofocus />
        <label for="password2">Confirm password</label>
        <input id="password2" name="password2" type="password" required minlength="8"
               autocomplete="new-password" />
        <button type="submit">Set new password</button>
      </form>
      <p class="links"><a href="/login">Back to login</a></p>
    """
    return _shell("Reset password", body)


@app.get("/login", response_model=None)
def login_get(request: Request):
    if auth_enforced() and session_user(request):
        return RedirectResponse(url="/", status_code=303)
    if not auth_enforced():
        return RedirectResponse(url="/", status_code=303)
    return HTMLResponse(_login_page())


@app.post("/login", response_model=None)
async def login_post(
    request: Request,
    password: str = Form(...),
    username: str = Form(""),
):
    if not auth_enforced():
        return RedirectResponse(url="/", status_code=303)
    if not username_ok(username) or not password_ok(password):
        return HTMLResponse(
            _login_page(error="Invalid username or password.", username=username),
            status_code=401,
        )
    resp = RedirectResponse(url="/", status_code=303)
    set_session_cookie(resp, request, (username or "").strip() or auth_user())
    return resp


@app.post("/logout", response_model=None)
async def logout_post(request: Request):
    resp = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(resp, request)
    return resp


@app.get("/forgot", response_model=None)
def forgot_get(request: Request):
    if not auth_enforced():
        return RedirectResponse(url="/", status_code=303)
    return HTMLResponse(_forgot_page())


@app.post("/forgot", response_model=None)
async def forgot_post(request: Request, email: str = Form(...)):
    if not auth_enforced():
        return RedirectResponse(url="/", status_code=303)
    # Always show the same success copy (don't leak whether email matched)
    matched = recovery_email_ok(email)
    if matched:
        start_password_reset(request)
    msg = (
        "If that email matches the recovery address, a reset link was sent. "
        "Check inbox (and spam). Ops may also find the link in data/desk_last_reset.txt "
        "when SMTP is unavailable."
    )
    return HTMLResponse(_forgot_page(ok=msg))


@app.get("/reset", response_model=None)
def reset_get(request: Request, token: str = ""):
    if not auth_enforced():
        return RedirectResponse(url="/", status_code=303)
    if not (token or "").strip():
        return HTMLResponse(
            _forgot_page(error="Missing reset token. Request a new link."),
            status_code=400,
        )
    return HTMLResponse(_reset_page(token.strip()))


@app.post("/reset", response_model=None)
async def reset_post(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
):
    if not auth_enforced():
        return RedirectResponse(url="/", status_code=303)
    token = (token or "").strip()
    password = password or ""
    password2 = password2 or ""
    if len(password) < 8:
        return HTMLResponse(
            _reset_page(token, error="Password must be at least 8 characters."),
            status_code=400,
        )
    if password != password2:
        return HTMLResponse(
            _reset_page(token, error="Passwords do not match."),
            status_code=400,
        )
    if not consume_reset_token(token):
        return HTMLResponse(
            _forgot_page(error="Reset link invalid or expired. Request a new one."),
            status_code=400,
        )
    set_password(password)
    # Also refresh parent-facing password file copy used for VPS sync
    try:
        from pathlib import Path as _P

        parent_copy = _P("/tmp/desk_auth_for_parent.txt")
        parent_copy.write_text(password + "\n", encoding="utf-8")
        import os as _os

        _os.chmod(parent_copy, 0o600)
    except OSError:
        pass
    body = """
      <p class="ok">Password updated. You can sign in now.</p>
      <p class="links"><a href="/login">Go to login</a></p>
    """
    return HTMLResponse(_shell("Password updated", body))


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "service": "apex-trading-desk",
        "chat_key": xai_api_key_present(),
        "auth": auth_enforced(),
        "smtp": smtp_configured(),
    }


@app.get("/api/connect")
def api_connect() -> dict[str, Any]:
    """Cloud backup targets for the Connect panel (no secrets)."""
    return connect_settings()


@app.get("/api/bots")
def api_bots() -> dict[str, Any]:
    return bots_overview()


@app.get("/api/trading/status")
def api_trading_status() -> dict[str, Any]:
    return trading_status()


@app.get("/api/chat/status")
def api_chat_status() -> dict[str, Any]:
    return {"available": xai_api_key_present()}


@app.post("/api/chat")
async def api_chat(body: ChatRequest) -> Any:
    msgs = [m.model_dump() for m in body.messages]
    return await chat_completion(msgs, stream=body.stream)


@app.get("/")
def index() -> FileResponse:
    index_path = STATIC / "index.html"
    if not index_path.is_file():
        raise HTTPException(status_code=500, detail="Frontend missing")
    return FileResponse(index_path)


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
