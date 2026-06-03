"use strict";

const API = "";
let TOKEN = localStorage.getItem("token") || null;
let CURRENT_DEAL = null;

// --------------------------------------------------------------------------- //
// HTTP helper
// --------------------------------------------------------------------------- //
async function api(path, opts = {}) {
  const headers = opts.headers || {};
  if (TOKEN) headers["Authorization"] = "Bearer " + TOKEN;
  if (opts.body) headers["Content-Type"] = "application/json";
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401) { logout(); throw new Error("Unauthorized"); }
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status}: ${txt}`);
  }
  return res.status === 204 ? null : res.json();
}

const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));

const fmtDate = (s) => {
  if (!s) return "—";
  const d = new Date(s);
  return isNaN(d) ? "—" : d.toISOString().slice(0, 10);
};

const daysAgo = (s) => {
  if (!s) return null;
  return Math.round((Date.now() - new Date(s).getTime()) / 86400000);
};

// --------------------------------------------------------------------------- //
// Auth
// --------------------------------------------------------------------------- //
function showTab(which) {
  document.getElementById("form-login").classList.toggle("hidden", which !== "login");
  document.getElementById("form-signup").classList.toggle("hidden", which !== "signup");
  document.getElementById("tab-login").classList.toggle("active", which === "login");
  document.getElementById("tab-signup").classList.toggle("active", which === "signup");
}

async function doSignup(e) {
  e.preventDefault();
  const f = e.target;
  await authRequest("/auth/signup", {
    company_name: f.company_name.value || null,
    email: f.email.value,
    password: f.password.value,
  });
  return false;
}

async function doLogin(e) {
  e.preventDefault();
  const f = e.target;
  await authRequest("/auth/login", { email: f.email.value, password: f.password.value });
  return false;
}

async function authRequest(path, body) {
  const err = document.getElementById("auth-error");
  err.textContent = "";
  try {
    const data = await api(path, { method: "POST", body: JSON.stringify(body) });
    TOKEN = data.access_token;
    localStorage.setItem("token", TOKEN);
    await enterApp();
  } catch (ex) {
    err.textContent = ex.message;
  }
}

function logout() {
  TOKEN = null;
  localStorage.removeItem("token");
  document.getElementById("app").classList.add("hidden");
  document.getElementById("auth").classList.remove("hidden");
}

// --------------------------------------------------------------------------- //
// App
// --------------------------------------------------------------------------- //
async function enterApp() {
  document.getElementById("auth").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
  const me = await api("/auth/me");
  document.getElementById("whoami").textContent = `${me.email} · ${me.company_name}`;
  document.getElementById("proactive-toggle").checked = me.proactive_enabled;
  await Promise.all([loadDeals(), loadFeed()]);
}

async function loadDeals() {
  const page = await api("/deals?limit=100");
  const el = document.getElementById("deal-list");
  el.innerHTML = "";
  for (const d of page.items) {
    const days = daysAgo(d.last_activity_at);
    const div = document.createElement("div");
    div.className = "deal-row" + (d.is_closed ? " closed" : "");
    div.onclick = () => openDeal(d.id);
    div.innerHTML = `
      <div class="deal-name">${esc(d.deal_name)}</div>
      <div class="deal-meta">
        <span class="badge">${esc(d.stage_label || "—")}</span>
        <span class="muted">${days == null ? "no activity" : days + "d ago"}</span>
      </div>`;
    el.appendChild(div);
  }
}

async function openDeal(id) {
  CURRENT_DEAL = id;
  const el = document.getElementById("deal-detail");
  el.innerHTML = `<p class="muted">Loading…</p>`;
  const [deal, acts, contacts] = await Promise.all([
    api(`/deals/${id}`),
    api(`/deals/${id}/activities?limit=15`),
    api(`/deals/${id}/contacts`),
  ]);
  el.innerHTML = `
    <div class="detail-head">
      <h3>${esc(deal.deal_name)}</h3>
      <span class="badge">${esc(deal.stage_label || "—")}</span>
      ${deal.is_closed ? '<span class="badge closed-badge">closed</span>' : ""}
    </div>
    <p class="muted">Owner: ${esc(deal.deal_owner || "—")} ·
       Last activity: ${fmtDate(deal.last_activity_at)} ·
       Contacts: ${contacts.length}</p>

    <button onclick="recommend('${id}')">Get recommendation</button>
    <div id="rec-box"></div>

    <h4>Add activity</h4>
    <form onsubmit="return addActivity(event, '${id}')" class="activity-form">
      <select name="activity_type">
        <option>email</option><option>call</option><option>meeting</option>
        <option>note</option><option>task</option>
      </select>
      <select name="direction">
        <option value="">direction…</option>
        <option value="outbound">outbound</option>
        <option value="inbound">inbound</option>
      </select>
      <input name="subject" placeholder="subject" />
      <textarea name="full_text" placeholder="notes / body"></textarea>
      <button type="submit">Log activity</button>
    </form>

    <h4>Timeline (${acts.total})</h4>
    <div class="timeline">${acts.items.map(renderActivity).join("")}</div>`;
}

function renderActivity(a) {
  const dir = a.direction || "unknown";
  return `<div class="act" data-id="${esc(a.activity_id || a.id)}">
    <div class="act-head">
      <span class="badge sm">${esc(a.activity_type || "?")}</span>
      <span class="dir ${dir}">${dir}</span>
      <span class="muted">${fmtDate(a.timestamp)}</span>
    </div>
    <div class="act-subj">${esc(a.subject || "(no subject)")}</div>
    <div class="act-body muted">${esc((a.full_text || "").slice(0, 200))}</div>
  </div>`;
}

async function addActivity(e, id) {
  e.preventDefault();
  const f = e.target;
  await api(`/deals/${id}/activities`, {
    method: "POST",
    body: JSON.stringify({
      activity_type: f.activity_type.value,
      direction: f.direction.value || null,
      subject: f.subject.value || null,
      full_text: f.full_text.value || null,
    }),
  });
  await openDeal(id);
  setTimeout(loadFeed, 1500); // reactive trigger runs in background
  return false;
}

async function recommend(id) {
  const box = document.getElementById("rec-box");
  box.innerHTML = `<p class="muted">Agent thinking…</p>`;
  try {
    const r = await api(`/deals/${id}/recommendation`, { method: "POST" });
    box.innerHTML = renderRec(r, true);
    loadFeed();
  } catch (ex) {
    box.innerHTML = `<p class="error">${esc(ex.message)}</p>`;
  }
}

function renderRec(r, detail) {
  if (r.no_action) {
    return `<div class="rec none"><strong>No action needed.</strong>
      <span class="muted">${esc(r.rationale || "")}</span></div>`;
  }
  const ev = (r.evidence || []).map((e) =>
    `<li>${esc(e.subject || e.activity_id)} <span class="muted">${fmtDate(e.timestamp)}</span></li>`
  ).join("");
  return `<div class="rec urg-${esc(r.urgency)}">
    <div class="rec-head">
      ${detail ? "" : `<strong>${esc(r.deal_name || "")}</strong>`}
      <span class="badge urg">${esc(r.urgency)}</span>
    </div>
    <div class="rec-nba">${esc(r.nba)}</div>
    <div class="rec-why muted">${esc(r.rationale || "")}</div>
    ${ev ? `<details><summary>evidence (${r.evidence.length})</summary><ul>${ev}</ul></details>` : ""}
  </div>`;
}

async function loadFeed() {
  const el = document.getElementById("feed");
  try {
    const feed = await api("/proactive/feed");
    if (!feed.length) {
      el.innerHTML = `<p class="muted">No recommendations yet. Open a deal and click
        "Get recommendation", or wait for the next scan.</p>`;
      return;
    }
    el.innerHTML = feed.map((r) =>
      `<div class="feed-item" onclick="openDeal('${r.deal_id}')">
        <div class="feed-deal">${esc(r.deal_name || r.deal_id)}</div>
        ${renderRec(r, false)}
      </div>`
    ).join("");
  } catch (ex) {
    el.innerHTML = `<p class="error">${esc(ex.message)}</p>`;
  }
}

async function toggleProactive() {
  const on = document.getElementById("proactive-toggle").checked;
  await api(`/proactive/${on}`, { method: "POST" });
}

// Boot
if (TOKEN) {
  enterApp().catch(() => logout());
}
