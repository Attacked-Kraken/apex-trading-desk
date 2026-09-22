# Apex Trading Desk — deployed

- Droplet: apex-trading-desk (NYC1)
- IP: 159.89.91.6
- Public URL (Cloudflare quick tunnel): https://wallet-pix-difficulties-static.trycloudflare.com
- Service: apex-trading-desk (uvicorn :8787), apex-desk-tunnel
- Note: Cruz live paper data still on Grok Bot box; New Guy chat uses XAI on VPS. Next: sync status feed or migrate bots.
- Connect panel: Drive Attack folder + mailto backup + iCloud manual-help (GET /api/connect).

## Private access (password gate)

Anyone hitting the public Cloudflare URL sees `/login` until authenticated.
After a correct password, the desk sets an HttpOnly signed session cookie (~30 days).

### Env vars (do not commit secrets)

| Var | Required | Purpose |
|-----|----------|---------|
| `DESK_AUTH_PASSWORD` | **Yes on VPS** | Gate password. If unset (and no `data/desk_password.txt`), auth is open (dev only; logs a warning). |
| `DESK_AUTH_SECRET` | Recommended | HMAC secret for signing cookies. If missing, generated into `data/desk_auth_secret` (mode 0600). |
| `DESK_AUTH_USER` | Optional | Default `apex`. Form username may be blank or must match. |
| `DESK_AUTH_EMAIL` | Optional | Recovery email. Default `apexsignalsnow@gmail.com`. |
| `DESK_SMTP_HOST` | For email reset | Default `smtp.gmail.com` |
| `DESK_SMTP_PORT` | For email reset | Default `587` (STARTTLS) |
| `DESK_SMTP_USER` | For email reset | Gmail address |
| `DESK_SMTP_PASSWORD` | For email reset | Gmail app password (**never commit / never hardcode**) |
| `DESK_SMTP_FROM` | Optional | From header; defaults to SMTP user |

Local secret files (0600, gitignored): `data/desk_password.txt`, `data/desk_auth_secret`, `data/desk_smtp.env`, `data/desk_last_reset.txt`.

### VPS EnvironmentFile (parent deploy)

Sync box secrets into a systemd EnvironmentFile (do not put passwords in unit files committed to git):

```bash
# On the droplet:
sudo mkdir -p /opt/apex-trading-desk/data
# Copy/sync from box pack — example layout:
#   /etc/apex-trading-desk.env   ← DESK_AUTH_* + DESK_SMTP_* (mode 0600)
#   /opt/apex-trading-desk/data/desk_password.txt (optional; reset flow writes here)

sudo install -m 600 /path/from/sync/desk_smtp.env /etc/apex-trading-desk.env
# Append auth password/secret if not already in that file:
#   DESK_AUTH_PASSWORD=…
#   DESK_AUTH_SECRET=…
#   DESK_AUTH_USER=apex
#   DESK_AUTH_EMAIL=apexsignalsnow@gmail.com

# In systemd unit apex-trading-desk.service:
#   EnvironmentFile=/etc/apex-trading-desk.env
sudo systemctl daemon-reload
sudo systemctl restart apex-trading-desk
```

Local start (box):

```bash
set -a
source /workspace/apex-trading-desk/data/desk_smtp.env
# plus DESK_AUTH_PASSWORD / DESK_AUTH_SECRET from data/desk_password.txt or env
set +a
uvicorn app.main:app --host 0.0.0.0 --port 8787
```

Password preference: `data/desk_password.txt` (if present) overrides `DESK_AUTH_PASSWORD` so `/reset` persists across restarts.

### Behavior

- `GET /login` — login form; **Forgot password?** → `/forgot`
- `POST /login` — constant-time password check → session cookie → `/`
- `POST /logout` — clear cookie → `/login`
- `GET|POST /forgot` — if recovery email matches `DESK_AUTH_EMAIL`, issue 30‑min one-time token; email via Gmail SMTP; always write ops copy to `data/desk_last_reset.txt` when SMTP missing/fails (and on success for audit)
- `GET|POST /reset` — set new password (file + process env)
- Unauthenticated `/api/*` → **401** (except `GET /api/health`)
- Unauthenticated `/` or `/static/*` → redirect `/login`
- Header **Lock** button posts logout when logged in

### Tunnel note

The trycloudflare URL is still **secret-by-obscurity until `DESK_AUTH_PASSWORD` is set**.
Set the password on the VPS before sharing the URL widely. Cloudflare Access is not required yet (no custom domain).
