const API = window.API_URL;
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const date = (d) => new Date(d).toLocaleDateString();
let token = localStorage.getItem("token");
let me = null;

const BADGES = {
  verified_academic: "✔ Verified academic", first_answer: "First answer", accepted_answer: "Accepted answer",
  published_author: "Published", peer_reviewer: "Peer reviewer", contributor: "Contributor (100+)", trusted_voice: "Trusted voice (500+)",
};

async function api(path, opts = {}) {
  const headers = {};
  if (token) headers.Authorization = "Bearer " + token;
  let body = opts.body;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  const r = await fetch(API + path, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof d.detail === "string" ? d.detail : "Request failed (" + r.status + ")");
  return d;
}

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.style.display = "block";
  setTimeout(() => (t.style.display = "none"), 3500);
}

const tagLinks = (tags) => (tags || []).map((t) => `<a class="tag" href="#/?tag=${encodeURIComponent(t)}">#${esc(t)}</a>`).join("");
const userLink = (name, verified) => name
  ? `<a href="#/u/${encodeURIComponent(name)}">${esc(name)}</a>${verified ? ' <span class="ver" title="Verified academic">✔</span>' : ""}`
  : '<span class="ai">AI Assistant</span>';
const text = (s) => `<div class="body">${esc(s)}</div>`;
const list = (a) => (a && a.length ? `<ul>${a.map((x) => `<li>${esc(typeof x === "string" ? x : JSON.stringify(x))}</li>`).join("")}</ul>` : "<p class='meta'>None found.</p>");
const needLogin = () => `<div class="card">Please <a href="#/login">log in</a> or <a href="#/register">register</a> first.</div>`;

const voteBox = (t, id, score) => `<div class="votes">
  <button data-act="vote" data-t="${t}" data-i="${id}" data-v="1" title="Useful">▲</button>
  <b id="s-${t}-${id}">${score}</b>
  <button data-act="vote" data-t="${t}" data-i="${id}" data-v="-1" title="Not useful">▼</button></div>`;

const commentBlock = (t, id, comments) => `<div>
  ${comments.filter((c) => c.target_type === t && c.target_id === id).map((c) =>
    `<div class="comment">${esc(c.body)} — ${userLink(c.username, c.verified)} <span class="meta">${date(c.created_at)}</span></div>`).join("")}
  <form class="comment-form" data-form="comment" data-t="${t}" data-i="${id}"><input name="body" placeholder="Add a comment…" required minlength="2"></form></div>`;

// ---------- views ----------
async function home(p) {
  const qs = new URLSearchParams();
  for (const k of ["tag", "q", "sort"]) if (p.get(k)) qs.set(k, p.get(k));
  const [qsList, tags] = await Promise.all([api("/questions?" + qs), api("/tags")]);
  const cur = (p.get("sort") || "new");
  return `<div class="row"><div class="grow">
    <div style="display:flex;justify-content:space-between;align-items:center"><h1>${p.get("tag") ? "#" + esc(p.get("tag")) : p.get("q") ? "Search: " + esc(p.get("q")) : "Questions"}</h1><a class="btn" href="#/ask">Ask a question</a></div>
    <p class="filters">${["new", "top", "unanswered"].map((s) => `<a href="#/?${new URLSearchParams({ ...Object.fromEntries(p), sort: s })}" ${cur === s ? "style='font-weight:700'" : ""}>${s}</a>`).join("")}</p>
    ${qsList.map((q) => `<div class="card row">
      <div class="stat">${"<b>" + q.score + "</b>votes"}</div>
      <div class="stat ${q.accepted_answer_id ? "ok" : ""}"><b>${q.answer_count}</b>answers</div>
      <div class="grow"><a href="#/q/${q.id}"><strong>${esc(q.title)}</strong></a>
        <div class="meta">${esc(q.excerpt)}…</div>
        <div>${tagLinks(q.tags)} <span class="meta">${userLink(q.username, q.verified)} · ${date(q.created_at)} · ${q.views} views</span></div></div></div>`).join("") || "<p class='meta'>No questions yet. Be the first!</p>"}
  </div>
  <aside style="width:190px" class="card"><h2>Fields</h2>${tags.map((t) => `<a class="tag" href="#/?tag=${encodeURIComponent(t.tag)}">#${esc(t.tag)} ${t.n}</a>`).join("") || "<span class='meta'>No tags yet</span>"}</aside></div>`;
}

