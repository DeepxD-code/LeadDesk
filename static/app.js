/* LeadDesk front end - plain JavaScript, no build step. */
"use strict";

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
class Raw { constructor(s) { this.s = s; } toString() { return this.s; } }
const raw = (s) => new Raw(s);
function html(strings, ...vals) {
  let out = "";
  strings.forEach((s, i) => {
    out += s;
    if (i < vals.length) {
      const v = vals[i];
      if (v instanceof Raw) out += v.s;
      else if (Array.isArray(v)) out += v.map((x) => (x instanceof Raw ? x.s : esc(x))).join("");
      else if (v === false || v === null || v === undefined) out += "";
      else out += esc(v);
    }
  });
  return raw(out);
}

async function api(path, opts = {}) {
  if (window.LEADDESK_PREVIEW_API) return window.LEADDESK_PREVIEW_API(path, opts);
  const o = { method: "GET", headers: {}, ...opts };
  if (o.body && !(o.body instanceof FormData)) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(o.body); }
  const r = await fetch(path, o);
  if (r.status === 401 && !path.startsWith("/api/auth")) { S.me = null; closeModal(); renderLogin(); throw new Error("Please sign in"); }
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    let msg = data && data.detail ? data.detail : r.statusText;
    if (Array.isArray(msg)) msg = msg.map((d) => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join("; ");
    const e = new Error(msg); e.status = r.status; throw e;
  }
  return data;
}

function toast(msg, kind = "") {
  const t = document.createElement("div");
  t.className = "toast " + kind; t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), kind === "bad" ? 6000 : 3200);
}
const fail = (e) => toast(e.message || String(e), "bad");

function modal(content, { wide = false, onClose } = {}) {
  closeModal();
  const ov = document.createElement("div");
  ov.className = "overlay"; ov.id = "overlay";
  ov.innerHTML = `<div class="modal ${wide ? "wide" : ""}">${content}</div>`;
  ov.addEventListener("mousedown", (e) => { if (e.target === ov) closeModal(); });
  document.body.appendChild(ov);
  ov._onClose = onClose;
  $$("[data-close]", ov).forEach((b) => (b.onclick = closeModal));
  return ov;
}
function closeModal() { const ov = $("#overlay"); if (ov) { ov.remove(); ov._onClose && ov._onClose(); } }
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });

function reasonModal({ title, description, label, submitLabel, required = true, onSubmit, onSuccess, onCancel }) {
  let submitted = false;
  const ov = modal(html`
    <div class="modal-head"><h2>${title}</h2><button class="x" type="button" data-close aria-label="Close">×</button></div>
    <p class="muted">${description}</p>
    <form id="reason-form">
      <label class="f">${label}<textarea class="input" name="reason" rows="4" maxlength="1000" ${required ? raw("required") : ""}></textarea></label>
      <div class="row"><span class="grow"></span><button type="button" class="btn" data-close>Cancel</button><button type="submit" class="btn primary">${submitLabel}</button></div>
    </form>`.s, { onClose: () => { if (!submitted && onCancel) onCancel(); } });
  $("#reason-form", ov).onsubmit = async (e) => {
    e.preventDefault();
    const reason = new FormData(e.target).get("reason").toString();
    if (required && !reason.trim()) { $("[name=reason]", ov).focus(); return; }
    const submit = $('button[type="submit"]', e.target);
    submit.disabled = true;
    try {
      await onSubmit(reason);
      submitted = true;
      closeModal();
      onSuccess && onSuccess();
    } catch (er) { fail(er); submit.disabled = false; }
  };
}

// Server works in IST; we display server wall-clock times as written.
let skewMs = 0;
const parseLocal = (s) => (s ? new Date(s.length === 16 ? s + ":00" : s) : null);
const nowServer = () => new Date(Date.now() + skewMs);
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
function fmtTime(d) { let h = d.getHours(), m = d.getMinutes(); const ap = h >= 12 ? "PM" : "AM"; h = h % 12 || 12; return `${h}:${String(m).padStart(2, "0")} ${ap}`; }
function fmtDT(s, withDay = true) {
  const d = parseLocal(s); if (!d) return "-";
  const n = nowServer(); const sameDay = d.toDateString() === n.toDateString();
  const tmr = new Date(n); tmr.setDate(n.getDate() + 1);
  const yst = new Date(n); yst.setDate(n.getDate() - 1);
  let day = sameDay ? "Today" : d.toDateString() === tmr.toDateString() ? "Tomorrow" : d.toDateString() === yst.toDateString() ? "Yesterday"
    : `${withDay ? DAYS[d.getDay()] + " " : ""}${d.getDate()} ${MONTHS[d.getMonth()]}`;
  return `${day}, ${fmtTime(d)}`;
}
function rel(s) {
  const d = parseLocal(s); const diff = (d - nowServer()) / 60000;
  const a = Math.abs(diff);
  const txt = a < 60 ? `${Math.round(a)} min` : a < 60 * 48 ? `${Math.round(a / 60)} h` : `${Math.round(a / 1440)} days`;
  return diff < 0 ? `${txt} overdue` : `in ${txt}`;
}
const dateInput = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const dtInput = (d) => `${dateInput(d)}T${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
const COLORS = ["#6366f1", "#0ea5e9", "#14b8a6", "#22c55e", "#eab308", "#f97316", "#ef4444", "#ec4899", "#a855f7", "#64748b"];
const initials = (n) => (n || "?").split(" ").filter(Boolean).slice(0, 2).map((w) => w[0]).join("").toUpperCase();
const avatar = (name, id = 0) => html`<span class="avatar" style="background:${COLORS[(id || name.length) % COLORS.length]}">${initials(name)}</span>`;
const STATUS = { pending: ["Pending", ""], in_progress: ["In progress", "info"], escalated: ["Escalated", "warn"], done: ["Done", "ok"] };
const statusPill = (s) => html`<span class="pill ${STATUS[s][1]}"><span class="dot"></span>${STATUS[s][0]}</span>`;
const prioPill = (p) => html`<span class="pill prio-${p}">${p[0].toUpperCase() + p.slice(1)}</span>`;

// ------------------------------------------------------------------ state + nav
const S = { me: null, meta: null, notes: { items: [], unread: 0 }, ai: null, counts: {} };
const FORUM_ONLY_ROLES = new Set(["tester", "developer"]);

const NAV = {
  lead: [
    { id: "work", label: "Work", items: [["overview", "Overview"], ["board", "Task board"], ["weekly-report", "Weekly report"], ["leave", "Leave"]] },
    { id: "knowledge", label: "Knowledge", items: [["assistant", "Ask the SOPs"], ["needs-lead", "Needs lead", "needs"], ["sops", "SOP library"]] },
    { id: "community", label: "Community", items: [["forum", "Team forum"]] },
    { id: "records", label: "Records", items: [["vault", "Documents"], ["proof", "System proof"]] },
    { id: "presentation", label: "Presentation", items: [["demo", "Demo walkthrough"]] },
  ],
  member: [
    { id: "work", label: "Work", items: [["my-tasks", "My tasks"], ["assistant", "Ask the SOPs"], ["weekly-report", "Weekly report"], ["leave", "Leave"]] },
    { id: "community", label: "Community", items: [["forum", "Team forum"]] },
    { id: "records", label: "Records", items: [["vault", "My documents"]] },
  ],
  hr: [
    { id: "people", label: "People", items: [["vault", "Document vault"], ["interviews", "Interviews"]] },
    { id: "knowledge", label: "Knowledge", items: [["assistant", "Ask the SOPs"], ["proof", "System proof"]] },
    { id: "community", label: "Community", items: [["forum", "Team forum"]] },
    { id: "presentation", label: "Presentation", items: [["demo", "Demo walkthrough"]] },
  ],
  admin: [
    { id: "work", label: "Work", items: [["overview", "Overview"], ["board", "Task board"]] },
    { id: "knowledge", label: "Knowledge", items: [["assistant", "Ask the SOPs"], ["needs-lead", "Needs lead", "needs"], ["sops", "SOP library"]] },
    { id: "community", label: "Community", items: [["forum", "Team forum"]] },
    { id: "records", label: "Records", items: [["vault", "Document vault"], ["audit", "Audit log"], ["interviews", "Interviews"]] },
    { id: "system", label: "System", items: [["proof", "System proof"], ["demo", "Demo walkthrough"]] },
  ],
  interviewer: [
    { id: "interviews", label: "Interviews", items: [["my-interviews", "My interviews"], ["availability", "Availability"]] },
    { id: "community", label: "Community", items: [["forum", "Team forum"]] },
  ],
  tester: [{ id: "community", label: "Community", items: [["forum", "Team forum"]] }],
  developer: [{ id: "community", label: "Community", items: [["forum", "Team forum"]] }],
};
const HOME = { lead: "overview", member: "my-tasks", hr: "vault", admin: "overview", interviewer: "my-interviews",
  tester: "forum", developer: "forum" };
const NAV_ICONS = {
  overview: '<path d="M3 3.5h4v4H3zM9 3.5h4v4H9zM3 9h4v4H3zM9 9h4v4H9z"/>',
  board: '<rect x="2.5" y="3" width="4" height="10" rx="1"/><rect x="9.5" y="3" width="4" height="6" rx="1"/>',
  "my-tasks": '<path d="m3.3 8.2 2.4 2.4 6-6"/><path d="M12.5 8v4a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h5"/>',
  assistant: '<path d="m8 2.5 1.4 4.1 4.1 1.4-4.1 1.4L8 13.5l-1.4-4.1-4.1-1.4 4.1-1.4z"/>',
  "needs-lead": '<circle cx="8" cy="8" r="5.5"/><path d="M8 5v3.5M8 11.2v.1"/>',
  sops: '<path d="M4 2.8h5l3 3v7.4H4z"/><path d="M9 2.8v3h3M6 8.5h4M6 10.8h4"/>',
  forum: '<path d="M2.8 3.5h10.4v7H8l-3.1 2.2v-2.2H2.8z"/>',
  vault: '<path d="M3.3 2.8h6l3.4 3.4v7H3.3z"/><path d="M9.3 2.8v3.4h3.4M5.5 8h5M5.5 10.3h5"/>',
  proof: '<path d="m8 2.5 4.5 1.8v3.4c0 2.4-1.7 4.2-4.5 5.8-2.8-1.6-4.5-3.4-4.5-5.8V4.3z"/><path d="m5.8 7.8 1.5 1.5 3-3"/>',
  demo: '<path d="M5 3.5v9l7-4.5z"/>',
  interviews: '<rect x="2.8" y="4" width="10.4" height="9" rx="1"/><path d="M5.5 2.5v3M10.5 2.5v3M2.8 7h10.4"/>',
  "my-interviews": '<rect x="2.8" y="4" width="10.4" height="9" rx="1"/><path d="M5.5 2.5v3M10.5 2.5v3M2.8 7h10.4M5.3 9.5h2.2"/>',
  availability: '<circle cx="8" cy="8" r="5.5"/><path d="M8 4.8v3.5l2.2 1.3"/>',
  "weekly-report": '<rect x="2.8" y="3" width="10.4" height="8" rx="1"/><path d="M5.5 3v3M10.5 3v3"/>',
  leave: '<path d="M12 3a2 2 0 0 0-2 2v7a2 2 0 0 0 4 0V5a2 2 0 0 0-2-2zM5 3a2 2 0 0 1 2 2v7a2 2 0 0 1-4 0V5a2 2 0 0 1 2-2z"/>',
  audit: '<path d="M3.5 3h9M3.5 6.5h9M3.5 10h6M3.5 13h9"/>',
  bell: '<path d="M4.6 6.8a3.4 3.4 0 0 1 6.8 0c0 4 1.5 4.2 1.5 5.3H3.1c0-1.1 1.5-1.3 1.5-5.3z"/><path d="M6.5 13.2a1.5 1.5 0 0 0 3 0"/>',
};
const navIcon = (id) => raw(`<svg class="nav-icon" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.45" stroke-linecap="round" stroke-linejoin="round">${NAV_ICONS[id] || NAV_ICONS.overview}</svg>`);

// ------------------------------------------------------------------ login
async function renderLogin() {
  const { users = [], password } = await api("/api/auth/demo-users").catch(() => ({ users: [] }));
  $("#root").innerHTML = html`
  <div class="login">
    <div class="hero">
      <div class="brand" style="padding:0"><span class="logo">LD</span> LeadDesk</div>
      <h1>Operations workspace</h1>
      <ul>
        <li>See workload, deadlines, and priorities in one view</li>
        <li>Answer team questions from verified SOP sources</li>
        <li>Keep HR documents encrypted and access controlled</li>
        <li>Coordinate interviews with independent booking and feedback</li>
      </ul>
    </div>
    <div class="panel">
      <h1>Sign in</h1>
      <p class="muted">${window.LEADDESK_PREVIEW_MODE ? "Choose a sample persona below. No real account is required." : "Use your username and password."}</p>
      <form id="lf" class="stack">
        <label class="f">Username <input class="input" name="username" autocomplete="username" required></label>
        <label class="f">Password <input class="input" name="password" type="password" autocomplete="current-password" required></label>
        <button class="btn primary big" type="submit">Sign in</button>
      </form>
      ${users.length ? html`<button class="btn big tour" id="tour">Open guided demo</button>
        <p class="muted tiny" id="tourhint" style="margin:6px 0 0">${window.LEADDESK_PREVIEW_MODE ? "Opens a guided tour of the sample workspace." : "Signs you in as a team lead and walks the whole product, one real action at a time."}</p>
        <h3 style="margin-top:24px">Demo: sign in as…</h3>
        <div class="persona">${users.map((u) => html`<button data-u="${u.username}"><b>${u.name}</b><span class="muted small">${u.role_label}${u.department && u.role === "hr" ? " · " + u.department : ""}${u.shift ? " · " + u.shift + " shift" : ""}</span></button>`)}</div>` : ""}
    </div>
  </div>`;
  const go = async (username, pw, target) => {
    try {
      const r = await api("/api/auth/login", { method: "POST", body: { username, password: pw } });
      closeModal();
      S.me = r.user;
      await boot();
      if (target) location.hash = target;
    }
    catch (e) { fail(e); }
  };
  $("#lf").onsubmit = (e) => { e.preventDefault(); const f = new FormData(e.target); go(f.get("username"), f.get("password")); };
  $$(".persona button").forEach((b) => (b.onclick = () => go(b.dataset.u, password)));
  const tour = $("#tour");
  if (tour) tour.onclick = () => { tour.disabled = true; $("#tourhint").textContent = "Signing in…"; go("lead", password, "#/demo"); };
}

function changePasswordDialog() {
  const ov = modal(html`<h2>Change your password</h2>
    <p class="muted small">Every other signed-in device is signed out when you save.</p>
    <form id="pwform" class="stack">
      <label class="f">Current password <input class="input" type="password" name="current" autocomplete="current-password" required></label>
      <label class="f">New password <input class="input" type="password" name="new" autocomplete="new-password" minlength="8" required></label>
      <label class="f">Repeat new password <input class="input" type="password" name="again" autocomplete="new-password" minlength="8" required></label>
      <div class="row"><button class="btn primary" type="submit">Save password</button>
        <button class="btn" type="button" data-close>Cancel</button></div>
    </form>`);
  ov.querySelector("#pwform").onsubmit = async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    if (f.get("new") !== f.get("again")) return fail(new Error("The two new passwords do not match."));
    const b = e.target.querySelector("button[type=submit]");
    b.disabled = true;
    try {
      await api("/api/auth/password", { method: "POST", body: { current: f.get("current"), new: f.get("new") } });
      closeModal();
      toast(window.LEADDESK_PREVIEW_MODE ? "Preview only; the password was not changed." : "Password changed. Other devices were signed out.", "ok");
    } catch (err) { fail(err); }
    b.disabled = false;
  };
}

// ------------------------------------------------------------------ shell
async function boot() {
  if (!S.me) {
    try { S.me = (await api("/api/auth/me")).user; } catch { return renderLogin(); }
  }
  const forumOnly = FORUM_ONLY_ROLES.has(S.me.role);
  if (forumOnly) {
    const health = await api("/api/health");
    skewMs = parseLocal(health.time) - Date.now();
    S.meta = null;
  } else {
    S.meta = await api("/api/meta");
    skewMs = parseLocal(S.meta.now) - Date.now();
  }
  renderShell();
  route();
  clearInterval(S.timer);
  if (!forumOnly) {
    refreshNotes(); refreshAI();
    S.timer = setInterval(() => { refreshNotes(); }, 20000);
  }
}

function preferenceKey(name) {
  return `leaddesk:${S.me.username}:${name}`;
}

function readPreference(name, fallback) {
  try {
    const value = localStorage.getItem(preferenceKey(name));
    return value === null ? fallback : value;
  } catch {
    return fallback;
  }
}

function savePreference(name, value) {
  try {
    localStorage.setItem(preferenceKey(name), value);
  } catch {
    return;
  }
}

function navGroupsClosed() {
  try {
    return JSON.parse(readPreference("nav-groups", "{}"));
  } catch {
    return {};
  }
}

function projectPath(kind, value) {
  const query = new URLSearchParams({ [kind === "department" ? "department" : "task_type"]: value });
  return kind === "department" ? `#/vault?${query}` : `#/${S.me.role === "member" ? "my-tasks" : "board"}?${query}`;
}

