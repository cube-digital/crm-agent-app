"use strict";

const API = "";
let TOKEN = localStorage.getItem("token") || null;
let CURRENT_DEAL = null;
let CURRENT_DEAL_NAME = null;
let CHAT_HISTORY = [];     // [{role:'user'|'assistant', content}] for the active deal
let FEED = {};             // deal_id -> recommendation

const QUICK_PROMPTS = [
  "Why now?",
  "Who should I contact?",
  "What's blocking this deal?",
  "What did they last say?",
  "When should I follow up?",
];

// --------------------------------------------------------------------------- //
// HTTP helper
// --------------------------------------------------------------------------- //
async function api(path, opts = {}) {
  const headers = opts.headers || {};
  if (TOKEN) headers["Authorization"] = "Bearer " + TOKEN;
  if (opts.body) headers["Content-Type"] = "application/json";
  const res = await fetch(API + path, { ...opts, headers });
  if (res.status === 401) { logout(); throw new Error("Unauthorized"); }
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.status === 204 ? null : res.json();
}

const esc = (s) => (s == null ? "" : String(s).replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])));
const fmtDate = (s) => { if (!s) return "—"; const d = new Date(s); return isNaN(d) ? "—" : d.toISOString().slice(0, 10); };
const daysAgo = (s) => s ? Math.round((Date.now() - new Date(s).getTime()) / 86400000) : null;

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
  e.preventDefault(); const f = e.target;
  await authRequest("/auth/signup", {
    company_name: f.company_name.value || null, email: f.email.value, password: f.password.value });
  return false;
}
async function doLogin(e) {
  e.preventDefault(); const f = e.target;
  await authRequest("/auth/login", { email: f.email.value, password: f.password.value });
  return false;
}
async function authRequest(path, body) {
  const err = document.getElementById("auth-error"); err.textContent = "";
  try {
    const data = await api(path, { method: "POST", body: JSON.stringify(body) });
    TOKEN = data.access_token; localStorage.setItem("token", TOKEN);
    await enterApp();
  } catch (ex) { err.textContent = ex.message; }
}
function logout() {
  TOKEN = null; localStorage.removeItem("token");
  document.getElementById("app").classList.add("hidden");
  document.getElementById("auth").classList.remove("hidden");
}

// --------------------------------------------------------------------------- //
// App boot
// --------------------------------------------------------------------------- //
async function enterApp() {
  document.getElementById("auth").classList.add("hidden");
  document.getElementById("app").classList.remove("hidden");
  const me = await api("/auth/me");
  document.getElementById("whoami").textContent = `${me.email} · ${me.company_name}`;
  document.getElementById("proactive-toggle").checked = me.proactive_enabled;
  await loadDeals();
  await refreshRecs();
  pollForRecs();  // the first proactive scan runs server-side after signup
}

// After signup the inbox starts empty while the background scan runs; poll a few
// times so recommendations appear on their own (~30s) without a manual refresh.
// Stops once recs arrive or the user drills into a specific deal.
function pollForRecs() {
  let tries = 0;
  const iv = setInterval(async () => {
    tries += 1;
    if (CURRENT_DEAL || tries > 5) { clearInterval(iv); return; }
    try {
      const feed = await api("/proactive/feed");
      if (feed.length) { clearInterval(iv); if (!CURRENT_DEAL) await refreshRecs(); }
    } catch (_) { /* ignore transient errors */ }
  }, 7000);
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
    div.dataset.deal = d.id;
    div.innerHTML = `
      <div class="deal-name">${esc(d.deal_name)}</div>
      <div class="deal-meta">
        <span class="badge">${esc(d.stage_label || "—")}</span>
        <span class="muted">${days == null ? "no activity" : days + "d ago"}</span>
      </div>`;
    el.appendChild(div);
  }
}

function highlightDeal(id) {
  document.querySelectorAll(".deal-row").forEach((r) =>
    r.classList.toggle("active", r.dataset.deal === id));
}