async function askForm() {
  if (!me) return needLogin();
  return `<h1>Ask a question</h1><form class="card" data-form="ask">
    <label>Title</label><input name="title" required minlength="10" placeholder="e.g. Why does my qPCR show amplification in the no-template control?">
    <label>Details (protocol, equipment settings, what you already tried)</label><textarea name="body" required minlength="20"></textarea>
    <label>Field tags (comma separated)</label><input name="tags" required placeholder="bioinformatics, rheumatology">
    <button class="btn">Post question</button></form>`;
}

async function questionView(id) {
  const d = await api("/questions/" + id);
  const q = d.question;
  return `<h1>${esc(q.title)}</h1>
  <div class="card row">${voteBox("question", q.id, q.score)}<div class="grow">${text(q.body)}
    <div>${tagLinks(q.tags)}</div><div class="meta">${userLink(q.username, q.verified)} · ${date(q.created_at)} · ${q.views} views</div>
    ${commentBlock("question", q.id, d.comments)}</div></div>
  <div style="margin:8px 0"><button class="btn ghost" data-act="summarize" data-i="${id}">✨ Summarize thread</button>
    ${d.answers.some((a) => a.ai_generated) ? "" : `<button class="btn ghost" data-act="ai-answer" data-i="${id}">🤖 Propose AI answer</button>`}</div>
  <div id="ai-box"></div>
  <h2>${d.answers.length} answer(s)</h2>
  ${d.answers.map((a) => `<div class="card row ${q.accepted_answer_id === a.id ? "accepted" : ""}">${voteBox("answer", a.id, a.score)}<div class="grow">
    ${a.ai_generated ? '<div class="meta ai">AI-generated — verify before relying on it</div>' : ""}${text(a.body)}
    <div class="meta">${userLink(a.username, a.verified)} · ${date(a.created_at)}
    ${q.accepted_answer_id === a.id ? " · <b class='ver'>✔ accepted</b>" : me && me.id === q.author_id ? ` · <a href="#" data-act="accept" data-q="${q.id}" data-i="${a.id}">accept this answer</a>` : ""}</div>
    ${commentBlock("answer", a.id, d.comments)}</div></div>`).join("")}
  ${me ? `<form class="card" data-form="answer" data-q="${q.id}"><label>Your answer</label><textarea name="body" required minlength="10"></textarea><button class="btn">Post answer</button></form>` : needLogin()}`;
}

async function articlesView(p) {
  const kind = p.get("kind") || "";
  const items = await api("/articles?" + new URLSearchParams(kind ? { kind } : {}));
  return `<div style="display:flex;justify-content:space-between;align-items:center"><h1>Articles &amp; pre-prints</h1><a class="btn" href="#/write">Write</a></div>
  <p class="filters"><a href="#/articles">all</a><a href="#/articles?kind=blog">blogs</a><a href="#/articles?kind=hypothesis">hypotheses</a><a href="#/articles?kind=preprint">pre-prints</a></p>
  ${items.map((a) => `<div class="card row">${`<div class="stat"><b>${a.score}</b>votes</div>`}<div class="grow"><span class="pill">${esc(a.kind)}</span>
    <a href="#/article/${a.id}"><strong>${esc(a.title)}</strong></a><div class="meta">${esc((a.abstract || "").slice(0, 200))}</div>
    <div>${tagLinks(a.tags)} <span class="meta">${userLink(a.username, a.verified)} · ${date(a.created_at)}</span></div></div></div>`).join("") || "<p class='meta'>Nothing published yet.</p>"}`;
}

async function writeForm() {
  if (!me) return needLogin();
  return `<h1>Publish</h1><form class="card" data-form="article">
    <label>Type</label><select name="kind"><option value="blog">Technical blog</option><option value="hypothesis">Working hypothesis</option><option value="preprint">Pre-print</option></select>
    <label>Title</label><input name="title" required minlength="5">
    <label>Abstract</label><textarea name="abstract" style="min-height:70px"></textarea>
    <label>Body</label><textarea name="body" required minlength="50" style="min-height:280px"></textarea>
    <label>Field tags (comma separated)</label><input name="tags" required>
    <button class="btn">Publish</button></form>`;
}

