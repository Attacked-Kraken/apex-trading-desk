# Apex Trading Desk — stable private URL (Tailscale)

Goal: a **stable** private URL that does **not** change when `cloudflared` restarts.  
No custom domain purchase required.

## Status (as of install)

| Item | State |
|------|--------|
| Tailscale package | **Installed** on droplet `159.89.91.6` (`tailscale` 1.102.4) |
| `tailscaled` | **Enabled + running** |
| Tailnet join | **Blocked** — needs Apex auth key (`Logged out.`) |
| Desk bind | `127.0.0.1:8787` only (unchanged) |
| UFW port 8787 | **Not opened** publicly |
| Desk password + SMTP reset | **Unchanged** (still required after Tailscale connect) |
| trycloudflare secondary | **Still running** (`apex-desk-tunnel`) — URL can change on restart |

Prepared on VPS:

- Secret file: `/etc/apex-trading-desk/tailscale.env` (mode `0600`, `TS_AUTHKEY=` empty)
- Join script: `/usr/local/sbin/apex-desk-tailscale-up.sh`

---

## Human step (Apex) — paste auth key, then join

### 1. Create an auth key

1. Open https://login.tailscale.com/admin/settings/keys  
2. Sign in as the Apex Tailscale account (create a free tailnet if needed).  
3. **Generate auth key** with:
   - **Reusable**: Yes (so re-runs / rebuilds work)
   - **Ephemeral**: No (droplet should stay in the tailnet)
   - **Expiration**: your choice (e.g. 90 days); regenerate later if expired
   - **Tags**: optional (e.g. `tag:server` if you use ACLs)

### 2. Put the key in the VPS secret (do not commit it)

SSH as root:

```bash
ssh -i ~/.ssh/apex_desk_ed25519 root@159.89.91.6
nano /etc/apex-trading-desk/tailscale.env
```

Set the line (paste your real key; do not invent one):

```bash
TS_AUTHKEY=tskey-auth-XXXXXXXX
```

Save, ensure permissions:

```bash
chmod 600 /etc/apex-trading-desk/tailscale.env
```

### 3. Join the tailnet + publish desk on MagicDNS

```bash
sudo /usr/local/sbin/apex-desk-tailscale-up.sh
```

That runs:

- `tailscale up --auth-key=… --hostname=apex-trading-desk --accept-dns=true`
- `tailscale serve --bg --http=80 http://127.0.0.1:8787`

### 4. Note your stable URLs

After join, script prints MagicDNS and Tailscale IP. Typical forms:

- `http://apex-trading-desk.<your-tailnet>.ts.net/`  ← **bookmark this** (stable)
- `http://100.x.y.z/`  ← Tailscale IP (also stable for this node)

Confirm:

```bash
tailscale status
tailscale serve status
```

---

## iPhone (Tailscale app) — recommended bookmark steps

1. App Store → install **Tailscale**.  
2. Open Tailscale → **Log in** with the **same** account/tailnet as the auth key.  
3. Toggle **VPN / Connected** ON (status should show Connected).  
4. Optional: Tailscale app → Settings → enable **MagicDNS** if not already on for the device.  
5. Safari → open `http://apex-trading-desk.<your-tailnet>.ts.net/`  
   (or the Tailscale IP from `tailscale status` on the VPS).  
6. You will see the **desk login** page — enter the desk password (auth is not disabled).  
7. Safari → **Share** → **Add to Home Screen** → name **Apex Desk** (stable private shortcut).  
8. Optional: keep the trycloudflare URL as a backup only; it may change when the tunnel service restarts.

---

## Security notes

- Tailscale = private network gate; **desk password gate stays on**.  
- Port **8787 is not** allowed on UFW from the public Internet.  
- Serve publishes HTTP **only on the Tailscale interface** (proxy to localhost:8787).  
- Do **not** put `TS_AUTHKEY` in git, Drive docs, or chat logs.  
- After successful join you may clear or rotate `TS_AUTHKEY` in `tailscale.env` (node stays keyed until `tailscale logout`).

## Optional: leave trycloudflare as secondary

`apex-desk-tunnel.service` remains enabled. Public URL (changes on restart):

`https://wallet-pix-difficulties-static.trycloudflare.com`

Prefer the Tailscale MagicDNS name for day-to-day 24/7 access.

## If join fails

- Key expired / already used (if not reusable) → generate a new key.  
- Device approval required in admin console → approve `apex-trading-desk`.  
- Check: `journalctl -u tailscaled -n 50 --no-pager`