async function refreshProjects() {
  const box = $("#project-nav");
  if (!box) return;
  const projects = [];
  if (["lead", "admin", "member"].includes(S.me.role)) {
    const path = S.me.role === "member" ? "/api/tasks?mine=true" : "/api/tasks";
    const { tasks } = await api(path);
    const counts = new Map((S.meta.task_types || []).map((type) => [type, 0]));
    tasks.forEach((task) => {
      if (task.status !== "done") counts.set(task.task_type, (counts.get(task.task_type) || 0) + 1);
    });
    (S.meta.task_types || []).forEach((type) => projects.push({ kind: "task", value: type, count: counts.get(type) || 0 }));
  }
  if (["hr", "admin"].includes(S.me.role)) {
    const { employees } = await api("/api/vault/employees");
    const departments = S.me.role === "hr" ? [S.me.department].filter(Boolean)
      : [...new Set(employees.map((employee) => employee.department).filter(Boolean))].sort();
    departments.forEach((department) => projects.push({ kind: "department", value: department }));
  }
  box.classList.toggle("hidden", !projects.length);
  box.innerHTML = projects.length ? html`
    <div class="projects-heading">Projects</div>
    ${projects.map((project) => html`<a class="project-link" href="${projectPath(project.kind, project.value)}"
      data-project-kind="${project.kind}" data-project-value="${project.value}" title="${project.value}">
      <span class="project-label">${project.value}</span>
      ${project.kind === "task" ? html`<span class="project-count">${project.count}</span>` : ""}
    </a>`)}`.s : "";
  const selected = new URLSearchParams(location.hash.split("?")[1] || "");
  const kind = selected.has("department") ? "department" : "task";
  const value = selected.get(kind === "department" ? "department" : "task_type");
  $$(".project-link", box).forEach((link) => {
    link.classList.toggle("active", link.dataset.projectKind === kind && link.dataset.projectValue === value);
  });
}