async function articleView(id) {
  const d = await api("/articles/" + id);
  const a = d.article;
  return `<span class="pill">${esc(a.kind)}</span><h1>${esc(a.title)}</h1>
  <div class="card row">${voteBox("article", a.id, a.score)}<div class="grow">
    ${a.abstract ? `<p><em>${esc(a.abstract)}</em></p>` : ""}${text(a.body)}
    <div>${tagLinks(a.tags)}</div><div class="meta">${userLink(a.username, a.verified)} · ${date(a.created_at)}</div></div></div>
  <h2>Peer review &amp; discussion</h2><div class="card">${me ? commentBlock("article", a.id, d.comments)
    : d.comments.map((c) => `<div class="comment">${esc(c.body)} — ${userLink(c.username, c.verified)}</div>`).join("") + needLogin()}</div>`;
}

async function lab() {
  if (!me) return needLogin();
  const papers = await api("/papers");
  return `<h1>Paper Lab</h1><form class="card" data-form="paper"><label>Upload a pre-print or paper (PDF, max 5 MB, must contain text)</label>
    <input type="file" name="file" accept="application/pdf" required><button class="btn">Upload &amp; analyze</button>
    <p class="meta">Your papers are private to you.</p></form>
    <div class="card"><h2>Your papers</h2><ul class="clean">${papers.map((p) => `<li><a href="#/paper/${p.id}">${esc(p.filename)}</a> <span class="meta">${date(p.created_at)}</span></li>`).join("") || "<li class='meta'>None yet</li>"}</ul></div>`;
}

async function paperView(id) {
  if (!me) return needLogin();
  const p = await api("/papers/" + id);
  const s = p.summary;
  return `<h1>${esc(s.title || p.filename)}</h1>
  <div class="card"><h2>Key takeaways</h2>${list(s.takeaways)}<h2>Methods</h2>${list(s.methods)}<h2>Findings</h2>${list(s.findings)}<h2>Limitations</h2>${list(s.limitations)}</div>
  <div class="card"><h2>Citations found in paper</h2>${list(s.references)}</div>
  <div class="card"><h2>Ask this paper</h2><form data-form="paperask" data-i="${id}"><input name="question" required minlength="3" placeholder="What buffer concentration did they use?"><button class="btn">Ask</button></form><div id="paper-answer" class="body"></div></div>
  <div class="card"><button class="btn ghost" data-act="related" data-i="${id}">Find related discussions on SciLab</button><div id="related"></div></div>`;
}

async function profileView(name) {
  const u = await api("/users/" + encodeURIComponent(name));
  const mine = me && me.username === u.username;
  return `<div class="card"><h1>${esc(u.display_name || u.username)} ${u.verified ? '<span class="ver">✔</span>' : ""}</h1>
    <div class="meta">@${esc(u.username)} · ${esc(u.affiliation || "no affiliation")} · ${esc(u.field || "")} · ${u.orcid ? "ORCID " + esc(u.orcid) : ""}</div>
    <p>${esc(u.bio || "")}</p><p><b>${u.reputation}</b> reputation · ${u.followers} followers · ${u.following} following</p>
    <div>${u.badges.map((b) => `<span class="badge">${esc(BADGES[b] || b)}</span>`).join("")}</div>
    ${me && !mine ? `<p><button class="btn" data-act="follow" data-n="${esc(u.username)}">${u.is_following ? "Unfollow" : "Follow"}</button></p>
      <form data-form="message" data-n="${esc(u.username)}"><input name="body" required placeholder="Send a message…"><button class="btn ghost">Send</button></form>` : ""}</div>
    ${mine ? `<form class="card" data-form="profile"><h2>Edit profile</h2>
      <input name="display_name" placeholder="Full name" value="${esc(u.display_name)}"><input name="affiliation" placeholder="Institution" value="${esc(u.affiliation)}">
      <input name="field" placeholder="Field" value="${esc(u.field)}"><input name="orcid" placeholder="ORCID iD" value="${esc(u.orcid)}">
      <textarea name="bio" placeholder="Bio">${esc(u.bio)}</textarea><button class="btn">Save</button></form>` : ""}
    <div class="card"><h2>Questions</h2><ul class="clean">${u.questions.map((q) => `<li><a href="#/q/${q.id}">${esc(q.title)}</a> <span class="meta">(${q.score})</span></li>`).join("") || "<li class='meta'>None</li>"}</ul>
    <h2>Articles</h2><ul class="clean">${u.articles.map((a) => `<li><a href="#/article/${a.id}">${esc(a.title)}</a> <span class="pill">${esc(a.kind)}</span></li>`).join("") || "<li class='meta'>None</li>"}</ul></div>`;
}