// --------------------------------------------------------------------------- //
// Deal detail (middle)
// --------------------------------------------------------------------------- //
async function openDeal(id) {
  highlightDeal(id);
  const el = document.getElementById("deal-detail");
  el.innerHTML = `<p class="muted">Loading…</p>`;
  const [deal, contacts] = await Promise.all([api(`/deals/${id}`), api(`/deals/${id}/contacts`)]);
  CURRENT_DEAL_NAME = deal.deal_name;
  el.innerHTML = `
    <div class="detail-head">
      <h3>${esc(deal.deal_name)}</h3>
      <span class="badge">${esc(deal.stage_label || "—")}</span>
      ${deal.is_closed ? '<span class="badge closed-badge">closed</span>' : ""}
    </div>
    <p class="muted">Owner: ${esc(deal.deal_owner || "—")} ·
       Last activity: ${fmtDate(deal.last_activity_at)} · Contacts: ${contacts.length}</p>
    <button onclick="getRecommendation('${id}')">Get recommendation →</button>

    <h4>Add activity</h4>
    <form onsubmit="return addActivity(event, '${id}')" class="activity-form">
      <select name="activity_type"><option>email</option><option>call</option>
        <option>meeting</option><option>note</option><option>task</option></select>
      <select name="direction"><option value="">direction…</option>
        <option value="outbound">outbound</option><option value="inbound">inbound</option></select>
      <input name="subject" placeholder="subject" />
      <textarea name="full_text" placeholder="notes / body"></textarea>
      <button type="submit">Log activity</button>
    </form>

    <h4>Timeline</h4>
    <div id="timeline" class="timeline"></div>`;
  await loadTimeline(id);

  // Focus the chat on this deal.
  focusChat(id, deal.deal_name, deal.is_closed);
}

async function loadTimeline(id) {
  const acts = await api(`/deals/${id}/activities?limit=15`);
  document.getElementById("timeline").innerHTML =
    `<div class="muted tl-count">${acts.total} activities</div>` + acts.items.map(renderActivity).join("");
}