function renderShell() {
  const me = S.me;
  const forumOnly = FORUM_ONLY_ROLES.has(me.role);
  const groups = NAV[me.role] || [];
  const closedGroups = navGroupsClosed();
  S.density = readPreference("density", "comfortable");
  const mobileTabs = me.role === "member"
    ? [["my-tasks", "My tasks"], ["assistant", "Ask SOPs"], ["forum", "Forum"]]
    : me.role === "hr"
      ? [["vault", "Documents"], ["assistant", "Ask SOPs"], ["forum", "Forum"]]
      : me.role === "interviewer"
        ? [["my-interviews", "Interviews"], ["availability", "Availability"], ["forum", "Forum"]]
        : me.role === "tester" || me.role === "developer"
          ? [["forum", "Forum"]]
          : [["board", "Task board"], ["assistant", "Ask SOPs"], ["forum", "Forum"]];
  $("#root").innerHTML = html`
  <div class="app" id="app">
    <aside class="side" aria-label="Primary navigation">
      <div class="brand-plate" aria-label="Tilted Lads">
        <span class="brand-mark" aria-hidden="true"><span></span></span>
        <span class="brand-copy"><b>Tilted Lads</b></span>
      </div>
      <nav class="nav" aria-label="Workspace">
        ${groups.map((group) => html`<section class="nav-group-block ${closedGroups[group.id] ? "is-closed" : ""}" data-nav-group="${group.id}">
          <button class="nav-group-toggle" type="button" aria-expanded="${closedGroups[group.id] ? "false" : "true"}">
            ${navIcon(group.items[0][0])}<span class="nav-group-label">${group.label}</span>
            <span class="nav-group-dot hidden" data-group-dot="${group.id}"></span>
            <span class="nav-chevron" aria-hidden="true">⌄</span>
          </button>
          <div class="nav-group-items">
            ${group.items.map(([id, label, badge]) => html`<a href="#/${id}" data-nav="${id}" title="${label}">
              ${navIcon(id)}<span class="nav-label">${label}</span>
              ${badge ? html`<span class="badge hidden" data-badge="${badge}"></span>` : ""}
            </a>`)}
          </div>
        </section>`)}
        <div class="project-nav hidden" id="project-nav"></div>
      </nav>
      <button class="profile-button" id="profile-menu" type="button" aria-haspopup="menu" aria-expanded="false">
        ${avatar(me.name, me.id)}
        <span class="profile-copy"><b>${me.name}</b><small>${me.role === "hr" ? `${me.role_label} · ${me.department}` : me.role_label}</small>
          ${me.shift ? html`<small class="profile-shift"><i></i>${me.shift} shift</small>` : ""}
        </span>
        <span class="profile-more" aria-hidden="true">···</span>
      </button>
    </aside>
    <main class="main" id="main-content">
      <div class="top">
        <button class="iconbtn nav-toggle" id="nav-toggle" type="button" aria-label="Open navigation" aria-expanded="false">
          <span aria-hidden="true">☰</span>
        </button>
        ${window.LEADDESK_PREVIEW_MODE ? html`<span class="pill warn">Preview · sample data, resets on refresh</span>` : ""}
        ${forumOnly && !window.LEADDESK_PREVIEW_MODE ? "" : html`${!forumOnly ? html`<span class="pill ai-pill" id="aipill">AI: checking…</span>` : ""}
          <div style="position:relative">
            <button class="iconbtn" id="bell" title="Notifications" aria-label="Notifications">${navIcon("bell")}<span class="n hidden" id="belln"></span></button>
            <div class="pop hidden" id="pop"></div>
          </div>
          <button class="density-button" id="density-toggle" type="button" aria-pressed="${S.density === "compact"}" title="Change row density">
            ${S.density === "compact" ? "Compact" : "Comfortable"}
          </button>
          <select class="input" id="switch" title="Demo: switch person" aria-label="Demo: switch person"></select>`}
      </div>
      <div class="content" id="view" tabindex="-1"></div>
    </main>
  </div>
  <button class="shell-scrim" id="shell-scrim" type="button" aria-label="Close navigation"></button>
  <nav class="mobile-tabs" aria-label="Quick navigation">
    ${mobileTabs.map(([id, label]) => html`<a href="#/${id}" data-mobile-nav="${id}" title="${label}">${navIcon(id)}<span>${label}</span></a>`)}
    <button type="button" id="more-nav" aria-label="More navigation" aria-expanded="false">
      <span class="more-icon" aria-hidden="true">···</span><span>More</span>
    </button>
  </nav>
  <div class="account-menu hidden" id="account-menu" role="menu" aria-label="Account options">
    <div class="account-menu-user"><b>${me.name}</b><small>${me.role_label}</small></div>
    <button type="button" role="menuitem" id="account-details">Accounts</button>
    <button type="button" role="menuitem" id="password-action">Change password</button>
    <button type="button" role="menuitemcheckbox" aria-checked="${S.density === "compact"}" id="density-action">
      ${S.density === "compact" ? "Comfortable density" : "Compact density"}
    </button>
    <div class="account-menu-divider"></div>
    <button type="button" role="menuitem" id="logout">Sign out</button>
  </div>`;
  const profile = $("#profile-menu");
  const accountMenu = $("#account-menu");
  profile.onclick = () => {
    const open = accountMenu.classList.toggle("hidden") === false;
    profile.setAttribute("aria-expanded", String(open));
  };
  $("#account-details").onclick = () => {
    accountMenu.classList.add("hidden");
    profile.setAttribute("aria-expanded", "false");
    accountDialog();
  };
  $("#password-action").onclick = () => {
    accountMenu.classList.add("hidden");
    profile.setAttribute("aria-expanded", "false");
    changePasswordDialog();
  };
  const setDensity = () => {
    S.density = S.density === "compact" ? "comfortable" : "compact";
    savePreference("density", S.density);
    document.body.classList.toggle("compact-mode", S.density === "compact");
    $("#density-toggle")?.setAttribute("aria-pressed", String(S.density === "compact"));
    if ($("#density-toggle")) $("#density-toggle").textContent = S.density === "compact" ? "Compact" : "Comfortable";
    $("#density-action").textContent = S.density === "compact" ? "Comfortable density" : "Compact density";
    $("#density-action").setAttribute("aria-checked", String(S.density === "compact"));
  };
  $("#density-toggle")?.addEventListener("click", setDensity);
  $("#density-action").onclick = setDensity;
  document.body.classList.toggle("compact-mode", S.density === "compact");
  $("#logout").onclick = async () => {
    try {
      await api("/api/auth/logout", { method: "POST" });
      closeModal(); S.me = null; location.hash = ""; renderLogin();
    } catch (error) { fail(error); }
  };
  const bell = $("#bell");
  if (bell) bell.onclick = toggleNotes;
  $("#nav-toggle").onclick = () => setNavOpen(true);
  $("#shell-scrim").onclick = () => setNavOpen(false);
  $("#more-nav").onclick = () => {
    const open = !document.body.classList.contains("nav-open");
    setNavOpen(open);
    $("#more-nav").setAttribute("aria-expanded", String(open));
  };
  $$(".nav-group-toggle").forEach((button) => {
    button.onclick = () => {
      const group = button.closest("[data-nav-group]");
      const collapsed = group.classList.toggle("is-closed");
      button.setAttribute("aria-expanded", String(!collapsed));
      closedGroups[group.dataset.navGroup] = collapsed;
      savePreference("nav-groups", JSON.stringify(closedGroups));
    };
  });
  if (!S.shellListeners) {
    document.addEventListener("mousedown", (e) => {
      if (!e.target.closest("#pop") && !e.target.closest("#bell")) $("#pop")?.classList.add("hidden");
      if (!e.target.closest("#account-menu") && !e.target.closest("#profile-menu")) {
        $("#account-menu")?.classList.add("hidden");
        $("#profile-menu")?.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") setNavOpen(false);
    });
    S.shellListeners = true;
  }
  api("/api/auth/demo-users").then(({ users, password }) => {
    const sel = $("#switch");
    if (!sel) return;
    if (!users.length) return sel.remove();
    sel.innerHTML = `<option value="">Switch…</option>` + users.map((u) => `<option value="${esc(u.username)}">${esc(u.name)} - ${esc(u.role_label)}</option>`).join("");
    sel.onchange = async () => {
      if (!sel.value) return;
      try {
        const r = await api("/api/auth/login", { method: "POST", body: { username: sel.value, password } });
        closeModal(); S.me = r.user; location.hash = ""; await boot();
      } catch (error) { fail(error); }
    };
  }).catch(fail);
}

function setNavOpen(open) {
  document.body.classList.toggle("nav-open", open);
  $("#nav-toggle")?.setAttribute("aria-expanded", String(open));
  $("#more-nav")?.setAttribute("aria-expanded", String(open));
  $("#nav-toggle")?.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
}

function accountDialog() {
  const me = S.me;
  modal(html`<div class="modal-head"><h2>Account</h2><button class="x" data-close aria-label="Close">×</button></div>
    <dl class="account-details">
      <div><dt>Name</dt><dd>${me.name}</dd></div>
      <div><dt>Username</dt><dd>${me.username}</dd></div>
      <div><dt>Role</dt><dd>${me.role_label}</dd></div>
      ${me.department ? html`<div><dt>Department</dt><dd>${me.department}</dd></div>` : ""}
      ${me.shift ? html`<div><dt>Shift</dt><dd>${me.shift}</dd></div>` : ""}
    </dl>
    <div class="row"><button class="btn" type="button" id="account-password">Change password</button></div>`);
  $("#account-password").onclick = changePasswordDialog;
}

async function refreshAI() {
  try {
    const st = await api("/api/sop/status"); S.ai = st;
    const p = $("#aipill"); if (!p) return;
    if (window.LEADDESK_PREVIEW_MODE) {
      p.className = "pill ai-pill warn";
      p.textContent = "Sample responses · no AI connected";
      p.title = st.detail;
      return;
    }
    p.className = "pill ai-pill " + (st.online ? "ok" : "warn");
    p.innerHTML = st.online ? `<span class="dot"></span>Local AI online · ${esc(st.model)}` : `<span class="dot"></span>AI offline · quoting SOP sections`;
    p.title = st.online ? `Running on your machine via Ollama (${st.url})` : st.detail;
  } catch { /* ignore */ }
}

async function refreshNotes() {
  try {
    S.notes = await api("/api/notifications");
    const n = $("#belln"); if (!n) return;
    n.textContent = S.notes.unread; n.classList.toggle("hidden", !S.notes.unread);
    if (["lead", "admin"].includes(S.me.role)) {
      const c = await api("/api/sop/questions?status=needs_lead");
      const needs = c.counts.needs_lead || 0;
      $$("[data-badge=needs]").forEach((b) => { b.textContent = needs; b.classList.toggle("hidden", !needs); });
      $$("[data-group-dot=knowledge]").forEach((dot) => dot.classList.toggle("hidden", !needs));
    }
  } catch { /* ignore */ }
}

function toggleNotes() {
  const pop = $("#pop");
  if (!pop.classList.contains("hidden")) return pop.classList.add("hidden");
  pop.innerHTML = S.notes.items.length ? S.notes.items.map((n) => `<div class="it ${n.read ? "" : "unread"}" data-link="${esc(n.link || "")}">${esc(n.text)}<div class="muted tiny">${esc(fmtDT(n.at))}</div></div>`).join("")
    : `<div class="empty">No notifications yet</div>`;
  pop.classList.remove("hidden");
  $$(".it", pop).forEach((it) => (it.onclick = () => { if (it.dataset.link) location.hash = it.dataset.link.replace(/^#/, "#"); pop.classList.add("hidden"); }));
  api("/api/notifications/read", { method: "POST" }).then(() => { $("#belln").classList.add("hidden"); S.notes.unread = 0; });
}

const VIEWS = {};
function route() {
  if (!S.me) return;
  const [path, qs] = (location.hash.replace(/^#\/?/, "") || HOME[S.me.role]).split("?");
  const params = Object.fromEntries(new URLSearchParams(qs || ""));
  const groups = NAV[S.me.role] || [];
  const allowed = groups.flatMap((group) => group.items.map((item) => item[0]));
  const id = allowed.includes(path) ? path : HOME[S.me.role];
  $$(".nav a").forEach((a) => {
    const active = a.dataset.nav === id;
    a.classList.toggle("active", active);
    if (active) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  const selectedProject = params.department || params.task_type || "";
  $$(".project-link").forEach((link) => {
    const active = link.dataset.projectValue === selectedProject;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  $$(".mobile-tabs [data-mobile-nav]").forEach((link) => {
    const active = link.dataset.mobileNav === id;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  setNavOpen(false);
  const view = $("#view");
  view.innerHTML = `<div class="empty">Loading…</div>`;
  Promise.resolve(VIEWS[id](view, params)).catch((e) => { view.innerHTML = html`<div class="alert bad">${e.message}</div>`.s; });
  refreshProjects().catch(fail);
}
window.addEventListener("hashchange", route);

async function drawForum(el) {
  const { posts } = await api("/api/forum/posts");
  el.innerHTML = html`
    <div class="page-head"><div class="grow"><h1>Team forum</h1><p>Share updates, ask questions, and reply across the team.</p></div>
      <button class="btn primary" id="new-forum-post">Start a discussion</button></div>
    ${posts.length ? html`<div class="grid">${posts.map((post) => html`
      <article class="card forum-card">
        <div class="row"><div>${avatar(post.author_name, post.id)}</div><div><b>${post.author_name}</b>
          <div class="muted tiny">${post.author_role_label} · ${fmtDT(post.updated_at)}</div></div>
          <span class="pill">${post.reply_count} ${post.reply_count === 1 ? "reply" : "replies"}</span></div>
        <h2 class="forum-title">${post.title}</h2><p class="forum-body">${post.body}</p>
        <button class="btn sm" data-thread="${post.id}">Open discussion</button>
      </article>`)}</div>` : html`<div class="card empty">No discussions yet. Start one to get the conversation going.</div>`}`;
  $("#new-forum-post", el).onclick = () => openForumPost(el);
  $$("[data-thread]", el).forEach((button) => {
    button.onclick = () => showForumThread(+button.dataset.thread, el).catch(fail);
  });
}

function openForumPost(el) {
  const ov = modal(html`
    <div class="page-head"><div class="grow"><h2>Start a discussion</h2></div><button class="btn sm" data-close>Close</button></div>
    <form id="forum-post-form" class="stack">
      <label class="f">Title <input class="input" name="title" maxlength="120" required></label>
      <label class="f">Message <textarea class="input forum-input" name="body" rows="6" maxlength="5000" required></textarea></label>
      <div class="row"><span class="grow"></span><button class="btn primary" type="submit">Post discussion</button></div>
    </form>`.s, { wide: true });
  $("#forum-post-form", ov).onsubmit = async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const button = $("button[type=submit]", event.currentTarget);
    button.disabled = true;
    try {
      const { post } = await api("/api/forum/posts", {
        method: "POST",
        body: { title: form.get("title"), body: form.get("body") },
      });
      closeModal();
      await drawForum(el);
      await showForumThread(post.id, el);
    } catch (error) {
      fail(error);
      button.disabled = false;
    }
  };
}

async function showForumThread(id, el) {
  const { post, replies } = await api(`/api/forum/posts/${id}`);
  const ov = modal(html`
    <div class="page-head"><div class="grow"><h2>${post.title}</h2></div><button class="btn sm" data-close>Close</button></div>
    <div class="muted small">Started by <b>${post.author_name}</b> · ${post.author_role_label} · ${fmtDT(post.created_at)}</div>
    <p class="forum-body forum-thread-body">${post.body}</p>
    <h3>${replies.length} ${replies.length === 1 ? "reply" : "replies"}</h3>
    ${replies.length ? html`<div class="forum-replies">${replies.map((reply) => html`
      <article class="forum-reply"><div class="row"><b>${reply.author_name}</b><span class="muted tiny">${reply.author_role_label} · ${fmtDT(reply.created_at)}</span></div>
        <p class="forum-body">${reply.body}</p></article>`)}</div>` : html`<p class="muted small">No replies yet.</p>`}
    <form id="forum-reply-form" class="stack">
      <label class="f">Add a reply <textarea class="input forum-input" name="body" rows="3" maxlength="3000" required></textarea></label>
      <div class="row"><span class="grow"></span><button class="btn primary" type="submit">Reply</button></div>
    </form>`.s, { wide: true });
  $("#forum-reply-form", ov).onsubmit = async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const button = $("button[type=submit]", event.currentTarget);
    button.disabled = true;
    try {
      await api(`/api/forum/posts/${id}/replies`, { method: "POST", body: { body: form.get("body") } });
      await drawForum(el);
      await showForumThread(id, el);
    } catch (error) {
      fail(error);
      button.disabled = false;
    }
  };
}

VIEWS.forum = drawForum;

async function drawLeave(el) {
  const r = await api("/api/leaves");
  const canDecide = ["lead", "admin", "hr"].includes(S.me.role);
  el.innerHTML = html`
    <div class="page-head">
      <div class="grow"><h1>Leave</h1><p>Time away from the shift.</p></div>
      ${canDecide ? html`<button class="btn primary" id="leave-new">Request leave</button>` : ""}
    </div>
    <section class="panel">
      <header class="panel-head"><div><h2>Leave requests</h2><p>Submitted leave with its decision</p></div></header>
      <div class="panel-body">
        ${r.leaves.length ? html`<div>${r.leaves.map((l) => html`
          <div class="card" style="padding:14px">
            <div class="row">
              <span class="grow"><b>${l.user_name}</b> <span class="muted small">${l.user_role}</span></span>
              <span class="pill ${l.status === "approved" ? "ok" : l.status === "rejected" ? "bad" : "warn"}">${l.status}</span>
              ${canDecide && l.status === "pending" ? html`
                <button class="btn sm" data-leave-decide="${l.id}" data-decide="approved">Approve</button>
                <button class="btn sm" data-leave-decide="${l.id}" data-decide="rejected">Reject</button>
              ` : ""}
            </div>
            <div class="muted small">${l.start_date} → ${l.end_date}</div>
            ${l.reason ? html`<div class="small">${l.reason}</div>` : ""}
          </div>`)}` : html`<div class="empty-state">No leave requests yet</div>`}
      </div>
    </section>
    ${canDecide ? html`
      <section class="panel">
        <header class="panel-head"><div><h2>Request leave</h2><p>For a team member</p></div></header>
        <form class="panel-body" id="leave-form">
          <div class="row">
            <label class="grow"><span class="small">From</span><input type="date" name="start_date" required /></label>
            <label class="grow"><span class="small">To</span><input type="date" name="end_date" required /></label>
          </div>
          <label class="block"><span class="small">Reason</span><input name="reason" maxlength="1000" /></label>
          <button class="btn primary" type="submit">Submit leave</button>
        </form>
      </section>` : ""}
  `;
  if (canDecide) {
    $$("[data-leave-decide]", el).forEach((b) => (b.onclick = async () => {
      await api(`/api/leaves/${b.dataset.leave}/decide`, { method: "POST", body: { status: b.dataset.decide } });
      await drawLeave(el);
    }));
  }
  const form = $("#leave-form", el);
  if (form) {
    form.onsubmit = async (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      await api("/api/leaves", { method: "POST", body: { start_date: String(fd.get("start_date") || ""), end_date: String(fd.get("end_date") || ""), reason: String(fd.get("reason") || "") } });
      await drawLeave(el);
    };
  }
};

VIEWS["leave"] = drawLeave;

// ------------------------------------------------------------------ weekly report (impact numbers)
VIEWS["weekly-report"] = async (el) => {
  const r = await api("/api/impact");
  const a = r.assistant, b = r.board, v = r.vault, iv = r.interviews;
  el.innerHTML = html`
    <div class="page-head">
      <div class="grow"><h1>Weekly report</h1><p>Impact numbers for the last ${r.window_days} days.</p></div>
    </div>
    <div class="metric-strip">
      <button class="metric-card" data-go="board?filter=overdue"><span class="metric-label">Open tasks</span><strong>${b.tasks}</strong><span class="metric-trend">${b.overdue} overdue</span></button>
      <button class="metric-card" data-go="board?filter=today"><span class="metric-label">Due today</span><strong>${b.due_today}</strong><span class="metric-trend warn">Next 24 hours</span></button>
      <button class="metric-card" data-go="board?filter=escalated"><span class="metric-label">Escalated</span><strong>${b.escalated}</strong><span class="metric-trend">Active issues</span></button>
      <button class="metric-card" data-go="board"><span class="metric-label">Overloaded</span><strong>${b.overloaded}</strong><span class="metric-trend">${b.busiest ? `Busiest: ${b.busiest.name}` : "No data"}</span></button>
      <button class="metric-card" data-go="assistant"><span class="metric-label">Assistant answer rate</span><strong>${a.answer_rate_pct}%</strong><span class="metric-trend">${a.hours_saved} h saved</span></button>
      <button class="metric-card" data-go="interviews"><span class="metric-label">Interviews booked</span><strong>${iv.upcoming}</strong><span class="metric-trend">${iv.feedback_pending} feedback pending</span></button>
    </div>
    <div class="dashboard-grid">
      <section class="panel">
        <header class="panel-head"><div><h2>Assistant</h2><p>SOP questions asked and answered</p></div></header>
        <div class="panel-body">
          <div class="metric-strip">
            <span class="metric-card"><span class="metric-label">Asked</span><strong>${a.asked}</strong></span>
            <span class="metric-card"><span class="metric-label">Answered</span><strong>${a.answered}</strong></span>
            <span class="metric-card"><span class="metric-label">Answer rate</span><strong>${a.answer_rate_pct}%</strong></span>
          </div>
        </div>
      </section>
      <section class="panel">
        <header class="panel-head"><div><h2>Work</h2><p>Open tasks and deadlines</p></div><button class="text-action" data-go="board">Task board</button></header>
        <div class="panel-body">
          <div class="metric-strip">
            <span class="metric-card"><span class="metric-label">Tasks</span><strong>${b.tasks}</strong></span>
            <span class="metric-card"><span class="metric-label">Overdue</span><strong>${b.overdue}</strong></span>
            <span class="metric-card"><span class="metric-label">Due today</span><strong>${b.due_today}</strong></span>
          </div>
        </div>
      </section>
      <aside class="dashboard-side">
        <section class="panel attention-panel">
          <header class="panel-head"><div><h2>Interviews</h2><p>Upcoming and feedback</p></div><button class="text-action" data-go="interviews">Interviews</button></header>
          <div class="panel-body">
            <div class="metric-strip">
              <span class="metric-card"><span class="metric-label">Upcoming</span><strong>${iv.upcoming}</strong></span>
              <span class="metric-card"><span class="metric-label">Hours booked</span><strong>${iv.hours_booked}</strong></span>
              <span class="metric-card"><span class="metric-label">Feedback pending</span><strong>${iv.feedback_pending}</strong></span>
            </div>
          </div>
        </section>
      </aside>
    </div>
    <section class="panel recent-panel">
      <header class="panel-head"><div><h2>Assumptions</h2><p>Every number is a named count over demo data</p></div></header>
      <div class="panel-body">
        <ul class="muted small" style="margin:0;padding-left:18px">${r.assumptions.map((x) => html`<li>${x}</li>`).join("")}</ul>
      </div>
    </section>`;
  $$("[data-go]", el).forEach((k) => (k.onclick = () => (location.hash = "#/" + k.dataset.go)));
};

// ------------------------------------------------------------------ overview (lead)
VIEWS.overview = async (el) => {
  const [w, qs] = await Promise.all([api("/api/workload"), api("/api/sop/questions?status=needs_lead")]);
  const t = w.totals;
  const peopleNeedingHelp = w.members.filter((m) => m.needs_help).sort((a, b) => b.overdue - a.overdue || b.open - a.open);
  const helpers = peopleNeedingHelp.slice(0, 5);
  const maxOpen = Math.max(w.threshold + 2, ...w.members.map((m) => m.open));
  const chartMembers = w.members.slice(0, 7);
  const maxOverdue = Math.max(4, ...chartMembers.map((m) => m.overdue));
  const chartTicks = (max) => [max, Math.round(max * .75), Math.round(max * .5), Math.round(max * .25), 0];
  el.innerHTML = html`
  <div class="page-head">
    <div class="grow"><h1>Good ${nowServer().getHours() < 12 ? "morning" : nowServer().getHours() < 17 ? "afternoon" : "evening"}, ${S.me.name.split(" ")[0]}</h1>
      <p>${t.open} open tasks across ${t.members} people · updated ${fmtTime(parseLocal(w.now))}</p></div>
    <button class="btn" id="exp">Export report</button>
    <button class="btn primary" id="newt"><span aria-hidden="true">+</span> New task</button>
  </div>
  <div class="metric-strip">
    <button class="metric-card" data-go="board?filter=overdue"><span class="metric-label">Overdue</span><strong>${t.overdue}</strong><span class="metric-trend bad">Needs action</span></button>
    <button class="metric-card" data-go="board?filter=today"><span class="metric-label">Due today</span><strong>${t.due_today}</strong><span class="metric-trend warn">Next 24 hours</span></button>
    <button class="metric-card" data-go="board?filter=escalated"><span class="metric-label">Escalated</span><strong>${t.escalated}</strong><span class="metric-trend">Active issues</span></button>
    <button class="metric-card" data-go="board"><span class="metric-label">Open workload</span><strong>${t.open}</strong><span class="metric-trend">${t.overloaded} overloaded</span></button>
  </div>
  <div class="dashboard-grid">
    <section class="panel workload-panel">
      <header class="panel-head">
        <div><h2>Team workload</h2><p>Open tasks by team member</p></div>
        <div class="seg view-tabs" id="workload-tabs">
          <button class="on" type="button" data-chart="open" aria-pressed="true">Open</button>
          <button type="button" data-chart="overdue" aria-pressed="false">Overdue</button>
        </div>
      </header>
      <div class="chart-shell">
        <div class="chart-y">${chartTicks(maxOpen).map((tick) => html`<span>${tick}</span>`)}</div>
        <div class="bar-chart" id="bar-chart">
          ${chartMembers.map((m) => html`
            <button class="bar-item" type="button" data-member="${m.id}" data-name="${m.name}" aria-label="${m.name}: ${m.open} open tasks" title="${m.name}: ${m.open} open tasks">
              <span class="bar-track"><span class="bar-fill ${m.overloaded ? "bar-danger" : m.open >= w.threshold - 1 ? "bar-warn" : ""}" data-open="${m.open}" data-overdue="${m.overdue}" style="height:${Math.max(7, (m.open / maxOpen) * 100)}%"></span></span>
              <span class="bar-name">${m.name.split(" ")[0]} ${m.name.split(" ").slice(-1)[0][0]}<small>${m.open}</small></span>
            </button>
          `)}
        </div>
      </div>
      <footer class="panel-foot">
        <span data-chart-legend="open"><i class="legend-dot normal"></i>Within capacity</span>
        <span data-chart-legend="open"><i class="legend-dot warning"></i>Near limit</span>
        <span data-chart-legend="open"><i class="legend-dot danger"></i>Overloaded</span>
        <span class="hidden" data-chart-legend="overdue"><i class="legend-dot danger"></i>Has overdue tasks</span>
        <button class="text-action" id="show-all">View all people</button>
      </footer>
    </section>
    <aside class="dashboard-side">
      <section class="panel attention-panel">
        <header class="panel-head"><div><h2>Needs attention</h2><p>People with the highest risk</p></div><button class="icon-action" id="attention-next" aria-label="View all">›</button></header>
        ${helpers.length ? html`<div class="attention-list">${helpers.map((m) => html`<button class="attention-row" data-member="${m.id}">
          ${avatar(m.name, m.id)}<span class="grow"><b>${m.name}</b><small>${m.overdue ? `${m.overdue} overdue` : `${m.open} open tasks`}</small></span><span class="chevron">›</span>
        </button>`)}</div>` : html`<div class="empty-state">No people need attention</div>`}
      </section>
      <section class="panel concise-panel">
        <button class="concise-row" data-go="needs-lead"><span><small>Unanswered questions</small><strong>${qs.counts.needs_lead || 0}</strong></span><span class="chevron">›</span></button>
        <button class="concise-row" data-go="board?filter=overdue"><span><small>Past deadline</small><strong>${t.overdue}</strong></span><span class="chevron">›</span></button>
      </section>
    </aside>
  </div>
  <section class="panel recent-panel">
    <header class="panel-head"><div><h2>At risk</h2><p>Tasks requiring the next action</p></div><button class="text-action" id="view-risk">View task board</button></header>
    ${w.at_risk.length ? html`<div class="risk-table">${w.at_risk.slice(0, 5).map((x) => html`<button class="risk-row" data-task="${x.id}">
      <span class="risk-status ${x.overdue ? "bad" : "warn"}"></span>
      <span class="risk-name"><strong>${x.title}</strong><small>${x.assignee_name || "Unassigned"} · ${x.task_type}</small></span>
      <span class="risk-meta ${x.overdue ? "bad" : ""}">${x.overdue ? rel(x.deadline) : x.status === "escalated" ? "Escalated" : "Due " + fmtTime(parseLocal(x.deadline))}</span>
      <span class="chevron">›</span>
    </button>`)}</div>` : html`<div class="empty-state">No tasks are at risk</div>`}
  </section>`;
  $$("[data-go]", el).forEach((k) => (k.onclick = () => (location.hash = "#/" + k.dataset.go)));
  $$("[data-member]", el).forEach((r) => (r.onclick = () => (location.hash = "#/board?member=" + r.dataset.member)));
  $$("[data-task]", el).forEach((r) => (r.onclick = () => openTask(+r.dataset.task, () => route())));
  $("#newt").onclick = () => taskForm(null, () => route());
  $("#exp").onclick = () => exportMenu();
  const showPeople = (title, people, description) => {
    const ov = modal(html`
      <div class="modal-head"><h2>${title}</h2><button class="x" type="button" data-close aria-label="Close">×</button></div>
      <p class="muted small">${description}</p>
      ${people.length ? html`<div class="people-list">${people.map((m) => html`
        <button class="people-list-row" type="button" data-person="${m.id}" aria-label="View tasks for ${m.name}">
          ${avatar(m.name, m.id)}
          <span class="grow"><b>${m.name}</b><small>${m.open} open · ${m.overdue} overdue</small></span>
          <span class="pill ${m.overloaded ? "bad" : m.open >= w.threshold - 1 ? "warn" : "ok"}">${m.overloaded ? "Overloaded" : m.open >= w.threshold - 1 ? "Near limit" : "Within capacity"}</span>
          <span class="chevron" aria-hidden="true">›</span>
        </button>`)}</div>` : html`<div class="empty-state">No people need attention</div>`}
    `);
    $$("[data-person]", ov).forEach((button) => {
      button.onclick = () => {
        closeModal();
        location.hash = "#/board?member=" + button.dataset.person;
      };
    });
  };
  $("#show-all").onclick = () => showPeople("All team members", w.members, "Choose a person to see their tasks on the board.");
  $("#view-risk").onclick = () => (location.hash = "#/board");
  $("#attention-next").onclick = () => showPeople("People needing attention", peopleNeedingHelp, "People with overdue work or workload above the team limit.");
  $$("#workload-tabs button", el).forEach((tab) => tab.onclick = () => {
    const metric = tab.dataset.chart;
    const max = metric === "open" ? maxOpen : maxOverdue;
    const ticks = chartTicks(max);
    $$("#workload-tabs button", el).forEach((item) => {
      const selected = item === tab;
      item.classList.toggle("on", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    $$("[data-chart-legend]", el).forEach((item) => item.classList.toggle("hidden", item.dataset.chartLegend !== metric));
    $(".workload-panel .panel-head p", el).textContent = metric === "open" ? "Open tasks by team member" : "Overdue tasks by team member";
    $$(".chart-y span", el).forEach((tick, index) => { tick.textContent = ticks[index]; });
    $$(".bar-fill", el).forEach((bar) => {
      const value = +bar.dataset[metric];
      const item = bar.closest(".bar-item");
      const name = item.querySelector(".bar-name small");
      const label = metric === "open" ? "open tasks" : "overdue tasks";
      bar.style.height = `${value ? Math.max(7, (value / max) * 100) : 0}%`;
      bar.className = `bar-fill ${metric === "overdue" ? (value > 0 ? "bar-danger" : "") : bar.dataset.open >= w.threshold - 1 ? "bar-warn" : ""}`;
      name.textContent = value;
      item.title = `${item.dataset.name}: ${value} ${label}`;
      item.setAttribute("aria-label", `${item.dataset.name}: ${value} ${label}`);
    });
  });
};

function exportMenu() {
  modal(html`<div class="modal-head"><h2>Download workload report</h2><button class="x" data-close>×</button></div>
    <p class="muted">Per-person open, overdue and due-today counts, plus every task at risk.</p>
    <div class="row"><a class="btn primary" href="/api/workload/export?fmt=xlsx">Excel (.xlsx)</a><a class="btn" href="/api/workload/export?fmt=csv">CSV</a></div>`.s);
}

// ------------------------------------------------------------------ task board (lead)
VIEWS.board = async (el, params) => {
  const { tasks } = await api("/api/tasks");
  const M = S.meta;
  el.innerHTML = html`
  <div class="page-head">
    <div class="grow"><h1>${params.task_type ? `Task board · ${params.task_type}` : "Task board"}</h1><p>Drag a card to change its status. Click a card for details and history.</p></div>
    <button class="btn primary" id="newt">New task</button>
  </div>
  ${params.task_type ? html`<p class="filter-context">Showing ${params.task_type} <a href="#/board">Clear queue filter</a></p>` : ""}
  <div class="card" style="padding:12px;margin-bottom:14px">
    <div class="row">
      <input class="input grow" id="fq" placeholder="Search tasks…" style="min-width:180px">
      <select class="input" id="fm"><option value="">Everyone</option><option value="none">Not assigned</option>${M.members.map((m) => html`<option value="${m.id}">${m.name} (${m.shift})</option>`)}</select>
      <select class="input" id="ft"><option value="">All task types</option>${M.task_types.map((t) => html`<option>${t}</option>`)}</select>
      <select class="input" id="fp"><option value="">Any priority</option>${M.priorities.map((p) => html`<option value="${p}">${p}</option>`)}</select>
      <div class="seg" id="fw" aria-label="Task filters">
        <button type="button" data-w="" class="on" aria-pressed="true">All</button>
        <button type="button" data-w="overdue" aria-pressed="false">Overdue</button>
        <button type="button" data-w="today" aria-pressed="false">Due today</button>
        <button type="button" data-w="escalated" aria-pressed="false">Escalated</button>
      </div>
    </div>
  </div>
  <div class="board" id="board"></div>`;
  if (params.member) $("#fm").value = params.member;
  if (M.task_types.includes(params.task_type)) $("#ft").value = params.task_type;
  if (params.filter === "unassigned") $("#fm").value = "none";
  let when = ["overdue", "today", "escalated"].includes(params.filter) ? params.filter : "";
  $$("#fw button").forEach((b) => {
    const selected = b.dataset.w === when;
    b.classList.toggle("on", selected);
    b.setAttribute("aria-pressed", String(selected));
  });
  const draw = () => {
    const fq = $("#fq").value.toLowerCase(), fm = $("#fm").value, ft = $("#ft").value, fp = $("#fp").value;
    const list = tasks.filter((t) => (!fq || t.title.toLowerCase().includes(fq)) && (!fm || (fm === "none" ? !t.assignee_id : String(t.assignee_id) === fm))
      && (!ft || t.task_type === ft) && (!fp || t.priority === fp)
      && (!when || (when === "overdue" ? t.overdue : when === "today" ? t.due_today : t.status === "escalated")));
    $("#board").innerHTML = M.statuses.map((s) => {
      const items = list.filter((t) => t.status === s).sort((a, b) => (s === "done" ? b.deadline.localeCompare(a.deadline) : a.deadline.localeCompare(b.deadline)));
      return html`<div class="col" data-status="${s}">
        <div class="col-head">${statusPill(s)}<span class="n">${items.length}</span></div>
        ${items.slice(0, s === "done" ? 15 : 200).map((t) => html`<div class="tcard ${t.overdue ? "overdue" : t.due_today ? "today" : ""}" draggable="true" data-id="${t.id}">
          <div class="tt">${t.title}</div>
          <div class="meta">${prioPill(t.priority)}<span>${t.task_type}</span></div>
          <div class="meta" style="margin-top:6px">${t.assignee_name ? html`${avatar(t.assignee_name, t.assignee_id)}<span>${t.assignee_name}</span>` : html`<span class="pill warn">Not assigned</span>`}
            <span class="grow"></span><span class="${t.overdue ? "pill bad" : ""}" title="${t.deadline}">${t.status === "done" ? "Done" : t.overdue ? rel(t.deadline) : fmtDT(t.deadline)}</span></div>
        </div>`)}
        ${s === "done" && items.length > 15 ? html`<div class="muted small" style="text-align:center">+ ${items.length - 15} more</div>` : ""}
      </div>`.s;
    }).join("");
    $$(".tcard").forEach((c) => {
      c.onclick = () => openTask(+c.dataset.id, reload);
      c.ondragstart = (e) => e.dataTransfer.setData("text/plain", c.dataset.id);
    });
    $$(".col").forEach((col) => {
      col.ondragover = (e) => { e.preventDefault(); col.classList.add("drop"); };
      col.ondragleave = () => col.classList.remove("drop");
      col.ondrop = async (e) => {
        e.preventDefault(); col.classList.remove("drop");
        const id = +e.dataTransfer.getData("text/plain"); const t = tasks.find((x) => x.id === id);
        if (!t || t.status === col.dataset.status) return;
        try {
          const r = await api(`/api/tasks/${id}`, { method: "PATCH", body: { status: col.dataset.status } });
          Object.assign(t, r.task); draw(); toast(`Moved to ${STATUS[col.dataset.status][0]}`, "ok");
        } catch (er) { fail(er); }
      };
    });
  };
  const reload = async () => { const r = await api("/api/tasks"); tasks.splice(0, tasks.length, ...r.tasks); draw(); };
  ["#fq", "#fm", "#ft", "#fp"].forEach((s) => ($(s).oninput = draw));
  $$("#fw button").forEach((b) => (b.onclick = () => {
    when = b.dataset.w;
    $$("#fw button").forEach((item) => {
      const selected = item === b;
      item.classList.toggle("on", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    draw();
  }));
  $("#newt").onclick = () => taskForm(null, reload);
  draw();
  if (params.task) openTask(+params.task, reload);
};

function taskForm(task, done) {
  const M = S.meta;
  const d = new Date(nowServer()); d.setHours(d.getHours() + 3, 0, 0, 0);
  const t = task || { title: "", description: "", task_type: M.task_types[0], assignee_id: "", deadline: dtInput(d), priority: "medium", status: "pending" };
  const ov = modal(html`<div class="modal-head"><h2>${task ? "Edit task" : "New task"}</h2><button class="x" data-close>×</button></div>
    <form id="tf" class="stack">
      <label class="f">What needs doing? <input class="input" name="title" required minlength="2" value="${t.title}" placeholder="e.g. Reconcile HDFC account for 22 Nov"></label>
      <div class="form-grid">
        <label class="f">Assign to <select class="input" name="assignee_id"><option value="">- Not yet -</option>${M.members.map((m) => html`<option value="${m.id}" ${m.id === t.assignee_id ? raw("selected") : ""}>${m.name} (${m.shift})</option>`)}</select></label>
        <label class="f">Type <select class="input" name="task_type">${M.task_types.map((x) => html`<option ${x === t.task_type ? raw("selected") : ""}>${x}</option>`)}</select></label>
        <label class="f">Deadline (IST) <input class="input" type="datetime-local" name="deadline" required value="${t.deadline.slice(0, 16)}"></label>
        <label class="f">Priority <select class="input" name="priority">${M.priorities.map((p) => html`<option value="${p}" ${p === t.priority ? raw("selected") : ""}>${p}</option>`)}</select></label>
        <label class="f">Status <select class="input" name="status">${M.statuses.map((s) => html`<option value="${s}" ${s === t.status ? raw("selected") : ""}>${STATUS[s][0]}</option>`)}</select></label>
      </div>
      <div id="loadhint" class="small"></div>
      <label class="f">Notes (optional) <textarea class="input" name="description" rows="2">${t.description || ""}</textarea></label>
      <div class="row"><span class="grow"></span><button type="button" class="btn" data-close>Cancel</button><button class="btn primary">${task ? "Save" : "Create task"}</button></div>
    </form>`.s);
  $$("[data-close]", ov).forEach((b) => (b.onclick = closeModal));
  // Show the chosen person's current load so the lead picks someone with capacity.
  api("/api/workload").then((w) => {
    const sel = $("[name=assignee_id]", ov);
    const show = () => {
      const m = w.members.find((x) => String(x.id) === sel.value);
      $("#loadhint", ov).innerHTML = m ? `<span class="pill ${m.overloaded ? "bad" : m.open >= w.threshold - 1 ? "warn" : "ok"}">${esc(m.name)} has ${m.open} open task(s)${m.overdue ? `, ${m.overdue} overdue` : ""}${m.overloaded ? " - above the limit" : ""}</span>` : "";
    };
    $$("option", sel).forEach((o) => { const m = w.members.find((x) => String(x.id) === o.value); if (m) o.textContent += ` - ${m.open} open${m.overloaded ? " ⚠" : ""}`; });
    sel.onchange = show; show();
  });
  $("#tf", ov).onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    f.assignee_id = f.assignee_id ? +f.assignee_id : null;
    try {
      if (task) await api(`/api/tasks/${task.id}`, { method: "PATCH", body: f });
      else await api("/api/tasks", { method: "POST", body: f });
      closeModal(); toast(task ? "Task saved" : f.assignee_id ? "Task created - the person has been notified" : "Task created", "ok"); done && done();
    } catch (er) { fail(er); }
  };
}

async function openTask(id, done) {
  const [{ tasks }, { events }] = await Promise.all([api("/api/tasks" + (S.me.role === "member" ? "" : "")), api(`/api/tasks/${id}/history`)]);
  const t = tasks.find((x) => x.id === id);
  if (!t) return toast("Task not found", "bad");
  const isLead = ["lead", "admin"].includes(S.me.role);
  const ov = modal(html`<div class="modal-head"><h2>${t.title}</h2><button class="x" data-close>×</button></div>
    <div class="row" style="margin-bottom:12px">${statusPill(t.status)}${prioPill(t.priority)}<span class="pill">${t.task_type}</span>
      ${t.overdue ? html`<span class="pill bad">${rel(t.deadline)}</span>` : ""}</div>
    <div class="form-grid" style="margin-bottom:14px">
      <div><div class="muted small">Assigned to</div><b>${t.assignee_name || "Not assigned"}</b></div>
      <div><div class="muted small">Deadline</div><b>${fmtDT(t.deadline)}</b></div>
      <div><div class="muted small">Created by</div><b>${t.created_by_name || "-"}</b></div>
    </div>
    ${t.description ? html`<p>${t.description}</p>` : ""}
    <div class="row" style="margin-bottom:16px">
      ${t.status !== "in_progress" && t.status !== "done" ? html`<button class="btn" data-st="in_progress">▶ Start</button>` : ""}
      ${t.status !== "done" ? html`<button class="btn ok" data-st="done">✓ Mark done</button>` : html`<button class="btn" data-st="in_progress">↺ Reopen</button>`}
      ${t.status !== "escalated" && t.status !== "done" ? html`<button class="btn warn" data-st="escalated">⚑ Escalate</button>` : ""}
      ${isLead ? html`<span class="grow"></span><button class="btn" id="edit">✎ Edit / reassign</button>` : ""}
    </div>
    <h3>History</h3>
    <ul class="timeline">${events.map((e) => html`<li><b>${e.actor_name || "System"}</b> ${describeEvent(e)}
      <div class="muted tiny">${fmtDT(e.at)}</div>${e.note ? html`<div class="small" style="margin-top:3px">“${e.note}”</div>` : ""}</li>`)}</ul>`.s);
  $$("[data-st]", ov).forEach((b) => (b.onclick = async () => {
    if (b.dataset.st === "escalated") {
      reasonModal({
        title: "Escalate task",
        description: "Tell your team lead what is blocking the work.",
        label: "What is blocking you?",
        submitLabel: "Escalate task",
        required: !isLead,
        onSubmit: (note) => api(`/api/tasks/${id}`, { method: "PATCH", body: { status: b.dataset.st, note } }),
        onSuccess: () => { toast("Updated", "ok"); done && done(); },
        onCancel: () => openTask(id, done),
      });
      return;
    }
    try { await api(`/api/tasks/${id}`, { method: "PATCH", body: { status: b.dataset.st, note: null } }); closeModal(); toast("Updated", "ok"); done && done(); } catch (er) { fail(er); }
  }));
  const ed = $("#edit", ov); if (ed) ed.onclick = () => taskForm(t, done);
}
function describeEvent(e) {
  if (e.action === "created") return "created the task";
  if (e.action === "assigned") return raw(`assigned it to <b>${esc(e.to_value)}</b>`);
  if (e.action === "reassigned") return raw(`reassigned it from ${esc(e.from_value || "nobody")} to <b>${esc(e.to_value)}</b>`);
  if (e.action === "status") return raw(`changed status ${e.from_value ? esc(e.from_value) + " → " : "to "}<b>${esc(e.to_value)}</b>`);
  if (e.action === "note") return "added a note";
  return raw(`${esc(e.action)}: ${esc(e.from_value || "")} → <b>${esc(e.to_value || "")}</b>`);
}

// ------------------------------------------------------------------ my tasks (member)
VIEWS["my-tasks"] = async (el, params) => {
  const { tasks } = await api("/api/tasks?mine=true");
  const taskType = params.task_type || "";
  const scopedTasks = tasks.filter((task) => !taskType || task.task_type === taskType);
  const open = scopedTasks.filter((t) => t.status !== "done");
  const done = scopedTasks.filter((t) => t.status === "done").slice(-5).reverse();
  const order = (t) => (t.overdue ? 0 : t.due_today ? 1 : 2);
  open.sort((a, b) => order(a) - order(b) || a.deadline.localeCompare(b.deadline));
  el.innerHTML = html`
  <div class="page-head"><div class="grow"><h1>${taskType ? "My tasks · " + taskType : "My tasks"}</h1><p>${open.length} to do${open.filter((t) => t.overdue).length ? ` · ${open.filter((t) => t.overdue).length} overdue` : ""}. Stuck? Press “Need help” or ask the SOPs.</p></div>
    <a class="btn" href="#/assistant">Open SOP assistant</a></div>
  ${taskType ? html`<p class="filter-context">Showing ${taskType} <a href="#/my-tasks">Clear queue filter</a></p>` : ""}
  <div class="stack">
    ${open.length ? open.map((t) => html`    <div class="card mytask ${t.overdue ? "overdue" : t.due_today ? "today" : ""}">
      <div><div class="row" style="gap:8px;margin-bottom:6px">${statusPill(t.status)}${prioPill(t.priority)}<span class="pill">${t.task_type}</span></div>
        <h2 style="margin:0 0 4px;cursor:pointer" data-open="${t.id}">${t.title}</h2>
        <div class="${t.overdue ? "proof-bad" : "muted"}">Due ${fmtDT(t.deadline)} ${t.overdue ? "- " + rel(t.deadline) : ""}</div></div>
      <div class="acts">
        ${t.status === "pending" || t.status === "escalated" ? html`<button class="btn big" data-st="in_progress" data-id="${t.id}">▶ Start</button>` : ""}
        <button class="btn big ok" data-st="done" data-id="${t.id}">✓ Done</button>
        ${t.status !== "escalated" ? html`<button class="btn big" data-st="escalated" data-id="${t.id}">⚑ Need help</button>` : html`<span class="pill warn">Waiting for lead</span>`}
      </div></div>`) : html`<div class="card empty">Nothing assigned to you right now. 🎉</div>`}
    ${done.length ? html`<h3 class="muted" style="margin-top:24px">Recently finished</h3>${done.map((t) => html`<div class="card row" style="padding:10px 16px">${statusPill("done")}<span class="grow">${t.title}</span><span class="muted small">${fmtDT(t.done_at || t.deadline)}</span></div>`)}` : ""}
  </div>`;
  $$("[data-st]", el).forEach((b) => (b.onclick = async () => {
    if (b.dataset.st === "escalated") {
      reasonModal({
        title: "Ask for help",
        description: "Your team lead will see this note with the task.",
        label: "What is blocking you?",
        submitLabel: "Send to team lead",
        onSubmit: (note) => api(`/api/tasks/${b.dataset.id}`, { method: "PATCH", body: { status: b.dataset.st, note } }),
        onSuccess: () => { toast("Sent to your team lead", "ok"); route(); },
      });
      return;
    }
    try { await api(`/api/tasks/${b.dataset.id}`, { method: "PATCH", body: { status: b.dataset.st, note: null } }); toast("Updated", "ok"); route(); } catch (e) { fail(e); }
  }));
  $$("[data-open]", el).forEach((h) => (h.onclick = () => openTask(+h.dataset.open, route)));
  if (params.task) openTask(+params.task, route);
};

// ------------------------------------------------------------------ assistant
const SUGGEST = ["What do I do when error 402 appears?", "Who approves a refund above ₹10,000?", "Which form is used for a duplicate payment?",
  "What is the cut-off time for daily reconciliation?", "त्रुटि 402 आने पर क्या करें?", "₹10,000 થી વધુ રિફંડ કોણ મંજૂર કરે છે?"];

function answerBubble(r) {
  if (r.status === "needs_lead" || (!r.answer && r.status !== "resolved")) {
    return html`<div class="bubble a miss"><b>I couldn't find this in the SOPs.</b>
I've passed your question to your team lead${r.reason ? html` <span class="muted small">(${r.reason})</span>` : ""}. You'll get a notification when they answer.</div>`;
  }
  return html`<div class="bubble a">${r.answer}${r.answer_en && r.answer_en !== r.answer ? html`<details class="small muted" style="margin-top:6px"><summary>English answer</summary>${r.answer_en}</details>` : ""}
<div class="src">${(r.sources || []).map((s) => html`<details><summary>📄 ${s.doc} › ${s.section}</summary><blockquote>${s.excerpt}</blockquote></details>`)}
${r.mode === "extractive" ? html`<span class="muted tiny">Quoted directly from the SOP section${S.ai && !S.ai.online ? " (local AI offline)" : ""}.</span>` : html`<span class="muted tiny">Written by the local AI from the sources above only.</span>`}
${r.id ? html`<div class="row" style="gap:6px"><span class="muted tiny">Did this help?</span><button class="btn sm" data-fb="1" data-q="${r.id}">👍</button><button class="btn sm" data-fb="0" data-q="${r.id}">👎 Ask my lead</button></div>` : ""}</div></div>`;
}

VIEWS.assistant = async (el) => {
  const { questions } = await api("/api/sop/my-questions");
  const docs = (await api("/api/sop/docs")).docs;
  el.innerHTML = html`
  <div class="page-head"><div class="grow"><h1>Ask the SOPs</h1><p>${window.LEADDESK_PREVIEW_MODE ? `Try sample answers based on ${docs.length} example SOP document(s). Nothing is sent to an AI service.` : `Answers come only from the ${docs.length} SOP document(s) your team lead uploaded, with the source. You can ask in English, हिन्दी or ગુજરાતી.`}</p></div></div>
  <div class="chat" id="chat"></div>
  <div class="ask-box"><input class="input" id="qin" placeholder="Type your question, e.g. What do I do when error 402 appears?" maxlength="600"><button class="btn primary big" id="qgo">Ask</button></div>
  <div class="chips" id="chips">${SUGGEST.map((s) => html`<button class="chip">${s}</button>`)}</div>`;
  const chat = $("#chat");
  const add = (node) => { chat.insertAdjacentHTML("beforeend", node.s || node); wireFb(); };
  const wireFb = () => $$("[data-fb]", chat).forEach((b) => (b.onclick = async () => {
    try {
      await api(`/api/sop/questions/${b.dataset.q}/feedback`, { method: "POST", body: { helpful: b.dataset.fb === "1" } });
      b.parentElement.innerHTML = b.dataset.fb === "1" ? `<span class="muted tiny">Thanks!</span>` : `<span class="muted tiny">Sent to your team lead.</span>`;
    } catch (e) { fail(e); }
  }));
  if (!questions.length) add(html`<div class="bubble a">Hi ${S.me.name.split(" ")[0]} - Ask about error codes, approvals, forms or cut-offs. If the SOPs do not cover it, the question goes to the team lead.</div>`);
  questions.slice().reverse().slice(-8).forEach((qq) => {
    add(html`<div class="bubble q">${qq.question}</div>`);
    if (qq.status === "resolved") add(html`<div class="bubble a"><b>Answer from ${qq.resolved_by ? "your team lead" : "the lead"}:</b>\n${qq.lead_answer}<div class="muted tiny" style="margin-top:6px">Not in the SOPs yet - answered by hand ${fmtDT(qq.resolved_at)}</div></div>`);
    else add(answerBubble({ ...qq, answer: qq.answer }));
  });
  const ask = async (text) => {
    text = (text || "").trim(); if (text.length < 3) return;
    $("#qin").value = ""; $("#qgo").disabled = true;
    add(html`<div class="bubble q">${text}</div>`);
    add(`<div class="bubble a" id="typing"><span class="typing"><span></span><span></span><span></span></span> Searching the SOPs…</div>`);
    window.scrollTo(0, document.body.scrollHeight);
    try { const r = await api("/api/sop/ask", { method: "POST", body: { question: text } }); $("#typing").remove(); add(answerBubble(r)); }
    catch (e) { $("#typing").remove(); fail(e); }
    $("#qgo").disabled = false; $("#qin").focus(); window.scrollTo(0, document.body.scrollHeight);
  };
  $("#qgo").onclick = () => ask($("#qin").value);
  $("#qin").onkeydown = (e) => { if (e.key === "Enter") ask($("#qin").value); };
  $$("#chips .chip").forEach((c) => (c.onclick = () => ask(c.textContent)));
  $("#qin").focus();
};

// ------------------------------------------------------------------ needs lead (gaps)
VIEWS["needs-lead"] = async (el, params) => {
  let status = params.status || "needs_lead";
  const r = await api("/api/sop/questions?status=" + status);
  const c = r.counts;
  el.innerHTML = html`
  <div class="page-head"><div class="grow"><h1>Needs lead</h1><p>Questions the SOPs could not answer. Answer them here - and use the list to see what is missing from the SOPs.</p></div>
    <div class="seg" id="qs">${[["needs_lead", `Waiting (${c.needs_lead || 0})`], ["resolved", `Answered by you (${c.resolved || 0})`], ["answered", `Answered by AI (${c.answered || 0})`], ["all", "All"]].map(([k, l]) => html`<button data-s="${k}" class="${k === status ? "on" : ""}">${l}</button>`)}</div></div>
  <div class="stack">${r.questions.length ? r.questions.map((q) => html`<div class="card">
    <div class="row" style="flex-wrap:nowrap;align-items:flex-start">${avatar(q.asked_by || "?", q.user_id)}<div class="grow">
      <div class="row" style="gap:8px"><b>${q.asked_by}</b><span class="muted small">${fmtDT(q.asked_at)}</span>${q.language !== "en" ? html`<span class="pill info">${q.language === "hi" ? "Hindi" : "Gujarati"}</span>` : ""}
        ${q.helpful === 0 ? html`<span class="pill warn">Marked unhelpful</span>` : ""}<span class="pill">match ${Math.round((q.top_score || 0) * 100)}%</span></div>
      <h2 style="margin:6px 0">“${q.question}”</h2>
      ${q.answer ? html`<div class="small muted">AI answered: ${q.answer.slice(0, 260)}${q.sources.length ? html` <i>(${q.sources.map((s) => s.doc + " › " + s.section).join("; ")})</i>` : ""}</div>` : ""}
      ${q.status === "resolved" ? html`<div class="alert ok" style="margin-top:8px"><b>${q.resolved_by_name} answered:</b> ${q.lead_answer}</div>`
        : q.status === "needs_lead" ? html`<div class="row" style="margin-top:10px;flex-wrap:nowrap"><textarea class="input" rows="2" placeholder="Type the answer for ${q.asked_by}…" data-ans="${q.id}"></textarea><button class="btn primary" data-send="${q.id}">Send answer</button></div>` : ""}
    </div></div></div>`) : html`<div class="card empty">${status === "needs_lead" ? "No open questions. The SOPs are covering everything so far. 🎉" : "Nothing here yet."}</div>`}</div>`;
  $$("#qs button", el).forEach((b) => (b.onclick = () => (location.hash = "#/needs-lead?status=" + b.dataset.s)));
  $$("[data-send]", el).forEach((b) => (b.onclick = async () => {
    const ta = $(`[data-ans="${b.dataset.send}"]`, el);
    if (!ta.value.trim()) return toast("Type an answer first", "bad");
    try { await api(`/api/sop/questions/${b.dataset.send}/resolve`, { method: "POST", body: { answer: ta.value } }); toast("Answer sent", "ok"); refreshNotes(); route(); } catch (e) { fail(e); }
  }));
};

// ------------------------------------------------------------------ SOP library
VIEWS.sops = async (el) => {
  const { docs } = await api("/api/sop/docs");
  el.innerHTML = html`
  <div class="page-head"><div class="grow"><h1>SOP library</h1><p>${window.LEADDESK_PREVIEW_MODE ? "Browse sample procedures. File uploads and edits are temporary and are not stored." : "Upload PDF or Word SOPs. They are split into sections and indexed; the assistant answers only from these."}</p></div></div>
  <div class="card" style="margin-bottom:16px">
    <form id="up" class="row"><input type="file" name="file" accept=".pdf,.docx" class="input grow" required><button class="btn primary">⬆ Upload and index</button></form>
    <div class="muted small" style="margin-top:6px">Uploading a file with the same name replaces the old version.</div>
  </div>
  <div class="card"><table class="t"><thead><tr><th>Document</th><th>File</th><th class="num">Sections</th><th>Uploaded</th><th></th></tr></thead>
  <tbody>${docs.map((d) => html`<tr><td><b>${d.title}</b></td><td class="muted small">${d.filename}</td><td class="num">${d.n_sections}</td>
    <td class="small">${fmtDT(d.uploaded_at)}<div class="muted tiny">${d.uploaded_by || ""}</div></td>
    <td class="num"><button class="btn sm" data-view="${d.id}">View sections</button> <button class="btn sm danger" data-del="${d.id}">Remove</button></td></tr>`)}</tbody></table>
  ${docs.length ? "" : html`<div class="empty">No SOPs yet. Upload one above.</div>`}</div>`;
  $("#up").onsubmit = async (e) => {
    e.preventDefault(); const btn = $("button", e.target); btn.disabled = true; btn.textContent = "Indexing…";
    try { const r = await api("/api/sop/docs", { method: "POST", body: new FormData(e.target) }); toast(window.LEADDESK_PREVIEW_MODE ? `Sample SOP added for this session (${r.sections} sections).` : `Indexed “${r.title}” - ${r.sections} sections`, "ok"); route(); }
    catch (er) { fail(er); btn.disabled = false; btn.textContent = "⬆ Upload and index"; }
  };
  $$("[data-del]", el).forEach((b) => (b.onclick = async () => { if (!confirm("Remove this SOP? The assistant will stop using it.")) return; await api(`/api/sop/docs/${b.dataset.del}`, { method: "DELETE" }).catch(fail); route(); }));
  $$("[data-view]", el).forEach((b) => (b.onclick = async () => {
    const r = await api(`/api/sop/docs/${b.dataset.view}/sections`);
    modal(html`<div class="modal-head"><h2>${r.doc.title}</h2><button class="x" data-close>×</button></div>
      <p class="muted small">This is exactly how the assistant sees the document: each section is cited by name.</p>
      ${r.sections.map((s) => html`<details class="card" style="padding:10px 14px;margin-bottom:8px"><summary><b>${s.section}</b></summary><div class="small" style="white-space:pre-wrap;margin-top:6px">${s.text}</div></details>`)}`.s, { wide: true });
  }));
};

// ------------------------------------------------------------------ vault
let lastSearch = "";
function highlight(text, q) {
  let h = esc(text);
  if (!q) return h;
  const terms = [q.toLowerCase().replace(/"/g, ""), ...q.toLowerCase().split(/\s+/)].filter((t) => t.length > 1).sort((a, b) => b.length - a.length);
  const re = new RegExp("(" + terms.map((t) => esc(t).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "gi");
  return h.replace(re, "<mark>$1</mark>");
}
const typePill = (d) => html`<span class="pill ${d.doc_type === "other" ? "" : "accent"}" title="${d.type_reason || ""}">${d.doc_type_label}</span>${d.doc_type_source === "rule" ? html` <span class="muted tiny">auto</span>` : html` <span class="muted tiny">✎ set by hand</span>`}`;

VIEWS.vault = async (el, params = {}) => {
  const [meta, list] = await Promise.all([api("/api/vault/meta"), api("/api/vault/docs")]);
  const department = params.department || "";
  const scopedDocs = list.docs.filter((doc) => !department || doc.department === department);
  el.innerHTML = html`
  <div class="page-head"><div class="grow"><h1>${department ? `Vault · ${department}` : window.LEADDESK_PREVIEW_MODE && S.me.role === "lead" ? "Team documents" : meta.can_upload ? "Document vault" : "My documents"}</h1>
    <p>${window.LEADDESK_PREVIEW_MODE ? "Sample documents only. No files are uploaded or stored." : "Encrypted at rest (AES-256)."} You can see: <span class="pill accent">${meta.scope}</span>${window.LEADDESK_PREVIEW_MODE ? "" : " · every open, download and search is logged."}</p></div>
    ${meta.can_upload ? html`<button class="btn primary" id="upb">⬆ Upload document</button>` : ""}</div>
  ${department ? html`<p class="filter-context">Showing ${department} <a href="#/vault">Clear department filter</a></p>` : ""}
  <div class="card" style="margin-bottom:16px">
    <div class="row"><input class="input grow" id="vq" placeholder="Search inside documents - including scanned images, e.g.  relocation bonus" style="font-size:16px;padding:12px">
      <button class="btn primary big" id="vgo">🔎 Search</button></div>
    <div id="vres"></div>
  </div>
  <div class="card">
    <div class="section-title"><h2>Documents</h2><span class="grow"></span>
      <select class="input" id="vt"><option value="">All types</option>${Object.entries(meta.doc_types).map(([k, v]) => html`<option value="${k}">${v}</option>`)}</select>
      <form id="openref" class="row" style="gap:6px"><input class="input" name="id" placeholder="Open by doc #" style="width:130px" title="Simulates opening a shared link"><button class="btn">Open</button></form>
    </div>
    <table class="t"><thead><tr><th>#</th><th>Employee</th><th>Type</th><th>File</th><th>Uploaded</th><th>Retention</th></tr></thead><tbody id="vtb"></tbody></table>
  </div>
  ${meta.is_admin ? html`<div class="card" style="margin-top:16px" id="delreq"></div>` : ""}`;
  const draw = () => {
    const t = $("#vt").value;
    const rows = scopedDocs.filter((d) => !t || d.doc_type === t);
    $("#vtb").innerHTML = rows.map((d) => html`<tr class="click" data-doc="${d.id}"><td class="muted">${d.id}</td><td><b>${d.employee_name}</b><div class="muted tiny">${d.employee_id} · ${d.department}</div></td>
      <td>${typePill(d)}</td><td>${d.original_name} ${d.ocr_used ? html`<span class="pill info" title="Text read with OCR">scan · OCR</span>` : ""}</td>
      <td class="small">${fmtDT(d.uploaded_at)}<div class="muted tiny">${d.uploaded_by_name || ""}</div></td>
      <td class="small">${d.retention_until ? html`<span class="${d.retention_expired ? "pill bad" : "muted"}">${d.retention_until}</span>` : "-"}</td></tr>`.s).join("")
      || `<tr><td colspan="6" class="empty">No documents you can see.</td></tr>`;
    $$("#vtb [data-doc]").forEach((r) => (r.onclick = () => openDoc(+r.dataset.doc, meta)));
  };
  $("#vt").onchange = draw; draw();
  const search = async () => {
    const q = $("#vq").value.trim(); if (q.length < 2) return;
    lastSearch = q;
    try {
      const r = await api("/api/vault/search?qs=" + encodeURIComponent(q));
      $("#vres").innerHTML = html`<div class="muted small" style="margin:12px 0 6px">${r.results.length} result(s) for “${q}” within ${r.scope}.${window.LEADDESK_PREVIEW_MODE ? " Sample results; searches are not logged." : " This search was logged."}</div>
        ${r.results.map((x) => html`<div class="card click" style="padding:12px;margin-bottom:8px;cursor:pointer" data-doc="${x.doc.id}">
          <div class="row" style="gap:8px"><b>${x.doc.original_name}</b>${typePill(x.doc)}${x.doc.ocr_used ? html`<span class="pill info">found inside a scan</span>` : ""}<span class="muted small">${x.doc.employee_id}</span></div>
          ${x.snippets.map((s) => html`<div class="small" style="margin-top:6px">${raw(s)}</div>`)}</div>`)}`.s;
      $$("#vres [data-doc]").forEach((r) => (r.onclick = () => openDoc(+r.dataset.doc, meta)));
    } catch (e) { fail(e); }
  };
  $("#vgo").onclick = search; $("#vq").onkeydown = (e) => e.key === "Enter" && search();
  $("#openref").onsubmit = (e) => { e.preventDefault(); const id = +new FormData(e.target).get("id"); if (id) openDoc(id, meta); };
  if (meta.can_upload) $("#upb").onclick = () => uploadForm(meta);
  if (meta.is_admin) drawDeleteRequests();
};

async function drawDeleteRequests() {
  const box = $("#delreq"); if (!box) return;
  const { requests } = await api("/api/vault/delete-requests");
  box.innerHTML = html`<h2>Deletion requests (two-person rule)</h2>
    ${requests.length ? html`<table class="t"><tbody>${requests.map((r) => html`<tr><td><b>#${r.doc_id} ${r.original_name}</b><div class="muted tiny">requested by ${r.requested_by_name} · ${fmtDT(r.requested_at)} · “${r.reason || "no reason"}”</div></td>
      <td class="num">${r.status === "pending" ? html`<button class="btn sm danger" data-dec="${r.id}" data-a="1">Approve delete</button> <button class="btn sm" data-dec="${r.id}" data-a="0">Reject</button>` : html`<span class="pill ${r.status === "approved" ? "bad" : ""}">${r.status} by ${r.approved_by_name}</span>`}</td></tr>`)}</tbody></table>` : html`<div class="muted">No requests.</div>`}`.s;
  $$("[data-dec]", box).forEach((b) => (b.onclick = async () => {
    try { await api(`/api/vault/delete-requests/${b.dataset.dec}/decide`, { method: "POST", body: { approve: b.dataset.a === "1" } }); toast("Done", "ok"); route(); } catch (e) { fail(e); }
  }));
}

function uploadForm(meta) {
  const ov = modal(html`<div class="modal-head"><h2>Upload HR document</h2><button class="x" data-close>×</button></div>
    <form id="vu" class="stack">
      <label class="f">Employee ID <input class="input" name="employee_id" list="emps" required placeholder="e.g. EMP0001"><datalist id="emps"></datalist></label>
      <label class="f">File (PDF, image scan, Word or text) <input class="input" type="file" name="file" required accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.docx,.txt"></label>
      <div class="form-grid">
        <label class="f">Document type <select class="input" name="doc_type"><option value="">Detect automatically</option>${Object.entries(meta.doc_types).map(([k, v]) => html`<option value="${k}">${v}</option>`)}</select></label>
        <label class="f">Keep until (retention) <input class="input" type="date" name="retention_until"></label>
      </div>
      <div class="alert small">${window.LEADDESK_PREVIEW_MODE ? "Uploads are simulated. No file is stored or processed." : "The file is encrypted before it is written to disk. Scans are read with OCR so their text becomes searchable."}</div>
      <div class="row"><span class="grow"></span><button type="button" class="btn" data-close>Cancel</button><button class="btn primary">Encrypt and upload</button></div>
    </form>`.s);
  $$("[data-close]", ov).forEach((b) => (b.onclick = closeModal));
  const inp = $("[name=employee_id]", ov);
  inp.oninput = async () => {
    const r = await api("/api/vault/employees?qs=" + encodeURIComponent(inp.value)).catch(() => ({ employees: [] }));
    $("#emps", ov).innerHTML = r.employees.map((e) => `<option value="${esc(e.employee_id)}">${esc(e.name)} - ${esc(e.department)}</option>`).join("");
  };
  inp.oninput();
  $("#vu", ov).onsubmit = async (e) => {
    e.preventDefault(); const b = $("button.primary", e.target); b.disabled = true; b.textContent = "Encrypting and reading…";
    try {
      const r = await api("/api/vault/docs", { method: "POST", body: new FormData(e.target) });
      closeModal(); toast(window.LEADDESK_PREVIEW_MODE ? "Sample document added for this session; no file was stored." : `Stored #${r.doc.id} as ${r.doc.doc_type_label}${r.doc.ocr_used ? " (OCR)" : ""}`, "ok"); route();
    } catch (er) { fail(er); b.disabled = false; b.textContent = "Encrypt and upload"; }
  };
}

async function openDoc(id, meta) {
  let r;
  try { r = await api(`/api/vault/docs/${id}`); }
  catch (e) {
    if (e.status === 403 || e.status === 404) {
      return modal(html`<div class="modal-head"><h2>⛔ Access denied</h2><button class="x" data-close>×</button></div>
        <div class="alert bad">${e.message}</div><p class="muted small">You are signed in as <b>${S.me.name}</b> (${S.me.role_label}). Your scope: ${meta.scope}.</p>`.s);
    }
    return fail(e);
  }
  const d = r.doc;
  const src = `/api/vault/docs/${id}/file`;
  const preview = window.LEADDESK_PREVIEW_MODE ? html`<div class="empty">Sample file preview unavailable. The example text is shown alongside.</div>`
    : d.mime.startsWith("image/") ? html`<img src="${src}" style="max-width:100%;border:1px solid var(--line);border-radius:8px">`
    : d.mime === "application/pdf" ? html`<iframe src="${src}" style="width:100%;height:520px;border:1px solid var(--line);border-radius:8px"></iframe>`
    : html`<div class="muted">No preview for this file type - see the text on the right or download it.</div>`;
  const canEdit = meta.can_upload;
  const ov = modal(html`<div class="modal-head"><h2>#${d.id} · ${d.original_name}</h2><button class="x" data-close>×</button></div>
    <div class="grid g2">
      <div>${preview}</div>
      <div class="stack">
        <div class="form-grid">
          <div><div class="muted small">Employee</div><b>${d.employee_name}</b><div class="muted tiny">${d.employee_id} · ${d.department}</div></div>
          <div><div class="muted small">Uploaded</div><b>${fmtDT(d.uploaded_at)}</b><div class="muted tiny">${d.uploaded_by_name || ""}</div></div>
        </div>
        <div><div class="muted small">Type</div>${canEdit ? html`<div class="row"><select class="input" id="dt">${Object.entries(meta.doc_types).map(([k, v]) => html`<option value="${k}" ${k === d.doc_type ? raw("selected") : ""}>${v}</option>`)}</select><span class="muted tiny">${d.type_reason || ""}</span></div>` : typePill(d)}</div>
        ${canEdit ? html`<div><div class="muted small">Keep until</div><input class="input" type="date" id="ret" value="${d.retention_until || ""}"></div>` : ""}
        <div><div class="muted small">Text ${d.ocr_used ? "(read by OCR from the scan)" : ""}</div>
          <div class="small" style="white-space:pre-wrap;max-height:260px;overflow:auto;background:var(--soft);padding:10px;border-radius:8px">${raw(highlight(r.text || "(no text)", lastSearch))}</div></div>
        <div class="row">${window.LEADDESK_PREVIEW_MODE ? html`<button class="btn primary" type="button" disabled title="Downloads are not available in the preview">Download disabled in preview</button>` : html`<a class="btn primary" href="${src}?download=true">Download watermarked copy</a>`}${canEdit ? html`<button class="btn danger" id="delr">Request deletion</button>` : ""}</div>
        <div class="muted tiny">Opening this document was recorded in the audit log.</div>
      </div></div>`.s, { wide: true });
  if (canEdit) {
    $("#dt", ov).onchange = async (e) => { try { await api(`/api/vault/docs/${id}`, { method: "PATCH", body: { doc_type: e.target.value } }); toast("Type corrected", "ok"); } catch (er) { fail(er); } };
    $("#ret", ov).onchange = async (e) => { try { await api(`/api/vault/docs/${id}`, { method: "PATCH", body: { retention_until: e.target.value } }); toast("Retention saved", "ok"); } catch (er) { fail(er); } };
    $("#delr", ov).onclick = async () => {
      reasonModal({
        title: "Request document deletion",
        description: "A second administrator must approve this request.",
        label: "Reason for deletion",
        submitLabel: "Request deletion",
        required: false,
        onSubmit: (reason) => api(`/api/vault/docs/${id}/delete-request`, { method: "POST", body: { reason } }),
        onSuccess: () => { toast("Deletion requested - waiting for a second approver", "ok"); openDoc(id, meta); },
        onCancel: () => openDoc(id, meta),
      });
    };
  }
  ov._onClose = () => { if (location.hash.startsWith("#/vault")) route(); };
}

// ------------------------------------------------------------------ audit log (admin)
VIEWS.audit = async (el, params) => {
  const f = params.f || "";
  const r = await api("/api/vault/audit" + (f ? "?action=" + f : ""));
  const docs = (await api("/api/vault/docs")).docs;
  el.innerHTML = html`
  <div class="page-head"><div class="grow"><h1>Audit log</h1><p>${window.LEADDESK_PREVIEW_MODE ? "Example activity only. This preview does not record access or verify an audit chain." : "Every upload, view, download and search. Append-only: the database refuses edits and deletes, and each entry is hash-chained to the previous one."}</p></div>
    <span class="pill ${r.chain.ok ? "ok" : "bad"}" style="font-size:14px;padding:6px 12px">${r.chain.ok ? `${window.LEADDESK_PREVIEW_MODE ? "Sample chain" : "✔ Chain intact"} · ${r.chain.entries} entries` : `✖ Chain broken at #${r.chain.broken_at}`}</span></div>
  <div class="grid g-main">
    <div class="card">
      <div class="seg" id="af" style="margin-bottom:10px">${[["", "All"], ["denied", "Denied"], ["view", "Views"], ["download", "Downloads"], ["search", "Searches"], ["upload", "Uploads"]].map(([k, l]) => html`<button data-f="${k}" class="${k === f ? "on" : ""}">${l}</button>`)}</div>
      <table class="t"><thead><tr><th>When</th><th>Who</th><th>Action</th><th>Doc</th><th>Detail</th></tr></thead>
      <tbody>${r.entries.map((e) => html`<tr class="${e.outcome === "denied" ? "hl" : ""}"><td class="small">${fmtDT(e.at)}</td><td><b>${e.username}</b><div class="muted tiny">${e.role}</div></td>
        <td><span class="pill ${e.outcome === "denied" ? "bad" : e.action === "download" ? "warn" : e.action === "upload" ? "ok" : ""}">${e.outcome === "denied" ? "DENIED " : ""}${e.action}</span></td>
        <td>${e.doc_id ? "#" + e.doc_id : "-"}</td><td class="small mono" style="max-width:320px;word-break:break-word">${e.detail || ""}</td></tr>`)}</tbody></table>
    </div>
    <div class="card"><h2>🔬 ${window.LEADDESK_PREVIEW_MODE ? "Storage example" : "What is on disk?"}</h2>
      <p class="muted small">${window.LEADDESK_PREVIEW_MODE ? "Illustrative values only. This preview does not read or decrypt any files." : "Pick a document to compare the stored file with the original. The stored file is AES-256-GCM ciphertext."}</p>
      <select class="input" id="sp" style="width:100%"><option value="">Choose a document…</option>${docs.map((d) => html`<option value="${d.id}">#${d.id} ${d.original_name}</option>`)}</select>
      <div id="spout" style="margin-top:12px"></div></div>
  </div>`;
  $$("#af button", el).forEach((b) => (b.onclick = () => (location.hash = "#/audit?f=" + b.dataset.f)));
  $("#sp").onchange = async (e) => {
    if (!e.target.value) return;
    const p = await api(`/api/vault/storage/${e.target.value}`);
    $("#spout").innerHTML = html`<div class="stack small">
      <div><b>${window.LEADDESK_PREVIEW_MODE ? "Sample encrypted bytes" : "Stored on disk"}</b> <span class="muted">(${p.path_on_disk}, ${p.stored_bytes} bytes)</span><div class="hex">${p.disk_head_hex}</div><div class="hex" style="margin-top:4px">${p.disk_head_text}</div></div>
      <div><b>${window.LEADDESK_PREVIEW_MODE ? "Sample original bytes" : "Original after decryption"}</b> <span class="muted">(${p.original_bytes} bytes)</span><div class="hex plain">${p.original_head_hex}</div><div class="hex plain" style="margin-top:4px">${p.original_head_text}</div></div>
      <div class="alert ${window.LEADDESK_PREVIEW_MODE ? "warn" : "ok"}">${window.LEADDESK_PREVIEW_MODE ? "Illustrative sample values; no file integrity check was performed." : html`Entropy ${p.entropy_bits_per_byte} bits/byte (8.0 = random) · ${Math.round(p.printable_ratio * 100)}% printable · integrity check ${p.sha256_matches ? "✔" : "✖"}<br>${p.cipher}. Master key fingerprint <code>${p.key_fingerprint}</code> - the key lives outside the code and database.`}</div></div>`.s;
  };
};

// ------------------------------------------------------------------ interviews: recruiter board
const IVS = { invited: ["Waiting to book", ""], scheduled: ["Scheduled", "info"], rescheduled: ["Rescheduled", "accent"], feedback_pending: ["Feedback pending", "bad"], completed: ["Completed", "ok"], cancelled: ["Cancelled", ""] };
VIEWS.interviews = async (el, params) => {
  const qs = new URLSearchParams(); if (params.recruiter) qs.set("recruiter_id", params.recruiter); if (params.role) qs.set("role", params.role);
  const b = await api("/api/iv/board?" + qs);
  let filt = params.status || "";
  el.innerHTML = html`
  <div class="page-head"><div class="grow"><h1>Interviews</h1><p>${window.LEADDESK_PREVIEW_MODE ? "Sample interview pipeline and candidate booking flow. No email or calendar invite is sent." : "Candidates book from their own link; the system stops double booking."} Times in ${b.time_zone}.</p></div>
    <button class="btn" id="outb">📬 Sent emails</button><a class="btn" href="/api/iv/export">⬇ Excel</a><button class="btn primary" id="addc">＋ Invite candidate</button></div>
  <div class="kpis">${Object.entries(IVS).map(([k, [l, c]]) => html`<div class="kpi click ${k === "feedback_pending" && b.counts[k] ? "bad" : ""}" data-k="${k}" style="${filt === k ? "border-color:var(--accent)" : ""}"><div class="v">${b.counts[k]}</div><div class="l">${l}</div></div>`)}</div>
  <div class="card">
    <div class="row" style="margin-bottom:10px">
      <select class="input" id="fr"><option value="">All recruiters</option>${b.recruiters.map((r) => html`<option value="${r.id}" ${String(r.id) === params.recruiter ? raw("selected") : ""}>${r.name}</option>`)}</select>
      <select class="input" id="fro"><option value="">All roles</option>${b.roles.map((r) => html`<option ${r === params.role ? raw("selected") : ""}>${r}</option>`)}</select>
      ${filt ? html`<button class="btn sm" id="clr">Showing: ${IVS[filt][0]} ✕</button>` : ""}
    </div>
    <table class="t"><thead><tr><th>Candidate</th><th>Role · round</th><th>Interviewer</th><th>When</th><th>Status</th><th></th></tr></thead>
    <tbody>${b.interviews.filter((i) => !filt || i.board_status === filt).map((i) => html`<tr class="${i.board_status === "feedback_pending" ? "hl" : ""}">
      <td><b>${i.candidate_name}</b><div class="muted tiny">${i.candidate_email} · recruiter ${i.recruiter_name}</div></td>
      <td>${i.role_title}<div class="muted tiny">${i.round_name}${i.length_min ? ` · ${i.length_min} min` : ""}</div></td>
      <td>${i.interviewer_name || "-"}</td>
      <td class="small">${i.start ? fmtDT(i.start) : "-"}${i.reschedule_count ? html`<div class="muted tiny">rescheduled ${i.reschedule_count}×</div>` : ""}
        ${i.calendar_sync && i.calendar_sync.status === "synced" ? html`<div class="muted tiny">Calendar synced</div>` : ""}
        ${i.calendar_sync && i.calendar_sync.status === "failed" ? html`<div class="small bad">Calendar sync failed: ${i.calendar_sync.error}</div><button class="btn sm" data-calendar-retry="${i.id}">Retry sync</button>` : ""}</td>
      <td><span class="pill ${IVS[i.board_status][1]}">${IVS[i.board_status][0]}</span></td>
      <td class="num" style="white-space:nowrap">
        ${window.LEADDESK_PREVIEW_MODE || S.me.role !== "hr" ? "" : html`<button class="btn sm" data-interview-notes="${i.id}">Notes</button>`}
        ${i.board_status === "invited" || i.board_status === "scheduled" || i.board_status === "rescheduled" ? html`<button class="btn sm" data-copy="${i.link}">🔗 Link</button>` : ""}
        ${i.start && i.status !== "invited" ? html`<a class="btn sm" href="/api/iv/interviews/${i.id}/ics">.ics</a>` : ""}
        ${i.board_status === "feedback_pending" ? html`<button class="btn sm warn" data-nudge="${i.id}">Remind</button>` : ""}
        ${["completed", "feedback_pending"].includes(i.board_status) ? html`<button class="btn sm" data-fb="${i.candidate_id}" data-name="${i.candidate_name}">Feedback</button>` : ""}
        ${["invited", "scheduled", "rescheduled"].includes(i.board_status) ? html`<button class="btn sm danger" data-cancel="${i.id}">Cancel</button>` : ""}
      </td></tr>`)}</tbody></table>
  </div>`;
  const nav = (p) => { const n = new URLSearchParams({ recruiter: $("#fr").value, role: $("#fro").value, status: filt, ...p }); location.hash = "#/interviews?" + n; };
  $$("[data-k]", el).forEach((k) => (k.onclick = () => nav({ status: filt === k.dataset.k ? "" : k.dataset.k })));
  $("#fr").onchange = () => nav({}); $("#fro").onchange = () => nav({});
  const clr = $("#clr"); if (clr) clr.onclick = () => nav({ status: "" });
  $$("[data-copy]", el).forEach((x) => (x.onclick = () => { navigator.clipboard?.writeText(x.dataset.copy); toast("Booking link copied", "ok"); window.open(x.dataset.copy, "_blank"); }));
  $$("[data-nudge]", el).forEach((x) => (x.onclick = async () => { await api(`/api/iv/interviews/${x.dataset.nudge}/nudge`, { method: "POST" }).then(() => toast(window.LEADDESK_PREVIEW_MODE ? "Reminder simulated; no email was sent." : "Reminder sent to the interviewer", "ok")).catch(fail); }));
  $$("[data-cancel]", el).forEach((x) => (x.onclick = async () => { if (!confirm("Cancel this interview? A cancellation invite is sent to both sides.")) return; await api(`/api/iv/interviews/${x.dataset.cancel}/cancel`, { method: "POST" }).then(() => { toast("Cancelled", "ok"); route(); }).catch(fail); }));
  $$("[data-fb]", el).forEach((x) => (x.onclick = () => showFeedback(+x.dataset.fb, x.dataset.name)));
  $$("[data-interview-notes]", el).forEach((x) => (x.onclick = () => {
    const interview = b.interviews.find((i) => i.id === +x.dataset.interviewNotes);
    if (interview) showInterviewNotes(interview);
  }));
  $$("[data-calendar-retry]", el).forEach((x) => (x.onclick = async () => {
    x.disabled = true;
    try {
      const result = await api(`/api/iv/interviews/${x.dataset.calendarRetry}/calendar-sync`, { method: "POST" });
      toast(result.status === "synced" ? "Calendar event synced" : "Calendar sync status updated", "ok");
      route();
    } catch (e) { x.disabled = false; fail(e); }
  }));
  $("#addc").onclick = () => candidateForm();
  $("#outb").onclick = () => showOutbox();
};

function candidateForm() {
  const ov = modal(html`<div class="modal-head"><h2>Invite a candidate</h2><button class="x" data-close>×</button></div>
    <form id="cf" class="stack"><div class="form-grid">
      <label class="f">Name <input class="input" name="name" required></label>
      <label class="f">Email <input class="input" type="email" name="email" required></label>
      <label class="f">Role <input class="input" name="role_title" required placeholder="e.g. Process Associate"></label>
      <label class="f">Round <input class="input" name="round_name" value="Round 1"></label>
      <label class="f">Length <select class="input" name="length_min"><option value="">Any (30/45/60)</option><option>30</option><option>45</option><option>60</option></select></label>
    </div><div class="row"><span class="grow"></span><button class="btn primary">Create booking link</button></div></form><div id="cout"></div>`.s);
  $("#cf", ov).onsubmit = async (e) => {
    e.preventDefault(); const f = Object.fromEntries(new FormData(e.target)); f.length_min = f.length_min ? +f.length_min : null;
    try {
      const r = await api("/api/iv/candidates", { method: "POST", body: f });
      $("#cout", ov).innerHTML = html`<div class="alert ok" style="margin-top:12px"><b>${window.LEADDESK_PREVIEW_MODE ? "Sample booking link created. No email was sent." : "Link created and emailed."}</b><br><a href="${r.link}" target="_blank">${r.link}</a></div>`.s;
      $("#cf", ov).remove(); ov._onClose = route;
    } catch (er) { fail(er); }
  };
}

async function showOutbox() {
  const r = await api("/api/iv/outbox");
  modal(html`<div class="modal-head"><h2>Sent emails</h2><button class="x" data-close>×</button></div>
    <p class="muted small">${window.LEADDESK_PREVIEW_MODE ? "Example messages only. This preview does not send emails." : html`Every email the scheduler sends. With Docker they are also delivered to the local test mail server: <a href="${r.mail_ui}" target="_blank">${r.mail_ui}</a>`}</p>
    <table class="t"><tbody>${r.messages.map((m) => html`<tr><td class="small">${fmtDT(m.at)}</td><td><b>${m.subject}</b><div class="muted tiny">to ${m.to_addr} · ${m.kind}</div>
      <details class="tiny"><summary>Body</summary><pre style="white-space:pre-wrap">${m.body}</pre></details></td>
      <td>${m.delivered ? html`<span class="pill ok">delivered</span>` : html`<span class="pill" title="${m.error || ""}">outbox only</span>`}</td>
      <td>${m.has_ics ? html`<a class="btn sm" href="/api/iv/outbox/${m.id}/ics">📅 .ics</a>` : ""}</td></tr>`)}</tbody></table>`.s, { wide: true });
}

async function showFeedback(cid, name) {
  try {
    const r = await api(`/api/iv/candidates/${cid}/feedback`);
    modal(html`<div class="modal-head"><h2>Feedback · ${name}</h2><button class="x" data-close>×</button></div>
      ${r.locked ? html`<div class="alert warn">🔒 ${r.hidden} colleague(s) have submitted feedback. Submit your own first - then you can see theirs. This keeps every opinion independent.</div>`
        : r.feedback.length ? html`<table class="t"><thead><tr><th>Interviewer</th><th class="num">Comm.</th><th class="num">Technical</th><th class="num">Problem solving</th><th class="num">Culture fit</th><th>Recommendation</th></tr></thead>
        <tbody>${r.feedback.map((f) => html`<tr><td><b>${f.interviewer_name}</b><div class="muted tiny">${f.round_name}</div><div class="small">${f.comments}</div></td>
          <td class="num">${f.communication}</td><td class="num">${f.technical}</td><td class="num">${f.problem_solving}</td><td class="num">${f.culture_fit}</td>
          <td><span class="pill ${f.recommendation === "advance" ? "ok" : f.recommendation === "reject" ? "bad" : "warn"}">${f.recommendation}</span></td></tr>`)}</tbody></table>`
        : html`<div class="empty">No feedback yet.</div>`}`.s, { wide: true });
  } catch (e) { fail(e); }
}

async function showInterviewNotes(interview) {
  const viewerId = S.me?.id;
  try {
    const result = await api(`/api/iv/interviews/${interview.id}/notes`);
    if (!S.me || S.me.id !== viewerId) return;
    const ov = modal(html`<div class="modal-head"><h2>Interview notes · ${interview.candidate_name}</h2><button class="x" data-close>×</button></div>
      <p class="muted small">${interview.role_title} · ${interview.round_name}. Visible to HR and the assigned interviewer only; candidates cannot see these notes.</p>
      <div id="interview-note-list" class="stack"></div>
      <form id="interview-note-form" class="stack" style="margin-top:16px">
        <input type="hidden" id="interview-note-id">
        <label class="f" for="interview-note-body">Add a note
          <textarea class="input" id="interview-note-body" rows="4" maxlength="5000" required aria-describedby="interview-note-help"></textarea>
        </label>
        <div id="interview-note-help" class="muted tiny">Up to 5,000 characters. Notes are for internal interview preparation and follow-up.</div>
        <div class="row"><button type="button" class="btn hidden" id="cancel-note-edit">Cancel edit</button><span class="grow"></span><button class="btn primary" id="save-interview-note">Add note</button></div>
      </form>`.s, { wide: true });

    let notes = result.notes;
    const list = $("#interview-note-list", ov);
    const form = $("#interview-note-form", ov);
    const body = $("#interview-note-body", ov);
    const noteId = $("#interview-note-id", ov);
    const save = $("#save-interview-note", ov);
    const cancelEdit = $("#cancel-note-edit", ov);

    function renderNotes() {
      list.innerHTML = notes.length ? html`${notes.map((n) => html`<article class="card">
        <div class="row"><b>${n.author_name}</b><span class="muted tiny">${fmtDT(n.created_at)}</span><span class="grow"></span>
          ${n.can_edit ? html`<button type="button" class="btn sm" data-edit-note="${n.id}">Edit</button><button type="button" class="btn sm danger" data-delete-note="${n.id}">Delete</button>` : ""}
        </div><p class="small" style="white-space:pre-wrap;overflow-wrap:anywhere;margin-bottom:0">${n.body}</p>
      </article>`)}`.s : html`<div class="empty">No notes yet. Add the first internal note below.</div>`.s;
      $$("[data-edit-note]", list).forEach((button) => (button.onclick = () => {
        const note = notes.find((item) => item.id === +button.dataset.editNote);
        if (!note) return;
        noteId.value = note.id;
        body.value = note.body;
        save.textContent = "Save changes";
        cancelEdit.classList.remove("hidden");
        body.focus();
      }));
      $$("[data-delete-note]", list).forEach((button) => (button.onclick = async () => {
        if (!confirm("Delete this note? This cannot be undone.")) return;
        try {
          await api(`/api/iv/notes/${button.dataset.deleteNote}`, { method: "DELETE" });
          notes = (await api(`/api/iv/interviews/${interview.id}/notes`)).notes;
          renderNotes();
          toast("Note deleted", "ok");
        } catch (e) { fail(e); }
      }));
    }

    function clearEdit() {
      form.reset();
      noteId.value = "";
      save.textContent = "Add note";
      cancelEdit.classList.add("hidden");
    }

    cancelEdit.onclick = clearEdit;
    form.onsubmit = async (event) => {
      event.preventDefault();
      const id = noteId.value;
      try {
        await api(id ? `/api/iv/notes/${id}` : `/api/iv/interviews/${interview.id}/notes`, {
          method: id ? "PATCH" : "POST",
          body: { body: body.value },
        });
        clearEdit();
        notes = (await api(`/api/iv/interviews/${interview.id}/notes`)).notes;
        renderNotes();
        toast(id ? "Note updated" : "Note added", "ok");
      } catch (e) { fail(e); }
    };
    renderNotes();
  } catch (e) { fail(e); }
}

// ------------------------------------------------------------------ interviewer views
VIEWS["my-interviews"] = async (el) => {
  const { interviews } = await api("/api/iv/mine");
  const pending = interviews.filter((i) => i.board_status === "feedback_pending");
  const upcoming = interviews.filter((i) => ["scheduled", "rescheduled"].includes(i.board_status));
  const done = interviews.filter((i) => i.board_status === "completed");
  const row = (i) => html`<div class="card row" style="flex-wrap:nowrap">${avatar(i.candidate_name, i.candidate_id)}<div class="grow"><b>${i.candidate_name}</b> · ${i.role_title} <span class="muted small">(${i.round_name})</span>
    <div class="muted small">${fmtDT(i.start)} · ${i.location && i.location.startsWith("http") ? html`<a href="${i.location}" target="_blank">join link</a>` : i.location}</div></div>
    <span class="pill ${IVS[i.board_status][1]}">${IVS[i.board_status][0]}</span>
    <a class="btn sm" href="/api/iv/interviews/${i.id}/ics">📅 .ics</a>
    ${window.LEADDESK_PREVIEW_MODE ? "" : html`<button class="btn sm" data-interview-notes="${i.id}">Notes</button>`}
    ${i.board_status === "feedback_pending" ? html`<button class="btn primary" data-give="${i.id}">Give feedback</button>` : ""}
    ${i.board_status === "completed" ? html`<button class="btn sm" data-see="${i.candidate_id}" data-name="${i.candidate_name}">Panel feedback</button>` : ""}</div>`;
  el.innerHTML = html`
  <div class="page-head"><div class="grow"><h1>My interviews</h1><p>Times in IST. Give feedback right after each interview - it's 4 ratings, a recommendation and a comment.</p></div><a class="btn" href="#/availability">🕒 Add availability</a></div>
  ${pending.length ? html`<div class="alert warn" style="margin-bottom:14px"><b>${pending.length} interview(s) waiting for your feedback.</b></div>` : ""}
  <div class="stack">${pending.map(row)}</div>
  <h2 style="margin-top:22px">Upcoming</h2><div class="stack">${upcoming.length ? upcoming.map(row) : html`<div class="card empty">No upcoming interviews.</div>`}</div>
  <h2 style="margin-top:22px">Done</h2><div class="stack">${done.length ? done.map(row) : html`<div class="muted">None yet.</div>`}</div>`;
  $$("[data-give]", el).forEach((b) => (b.onclick = () => feedbackForm(interviews.find((i) => i.id === +b.dataset.give))));
  $$("[data-see]", el).forEach((b) => (b.onclick = () => showFeedback(+b.dataset.see, b.dataset.name)));
  $$("[data-interview-notes]", el).forEach((b) => (b.onclick = () => {
    const interview = interviews.find((i) => i.id === +b.dataset.interviewNotes);
    if (interview) showInterviewNotes(interview);
  }));
};

function feedbackForm(iv) {
  const crit = [["communication", "Communication"], ["technical", "Technical skill"], ["problem_solving", "Problem solving"], ["culture_fit", "Team / culture fit"]];
  const val = {};
  const ov = modal(html`<div class="modal-head"><h2>Feedback · ${iv.candidate_name}</h2><button class="x" data-close>×</button></div>
    <p class="muted small">${iv.role_title} · ${iv.round_name} · ${fmtDT(iv.start)}. You will see colleagues' feedback only after you submit.</p>
    <div class="stack">${crit.map(([k, l]) => html`<div class="row"><b style="width:170px">${l}</b><div class="stars" data-c="${k}">${[1, 2, 3, 4, 5].map((n) => html`<button type="button" data-n="${n}">${n}</button>`)}</div></div>`)}
      <div class="row"><b style="width:170px">Recommendation</b><div class="seg" id="rec"><button data-r="advance">✅ Advance</button><button data-r="hold">⏸ Hold</button><button data-r="reject">✖ Reject</button></div></div>
      <label class="f">Comments <textarea class="input" id="cm" rows="3" placeholder="What stood out? Any concerns?"></textarea></label>
      <div class="row"><span class="grow"></span><button class="btn primary big" id="sub">Submit feedback</button></div></div>`.s);
  $$(".stars", ov).forEach((s) => $$("button", s).forEach((b) => (b.onclick = () => { val[s.dataset.c] = +b.dataset.n; $$("button", s).forEach((x) => x.classList.toggle("on", +x.dataset.n <= +b.dataset.n)); })));
  $$("#rec button", ov).forEach((b) => (b.onclick = () => { val.recommendation = b.dataset.r; $$("#rec button", ov).forEach((x) => x.classList.toggle("on", x === b)); }));
  $("#sub", ov).onclick = async () => {
    if (crit.some(([k]) => !val[k]) || !val.recommendation) return toast("Please rate all four and pick a recommendation", "bad");
    try {
      await api(`/api/iv/interviews/${iv.id}/feedback`, { method: "POST", body: { ...val, comments: $("#cm", ov).value } });
      toast("Feedback saved", "ok"); closeModal(); await showFeedback(iv.candidate_id, iv.candidate_name); $("#overlay")._onClose = route;
    } catch (e) { fail(e); }
  };
}

VIEWS.availability = async (el) => {
  const r = await api("/api/iv/slots");
  const tom = new Date(nowServer()); tom.setDate(tom.getDate() + 1);
  const byDay = {};
  r.slots.forEach((s) => (byDay[s.start.slice(0, 10)] ||= []).push(s));
  const calendar = r.google_calendar;
  el.innerHTML = html`
  <div class="page-head"><div class="grow"><h1>My availability</h1><p>Add the times you can interview. Candidates only see open times. Times in ${r.time_zone}.</p></div></div>
  ${window.LEADDESK_PREVIEW_MODE ? "" : html`<section class="card" aria-labelledby="google-calendar-title" style="margin-bottom:16px">
    <div class="section-title"><h2 id="google-calendar-title">Google Calendar</h2><span class="grow"></span>
      ${calendar && calendar.connected ? html`<span class="pill ok">Connected</span>` : html`<span class="pill">${calendar && calendar.configured ? "Not connected" : "Not configured"}</span>`}
    </div>
    ${calendar && calendar.connected
      ? html`<p class="small">Connected to ${calendar.calendar_label || "your primary calendar"}. Busy times are checked before candidates see slots, and confirmed interviews are synced here.</p>
        <button class="btn sm" id="google-disconnect">Disconnect calendar</button>`
      : calendar && calendar.configured
        ? html`<p class="small">Connect your own calendar to hide busy times and sync interview invitations, changes, and cancellations.</p>
          <a class="btn sm primary" href="/api/iv/google/connect">Connect Google Calendar</a>`
        : html`<p class="small">To enable calendar sync, configure GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REDIRECT_URI on the server, then restart the app.</p>`}
  </section>`}
  <div class="card" style="margin-bottom:16px"><form id="sf" class="stack">
    <div class="form-grid">
      <label class="f">Day <input class="input" type="date" name="day" required value="${dateInput(tom)}"></label>
      <label class="f">From <input class="input" type="time" name="start_time" required value="10:00"></label>
      <label class="f">To <input class="input" type="time" name="end_time" required value="13:00"></label>
      <label class="f">Interview length <select class="input" name="length_min"><option>30</option><option selected>45</option><option>60</option></select></label>
      <label class="f">Repeat <select class="input" name="repeat_weeks"><option value="0">Just this day</option>${[1, 2, 3, 4, 6, 8].map((n) => html`<option value="${n}">Same day for ${n} more week${n > 1 ? "s" : ""}</option>`)}</select></label>
      <label class="f">Location (blank = video link) <input class="input" name="location" placeholder="e.g. Meeting room 2"></label>
    </div><div class="row"><span class="grow"></span><button class="btn primary">＋ Add slots</button></div></form></div>
  <div class="stack">${Object.keys(byDay).length ? Object.entries(byDay).map(([d, ss]) => html`<div class="card"><h3>${fmtDT(d + "T00:00").split(",")[0]}</h3>
    <div class="row">${ss.map((s) => html`<span class="pill ${s.state === "booked" ? "ok" : s.state === "blocked" ? "" : "info"}" style="padding:6px 10px">
      ${fmtTime(parseLocal(s.start))}–${fmtTime(parseLocal(s.end))} · ${s.length_min}m ${s.state === "booked" ? "· " + s.candidate_name : s.state === "blocked" ? "· overlaps a booking" : ""}
      ${s.state === "calendar_blocked" ? "· busy on Google Calendar" : ""}
      ${s.state === "open" || s.state === "calendar_blocked" ? html`<button class="x" style="font-size:14px" data-rm="${s.id}" title="Remove">×</button>` : ""}</span>`)}</div></div>`) : html`<div class="card empty">No upcoming slots yet.</div>`}</div>`;
  $("#sf").onsubmit = async (e) => {
    e.preventDefault(); const f = Object.fromEntries(new FormData(e.target)); f.length_min = +f.length_min; f.repeat_weeks = +f.repeat_weeks;
    try { const x = await api("/api/iv/slots", { method: "POST", body: f }); toast(`${x.created} slot(s) added${x.skipped ? `, ${x.skipped} skipped (past or overlapping)` : ""}`, "ok"); route(); } catch (er) { fail(er); }
  };
  $$("[data-rm]", el).forEach((b) => (b.onclick = async () => { await api(`/api/iv/slots/${b.dataset.rm}`, { method: "DELETE" }).catch(fail); route(); }));
  const disconnect = $("#google-disconnect", el);
  if (disconnect) disconnect.onclick = async () => {
    if (!confirm("Disconnect Google Calendar? Existing events stay on your calendar, but future changes will no longer sync.")) return;
    disconnect.disabled = true;
    try {
      await api("/api/iv/google/disconnect", { method: "POST" });
      toast("Google Calendar disconnected", "ok");
      route();
    } catch (e) { disconnect.disabled = false; fail(e); }
  };
};

// ------------------------------------------------------------------ proof
VIEWS.proof = async (el) => {
  const p = await api("/api/proof");
  const ev = p.eval;
  const canRun = ["lead", "admin"].includes(S.me.role);
  const canRace = ["hr", "admin"].includes(S.me.role);
  el.innerHTML = html`
  <div class="page-head"><div class="grow"><h1>How we know it works</h1><p>${window.LEADDESK_PREVIEW_MODE ? "Sample results for the interactive preview. Live checks run only in the full app." : "Live checks of the claims this app makes - run them yourself."}</p></div></div>
  <div class="grid g2">
    <div class="card"><div class="section-title"><h2>💬 SOP assistant test</h2><span class="grow"></span>${canRun ? html`<button class="btn primary" id="run">${window.LEADDESK_PREVIEW_MODE ? "Show sample results" : "▶ Run test questions"}</button>` : ""}</div>
      <div id="evbox">${evalBox(ev)}</div></div>
    <div class="stack">
      <div class="card"><h2>🤖 Local AI</h2><p>${p.ai.online ? html`<span class="proof-ok">Online</span> - model <code>${p.ai.model}</code> served by Ollama at <code>${p.ai.url}</code>. No question or document leaves this machine.`
        : window.LEADDESK_PREVIEW_MODE ? html`<span class="proof-bad">Not connected</span> - sample responses are used; no model is running.` : html`<span class="proof-bad">Offline</span> - ${p.ai.detail}. The assistant still answers by quoting the best SOP section.`}</p>
        <p class="muted small">${p.sop_sections} ${window.LEADDESK_PREVIEW_MODE ? "sample SOP sections" : "SOP sections indexed"} · ${p.gaps} ${window.LEADDESK_PREVIEW_MODE ? "sample gaps" : "open SOP gaps"}</p></div>
      <div class="card"><h2>🔐 Vault</h2><p>${window.LEADDESK_PREVIEW_MODE ? `${p.vault_docs} sample documents, including ${p.scans} example scans. No files are stored by this preview.` : `${p.vault_docs} documents stored encrypted (AES-256-GCM, one key per file, wrapped by a master key kept outside the code). ${p.scans} are scans made searchable with Tesseract OCR.`}</p>
        <p>${window.LEADDESK_PREVIEW_MODE ? "Sample audit chain:" : "Audit chain:"} ${p.audit_chain.ok ? html`<span class="proof-ok">✔ ${window.LEADDESK_PREVIEW_MODE ? "sample" : "intact"} (${p.audit_chain.entries} entries)</span>` : html`<span class="proof-bad">✖ broken</span>`}</p>
        ${S.me.role === "admin" ? html`<a class="btn sm" href="#/audit">See ciphertext on disk →</a>` : ""}</div>
      <div class="card"><div class="section-title"><h2>🗓️ Double-booking guard</h2><span class="grow"></span>${canRace ? html`<button class="btn" id="race">⚡ Simulate a race</button>` : ""}</div>
        <p class="small">${window.LEADDESK_PREVIEW_MODE ? "The sample simulates two candidates choosing the same time. It does not test a live database." : "Two candidates press “Book” on the same slot at the same moment. Bookings run in a locked database transaction and a unique index allows only one live booking per slot."}</p><div id="raceout"></div></div>
    </div>
  </div>`;
  const run = $("#run");
  if (run) run.onclick = async () => {
    run.disabled = true; run.textContent = "Running… (about a minute)";
    $("#evbox").innerHTML = `<div class="empty"><span class="typing"><span></span><span></span><span></span></span> Asking all test questions…</div>`;
    try { const r = await api("/api/sop/eval", { method: "POST" }); $("#evbox").innerHTML = evalBox(r).s; } catch (e) { fail(e); }
    run.disabled = false; run.textContent = "▶ Run test questions";
  };
  const race = $("#race");
  if (race) race.onclick = async () => {
    try {
      const r = await api("/api/iv/demo/race", { method: "POST" });
      $("#raceout").innerHTML = html`<div class="alert ${r.bookings_made === 1 ? "ok" : "bad"}"><b>${r.bookings_made === 1 ? "✔ Only one booking was made." : "✖ Double booking!"}</b><br>
        ${r.results.map((x) => html`${x.who}: ${x.ok ? "booked" : "refused - " + x.message}<br>`)}<span class="tiny">Slot ${r.slot}. The test booking was removed afterwards.</span></div>`.s;
    } catch (e) { fail(e); }
  };
};
function evalBox(ev) {
  if (!ev) return html`<div class="empty">Not run yet. Press “Run test questions”.</div>`;
  return html`<div class="row" style="gap:28px;margin-bottom:12px">
      <div><div class="score-big">${ev.answerable_passed}/${ev.answerable_total}</div><div class="muted small">answered correctly with source</div></div>
      <div><div class="score-big">${ev.gaps_caught}/${ev.gaps_total}</div><div class="muted small">out-of-scope sent to lead</div></div>
      <div><div class="score-big" style="color:var(--accent)">${ev.multilingual_passed}/${ev.multilingual_total}</div><div class="muted small">Hindi / Gujarati</div></div></div>
    <div class="muted tiny" style="margin-bottom:8px">Model ${ev.model} · run ${fmtDT(ev.at)}</div>
    <table class="t"><tbody>${ev.rows.map((r) => html`<tr><td>${r.passed ? "✅" : "❌"}</td><td><b>${r.question}</b><div class="small">${(r.answer || "").slice(0, 200)}</div>
      <div class="muted tiny">${r.sources.join(" · ") || (r.got === "needs_lead" ? "→ sent to the Needs-lead list" : "")}</div></td><td class="small muted num">${r.seconds}s</td></tr>`)}</tbody></table>`;
}

// ------------------------------------------------------------------ judge demo
// One page, real actions, in the order that tells the story. Every button calls
// the same API the product uses - nothing here is staged for the demo.
const DEMO_STEPS = [
  {
    id: "numbers", icon: "", go: "overview",
    title: "The whole shift on one screen",
    why: "Today a lead hands out work over chat and a spreadsheet, so nobody can see the total load and the same two people get everything. These figures are counted from the database on every page load, not typed into a slide.",
    cta: "Show the numbers",
    run: async () => {
      const i = await api("/api/impact");
      return html`<table class="t demo-t"><tbody>
        <tr><td class="muted">Team</td><td>${i.board.members} people · ${i.board.tasks} tasks · <b>${i.board.overdue} overdue</b> · ${i.board.due_today} due today</td></tr>
        <tr><td class="muted">Load</td><td><b>${i.board.overloaded}</b> over the ${i.board.threshold}-task line${i.board.busiest ? html` · busiest is <b>${i.board.busiest.name}</b> with ${i.board.busiest.open} open` : ""}</td></tr>
        <tr><td class="muted">Assistant</td><td>${i.assistant.asked} questions in ${i.window_days} days · <b>${i.assistant.answer_rate_pct}%</b> answered without a lead · ≈ <b>${i.assistant.hours_saved} hours</b> of lead time</td></tr>
        <tr><td class="muted">Vault</td><td>${i.vault.documents} encrypted documents · ${i.vault.scans_searchable} scans made searchable · ${i.vault.audit_entries} audit entries</td></tr>
        <tr><td class="muted">Interviews</td><td>${i.interviews.upcoming} booked (${i.interviews.hours_booked}h) · ${i.interviews.feedback_pending} awaiting feedback</td></tr>
      </tbody></table>
      <details class="tiny muted" style="margin-top:8px"><summary>How these are counted, and what is assumed</summary><ul>${i.assumptions.map((a) => html`<li>${a}</li>`)}</ul></details>`;
    },
  },
  {
    id: "answer", icon: "", go: "assistant",
    title: "A question answered from the SOP, with its source",
    why: "The assistant answers only from your SOP documents, and always shows the section it used. No source, no answer.",
    cta: "Ask: what do I do when error 402 appears?",
    run: async () => demoAnswer(await api("/api/sop/ask", { method: "POST", body: { question: "What do I do when error 402 appears?" } })),
  },
  {
    id: "honest", icon: "", go: "needs-lead",
    title: "It admits what it does not know",
    why: "The failure that kills trust in an assistant is a confident wrong answer. If no SOP section covers the question, it refuses and puts the question in the lead's queue - which is also your to-do list for writing the missing SOP.",
    cta: "Ask something the SOPs do not cover",
    run: async () => {
      const r = await api("/api/sop/ask", { method: "POST", body: { question: "What is the office Wi-Fi password?" } });
      return html`${demoAnswer(r)}<p class="tiny muted">Open <a href="#/needs-lead">Needs lead</a> - it is sitting there now.</p>`;
    },
  },
  {
    id: "hindi", icon: "🌐", go: "assistant",
    title: "Hindi and Gujarati, with no model installed",
    why: "The SOPs are English; the floor is not. A hand-written domain lexicon maps the words people actually use and passes numbers and error codes straight through, so this works on a machine with nothing downloaded. A local model, when present, only improves the phrasing.",
    cta: "Ask in Hindi",
    run: async () => {
      const r = await api("/api/sop/ask", { method: "POST", body: { question: "त्रुटि 402 आने पर मुझे क्या करना चाहिए?" } });
      return html`${demoAnswer(r)}${r.understood && r.understood.length ? html`<p class="tiny muted">Understood as: ${r.english} <span class="muted">(${r.understood.map((u) => u[0] + " → " + u[1]).join(", ")})</span></p>` : ""}`;
    },
  },
  {
    id: "vault", icon: "", go: "vault", role: ["admin"],
    title: "The vault is encrypted on disk, not just in the docs",
    why: "HR files are the most sensitive thing in the building. Each file is AES-256-GCM with its own key, wrapped by a master key kept outside the database and the code. This button reads the stored file and shows you the bytes.",
    cta: "Show me the ciphertext",
    run: async () => {
      const docs = await api("/api/vault/docs");
      const list = docs.docs || docs;
      if (!list.length) return html`<div class="empty">No documents to show.</div>`;
      const p = await api(`/api/vault/storage/${list[0].id}`);
      return html`<div style="margin-top:10px"><b>${list[0].title}</b>
        <div class="hex">${p.disk_head_hex}</div>
        <div class="hex" style="margin-top:4px">${p.disk_head_text}</div>
        <div class="alert ok" style="margin-top:8px">${p.stored_bytes} bytes on disk · entropy ${p.entropy_bits_per_byte} bits/byte (8.0 is perfectly random) · ${Math.round(p.printable_ratio * 100)}% printable · integrity ${p.sha256_matches ? "✔ matches" : "✖ mismatch"}<br><span class="tiny">${p.cipher} · master key fingerprint <code>${p.key_fingerprint}</code></span></div></div>`;
    },
  },
  {
    id: "race", icon: "", go: "interviews", role: ["hr", "admin"],
    title: "Two candidates, one slot, one booking",
    why: "The failure mode of every booking page is the double booking. Two real concurrent requests are fired at the same slot through separate threads; the database transaction and a unique index let exactly one through.",
    cta: "Fire both bookings at once",
    run: async () => {
      const r = await api("/api/iv/demo/race", { method: "POST" });
      return html`<div class="alert ${r.bookings_made === 1 ? "ok" : "bad"}" style="margin-top:10px">
        <b>${r.bookings_made === 1 ? "✔ Only one booking was made." : "✖ Double booking!"}</b><br>
        ${r.results.map((x) => html`${x.who}: ${x.ok ? "booked" : "refused - " + x.message}<br>`)}
        <span class="tiny">Slot ${r.slot}. The test booking was removed afterwards.</span></div>`;
    },
  },
  {
    id: "eval", icon: "", go: "proof", role: ["lead", "admin"],
    title: "The claim, measured",
    why: "Ten questions with known correct answers: five answerable, three that must be refused, two in Hindi and Gujarati. This is the same script that runs in the test suite, so the number cannot quietly drift.",
    cta: "Run all ten questions",
    run: async () => {
      const ev = await api("/api/sop/eval", { method: "POST" });
      return html`<div style="margin-top:10px">
        <div class="row" style="gap:28px;margin-bottom:8px">
          <div><div class="score-big">${ev.answerable_passed}/${ev.answerable_total}</div><div class="muted small">answered with source</div></div>
          <div><div class="score-big">${ev.gaps_caught}/${ev.gaps_total}</div><div class="muted small">refused correctly</div></div>
          <div><div class="score-big" style="color:var(--accent)">${ev.multilingual_passed}/${ev.multilingual_total}</div><div class="muted small">Hindi / Gujarati</div></div>
        </div>
        <div class="tiny muted">Model ${ev.model} · run ${fmtDT(ev.at)}</div></div>`;
    },
  },
];

function demoAnswer(r) {
  const ok = r.status === "answered";
  const src = (r.sources || [])[0];
  return html`<div class="alert ${ok ? "ok" : ""}" style="margin-top:10px;${ok ? "" : "border-color:var(--warn,#c98)"}">
    <b>${ok ? "Answered" : "Refused and sent to the lead"}</b>
    <span class="tiny muted">${r.mode ? " · " + r.mode : ""}${r.top_score != null ? " · match " + r.top_score : ""}</span>
    <div class="demo-ans">${r.answer || r.reason}</div>
    ${src ? html`<div class="tiny">📄 <b>${src.doc}</b> › ${src.section}</div>` : ""}
  </div>`;
}

VIEWS.demo = async (el) => {
  const steps = DEMO_STEPS.filter((s) => !s.role || s.role.includes(S.me.role));
  const hidden = DEMO_STEPS.length - steps.length;
  el.innerHTML = html`
  <div class="page-head"><div class="grow"><h1>Judge demo</h1>
    <p>${window.LEADDESK_PREVIEW_MODE ? `${steps.length} sample steps. Buttons simulate the experience with synthetic data; changes reset on refresh.` : `${steps.length} steps, about three minutes. Every button runs the real thing against the real database - nothing on this page is staged.`}</p></div></div>
  <div class="stack">
    ${steps.map((s, i) => html`<div class="card demo-step">
      <div class="demo-row">
        <div class="demo-num">${i + 1}</div>
        <div class="grow">
          <h2 class="demo-h">${s.icon} ${s.title}</h2>
          <p class="small muted demo-why">${window.LEADDESK_PREVIEW_MODE ? "Uses synthetic sample data. Actions are simulated in this browser session; nothing is sent or saved." : s.why}</p>
          <div class="row">
            <button class="btn primary" data-run="${s.id}">${s.cta}</button>
            ${s.go ? html`<a class="btn" href="#/${s.go}">Open the page →</a>` : ""}
          </div>
          <div data-out="${s.id}"></div>
        </div>
      </div></div>`)}
    <div class="card"><p class="muted small" style="margin:0">Signed in as <b>${S.me.name}</b> (${S.me.role_label}).
      ${hidden ? html`${hidden} step${hidden === 1 ? "" : "s"} appear for other roles - use the person switcher at the top right.` : ""}
      The full written case is in <code>docs/HACKATHON_PLAYBOOK.md</code>.</p></div>
  </div>`;
  $$("[data-run]").forEach((b) => (b.onclick = async () => {
    const step = DEMO_STEPS.find((x) => x.id === b.dataset.run);
    const out = $(`[data-out="${step.id}"]`);
    const label = b.textContent;
    b.disabled = true; b.textContent = "Running…";
    out.innerHTML = `<div class="empty"><span class="typing"><span></span><span></span><span></span></span> Working…</div>`;
    try { out.innerHTML = html`${await step.run()}`.s; }
    catch (e) { out.innerHTML = html`<div class="alert bad">${e.message}</div>`.s; }
    b.disabled = false; b.textContent = label;
  }));
};

// ------------------------------------------------------------------ start
boot();