async function leaders() {
  const rows = await api("/leaderboard");
  return `<h1>Top researchers</h1><div class="card"><ul class="clean">${rows.map((u, i) =>
    `<li>${i + 1}. ${userLink(u.username, u.verified)} <span class="meta">${esc(u.affiliation || "")} ${esc(u.field || "")}</span> — <b>${u.reputation}</b></li>`).join("")}</ul></div>`;
}

async function people(p) {
  const rows = await api("/users?" + new URLSearchParams({ q: p.get("q") || "", field: p.get("field") || "" }));
  return `<h1>Find researchers</h1><form class="card" data-form="people"><input name="q" placeholder="Name or institution" value="${esc(p.get("q"))}"><input name="field" placeholder="Field e.g. proteomics" value="${esc(p.get("field"))}"><button class="btn">Search</button></form>
  <div class="card"><ul class="clean">${rows.map((u) => `<li>${userLink(u.username, u.verified)} <span class="meta">${esc(u.affiliation || "")} · ${esc(u.field || "")} · ${u.reputation} rep</span></li>`).join("") || "<li class='meta'>No matches</li>"}</ul></div>`;
}

async function inbox() {
  if (!me) return needLogin();
  const m = await api("/messages");
  return `<h1>Messages</h1>${m.map((x) => `<div class="card"><div class="meta">${userLink(x.sender)} → ${userLink(x.recipient)} · ${date(x.created_at)}</div>${text(x.body)}</div>`).join("") || "<p class='meta'>No messages</p>"}`;
}

const authForm = (kind) => `<h1>${kind === "login" ? "Log in" : "Join SciLab"}</h1><form class="card" data-form="${kind}">
  <input name="email" type="email" placeholder="Email (use your institutional address to get verified)" required>
  ${kind === "register" ? '<input name="username" placeholder="Username" pattern="[A-Za-z0-9_]{3,30}" required><input name="affiliation" placeholder="Institution"><input name="field" placeholder="Field e.g. Bioinformatics">' : ""}
  <input name="password" type="password" placeholder="Password (8+ chars)" minlength="8" required><button class="btn">${kind === "login" ? "Log in" : "Create account"}</button></form>`;

// ---------- router ----------
async function render() {
  const [path, qs] = location.hash.slice(1).split("?");
  const p = new URLSearchParams(qs || "");
  const s = (path || "/").split("/").filter(Boolean);
  const routes = {
    "": () => home(p), ask: askForm, q: () => questionView(s[1]), articles: () => articlesView(p), write: writeForm,
    article: () => articleView(s[1]), lab, paper: () => paperView(s[1]), u: () => profileView(s[1]), leaders, people: () => people(p),
    inbox, login: () => authForm("login"), register: () => authForm("register"),
  };
  $("#app").innerHTML = '<p class="meta">Loading…</p>';
  try { $("#app").innerHTML = await (routes[s[0] || ""] || routes[""])(); }
  catch (e) { $("#app").innerHTML = `<div class="card">${esc(e.message)}</div>`; }
  window.scrollTo(0, 0);
}

function renderNav() {
  $("#nav").innerHTML = `<a href="#/articles">Articles</a><a href="#/lab">Paper Lab</a><a href="#/people">People</a><a href="#/leaders">Leaderboard</a><span style="flex:1"></span>` +
    (me ? `<a href="#/inbox">Inbox</a><a href="#/u/${esc(me.username)}">${esc(me.username)} (${me.reputation})</a><a href="#" data-act="logout">Log out</a>`
        : `<a href="#/login">Log in</a><a class="btn" href="#/register">Join</a>`);
}

