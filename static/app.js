
async function apiFetch(url, opts) {
  const res = await fetch(url, opts);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  return res;
}

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const state = {
  route: "office",
  bots: null,
  status: null,
  chat: [],
  sending: false,
  connect: null,
  connectOpen: false,
};

function money(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return "$" + Number(n).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function pct(n) {
  if (n == null || Number.isNaN(n)) return "—";
  const s = (n >= 0 ? "+" : "") + Number(n).toFixed(2) + "%";
  return s;
}

function ago(sec) {
  if (sec == null) return "—";
  if (sec < 1) return "just now";
  if (sec < 60) return `${sec.toFixed(0)}s ago`;
  if (sec < 3600) return `${(sec / 60).toFixed(1)}m ago`;
  return `${(sec / 3600).toFixed(1)}h ago`;
}

function setRoute(route) {
  state.route = route;
  location.hash = "#/" + route;
  $$(".nav button").forEach((b) => {
    b.classList.toggle("active", b.dataset.route === route);
  });
  $("#view-office").classList.toggle("hidden", route !== "office");
  $("#view-desk").classList.toggle("hidden", route !== "desk");
  $("#view-newguy").classList.toggle("hidden", route !== "newguy");
  if (route === "desk") refreshStatus();
  if (route === "office") refreshBots();
  if (route === "newguy") $("#chat-input")?.focus();
}

function parseHash() {
  const h = (location.hash || "#/office").replace(/^#\/?/, "");
  if (h.startsWith("desk")) return "desk";
  if (h.startsWith("newguy")) return "newguy";
  return "office";
}

async function refreshBots() {
  try {
    const res = await apiFetch("/api/bots");
    const data = await res.json();
    state.bots = data;
    renderOffice(data);
  } catch (e) {
    $("#office-grid").innerHTML =
      `<div class="panel muted">Could not load bots: ${e.message}</div>`;
  }
}

function renderOffice(data) {
  const grid = $("#office-grid");
  grid.innerHTML = (data.bots || [])
    .map((b) => {
      const online = !!b.online;
      return `
      <div class="card" data-href="${b.href}">
        <div class="card-top">
          <div>
            <h3>${escapeHtml(b.name)}</h3>
            <div class="kind">${escapeHtml(b.kind)}</div>
          </div>
          <span class="badge ${online ? "online" : "offline"}">
            <span class="dot"></span>${online ? "Online" : "Offline"}
          </span>
        </div>
        <div class="meta">
          <span>${escapeHtml(b.mode || "")}</span>
          <span>${escapeHtml(b.detail || "")}</span>
        </div>
      </div>`;
    })
    .join("");
  grid.querySelectorAll(".card").forEach((el) => {
    el.addEventListener("click", () => {
      const href = el.dataset.href || "";
      if (href.includes("desk")) setRoute("desk");
      else if (href.includes("newguy")) setRoute("newguy");
    });
  });
}

async function refreshStatus() {
  const stamp = $("#desk-stamp");
  try {
    const res = await apiFetch("/api/trading/status");
    const s = await res.json();
    state.status = s;
    renderDesk(s);
    if (stamp) stamp.textContent = "Updated " + new Date().toLocaleTimeString();
  } catch (e) {
    $("#desk-body").innerHTML =
      `<div class="muted">Status error: ${escapeHtml(e.message)}</div>`;
  }
}

function renderDesk(s) {
  const online = !!s.online;
  const pnlClass = (v) =>
    v == null ? "" : v >= 0 ? "good" : "bad";
  const rows = (s.positions || [])
    .map((p) => {
      const pnl = p.pnl;
      const cls = pnl == null ? "" : pnl >= 0 ? "pos" : "neg";
      return `<tr>
        <td>${escapeHtml(p.symbol)}</td>
        <td>${escapeHtml(p.side)}</td>
        <td>${Number(p.qty).toPrecision(6)}</td>
        <td>${money(p.entry)}</td>
        <td>${p.mark != null ? money(p.mark) : "—"}</td>
        <td class="${cls}">${pnl == null ? "—" : money(pnl)}</td>
        <td class="${cls}">${pct(p.pnl_pct)}</td>
      </tr>`;
    })
    .join("");

  $("#desk-body").innerHTML = `
    <div class="refresh-row">
      <span>
        <span class="badge ${online ? "online" : "offline"}">
          <span class="dot"></span>${online ? "Online" : "Offline"}
        </span>
        &nbsp; heartbeat ${ago(s.heartbeat_age_s)}
      </span>
      <button type="button" id="btn-refresh-desk">Refresh</button>
    </div>
    <div class="stats">
      <div class="stat"><div class="label">Mode</div><div class="value">${escapeHtml(s.mode || "—")}</div></div>
      <div class="stat"><div class="label">Cash</div><div class="value">${money(s.cash)}</div></div>
      <div class="stat"><div class="label">Equity est. (${escapeHtml(s.equity_basis || "cost")})</div>
        <div class="value ${pnlClass(s.unrealized_pnl)}">${money(s.equity_estimate)}</div></div>
      <div class="stat"><div class="label">Unrealized PnL</div>
        <div class="value ${pnlClass(s.unrealized_pnl)}">${s.unrealized_pnl == null ? "—" : money(s.unrealized_pnl)}</div></div>
      <div class="stat"><div class="label">Consec. losses</div>
        <div class="value ${s.consecutive_losses >= 3 ? "warn" : ""}">${s.consecutive_losses ?? "—"}</div></div>
      <div class="stat"><div class="label">CB paused?</div>
        <div class="value ${s.cb_paused ? "warn" : "good"}">${s.cb_paused ? "YES" : "no"}</div></div>
      <div class="stat"><div class="label">TG listener</div>
        <div class="value">${escapeHtml(String(s.tg_listener ?? "—"))}</div></div>
      <div class="stat"><div class="label">Updated at</div>
        <div class="value" style="font-size:0.85rem">${escapeHtml(s.updated_at || "—")}</div></div>
    </div>
    <div class="panel" style="margin-top:16px;padding:0;overflow:auto">
      <table>
        <thead>
          <tr>
            <th>Symbol</th><th>Side</th><th>Qty</th><th>Entry</th><th>Mark</th><th>PnL</th><th>PnL%</th>
          </tr>
        </thead>
        <tbody>
          ${rows || `<tr><td colspan="7" class="muted">No open positions</td></tr>`}
        </tbody>
      </table>
    </div>
    <p class="muted" style="margin-top:12px;font-size:0.78rem">
      PID ${s.pid ?? "—"} · dead_man: ${escapeHtml(String(s.dead_man ?? "—"))}
      ${s.cb_resume_in_s != null ? ` · CB resume in ${Math.round(s.cb_resume_in_s)}s` : ""}
    </p>
  `;
  $("#btn-refresh-desk")?.addEventListener("click", refreshStatus);
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function renderChat() {
  const log = $("#chat-log");
  log.innerHTML = state.chat
    .map(
      (m) => `
    <div class="bubble ${m.role}">
      <div class="who">${m.role === "user" ? "You" : "The New Guy"}</div>
      ${escapeHtml(m.content)}
    </div>`
    )
    .join("");
  log.scrollTop = log.scrollHeight;
}

async function sendChat() {
  const input = $("#chat-input");
  const text = (input.value || "").trim();
  if (!text || state.sending) return;
  state.chat.push({ role: "user", content: text });
  input.value = "";
  renderChat();
  state.sending = true;
  $("#chat-send").disabled = true;

  try {
    const res = await apiFetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        messages: state.chat.map(({ role, content }) => ({ role, content })),
        stream: false,
      }),
    });
    const data = await res.json();
    if (!res.ok) {
      state.chat.push({
        role: "assistant",
        content: "Error: " + (data.detail || res.statusText),
      });
    } else {
      state.chat.push({ role: "assistant", content: data.reply || "(empty)" });
    }
  } catch (e) {
    state.chat.push({ role: "assistant", content: "Network error: " + e.message });
  } finally {
    state.sending = false;
    $("#chat-send").disabled = false;
    renderChat();
    input.focus();
  }
}