function renderActivity(a) {
  const dir = a.direction || "unknown";
  return `<div class="act">
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
  await api(`/deals/${id}/activities`, { method: "POST", body: JSON.stringify({
    activity_type: f.activity_type.value, direction: f.direction.value || null,
    subject: f.subject.value || null, full_text: f.full_text.value || null }) });
  f.reset();
  await loadTimeline(id);
  if (id === CURRENT_DEAL) chatSystem("Activity logged — the agent is re-evaluating this deal in the background.");
}

// --------------------------------------------------------------------------- //
// Chat panel (right)
// --------------------------------------------------------------------------- //
function chatEl() { return document.getElementById("chat-messages"); }
function scrollChat() { const e = chatEl(); e.scrollTop = e.scrollHeight; }

function chatClear() { chatEl().innerHTML = ""; }

function chatBubble(role, html) {
  const div = document.createElement("div");
  div.className = `bubble ${role}`;
  div.innerHTML = html;
  chatEl().appendChild(div);
  scrollChat();
  return div;
}
function chatSystem(text) { return chatBubble("system", esc(text)); }

function renderRecBody(r) {
  if (r.no_action) {
    return `<strong>No action needed.</strong> <span class="muted">${esc(r.rationale || "")}</span>`;
  }
  const ev = (r.evidence || []).map((e) =>
    `<li>${esc(e.subject || e.activity_id)} <span class="muted">${fmtDate(e.timestamp)}</span></li>`).join("");
  return `
    <div class="rec-head"><span class="badge urg urg-${esc(r.urgency)}">${esc(r.urgency)}</span></div>
    <div class="rec-nba">${esc(r.nba)}</div>
    <div class="rec-why muted">${esc(r.rationale || "")}</div>
    ${ev ? `<details><summary>evidence (${r.evidence.length})</summary><ul>${ev}</ul></details>` : ""}`;
}

function recCard(r, withDiscuss) {
  const btn = withDiscuss
    ? `<div class="card-actions"><button class="chip" onclick="openDeal('${r.deal_id}')">Discuss →</button></div>`
    : "";
  return `<div class="rec urg-${esc(r.urgency)}">
    <div class="rec-deal">${esc(r.deal_name || r.deal_id)}</div>
    ${renderRecBody(r)}${btn}</div>`;
}

// Rebuild the chat into the "recommendations overview".
async function refreshRecs() {
  chatClear();
  CHAT_HISTORY = [];
  setChatEnabled(false);
  document.getElementById("chat-context").textContent = "Recommendations";
  renderQuick(false);
  let feed;
  try { feed = await api("/proactive/feed"); }
  catch (ex) { chatBubble("assistant", `<span class="error">${esc(ex.message)}</span>`); return; }
  FEED = {}; feed.forEach((r) => { FEED[r.deal_id] = r; });
  if (!feed.length) {
    chatBubble("assistant",
      "No recommendations yet. Open a deal and click <b>Get recommendation</b>, or wait for the next proactive scan. Then click a recommendation to ask follow-ups.");
    return;
  }
  chatBubble("assistant", `Here are the <b>${feed.length}</b> deals needing attention, ranked. Tap <b>Discuss</b> on any to ask follow-ups.`);
  feed.forEach((r) => chatBubble("assistant", recCard(r, true)));
}

// Switch the conversation to a specific deal.
function focusChat(id, name, isClosed) {
  CURRENT_DEAL = id; CURRENT_DEAL_NAME = name; CHAT_HISTORY = [];
  document.getElementById("chat-context").textContent = "Discussing: " + name;
  chatClear();
  chatSystem("Now discussing " + name);
  const rec = FEED[id];
  if (rec && !rec.no_action) {
    chatBubble("assistant", recCard(rec, false));
    CHAT_HISTORY.push({ role: "assistant",
      content: `Recommendation: ${rec.nba} (Rationale: ${rec.rationale}; urgency ${rec.urgency}).` });
  } else if (isClosed) {
    chatBubble("assistant", "This deal is closed — no action needed. You can still ask me about its history.");
  } else {
    chatBubble("assistant", "No proactive recommendation yet for this deal. Ask me anything, or click <b>Get recommendation</b>.");
  }
  setChatEnabled(true);
  renderQuick(true);
  document.getElementById("chat-text").focus();
}

async function getRecommendation(id) {
  if (id !== CURRENT_DEAL) { CURRENT_DEAL = id; }
  const typing = chatBubble("assistant typing", "Analyzing the deal…");
  try {
    const r = await api(`/deals/${id}/recommendation`, { method: "POST" });
    FEED[id] = r;
    typing.remove();
    chatBubble("assistant", recCard(r, false));
    CHAT_HISTORY.push({ role: "assistant",
      content: r.no_action ? "No action needed for this deal."
        : `Recommendation: ${r.nba} (Rationale: ${r.rationale}; urgency ${r.urgency}).` });
    setChatEnabled(true);
    renderQuick(true);
  } catch (ex) {
    typing.remove();
    chatBubble("assistant", `<span class="error">${esc(ex.message)}</span>`);
  }
}

function renderQuick(show) {
  const el = document.getElementById("chat-quick");
  if (!show) { el.innerHTML = ""; return; }
  el.innerHTML = QUICK_PROMPTS.map((p) =>
    `<button class="chip" onclick="askQuick('${p.replace(/'/g, "\\'")}')">${esc(p)}</button>`).join("");
}

function setChatEnabled(on) {
  document.getElementById("chat-text").disabled = !on;
  document.getElementById("chat-send").disabled = !on;
}

function askQuick(text) { doSend(text); }

function sendChat(e) { e.preventDefault(); const t = document.getElementById("chat-text").value.trim(); if (t) doSend(t); return false; }

async function doSend(text) {
  if (!CURRENT_DEAL) return;
  document.getElementById("chat-text").value = "";
  chatBubble("user", esc(text));
  CHAT_HISTORY.push({ role: "user", content: text });
  const typing = chatBubble("assistant typing", "…");
  try {
    const res = await api(`/deals/${CURRENT_DEAL}/chat`, {
      method: "POST", body: JSON.stringify({ messages: CHAT_HISTORY }) });
    typing.remove();
    chatBubble("assistant", esc(res.reply).replace(/\n/g, "<br>"));
    CHAT_HISTORY.push({ role: "assistant", content: res.reply });
  } catch (ex) {
    typing.remove();
    chatBubble("assistant", `<span class="error">${esc(ex.message)}</span>`);
  }
}

async function toggleProactive() {
  const on = document.getElementById("proactive-toggle").checked;
  await api(`/proactive/${on}`, { method: "POST" });
}

// Boot
if (TOKEN) enterApp().catch(() => logout());