// ---------- events ----------
const tagList = (s) => s.split(",").map((x) => x.trim()).filter(Boolean);
const forms = {
  async login(d) { token = (await api("/auth/login", { json: d })).token; await boot("#/"); },
  async register(d) { token = (await api("/auth/register", { json: d })).token; await boot("#/"); },
  async ask(d) { const r = await api("/questions", { json: { ...d, tags: tagList(d.tags) } }); location.hash = "#/q/" + r.id; },
  async answer(d, f) { await api(`/questions/${f.dataset.q}/answers`, { json: d }); render(); },
  async comment(d, f) { await api("/comments", { json: { target_type: f.dataset.t, target_id: +f.dataset.i, body: d.body } }); render(); },
  async article(d) { const r = await api("/articles", { json: { ...d, tags: tagList(d.tags) } }); location.hash = "#/article/" + r.id; },
  async message(d, f) { await api("/messages", { json: { to: f.dataset.n, body: d.body } }); f.reset(); toast("Sent"); },
  async profile(d) { await api("/me", { method: "PATCH", json: d }); await boot(); toast("Saved"); },
  async paper(d, f) {
    const btn = f.querySelector("button"); btn.disabled = true; btn.textContent = "Analyzing… (up to 30s)";
    try { const r = await api("/papers", { body: new FormData(f) }); location.hash = "#/paper/" + r.id; }
    finally { btn.disabled = false; btn.textContent = "Upload & analyze"; }
  },
  async paperask(d, f) { $("#paper-answer").textContent = "Thinking…"; $("#paper-answer").textContent = (await api(`/papers/${f.dataset.i}/ask`, { json: d })).answer; },
  async people(d) { location.hash = "#/people?" + new URLSearchParams(d); },
};
const acts = {
  async vote(el) {
    const r = await api("/vote", { json: { target_type: el.dataset.t, target_id: +el.dataset.i, value: +el.dataset.v } });
    $(`#s-${el.dataset.t}-${el.dataset.i}`).textContent = r.score;
  },
  async accept(el) { await api(`/questions/${el.dataset.q}/accept/${el.dataset.i}`, { method: "POST" }); render(); },
  async follow(el) { await api(`/users/${el.dataset.n}/follow`, { method: "POST" }); render(); },
  async "ai-answer"(el) { el.disabled = true; el.textContent = "Thinking…"; await api(`/questions/${el.dataset.i}/ai-answer`, { method: "POST" }); render(); },
  async summarize(el) {
    const box = $("#ai-box"); box.innerHTML = '<div class="card meta">Summarizing…</div>';
    box.innerHTML = `<div class="card"><b>✨ AI summary</b>${text((await api(`/questions/${el.dataset.i}/summarize`, { method: "POST" })).summary)}</div>`;
  },
  async related(el) {
    const r = await api(`/papers/${el.dataset.i}/related`);
    $("#related").innerHTML = `<p class="meta">Matched on: ${esc(r.keywords.join(", "))}</p><ul>` +
      r.questions.map((q) => `<li>Q: <a href="#/q/${q.id}">${esc(q.title)}</a></li>`).join("") +
      r.articles.map((a) => `<li>${esc(a.kind)}: <a href="#/article/${a.id}">${esc(a.title)}</a></li>`).join("") + "</ul>";
  },
  logout() { token = null; localStorage.removeItem("token"); me = null; boot("#/"); },
};

document.addEventListener("submit", async (e) => {
  const f = e.target.closest("form[data-form]");
  if (!f) { if (e.target.id === "search") { e.preventDefault(); location.hash = "#/?q=" + encodeURIComponent(new FormData(e.target).get("q")); } return; }
  e.preventDefault();
  try { await forms[f.dataset.form](Object.fromEntries(new FormData(f)), f); } catch (err) { toast(err.message); }
});
document.addEventListener("click", async (e) => {
  const el = e.target.closest("[data-act]");
  if (!el) return;
  e.preventDefault();
  try { await acts[el.dataset.act](el); } catch (err) { toast(err.message); }
});
window.addEventListener("hashchange", render);

async function boot(go) {
  if (token) {
    try { me = await api("/me"); localStorage.setItem("token", token); }
    catch { token = null; me = null; localStorage.removeItem("token"); }
  }
  renderNav();
  if (go && location.hash !== go) location.hash = go; else render();
}
boot();