function toggleConnectPanel(force) {
  const open = force != null ? !!force : !state.connectOpen;
  state.connectOpen = open;
  const panel = $("#connect-panel");
  const btn = $("#btn-connect");
  if (panel) panel.classList.toggle("hidden", !open);
  if (btn) {
    btn.setAttribute("aria-expanded", open ? "true" : "false");
    btn.classList.toggle("active", open);
  }
  if (open) loadConnect();
}

async function loadConnect() {
  try {
    const res = await apiFetch("/api/connect");
    const data = await res.json();
    state.connect = data;
    applyConnect(data);
  } catch (e) {
    const help = $("#connect-icloud-help");
    if (help) help.textContent = "Could not load Connect config: " + e.message;
  }
}

function applyConnect(data) {
  const driveUrl =
    (data && data.drive_folder_url) ||
    "https://drive.google.com/drive/folders/1yOA3dDrPIbFRobQpvD3ApsUhl6v8m_5n";
  const email = (data && data.email) || "apexsignalsnow@gmail.com";
  const subject = (data && data.email_subject) || "Apex desk backup";
  const help =
    (data && data.icloud_help) ||
    "iCloud has no login from this desk. Save the suitcase zip from Drive into Files → iCloud Drive manually.";

  const drive = $("#connect-drive");
  if (drive) drive.href = driveUrl;

  const mail = $("#connect-email");
  if (mail) {
    mail.href =
      "mailto:" +
      encodeURIComponent(email).replace(/%40/g, "@") +
      "?subject=" +
      encodeURIComponent(subject);
  }
  const mailLabel = $("#connect-email-label");
  if (mailLabel) mailLabel.textContent = email + " · " + subject;

  const helpEl = $("#connect-icloud-help");
  if (helpEl) helpEl.textContent = help;
}


function init() {
  $$(".nav button").forEach((b) => {
    if (b.id === "btn-connect") return;
    b.addEventListener("click", () => setRoute(b.dataset.route));
  });
  $("#btn-connect")?.addEventListener("click", () => toggleConnectPanel());
  $("#btn-connect-close")?.addEventListener("click", () => toggleConnectPanel(false));
  loadConnect();
  window.addEventListener("hashchange", () => setRoute(parseHash()));
  $("#chat-send")?.addEventListener("click", sendChat);
  $("#chat-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });
  setRoute(parseHash());
  refreshBots();
  setInterval(() => {
    if (state.route === "office") refreshBots();
    if (state.route === "desk") refreshStatus();
  }, 5000);
}

document.addEventListener("DOMContentLoaded", init);
