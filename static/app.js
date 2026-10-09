'use strict';

/* ---------- small helpers ---------- */
const $ = (sel, root = document) => root.querySelector(sel);
const root = $('#root');
const store = {
  get(k) { try { return sessionStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { v == null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch { /* storage blocked */ } },
};
const S = {
  token: store.get('cs_token'), user: null, meta: null, view: 'home', arg: null, seq: 0,
  notif: { unread: 0, items: [] }, lastNotif: null, badges: {}, reqTab: 'inbox', chat: null,
  staff: [], assignable: [], pq: '', timer: null,
};
const CACHE = {};

/* ---------- colour themes ---------- */
const THEMES = [
  { id: 'roman', name: 'Ancient Roman marble', light: true, sw: ['#E8E1D5', '#8B5E3C', '#5F7A6C'] },
  { id: 'chola', name: 'South Indian temple', light: true, sw: ['#E6D8C3', '#8B3A32', '#596B4F'] },
  { id: 'greek', name: 'Greek Mediterranean', light: true, sw: ['#E9E5DA', '#4A7272', '#A08A4E'] },
  { id: 'egypt', name: 'Egyptian papyrus', light: true, sw: ['#DED2B7', '#315B73', '#9A7430'] },
  { id: 'mughal', name: 'Mughal palace', light: true, sw: ['#E3D5C0', '#315B48', '#8E3D32'] },
  { id: 'renaissance', name: 'Renaissance', light: true, sw: ['#E4D9C7', '#8A5142', '#58705A'] },
  { id: 'wabi', name: 'Japanese wabi-sabi', light: true, sw: ['#DDD8CA', '#596C66', '#8C6752'] },
  { id: 'persian', name: 'Persian terracotta', light: true, sw: ['#DCCDB9', '#426B78', '#3F7E78'] },
  { id: 'coastal', name: 'Modern coastal stone', light: true, sw: ['#E5E1D8', '#587F82', '#A9824A'] },
  { id: 'bronze', name: 'Dark bronze', light: false, sw: ['#202522', '#343A35', '#A87C4F'] },
  { id: 'teal', name: 'Midnight teal', light: false, sw: ['#071221', '#142033', '#5fe3c6'] },
];
function savedTheme() {
  let id = null;
  try { id = localStorage.getItem('cs_theme'); } catch { /* storage blocked */ }
  return THEMES.some((t) => t.id === id) ? id : 'roman';
}
function applyTheme(id) {
  const theme = THEMES.find((t) => t.id === id) || THEMES[0];
  const el = document.documentElement;
  el.dataset.theme = theme.id;
  if (theme.light) el.dataset.light = '1';
  else delete el.dataset.light;
  try { localStorage.setItem('cs_theme', theme.id); } catch { /* storage blocked */ }
  S.theme = theme.id;
}
const swatch = (t) => `<span class="swatch">${t.sw.map((c) => `<i style="background:${c}"></i>`).join('')}</span>`;
function renderThemePanel() {
  const panel = $('#themes');
  if (panel) panel.innerHTML = `<h3>Colour theme</h3>${THEMES.map((t) => `<button class="theme-opt${S.theme === t.id ? ' on' : ''}" data-act="setTheme" data-id="${t.id}">${swatch(t)}${esc(t.name)}</button>`).join('')}`;
}
const themeDots = () => `<div class="theme-dots"><span>Theme</span>${THEMES.map((t) => `<button class="theme-dot${S.theme === t.id ? ' on' : ''}" data-act="setTheme" data-id="${t.id}" title="${esc(t.name)}" aria-label="${esc(t.name)} theme" style="background:linear-gradient(135deg, ${t.sw[0]} 50%, ${t.sw[1]} 50%)"></button>`).join('')}</div>`;

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const initials = (name) => String(name || '?').replace(/^Dr\.\s*/, '').split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase();
const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }) : '');
const fmtDate = (iso) => (iso ? new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' }) : '');
const fmtDay = (iso) => new Date(iso + 'T00:00').toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' });
const fmtShort = (iso) => new Date(iso + 'T00:00').toLocaleDateString([], { day: 'numeric', month: 'short' });
const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
function ago(iso) {
  const mins = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  if (mins < 1440) return `${Math.floor(mins / 60)} h ago`;
  return fmtDate(iso);
}

const PATHS = {
  home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5 10v10h14V10"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  queue: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5"/><path d="M16 4.8a3.5 3.5 0 0 1 0 6.4M18.5 14.8c1.7.8 2.7 2.5 3 5.2"/>',
  bed: '<path d="M3 18V6M3 14h18v4M21 14v-2a3 3 0 0 0-3-3h-7v5"/><circle cx="7" cy="11" r="1.8"/>',
  check: '<path d="M9 11.5 11.5 14 16 9"/><rect x="3.5" y="3.5" width="17" height="17" rx="4"/>',
  list: '<path d="M9 6h12M9 12h12M9 18h12"/><path d="m3 6 1.2 1.2L6.2 5M3 12l1.2 1.2L6.2 11M3 18l1.2 1.2L6.2 17"/>',
  chat: '<path d="M20 15a3 3 0 0 1-3 3H9l-5 3V7a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3z"/>',
  shield: '<path d="M12 3 4.5 6v6c0 4.5 3.2 7.7 7.5 9 4.3-1.3 7.5-4.5 7.5-9V6z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
  bell: '<path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 20.5a2.2 2.2 0 0 0 4 0"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
  logout: '<path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4M10 16l-4-4 4-4M6 12h10"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  x: '<path d="m6 6 12 12M18 6 6 18"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  back: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"/>',
  pulse: '<path d="M3 12h4l2.5-6 4 12 2.5-6h5"/>',
  download: '<path d="M12 4v11M7.5 11 12 15.5 16.5 11M5 20h14"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12 20 3M16 7l3 3M14 9l2 2"/>',
  idcard: '<rect x="3" y="5" width="18" height="14" rx="3"/><circle cx="9" cy="11" r="2.2"/><path d="M5.5 16c.6-1.6 1.9-2.4 3.5-2.4s2.9.8 3.5 2.4M15 10h4M15 13.5h3"/>',
  palette: '<path d="M12 3a9 9 0 1 0 0 18c1.2 0 2-.9 2-2 0-.6-.2-1-.5-1.4-.3-.4-.5-.8-.5-1.3 0-1.1.9-2 2-2h2.3A3.7 3.7 0 0 0 21 10.6C21 6.4 17 3 12 3z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7.5" r="1"/><circle cx="14.5" cy="7.5" r="1"/>',
};
const ic = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${PATHS[name]}</svg>`;
const avatar = (name, role) => `<span class="avatar ${esc(role || '')}">${esc(initials(name))}</span>`;

async function api(path, method = 'GET', body) {
  const headers = { 'Content-Type': 'application/json' };
  if (S.token) headers.Authorization = `Bearer ${S.token}`;
  let res;
  try {
    res = await fetch('/api' + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new Error('Cannot reach the server. Check that it is running.');
  }
  if (res.status === 401 && S.user) {
    signOut(false);
    throw new Error('Your session ended. Please sign in again.');
  }
  const isJson = (res.headers.get('content-type') || '').includes('json');
  const data = isJson ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = data && data.detail;
    throw new Error(typeof detail === 'string' ? detail : 'Please check the details and try again.');
  }
  return data;
}

function toast(message, isError) {
  const el = document.createElement('div');
  el.className = 'toast' + (isError ? ' error' : '');
  el.textContent = message;
  $('#toasts').append(el);
  setTimeout(() => el.remove(), isError ? 5200 : 3600);
}

function openModal(html) {
  const m = $('#modal');
  m.innerHTML = `<div class="modal-card glass" role="dialog" aria-modal="true">${html}</div>`;
  m.hidden = false;
  const first = m.querySelector('input:not([type=hidden]), select, textarea');
  if (first) first.focus();
}
function closeModal() {
  $('#modal').hidden = true;
  $('#modal').innerHTML = '';
}

/* ---------- sign in ---------- */
async function renderLogin() {
  let demo = [];
  try { demo = await api('/demo/accounts'); } catch { /* demo mode off */ }
  root.innerHTML = `
  <div class="login">
    <section class="hero">
      <div class="brand"><span class="brand-mark">${ic('pulse')}</span>CareSync</div>
      <h1>One hospital.<br><em>One patient record.</em><br>No waiting on paper.</h1>
      <p>Every department works from the same live record, so a patient only ever needs their name or ID.</p>
      <ul class="hero-points">
        <li>${ic('check')}<span><b>Live queues and wait estimates</b> for patients, reception and doctors.</span></li>
        <li>${ic('check')}<span><b>Approvals, tasks and messages</b> between staff, inside the same app.</span></li>
        <li>${ic('check')}<span><b>Role-based access</b> checked on the server, with an audit trail.</span></li>
      </ul>
      ${themeDots()}
    </section>
    <section class="login-card glass">
      <h2>Sign in</h2>
      <p class="sub">Staff use their username. Patients use their patient ID and PIN.</p>
      <form class="form" data-form="login">
        <label class="field">Username or patient ID<input name="username" autocomplete="username" required></label>
        <label class="field">Password or PIN<input name="password" type="password" autocomplete="current-password" required></label>
        <button class="btn primary block" type="submit">Sign in ${ic('arrow')}</button>
      </form>
      ${demo.length ? `<div class="demo">
        <div class="demo-title">Demo mode: open a workspace</div>
        <div class="demo-grid">${demo.map((a) => `
          <button class="demo-btn" data-act="demo" data-username="${esc(a.username)}">${avatar(a.name, a.role)}
            <span><b>${esc(a.name)}</b><small>${esc(a.role)}${a.department ? ' · ' + esc(a.department) : ''}</small></span>
          </button>`).join('')}</div>
      </div>` : ''}
    </section>
  </div>`;
}

async function startSession(data) {
  S.token = data.token;
  store.set('cs_token', data.token);
  await boot();
}

function signOut(callServer = true) {
  if (callServer && S.token) api('/logout', 'POST').catch(() => {});
  clearInterval(S.timer);
  Object.assign(S, { token: null, user: null, view: 'home', arg: null, lastNotif: null, chat: null, badges: {}, reqTab: 'inbox', pq: '', staff: [], assignable: [], notif: { unread: 0, items: [] } });
  store.set('cs_token', null);
  closeModal();
  renderLogin();
}

/* ---------- shell and routing ---------- */
const NAV = {
  patient: ['home'],
  receptionist: ['home', 'queue', 'patients', 'beds', 'requests', 'tasks', 'messages'],
  nurse: ['home', 'patients', 'beds', 'requests', 'tasks', 'messages'],
  doctor: ['home', 'patients', 'requests', 'tasks', 'messages'],
  dean: ['home', 'analytics', 'queue', 'patients', 'beds', 'staff', 'requests', 'tasks', 'messages'],
  chairman: ['home', 'analytics', 'queue', 'patients', 'beds', 'staff', 'requests', 'tasks', 'messages', 'admin'],
};
const HOME_LABEL = { patient: 'My visit', receptionist: 'Front desk', nurse: 'Ward queue', doctor: 'My queue', dean: 'Overview', chairman: 'Overview' };
const LABEL = { analytics: 'Analytics', queue: 'Live queue', patients: 'Patient records', beds: 'Beds', staff: 'Staff accounts', requests: 'Approvals', tasks: 'Tasks', messages: 'Messages', admin: 'Admin and audit', consult: 'Consultation' };
const ICON = { home: 'home', analytics: 'chart', queue: 'queue', patients: 'users', beds: 'bed', staff: 'idcard', requests: 'check', tasks: 'list', messages: 'chat', admin: 'shield' };
const label = (view) => (view === 'home' ? HOME_LABEL[S.user.role] : view === 'requests' && !['doctor', 'dean', 'chairman'].includes(S.user.role) ? 'Requests' : LABEL[view]);

function renderShell() {
  const u = S.user;
  const staff = u.role !== 'patient';
  root.innerHTML = `
  <div class="shell">
    <aside class="side glass">
      <div class="brand"><span class="brand-mark">${ic('pulse')}</span>CareSync</div>
      <nav class="nav" id="nav"></nav>
      <div class="side-foot">${avatar(u.name, u.role)}<div><b>${esc(u.name)}</b><small>${esc(u.role)}${u.department ? ' · ' + esc(u.department) : ''}</small></div>
        <button class="foot-btn" data-act="myPassword" title="Change my password" aria-label="Change my password">${ic('key')}</button></div>
    </aside>
    <main class="main">
      <header class="top">
        <div><h1 id="title"></h1><div class="crumb" id="crumb"></div></div>
        <span class="grow"></span>
        ${staff ? `<label class="lookup">${ic('search')}<input id="lookup" placeholder="Patient ID or name" aria-label="Find a patient"></label>` : ''}
        <div class="notif-wrap theme-wrap">
          <button class="icon-btn" data-act="themeMenu" aria-label="Colour theme" title="Colour theme">${ic('palette')}</button>
          <div class="theme-panel glass" id="themes" hidden></div>
        </div>
        <div class="notif-wrap">
          <button class="icon-btn" data-act="bell" aria-label="Notifications">${ic('bell')}<span class="dot" id="bell-dot" hidden></span></button>
          <div class="notif glass" id="notif" hidden></div>
        </div>
        <button class="icon-btn" data-act="signout" aria-label="Sign out" title="Sign out">${ic('logout')}</button>
      </header>
      <div id="view" class="view"></div>
    </main>
  </div>`;
  renderNav();
}

function renderNav() {
  const nav = $('#nav');
  if (!nav) return;
  nav.innerHTML = NAV[S.user.role].map((v) => {
    const n = S.badges[v] || 0;
    const active = S.view === v || (S.view === 'consult' && v === 'home');
    return `<button data-act="go" data-view="${v}" class="${active ? 'on' : ''}">${ic(ICON[v])}${esc(label(v))}${n ? `<span class="count">${n}</span>` : ''}</button>`;
  }).join('');
}

function go(view, arg = null) {
  if (view !== 'consult' && !NAV[S.user.role].includes(view)) view = 'home';
  S.view = view;
  S.arg = arg;
  $('#notif').hidden = true;
  renderNav();
  paint();
  window.scrollTo({ top: 0 });
}

async function paint() {
  const seq = ++S.seq;
  const el = $('#view');
  const today = new Date().toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'long' });
  $('#title').textContent = label(S.view);
  $('#crumb').textContent = S.user.department ? `${S.user.department} · ${today}` : today;
  try {
    const html = await VIEW[S.view]();
    if (seq !== S.seq) return;
    el.innerHTML = html;
  } catch (err) {
    if (seq !== S.seq || !S.user) return;
    el.innerHTML = `<div class="card glass"><div class="empty">${esc(err.message)}<br><br><button class="btn small" data-act="go" data-view="${esc(S.view)}">Try again</button></div></div>`;
  }
  el.style.animation = 'none';
  void el.offsetHeight;
  el.style.animation = '';
  if (AFTER[S.view]) AFTER[S.view]();
}

/* Regions marked data-live refresh on their own, so open forms are never wiped. */
const LIVE = {};
const AFTER = {};
async function live(name) {
  const html = await LIVE[name]();
  CACHE[name] = html;
  return `<div data-live="${name}">${html}</div>`;
}
async function refreshLive(name) {
  const el = $(`#view [data-live="${name}"]`);
  if (!el) return;
  const seq = S.seq;
  const html = await LIVE[name]();
  if (seq !== S.seq || !el.isConnected || CACHE[name] === html) return;
  CACHE[name] = html;
  el.innerHTML = html;
  if (name === 'thread') scrollChat();
}
async function tick() {
  if (!S.user || document.hidden) return;
  try { await refreshNotifs(); } catch { return; }
  for (const el of document.querySelectorAll('#view [data-live]')) {
    const active = document.activeElement;
    if (active && el.contains(active) && /INPUT|TEXTAREA|SELECT/.test(active.tagName)) continue;
    try { await refreshLive(el.dataset.live); } catch { /* keep the last good view */ }
  }
}

async function refreshNotifs() {
  const calls = [api('/notifications')];
  if (S.user.role !== 'patient') calls.push(api('/badges'));
  const [n, b] = await Promise.all(calls);
  const newest = n.items[0] ? n.items[0].id : 0;
  if (S.lastNotif !== null && newest > S.lastNotif && !n.items[0].read) toast(n.items[0].text);
  S.lastNotif = newest;
  S.notif = n;
  const dot = $('#bell-dot');
  if (dot) { dot.hidden = !n.unread; dot.textContent = n.unread > 9 ? '9+' : n.unread; }
  if (b && JSON.stringify(b) !== JSON.stringify(S.badges)) { S.badges = b; renderNav(); }
  if ($('#notif') && !$('#notif').hidden) renderNotifs();
}
function renderNotifs() {
  $('#notif').innerHTML = `<h3>Notifications</h3>${S.notif.items.length ? S.notif.items.map((n) => `
    <button class="${n.read ? '' : 'unread'}" data-act="go" data-view="${esc(n.view || 'home')}">${esc(n.text)}<small>${ago(n.at)}</small></button>`).join('')
    : '<div class="empty">Nothing new</div>'}`;
}

/* ---------- shared pieces ---------- */
const STATUS_PILL = { waiting: ['warn', 'Waiting'], in_consultation: ['good', 'With doctor'], done: ['', 'Completed'] };
const statusPill = (s) => `<span class="pill ${STATUS_PILL[s][0]}">${STATUS_PILL[s][1]}</span>`;

function deptTable(st) {
  return `<div class="scroll-x"><table>
    <thead><tr><th>Department</th><th class="num">Waiting</th><th class="num">Doctors free</th><th class="num">Wait for a new patient</th></tr></thead>
    <tbody>${st.departments.map((d) => `<tr><td>${esc(d.name)}</td><td class="num">${d.waiting}</td>
      <td class="num">${d.doctors_available ? d.doctors_available : '<span class="pill bad plain">none</span>'}</td>
      <td class="num">${d.est_wait ? `about ${d.est_wait} min` : '<span class="pill good plain">no wait</span>'}</td></tr>`).join('')}</tbody></table></div>`;
}
function doctorList(st) {
  return `<div class="list">${st.doctors.map((d) => `<div class="item"><div class="item-head">${avatar(d.name, 'doctor')}
    <span class="grow"><b>${esc(d.name)}</b><div class="meta">${esc(d.department)}</div></span>
    <span class="pill ${d.available ? 'good' : 'bad'}">${d.available ? 'Available' : 'Away'}</span></div></div>`).join('')}</div>`;
}
function wardList(st) {
  return `<div class="bars" data-group>${st.wards.map((w) => `<div class="ward-row" data-tip="${esc(w.ward)}" data-val="${w.free} of ${w.total} beds free"><div class="spread"><span>${esc(w.ward)}</span>
    <span class="hint"><b style="color:var(--text)">${w.free}</b> of ${w.total} free</span></div>
    <div class="meter" style="margin-top:8px"><i style="width:${Math.round((100 * (w.total - w.free)) / w.total)}%"></i></div></div>`).join('')}</div>`;
}
function vitalsRow(v) {
  if (!v || !(v.bp || v.temp || v.pulse || v.spo2)) return '';
  return `<div class="vitals">${v.bp ? `<span>BP <b>${esc(v.bp)}</b></span>` : ''}${v.temp ? `<span>Temp <b>${esc(v.temp)}°F</b></span>` : ''}
    ${v.pulse ? `<span>Pulse <b>${esc(v.pulse)}</b></span>` : ''}${v.spo2 ? `<span>SpO2 <b>${esc(v.spo2)}%</b></span>` : ''}</div>`;
}
function visitCard(v) {
  const clinical = 'diagnosis' in v;
  return `<div class="item">
    <div class="item-head"><span class="grow"><b>${esc(v.department)}</b>
      <div class="meta">${fmtDate(v.checkin_at)} · ${fmtTime(v.checkin_at)}${v.doctor ? ' · ' + esc(v.doctor) : ''}</div></span>
      ${v.referred_from ? `<span class="pill info">Referred from ${esc(v.referred_from)}</span>` : ''}${statusPill(v.status)}</div>
    ${v.complaint ? `<div class="meta">Complaint: ${esc(v.complaint)}</div>` : ''}
    ${clinical ? `${vitalsRow(v.vitals)}
      ${v.diagnosis ? `<div><span class="faint">Diagnosis</span><br><b style="font-weight:600">${esc(v.diagnosis)}</b></div>` : ''}
      ${v.notes ? `<div class="meta">${esc(v.notes)}</div>` : ''}
      ${v.prescriptions.length ? `<div class="meds">${v.prescriptions.map((m) => `<div><b>${esc(m.medicine)}</b><span class="faint">${esc(m.dosage)}${m.duration ? ' · ' + esc(m.duration) : ''}</span></div>`).join('')}</div>` : ''}` : ''}
  </div>`;
}
function picker(placeholder) {
  return `<div class="picker"><input data-q placeholder="${esc(placeholder)}" autocomplete="off" required>
    <input type="hidden" name="pid"><div class="picker-results"></div></div>`;
}
function columns(rows, key, labelOf, markLast, unit = 'patient') {
  const max = Math.max(1, ...rows.map((r) => r[key]));
  return `<div class="columns" data-group>${rows.map((r, i) => `<div class="col${markLast && i === rows.length - 1 ? ' today' : ''}" data-tip="${esc(labelOf(r, true))}" data-val="${esc(plural(r[key], unit))}" aria-label="${esc(labelOf(r, true))}: ${esc(plural(r[key], unit))}">
    <em>${r[key]}</em><i style="height:calc((100% - 40px) * ${(r[key] / max).toFixed(3)})"></i><span>${esc(labelOf(r))}</span></div>`).join('')}</div>`;
}
function bars(rows, nameKey, key, unit) {
  const max = Math.max(1, ...rows.map((r) => r[key]));
  return `<div class="bars" data-group>${rows.map((r) => `<div class="bar-row" data-tip="${esc(r[nameKey])}" data-val="${r[key]}${esc(unit)}"><span>${esc(r[nameKey])}</span>
    <div class="meter"><i style="width:${Math.round((100 * r[key]) / max)}%"></i></div><span class="v">${r[key]}${unit}</span></div>`).join('')}</div>`;
}
function queueItem(v, actions) {
  return `<div class="item${v.status === 'in_consultation' ? ' hot' : ''}">
    <div class="item-head"><span class="token">${esc(v.token)}</span>
      <span class="grow"><b>${esc(v.patient.name)}</b><div class="meta"><span class="mono">${esc(v.patient.pid)}</span> · ${v.patient.age} y · ${esc(v.patient.gender)}</div></span>
      ${v.referred_from ? `<span class="pill info">From ${esc(v.referred_from)}</span>` : ''}
      ${v.status === 'waiting' ? `<span class="pill warn">Waited ${v.waited} min</span>` : statusPill(v.status)}</div>
    ${v.complaint ? `<div class="meta">${esc(v.complaint)}</div>` : ''}
    ${v.patient.allergies ? `<div class="alert">Allergy: ${esc(v.patient.allergies)}</div>` : ''}
    ${vitalsRow(v.vitals)}${actions || ''}</div>`;
}
function taskItem(t, mine) {
  const pill = { open: ['warn', 'Open'], in_progress: ['info', 'In progress'], done: ['good', 'Done'] }[t.status];
  const btn = (status, text) => `<button class="btn small" data-act="taskStatus" data-id="${t.id}" data-status="${status}">${text}</button>`;
  return `<div class="item"><div class="item-head"><span class="grow"><b>${esc(t.title)}</b>
      <div class="meta">${mine ? 'From ' + esc(t.assigned_by) : 'To ' + esc(t.assigned_to)} · ${ago(t.created_at)}${t.patient_pid ? ` · <span class="mono">${esc(t.patient_pid)}</span>` : ''}</div></span>
      ${t.priority === 'urgent' ? '<span class="pill bad">Urgent</span>' : ''}<span class="pill ${pill[0]}">${pill[1]}</span></div>
    ${t.details ? `<div class="meta">${esc(t.details)}</div>` : ''}
    <div class="row">${t.status === 'open' && mine ? btn('in_progress', 'Start') : ''}${t.status !== 'done' ? btn('done', 'Mark done') : btn('open', 'Reopen')}</div></div>`;
}

/* ---------- home, by role ---------- */
const HOME = {};
const VIEW = { home: () => HOME[S.user.role]() };

LIVE.patientHome = async () => {
  const [rec, st, appts] = await Promise.all([api('/my/record'), api('/status'), api('/my/appointments')]);
  const a = rec.active;
  const past = rec.visits.filter((v) => v.status === 'done');
  const ticket = a ? `<div class="ticket glass">
      <div><div class="hint">Your token · ${esc(a.department)}</div><div class="big">${esc(a.token)}</div></div>
      <div>${a.status === 'in_consultation'
        ? `<span class="pill good">It is your turn</span><p style="margin-top:10px">${esc(a.doctor || 'The doctor')} is ready for you now.</p>`
        : `<div class="facts"><div><b>${a.ahead}</b><span>${a.ahead === 1 ? 'patient' : 'patients'} ahead of you</span></div>
           <div><b>${a.est_wait ? '~' + a.est_wait + ' min' : 'Next'}</b><span>estimated wait</span></div>
           <div><b>${fmtTime(a.checkin_at)}</b><span>checked in</span></div></div>
           <p class="hint" style="margin-top:14px">This updates by itself. You do not need to carry any papers: your doctor already has your record.</p>`}</div>
    </div>` : `<div class="card glass"><div class="card-head"><h2>No active visit today</h2></div>
      <p class="hint">When the front desk issues your token, it will appear here with your place in the queue.</p></div>`;
  const apptCard = `<div class="card glass"><div class="card-head"><h2>My appointments</h2><span class="grow"></span>
      <button class="btn primary small" data-act="bookAppt">${ic('plus')} Book an appointment</button></div>
    ${appts.length ? `<div class="list">${appts.map((p) => `<div class="item"><div class="item-head">
        <span class="token">${esc(p.time)}</span><span class="grow"><b>${esc(p.department)}</b>
        <div class="meta">${fmtDay(p.day)}${p.reason ? ' · ' + esc(p.reason) : ''}</div></span>
        ${p.status === 'arrived' ? '<span class="pill good">Checked in</span>'
          : `<span class="pill info">Booked</span><button class="btn small danger" data-act="cancelAppt" data-id="${p.id}" data-label="${esc(p.department + ' on ' + fmtDay(p.day) + ' at ' + p.time)}">Cancel</button>`}
      </div></div>`).join('')}</div>` : '<p class="hint">No upcoming appointments. Book one to skip the registration line.</p>'}</div>`;
  return `<div class="stack">${ticket}${apptCard}
    <div class="grid cols-2">
      <div class="card glass"><div class="card-head"><h2>Doctors today</h2></div>${doctorList(st)}</div>
      <div class="stack">
        <div class="card glass"><div class="card-head"><h2>Beds available</h2></div>${wardList(st)}</div>
        <div class="card glass"><div class="card-head"><h2>Current waiting times</h2></div>${deptTable(st)}</div>
      </div>
    </div>
    <div class="card glass"><div class="card-head"><h2>My medical history</h2><span class="grow"></span>
      <span class="pill plain mono">${esc(rec.patient.pid)}</span></div>
      ${past.length ? `<div class="timeline">${past.map(visitCard).join('')}</div>` : '<div class="empty">No past visits yet</div>'}</div>
  </div>`;
};
HOME.patient = () => live('patientHome');

LIVE.deptStatus = async () => deptTable(await api('/status'));
LIVE.apptToday = async () => {
  const rows = await api('/appointments');
  return rows.length ? `<div class="list">${rows.map((p) => `<div class="item"><div class="item-head">
      <span class="token">${esc(p.time)}</span><span class="grow"><b>${esc(p.patient.name)}</b>
      <div class="meta"><span class="mono">${esc(p.patient.pid)}</span> · ${esc(p.department)}${p.reason ? ' · ' + esc(p.reason) : ''}</div></span>
      ${p.status === 'arrived' ? '<span class="pill good">Checked in</span>'
        : `<button class="btn small primary" data-act="checkinAppt" data-id="${p.id}">Check in</button>`}
    </div></div>`).join('')}</div>` : '<div class="empty">No appointments booked for today</div>';
};
async function fillSlots(form) {
  const select = $('[name=slot]', form);
  const department = $('[name=department]', form).value;
  const day = $('[name=day]', form).value;
  select.innerHTML = '<option value="">Loading times…</option>';
  try {
    const slots = await api(`/appointments/slots?department=${encodeURIComponent(department)}&day=${encodeURIComponent(day)}`);
    select.innerHTML = slots.length ? slots.map((s) => `<option value="${s.slot}">${esc(s.time)}</option>`).join('')
      : '<option value="">No free times that day</option>';
  } catch (err) {
    select.innerHTML = '<option value="">Choose a date within the next 14 days</option>';
  }
}
HOME.receptionist = async () => `
  <div class="stack"><div class="grid cols-2">
    <div class="card glass"><div class="card-head"><h2>Register a new patient</h2></div>
      <form class="form" data-form="register">
        <label class="field">Full name<input name="name" required minlength="2" maxlength="120"></label>
        <div class="three">
          <label class="field">Age<input name="age" type="number" min="0" max="120" required></label>
          <label class="field">Gender<select name="gender"><option>Female</option><option>Male</option><option>Other</option></select></label>
          <label class="field">Blood group<select name="blood_group"><option value="">Unknown</option>${['A+', 'A-', 'B+', 'B-', 'O+', 'O-', 'AB+', 'AB-'].map((b) => `<option>${b}</option>`).join('')}</select></label>
        </div>
        <div class="two">
          <label class="field">Phone<input name="phone" maxlength="20" inputmode="tel"></label>
          <label class="field">Known allergies<input name="allergies" maxlength="240" placeholder="Leave empty if none"></label>
        </div>
        <button class="btn primary" type="submit">Register and create patient ID</button>
      </form></div>
    <div class="card glass"><div class="card-head"><h2>Issue a queue token</h2></div>
      <form class="form" data-form="token" id="token-form">
        <label class="field">Patient${picker('Search by name or patient ID')}</label>
        <label class="field">Department<select name="department">${S.meta.departments.map((d) => `<option>${esc(d)}</option>`).join('')}</select></label>
        <label class="field">Reason for visit<input name="complaint" maxlength="240" placeholder="Short description"></label>
        <div class="row"><button type="button" class="btn small" data-act="suggestDept">${ic('spark')} Suggest department</button><span class="hint" id="triage-hint"></span></div>
        <button class="btn primary" type="submit">Issue token</button>
      </form></div>
  </div>
  <div class="card glass"><div class="card-head"><h2>Today's appointments</h2></div>${await live('apptToday')}</div>
  <div class="card glass"><div class="card-head"><h2>Departments right now</h2></div>${await live('deptStatus')}</div></div>`;

LIVE.nurseHome = async () => {
  const [q, tasks] = await Promise.all([api('/queue'), api('/tasks')]);
  const open = tasks.to_me.filter((t) => t.status !== 'done');
  return `<div class="grid split">
    <div class="card glass"><div class="card-head"><h2>${esc(q.department)} queue</h2><span class="grow"></span><span class="pill plain">${plural(q.visits.length, 'patient')}</span></div>
      ${q.visits.length ? `<div class="list">${q.visits.map((v) => queueItem(v, `<div class="row">
        <button class="btn small${v.vitals.bp ? '' : ' primary'}" data-act="vitals" data-id="${v.id}" data-name="${esc(v.patient.name)}" data-bp="${esc(v.vitals.bp)}" data-temp="${esc(v.vitals.temp)}" data-pulse="${esc(v.vitals.pulse)}" data-spo2="${esc(v.vitals.spo2)}">${v.vitals.bp ? 'Update vitals' : 'Record vitals'}</button>
        <button class="btn small" data-act="openPatient" data-pid="${esc(v.patient.pid)}">Open record</button></div>`)).join('')}</div>`
        : '<div class="empty">No patients waiting</div>'}</div>
    <div class="card glass"><div class="card-head"><h2>My open tasks</h2><span class="grow"></span><button class="link" data-act="go" data-view="tasks">All tasks</button></div>
      ${open.length ? `<div class="list">${open.slice(0, 5).map((t) => taskItem(t, true)).join('')}</div>` : '<div class="empty">Nothing pending</div>'}</div>
  </div>`;
};
HOME.nurse = () => live('nurseHome');

LIVE.doctorHome = async () => {
  const q = await api('/queue');
  const mine = q.visits.find((v) => v.status === 'in_consultation' && v.doctor_id === S.user.id);
  const waiting = q.visits.filter((v) => v.status === 'waiting');
  const others = q.visits.filter((v) => v.status === 'in_consultation' && v.doctor_id !== S.user.id);
  return `<div class="stack">
    <div class="card glass"><div class="spread">
      <div><b style="font-size:17px;font-weight:600">${plural(waiting.length, 'patient')} waiting in ${esc(q.department)}</b>
        <div class="hint">${q.available ? 'You are shown as available to patients and the front desk.' : 'You are shown as away. New patients see a longer wait.'}</div></div>
      <button class="toggle ${q.available ? 'on' : ''}" data-act="toggleAvail" data-next="${q.available ? '0' : '1'}"><i></i>${q.available ? 'Available' : 'Away'}</button>
    </div></div>
    ${mine ? `<div class="card glass"><div class="card-head"><h2>In your room now</h2></div>${queueItem(mine, `<div class="row">
      <button class="btn primary small" data-act="resume" data-id="${mine.id}">Continue consultation ${ic('arrow')}</button></div>`)}</div>` : ''}
    <div class="card glass"><div class="card-head"><h2>Waiting</h2></div>
      ${waiting.length ? `<div class="list">${waiting.map((v, i) => queueItem(v, `<div class="row">
        <button class="btn small${i === 0 && !mine ? ' primary' : ''}" data-act="startVisit" data-id="${v.id}" ${mine ? 'disabled' : ''}>${i === 0 ? 'Call next patient' : 'Call this patient'}</button>
        <button class="btn small" data-act="openPatient" data-pid="${esc(v.patient.pid)}">Open record</button></div>`)).join('')}</div>` : '<div class="empty">Queue is clear</div>'}
      ${others.length ? `<p class="hint" style="margin-top:14px">${plural(others.length, 'patient')} with other doctors in this department.</p>` : ''}</div>
  </div>`;
};
HOME.doctor = () => live('doctorHome');

LIVE.overview = async () => {
  const [a, st] = await Promise.all([api('/analytics'), api('/status')]);
  const k = a.kpis;
  const diff = k.avg_wait_today - k.avg_wait_14d;
  return `<div class="stack">
    <div class="grid cols-4">
      <div class="tile glass"><div class="label">Patients today</div><div class="value">${k.patients_today}</div><div class="foot">${k.waiting_now} waiting right now</div></div>
      <div class="tile glass"><div class="label">Average wait today</div><div class="value">${k.avg_wait_today}<small>min</small></div>
        <div class="foot">${diff <= 0 ? `${Math.abs(diff).toFixed(1)} min better` : `${diff.toFixed(1)} min worse`} than the 14-day average</div></div>
      <div class="tile glass"><div class="label">Bed occupancy</div><div class="value">${k.bed_occupancy}<small>%</small></div><div class="foot">${k.beds_free} beds free</div></div>
      <div class="tile glass"><div class="label">Approvals pending</div><div class="value">${k.pending_requests}</div><div class="foot">${S.badges.requests || 0} waiting on you</div></div>
    </div>
    <div class="grid cols-2">
      <div class="card glass"><div class="card-head"><h2>Departments right now</h2></div>${deptTable(st)}</div>
      <div class="card glass"><div class="card-head"><h2>Average wait by department, last 14 days</h2></div>${bars(a.by_department, 'department', 'avg_wait', ' min')}</div>
    </div>
    <div class="grid cols-2">
      <div class="card glass"><div class="card-head"><h2>Patients per day</h2><span class="grow"></span><button class="link" data-act="go" data-view="analytics">Full analytics</button></div>
        ${columns(a.daily, 'visits', (r, full) => (full ? fmtDay(r.date) : String(new Date(r.date + 'T00:00').getDate())), true)}</div>
      <div class="card glass"><div class="card-head"><h2>Beds by ward</h2></div>${wardList(st)}</div>
    </div></div>`;
};
HOME.dean = HOME.chairman = () => live('overview');

/* ---------- consultation ---------- */
const medRow = () => `<div class="med-row"><input name="med" placeholder="Medicine" maxlength="120"><input name="dose" placeholder="Dosage" maxlength="60">
  <input name="dur" placeholder="Duration" maxlength="60"><button type="button" class="icon-btn" data-act="delMed" aria-label="Remove medicine">${ic('x')}</button></div>`;

VIEW.consult = async () => {
  const visit = await api('/visits/' + S.arg);
  const rec = await api('/patients/' + encodeURIComponent(visit.patient.pid));
  const p = rec.patient;
  const history = rec.visits.filter((v) => v.id !== visit.id && v.status === 'done');
  return `<div class="grid split">
    <div class="stack">
      <div class="card glass"><div class="card-head">${avatar(p.name, 'patient')}<div><h2>${esc(p.name)}</h2>
          <div class="hint"><span class="mono">${esc(p.pid)}</span> · ${p.age} y · ${esc(p.gender)} · Blood group ${esc(p.blood_group || 'unknown')}</div></div>
          <span class="grow"></span><span class="token">${esc(visit.token)}</span></div>
        ${p.allergies ? `<div class="alert" style="margin-bottom:12px">Allergy: ${esc(p.allergies)}</div>` : ''}
        ${visit.referred_from ? `<div class="note" style="margin-bottom:12px"><small>Referral</small>From ${esc(visit.referred_from)}${visit.referred_by ? ' by ' + esc(visit.referred_by) : ''}</div>` : ''}
        <dl class="kv"><dt>Today</dt><dd>${esc(visit.complaint || 'No reason recorded')}</dd><dt>Checked in</dt><dd>${fmtTime(visit.checkin_at)}</dd></dl>
        <div style="margin-top:12px">${vitalsRow(visit.vitals) || '<span class="hint">Vitals not recorded yet</span>'}</div>
        <div style="margin-top:16px"><button class="btn small" data-act="summary" data-pid="${esc(p.pid)}">${ic('spark')} Summarise history</button></div>
        <div id="summary" style="margin-top:12px"></div></div>
      <div class="card glass"><div class="card-head"><h2>History across all departments</h2><span class="grow"></span><span class="pill plain">${plural(history.length, 'visit')}</span></div>
        ${history.length ? `<div class="timeline">${history.map(visitCard).join('')}</div>` : '<div class="empty">First visit to this hospital</div>'}</div>
    </div>
    <div><div class="card glass sticky"><div class="card-head"><h2>Close this consultation</h2></div>
      <form class="form" data-form="complete" data-id="${visit.id}">
        <label class="field">Diagnosis<input name="diagnosis" required minlength="2" maxlength="240"></label>
        <label class="field">Notes<textarea name="notes" maxlength="2000" placeholder="Findings, advice, follow-up"></textarea></label>
        <div class="field" style="display:grid;gap:8px;color:var(--muted);font-size:13px">Medicines<div id="meds" style="display:grid;gap:8px">${medRow()}</div>
          <div><button type="button" class="btn small" data-act="addMed">${ic('plus')} Add medicine</button></div></div>
        <label class="field">Refer to another department<select name="refer_to"><option value="">No referral</option>
          ${S.meta.departments.filter((d) => d !== visit.department).map((d) => `<option>${esc(d)}</option>`).join('')}</select></label>
        <label class="field">Reason for referral<input name="refer_reason" maxlength="200" placeholder="Shown to the next doctor"></label>
        <button class="btn primary" type="submit">Save and close visit</button>
        <button class="btn" type="button" data-act="go" data-view="home">Back to queue</button>
      </form></div></div>
  </div>`;
};

/* ---------- queue, patients, beds ---------- */
LIVE.queueAll = async () => {
  const q = await api('/queue');
  return `<div class="grid cols-3">${S.meta.departments.map((d) => {
    const rows = q.visits.filter((v) => v.department === d);
    return `<div class="card glass"><div class="card-head"><h2>${esc(d)}</h2><span class="grow"></span><span class="pill plain">${rows.length}</span></div>
      ${rows.length ? `<div class="list">${rows.map((v) => `<div class="item${v.status === 'in_consultation' ? ' hot' : ''}"><div class="item-head">
        <span class="token">${esc(v.token)}</span><span class="grow"><b>${esc(v.patient.name)}</b></span></div>
        <div class="meta">${v.status === 'waiting' ? `Waited ${v.waited} min · ${v.est_wait ? 'about ' + v.est_wait + ' min to go' : 'next in line'}` : 'With ' + esc(v.doctor)}</div></div>`).join('')}</div>`
        : '<div class="empty">No one waiting</div>'}</div>`;
  }).join('')}</div>`;
};
VIEW.queue = () => live('queueAll');

function patientRows(rows) {
  return rows.length ? `<div class="list">${rows.map((p) => `<button class="item" style="text-align:left;cursor:pointer" data-act="openPatient" data-pid="${esc(p.pid)}">
    <div class="item-head">${avatar(p.name, 'patient')}<span class="grow"><b>${esc(p.name)}</b><div class="meta">${p.age} y · ${esc(p.gender)}${p.phone ? ' · ' + esc(p.phone) : ''}</div></span>
    <span class="pill plain mono">${esc(p.pid)}</span></div></button>`).join('')}</div>` : '<div class="empty">No matching patients</div>';
}
VIEW.patients = async () => {
  if (S.arg) {
    const rec = await api('/patients/' + encodeURIComponent(S.arg));
    const p = rec.patient;
    const canSummarise = ['doctor', 'dean', 'chairman'].includes(S.user.role);
    return `<div class="stack">
      <div><button class="btn small" data-act="go" data-view="patients">${ic('back')} All patients</button></div>
      <div class="card glass"><div class="card-head">${avatar(p.name, 'patient')}<div><h2>${esc(p.name)}</h2>
          <div class="hint"><span class="mono">${esc(p.pid)}</span> · ${p.age} y · ${esc(p.gender)}</div></div><span class="grow"></span>
          ${rec.bed ? `<span class="pill info">Bed ${esc(rec.bed.label)} · ${esc(rec.bed.ward)}</span>` : ''}</div>
        ${p.allergies && rec.clinical ? `<div class="alert" style="margin-bottom:14px">Allergy: ${esc(p.allergies)}</div>` : ''}
        <dl class="kv"><dt>Phone</dt><dd>${esc(p.phone || 'Not given')}</dd><dt>Blood group</dt><dd>${esc(p.blood_group || 'Unknown')}</dd>
          <dt>Registered</dt><dd>${fmtDate(p.registered)}</dd></dl>
        ${canSummarise ? `<div style="margin-top:16px"><button class="btn small" data-act="summary" data-pid="${esc(p.pid)}">${ic('spark')} Summarise history</button></div><div id="summary" style="margin-top:12px"></div>` : ''}
        ${rec.clinical ? '' : '<p class="hint" style="margin-top:14px">Clinical details are visible to medical staff only.</p>'}</div>
      <div class="card glass"><div class="card-head"><h2>Visits across all departments</h2><span class="grow"></span><span class="pill plain">${plural(rec.visits.length, 'visit')}</span></div>
        ${rec.visits.length ? `<div class="timeline">${rec.visits.map(visitCard).join('')}</div>` : '<div class="empty">No visits yet</div>'}</div>
    </div>`;
  }
  const rows = await api('/patients?q=' + encodeURIComponent(S.pq));
  return `<div class="card glass"><div class="card-head"><h2>Find a patient</h2></div>
    <input id="psearch" placeholder="Type a name or patient ID" value="${esc(S.pq)}" autocomplete="off" style="margin-bottom:16px">
    <div id="presults">${patientRows(rows)}</div></div>`;
};
AFTER.patients = () => { const el = $('#psearch'); if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } };

const canEditBeds = () => ['receptionist', 'nurse', 'dean', 'chairman'].includes(S.user.role);
LIVE.beds = async () => {
  const beds = await api('/beds');
  const wards = [...new Set(beds.map((b) => b.ward))];
  const text = { free: 'Free', cleaning: 'Cleaning' };
  return `<div class="wards">${wards.map((w) => {
    const rows = beds.filter((b) => b.ward === w);
    return `<div class="card glass"><div class="card-head"><h2>${esc(w)}</h2><span class="grow"></span>
      <span class="hint">${rows.filter((b) => b.status === 'free').length} of ${rows.length} free</span></div>
      <div class="beds">${rows.map((b) => `<button class="bed ${b.status}" data-act="bed" data-id="${b.id}" data-label="${esc(b.label)}" data-status="${b.status}"
        data-patient="${esc(b.patient ? b.patient.name + ' · ' + b.patient.pid : '')}" ${canEditBeds() ? '' : 'disabled'}>
        <b>${esc(b.label)}</b><small>${b.patient ? esc(b.patient.name) : text[b.status]}</small></button>`).join('')}</div></div>`;
  }).join('')}</div>`;
};
VIEW.beds = () => live('beds');

/* ---------- approvals ---------- */
const REQ_PILL = { pending: 'warn', approved: 'good', rejected: 'bad' };
function requestItem(r) {
  return `<div class="item"><div class="item-head"><span class="grow"><b>${esc(r.title)}</b>
      <div class="meta">${esc(r.kind)} · ${esc(r.creator.name)} (${esc(r.creator.role)}${r.creator.department ? ', ' + esc(r.creator.department) : ''}) · ${ago(r.created_at)}</div></span>
      <span class="pill ${REQ_PILL[r.status]}">${r.status === 'pending' ? 'Waiting on ' + esc(r.waiting_on) : r.status[0].toUpperCase() + r.status.slice(1)}</span></div>
    ${r.details ? `<div class="meta">${esc(r.details)}</div>` : ''}
    ${r.patient_pid ? `<div><button class="link mono" data-act="openPatient" data-pid="${esc(r.patient_pid)}">${esc(r.patient_pid)}</button></div>` : ''}
    <div class="trail">${r.trail.map((e, i) => `${i ? ic('arrow') : ''}<span title="${esc(e.note)}">${esc(e.who)} ${esc(e.action)}${e.note ? ': ' + esc(e.note) : ''}</span>`).join('')}</div>
    ${r.can_act ? `<div class="row">
      <button class="btn small primary" data-act="decide" data-id="${r.id}" data-action="approve" data-title="${esc(r.title)}">Approve</button>
      ${r.can_forward ? `<button class="btn small" data-act="decide" data-id="${r.id}" data-action="forward" data-to="${esc(r.forward_to)}" data-title="${esc(r.title)}">Send to ${esc(r.forward_to)}</button>` : ''}
      <button class="btn small danger" data-act="decide" data-id="${r.id}" data-action="reject" data-title="${esc(r.title)}">Reject</button></div>` : ''}</div>`;
}
LIVE.requests = async () => {
  const data = await api('/requests');
  const tabs = [['inbox', `Waiting on me (${data.inbox.length})`], ['mine', 'Raised by me'], ['handled', 'Handled by me']];
  if (data.all) tabs.push(['all', 'Whole hospital']);
  const usable = tabs.filter(([k]) => k !== 'mine' || data.can_create);
  if (!usable.some(([k]) => k === S.reqTab)) S.reqTab = usable[0][0];
  const rows = data[S.reqTab];
  return `<div class="spread" style="align-items:flex-start"><div class="tabs">${usable.map(([k, t]) => `<button data-act="reqTab" data-tab="${k}" class="${S.reqTab === k ? 'on' : ''}">${t}</button>`).join('')}</div>
    ${data.can_create ? `<button class="btn primary" data-act="newRequest">${ic('plus')} New request</button>` : ''}</div>
    ${rows.length ? `<div class="list">${rows.map(requestItem).join('')}</div>` : '<div class="card glass"><div class="empty">Nothing here</div></div>'}`;
};
VIEW.requests = () => live('requests');

/* ---------- tasks ---------- */
LIVE.tasks = async () => {
  const data = await api('/tasks');
  S.assignable = data.assignable;
  const col = (title, rows, mine) => `<div class="card glass"><div class="card-head"><h2>${title}</h2><span class="grow"></span><span class="pill plain">${rows.filter((t) => t.status !== 'done').length} open</span></div>
    ${rows.length ? `<div class="list">${rows.map((t) => taskItem(t, mine)).join('')}</div>` : '<div class="empty">Nothing here</div>'}</div>`;
  return `<div class="row" style="justify-content:flex-end;margin-bottom:18px"><button class="btn primary" data-act="newTask">${ic('plus')} New task</button></div>
    <div class="grid cols-2">${col('Assigned to me', data.to_me, true)}${col('Assigned by me', data.by_me, false)}</div>`;
};
VIEW.tasks = () => live('tasks');

/* ---------- messages ---------- */
LIVE.threadList = async () => {
  const [staff, threads] = await Promise.all([api('/staff'), api('/messages')]);
  S.staff = staff;
  const byId = Object.fromEntries(threads.map((t) => [t.user_id, t]));
  const others = staff.filter((u) => u.id !== S.user.id);
  others.sort((a, b) => ((byId[b.id] || {}).at || '').localeCompare((byId[a.id] || {}).at || '') || a.name.localeCompare(b.name));
  return others.map((u) => {
    const t = byId[u.id];
    return `<button data-act="openChat" data-id="${u.id}" class="${S.chat === u.id ? 'on' : ''}">${avatar(u.name, u.role)}
      <span class="who"><b>${esc(u.name)}</b><small${t ? '' : ' style="text-transform:capitalize"'}>${t ? esc(t.last) : esc(u.role) + (u.department ? ' · ' + esc(u.department) : '')}</small></span>
      ${t && t.unread && S.chat !== u.id ? `<span class="count">${t.unread}</span>` : ''}</button>`;
  }).join('');
};
LIVE.thread = async () => {
  if (!S.chat) return '<div class="empty" style="margin:auto">Choose a colleague to start a conversation</div>';
  const rows = await api('/messages/' + S.chat);
  return rows.length ? rows.map((m) => `<div class="bubble${m.mine ? ' mine' : ''}">${esc(m.body)}<small>${fmtTime(m.at)}</small></div>`).join('')
    : '<div class="empty" style="margin:auto">No messages yet. Say hello.</div>';
};
VIEW.messages = async () => {
  const list = await live('threadList');
  const other = S.staff.find((u) => u.id === S.chat);
  const body = await LIVE.thread();
  CACHE.thread = body;
  return `<div class="chat glass"><div class="chat-list">${list}</div>
    <div class="chat-pane">
      ${other ? `<div class="chat-head">${avatar(other.name, other.role)}<div><b style="font-weight:600">${esc(other.name)}</b>
        <div class="hint" style="text-transform:capitalize">${esc(other.role)}${other.department ? ' · ' + esc(other.department) : ''}</div></div></div>` : ''}
      <div class="chat-body" data-live="thread">${body}</div>
      ${other ? `<form class="chat-send" data-form="send"><input name="body" placeholder="Write a message" maxlength="2000" autocomplete="off" required>
        <button class="btn primary" type="submit">Send</button></form>` : ''}
    </div></div>`;
};
function scrollChat() { const el = $('.chat-body'); if (el) el.scrollTop = el.scrollHeight; }
AFTER.messages = () => { scrollChat(); const input = $('.chat-send input'); if (input) input.focus(); };

/* ---------- staff accounts ---------- */
LIVE.staffList = async () => {
  const data = await api('/admin/staff');
  S.staffRoles = data.roles;
  return `<div class="scroll-x"><table><thead><tr><th>Name</th><th>Username</th><th>Role</th><th>Status</th><th></th></tr></thead>
    <tbody>${data.staff.map((u) => `<tr><td><span class="row" style="flex-wrap:nowrap">${avatar(u.name, u.role)}<b style="font-weight:500">${esc(u.name)}</b></span></td>
      <td class="mono hint">${esc(u.username)}</td>
      <td style="text-transform:capitalize">${esc(u.role)}${u.department ? ' · ' + esc(u.department) : ''}</td>
      <td><span class="pill ${u.active ? 'good' : 'bad'}">${u.active ? 'Active' : 'Disabled'}</span></td>
      <td>${u.can_manage ? `<span class="row" style="justify-content:flex-end;flex-wrap:nowrap">
        <button class="btn small" data-act="staffReset" data-id="${u.id}" data-name="${esc(u.name)}">Reset password</button>
        <button class="btn small${u.active ? ' danger' : ''}" data-act="staffActive" data-id="${u.id}" data-name="${esc(u.name)}" data-active="${u.active ? '0' : '1'}">${u.active ? 'Disable' : 'Enable'}</button></span>` : ''}</td></tr>`).join('')}</tbody></table></div>`;
};
VIEW.staff = async () => {
  const list = await live('staffList');
  return `<div class="stack">
    <div class="card glass"><div class="card-head"><h2>Add a staff member</h2></div>
      <form class="form" data-form="staffAdd">
        <div class="two"><label class="field">Full name<input name="name" required minlength="2" maxlength="120"></label>
          <label class="field">Username<input name="username" required minlength="3" maxlength="32" placeholder="dr.name" autocomplete="off"></label></div>
        <div class="two"><label class="field">Role<select name="role">${S.staffRoles.map((r) => `<option value="${r}">${r[0].toUpperCase() + r.slice(1)}</option>`).join('')}</select></label>
          <label class="field">Department (doctors and nurses)<select name="department">${S.meta.departments.map((d) => `<option>${esc(d)}</option>`).join('')}</select></label></div>
        <div><button class="btn primary" type="submit">Create account</button></div>
      </form></div>
    <div class="card glass"><div class="card-head"><h2>Staff accounts</h2><span class="grow"></span><span class="hint">You can manage the roles that report to you</span></div>${list}</div>
  </div>`;
};
function showCredential(title, text, user, password) {
  openModal(`<h2>${esc(title)}</h2><p class="sub">${esc(text)}</p>
    <div class="credential"><div><span>Username</span><b>${esc(user.username)}</b></div><div><span>Temporary password</span><b>${esc(password)}</b></div></div>
    <p class="hint">This password is shown only once. Ask ${esc(user.name)} to change it after signing in, using the key button at the bottom of the sidebar.</p>
    <div class="modal-actions" style="margin-top:14px"><button class="btn primary" data-act="close">Done</button></div>`);
}

/* ---------- analytics and admin ---------- */
VIEW.analytics = async () => {
  const [a, settings, sync] = await Promise.all([api('/analytics'), api('/settings'), api('/analytics/sync')]);
  const k = a.kpis;
  const url = settings.cognos_url;
  const hour = (h) => `${((h + 11) % 12) + 1}${h < 12 ? 'a' : 'p'}`;
  const hourLong = (h) => `${((h + 11) % 12) + 1} ${h % 24 < 12 ? 'AM' : 'PM'}`;
  return `<div class="stack">
    <div class="grid cols-4">
      <div class="tile glass"><div class="label">Average wait, 14 days</div><div class="value">${k.avg_wait_14d}<small>min</small></div><div class="foot">Check-in to doctor</div></div>
      <div class="tile glass"><div class="label">Average wait today</div><div class="value">${k.avg_wait_today}<small>min</small></div><div class="foot">${k.patients_today} patients so far</div></div>
      <div class="tile glass"><div class="label">Cross-department referrals</div><div class="value">${k.referrals}</div><div class="foot">Handled without paper files</div></div>
      <div class="tile glass"><div class="label">Approval turnaround</div><div class="value">${k.approval_hours}<small>h</small></div><div class="foot">Average time to a decision</div></div>
    </div>
    <div class="grid cols-2">
      <div class="card glass"><div class="card-head"><h2>Patients per day</h2></div>${columns(a.daily, 'visits', (r, full) => (full ? fmtDay(r.date) : String(new Date(r.date + 'T00:00').getDate())), true)}</div>
      <div class="card glass"><div class="card-head"><h2>Arrivals by hour of day</h2></div>${columns(a.hourly, 'visits', (r, full) => (full ? `${hourLong(r.hour)} to ${hourLong(r.hour + 1)}, last 14 days` : hour(r.hour)))}</div>
    </div>
    <div class="grid cols-2">
      <div class="card glass"><div class="card-head"><h2>Average wait by department</h2></div>${bars(a.by_department, 'department', 'avg_wait', ' min')}</div>
      <div class="card glass"><div class="card-head"><h2>Patients seen per doctor</h2></div>${bars(a.doctors, 'name', 'seen', '')}</div>
    </div>
    <div class="card glass"><div class="card-head"><h2>IBM Cognos Analytics</h2>${syncPill(sync)}<span class="grow"></span>
        ${url ? `<a class="btn small" href="${esc(url)}" target="_blank" rel="noopener">Open in Cognos ${ic('arrow')}</a>` : ''}</div>
      ${url ? `<iframe class="frame" src="${esc(url)}" title="CareSync Hospital Dashboard in IBM Cognos Analytics" allow="encrypted-media" allowfullscreen></iframe>
        <p class="hint" style="margin-top:10px">Live from IBM Cognos Analytics. The first load can take up to a minute. If it stays blank, sign in to Cognos in this browser, then use Open in Cognos.</p>`
        : `<ol class="steps"><li><b>Export</b> the data below.</li><li><b>Upload</b> the files to Cognos Analytics and build the dashboard.</li>
          <li><b>Share</b> the dashboard, copy its embed link, and ${S.user.role === 'chairman' ? 'paste it under Admin and audit.' : 'ask the chairman to add it under Admin and audit.'}</li></ol>`}
      <div class="row" style="margin-top:18px">
        ${[['visits', 'Visits and waiting times'], ['beds', 'Beds'], ['requests', 'Approvals']].map(([n, t]) => `<button class="btn small" data-act="export" data-name="${n}">${ic('download')} ${t} (CSV)</button>`).join('')}
      </div></div>
  </div>`;
};

function syncPill(sync) {
  if (!sync.enabled) return '<span class="pill plain">Data by file upload</span>';
  if (sync.error) return `<span class="pill bad" title="${esc(sync.error)}">Live data link down</span>`;
  if (!sync.last_ok) return '<span class="pill warn">Connecting live data</span>';
  return `<span class="pill good" title="Reporting tables are pushed to the analytics database whenever they change">Live data · synced ${ago(sync.last_ok)}</span>`;
}

LIVE.audit = async () => {
  const rows = await api('/audit');
  return `<div class="scroll-x"><table><thead><tr><th>When</th><th>Who</th><th>Role</th><th>Action</th><th>Target</th></tr></thead>
    <tbody>${rows.slice(0, 60).map((r) => `<tr><td class="hint" style="white-space:nowrap">${fmtTime(r.at)} · ${fmtShort(r.at.slice(0, 10))}</td><td>${esc(r.who)}</td>
      <td style="text-transform:capitalize" class="hint">${esc(r.role)}</td><td>${esc(r.action)}</td><td class="mono hint">${esc(r.target)}</td></tr>`).join('')}</tbody></table></div>`;
};
VIEW.admin = async () => {
  const [settings, staff] = await Promise.all([api('/settings'), api('/staff')]);
  return `<div class="stack">
    <div class="grid cols-2">
      <div class="card glass"><div class="card-head"><h2>Cognos dashboard link</h2></div>
        <form class="form" data-form="settings">
          <label class="field">Embed link from Cognos Analytics<input name="cognos_url" value="${esc(settings.cognos_url)}" placeholder="https://..." maxlength="1000"></label>
          <p class="hint">Shown to the dean and chairman on the Analytics page.</p>
          <div><button class="btn primary" type="submit">Save link</button></div>
        </form>
        ${S.meta.demo ? `<div style="margin-top:20px;padding-top:18px;border-top:1px solid var(--stroke)"><p class="hint" style="margin-bottom:10px">Demo mode: rebuild the sample data around the current time. Everyone is signed out.</p>
          <button class="btn small danger" data-act="resetDemo">Reset demo data</button></div>` : ''}</div>
      <div class="card glass"><div class="card-head"><h2>Staff directory</h2><span class="grow"></span><span class="pill plain">${staff.length}</span></div>
        <div class="list" style="max-height:300px;overflow:auto">${staff.map((u) => `<div class="item"><div class="item-head">${avatar(u.name, u.role)}
          <span class="grow"><b>${esc(u.name)}</b><div class="meta" style="text-transform:capitalize">${esc(u.role)}${u.department ? ' · ' + esc(u.department) : ''}</div></span></div></div>`).join('')}</div></div>
    </div>
    <div class="card glass"><div class="card-head"><h2>Audit trail</h2><span class="grow"></span><span class="hint">Who did what, including every patient record opened</span></div>${await live('audit')}</div>
  </div>`;
};

/* ---------- actions ---------- */
const ACT = {
  async demo(d) { await startSession(await api('/demo/login', 'POST', { username: d.username })); },
  signout() { signOut(); },
  themeMenu() {
    const panel = $('#themes');
    panel.hidden = !panel.hidden;
    if ($('#notif')) $('#notif').hidden = true;
    if (!panel.hidden) renderThemePanel();
  },
  setTheme(d) {
    applyTheme(d.id);
    renderThemePanel();
    document.querySelectorAll('.theme-dot').forEach((b) => b.classList.toggle('on', b.dataset.id === d.id));
  },
  go(d) { closeModal(); go(d.view); },
  close() { closeModal(); },
  async bell() {
    const panel = $('#notif');
    panel.hidden = !panel.hidden;
    if (panel.hidden) return;
    renderNotifs();
    if (S.notif.unread) {
      await api('/notifications/read', 'POST');
      S.notif.unread = 0;
      $('#bell-dot').hidden = true;
    }
  },
  openPatient(d) { closeModal(); go('patients', d.pid); },
  pick(d, el) {
    const box = el.closest('.picker');
    $('[name=pid]', box).value = d.pid;
    $('[data-q]', box).value = `${d.name} · ${d.pid}`;
    $('.picker-results', box).innerHTML = '';
  },
  prefillToken(d) {
    closeModal();
    const form = $('#token-form');
    if (!form) return;
    $('[name=pid]', form).value = d.pid;
    $('[data-q]', form).value = `${d.name} · ${d.pid}`;
    $('[name=department]', form).focus();
  },
  vitals(d) {
    openModal(`<h2>Vitals</h2><p class="sub">${esc(d.name)}</p>
      <form class="form" data-form="vitals" data-id="${esc(d.id)}">
        <div class="two"><label class="field">Blood pressure<input name="bp" value="${esc(d.bp)}" placeholder="120/80" maxlength="12" required></label>
          <label class="field">Temperature (°F)<input name="temp" value="${esc(d.temp)}" placeholder="98.6" maxlength="8"></label></div>
        <div class="two"><label class="field">Pulse (per min)<input name="pulse" value="${esc(d.pulse)}" placeholder="76" maxlength="8"></label>
          <label class="field">SpO2 (%)<input name="spo2" value="${esc(d.spo2)}" placeholder="98" maxlength="8"></label></div>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn primary" type="submit">Save vitals</button></div>
      </form>`);
  },
  async suggestDept(d, el) {
    const form = el.closest('form');
    const complaint = $('[name=complaint]', form).value.trim();
    const hint = $('#triage-hint');
    if (complaint.length < 3) throw new Error('Type the reason for the visit first');
    el.disabled = true;
    hint.textContent = 'Thinking…';
    try {
      const out = await api('/triage', 'POST', { complaint });
      $('[name=department]', form).value = out.department;
      hint.textContent = `${out.source} suggests ${out.department}. ${out.reason} You can change it.`;
    } catch (err) {
      hint.textContent = '';
      throw err;
    } finally { el.disabled = false; }
  },
  pickItem(d, el) {
    const form = el.closest('form');
    const input = $('[name=title]', form);
    input.value = d.item;
    form.querySelectorAll('.chip-opt').forEach((c) => c.classList.toggle('on', c === el));
    $('[name=details]', form).focus();
  },
  staffReset(d) {
    openModal(`<h2>Reset password?</h2><p class="sub">${esc(d.name)} will be signed out and will need the new temporary password.</p>
      <div class="modal-actions"><button class="btn" data-act="close">Cancel</button><button class="btn primary" data-act="staffResetNow" data-id="${esc(d.id)}">Reset password</button></div>`);
  },
  async staffResetNow(d) {
    const out = await api(`/admin/staff/${d.id}/reset-password`, 'POST');
    showCredential('Password reset', `Give ${out.user.name} these sign-in details.`, out.user, out.password);
  },
  async staffActive(d) {
    await api(`/admin/staff/${d.id}/active`, 'POST', { active: d.active === '1' });
    toast(d.active === '1' ? `${d.name} can sign in again` : `${d.name} is disabled and signed out`);
    await refreshLive('staffList');
  },
  myPassword() {
    openModal(`<h2>Change my password</h2><p class="sub">Use at least 8 characters.</p>
      <form class="form" data-form="myPassword">
        <label class="field">Current password<input name="current" type="password" autocomplete="current-password" required></label>
        <label class="field">New password<input name="new" type="password" autocomplete="new-password" required minlength="8"></label>
        <label class="field">New password again<input name="again" type="password" autocomplete="new-password" required minlength="8"></label>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn primary" type="submit">Change password</button></div>
      </form>`);
  },
  async bookAppt() {
    const iso = (date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
    const today = new Date();
    const last = new Date(today.getTime() + 14 * 86400000);
    openModal(`<h2>Book an appointment</h2><p class="sub">Pick a department, a day and a free time. Reception checks you in when you arrive.</p>
      <form class="form" data-form="bookAppt">
        <label class="field">Department<select name="department">${S.meta.departments.filter((d) => d !== 'Emergency').map((d) => `<option>${esc(d)}</option>`).join('')}</select></label>
        <div class="two"><label class="field">Date<input name="day" type="date" value="${iso(today)}" min="${iso(today)}" max="${iso(last)}" required></label>
          <label class="field">Time<select name="slot" required></select></label></div>
        <label class="field">Reason for visit<input name="reason" maxlength="240" placeholder="Short description"></label>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn primary" type="submit">Book appointment</button></div>
      </form>`);
    await fillSlots($('form[data-form=bookAppt]'));
  },
  cancelAppt(d) {
    openModal(`<h2>Cancel this appointment?</h2><p class="sub">${esc(d.label)}</p>
      <div class="modal-actions"><button class="btn" data-act="close">Keep it</button><button class="btn danger" data-act="cancelApptNow" data-id="${esc(d.id)}">Cancel appointment</button></div>`);
  },
  async cancelApptNow(d) {
    await api(`/my/appointments/${d.id}/cancel`, 'POST');
    closeModal();
    toast('Appointment cancelled');
    await refreshLive('patientHome');
  },
  async checkinAppt(d) {
    const out = await api(`/appointments/${d.id}/checkin`, 'POST');
    openModal(`<h2>Checked in</h2><p class="sub">${esc(out.patient.name)} · ${esc(out.department)}</p>
      <div class="credential"><div><span>Token</span><b>${esc(out.token)}</b></div>
        <div><span>Estimated wait</span><b>${out.est_wait ? '~' + out.est_wait + ' min' : 'No wait'}</b></div></div>
      <div class="modal-actions"><button class="btn primary" data-act="close">Done</button></div>`);
    await Promise.all([refreshLive('apptToday'), refreshLive('deptStatus')]);
  },
  async toggleAvail(d) {
    await api('/availability', 'POST', { available: d.next === '1' });
    await refreshLive('doctorHome');
  },
  async startVisit(d) { await api(`/visits/${d.id}/start`, 'POST'); go('consult', d.id); },
  resume(d) { go('consult', d.id); },
  addMed() { $('#meds').insertAdjacentHTML('beforeend', medRow()); $('#meds .med-row:last-child input').focus(); },
  delMed(d, el) {
    const row = el.closest('.med-row');
    if ($('#meds').children.length > 1) row.remove();
    else row.querySelectorAll('input').forEach((i) => { i.value = ''; });
  },
  async summary(d, el) {
    el.disabled = true;
    const box = $('#summary');
    box.innerHTML = '<span class="hint">Reading the record…</span>';
    try {
      const out = await api(`/patients/${encodeURIComponent(d.pid)}/summary`);
      box.innerHTML = `<div class="note"><small>${esc(out.source)}</small>${esc(out.text)}</div>`;
    } finally { el.disabled = false; }
  },
  bed(d) {
    if (!canEditBeds()) return;
    const occupied = d.status === 'occupied';
    openModal(`<h2>Bed ${esc(d.label)}</h2><p class="sub">${occupied ? 'Occupied by ' + esc(d.patient) : d.status === 'cleaning' ? 'Being cleaned' : 'Free'}</p>
      ${occupied ? '' : `<form class="form" data-form="bedAssign" data-id="${esc(d.id)}"><label class="field">Admit a patient to this bed${picker('Search by name or patient ID')}</label>
        <button class="btn primary" type="submit">Admit patient</button></form>`}
      <div class="modal-actions" style="margin-top:16px;justify-content:flex-start">
        ${d.status !== 'cleaning' ? `<button class="btn" data-act="bedSet" data-id="${esc(d.id)}" data-status="cleaning">${occupied ? 'Discharge and send for cleaning' : 'Mark for cleaning'}</button>` : ''}
        ${d.status !== 'free' ? `<button class="btn" data-act="bedSet" data-id="${esc(d.id)}" data-status="free">Mark free</button>` : ''}
        <span style="flex:1"></span><button class="btn" data-act="close">Close</button></div>`);
  },
  async bedSet(d) {
    await api('/beds/' + d.id, 'POST', { status: d.status });
    closeModal();
    toast('Bed updated');
    await refreshLive('beds');
  },
  async reqTab(d) { S.reqTab = d.tab; await refreshLive('requests'); },
  async newRequest() {
    let doctorField = '';
    if (S.user.role === 'nurse') {
      const doctors = (await api('/staff')).filter((u) => u.role === 'doctor');
      doctors.sort((a, b) => (b.department === S.user.department) - (a.department === S.user.department));
      doctorField = `<label class="field">Doctor to approve<select name="doctor_id">${doctors.map((u) => `<option value="${u.id}">${esc(u.name)} · ${esc(u.department)}</option>`).join('')}</select></label>`;
    }
    const next = { receptionist: 'the dean', doctor: 'the dean', dean: 'the chairman', nurse: 'the doctor you choose' }[S.user.role];
    openModal(`<h2>New request</h2><p class="sub">This goes to ${next} for approval.</p>
      <form class="form" data-form="request">
        <div class="two"><label class="field">Type<select name="kind">${S.meta.request_kinds.map((k) => `<option>${esc(k)}</option>`).join('')}</select></label>
          <label class="field">Patient ID (optional)<input name="patient_pid" maxlength="20" placeholder="CS-2026-00001"></label></div>
        <div id="req-items">${requestItems(S.meta.request_kinds[0])}</div>
        <label class="field">What do you need?<input name="title" required minlength="3" maxlength="160"></label>
        <label class="field">Details<textarea name="details" maxlength="2000"></textarea></label>${doctorField}
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn primary" type="submit">Send for approval</button></div>
      </form>`);
  },
  decide(d) {
    const verb = { approve: 'Approve', reject: 'Reject', forward: `Send to ${d.to}` }[d.action];
    openModal(`<h2>${esc(verb)}</h2><p class="sub">${esc(d.title)}</p>
      <form class="form" data-form="decide" data-id="${esc(d.id)}" data-action="${esc(d.action)}">
        <label class="field">Note${d.action === 'approve' ? ' (optional)' : ''}<textarea name="note" maxlength="400" ${d.action === 'approve' ? '' : 'required'}></textarea></label>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button>
          <button class="btn ${d.action === 'reject' ? 'danger' : 'primary'}" type="submit">${esc(verb)}</button></div>
      </form>`);
  },
  newTask() {
    openModal(`<h2>New task</h2><p class="sub">You can assign work to yourself and to staff who report to your role.</p>
      <form class="form" data-form="task">
        <label class="field">Task<input name="title" required minlength="3" maxlength="160"></label>
        <label class="field">Details<textarea name="details" maxlength="2000"></textarea></label>
        <div class="two"><label class="field">Assign to<select name="assigned_to">${S.assignable.map((u) => `<option value="${u.id}">${u.id === S.user.id ? 'Myself' : esc(u.name) + ' · ' + esc(u.role)}</option>`).join('')}</select></label>
          <label class="field">Priority<select name="priority"><option value="normal">Normal</option><option value="urgent">Urgent</option><option value="low">Low</option></select></label></div>
        <label class="field">Patient ID (optional)<input name="patient_pid" maxlength="20"></label>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn primary" type="submit">Assign task</button></div>
      </form>`);
  },
  async taskStatus(d) {
    await api(`/tasks/${d.id}/status`, 'POST', { status: d.status });
    await Promise.all([refreshLive('tasks'), refreshLive('nurseHome')]);
    refreshNotifs().catch(() => {});
  },
  openChat(d) { S.chat = Number(d.id); paint(); },
  resetDemo() {
    openModal(`<h2>Reset demo data?</h2><p class="sub">All sample patients, queues, requests and messages are rebuilt around the current time. Anything entered since the last reset is removed.</p>
      <div class="modal-actions"><button class="btn" data-act="close">Cancel</button><button class="btn danger" data-act="resetDemoNow">Reset now</button></div>`);
  },
  async resetDemoNow() {
    await api('/demo/reset', 'POST');
    signOut(false);
    toast('Demo data rebuilt. Sign in again.');
  },
  async export(d) {
    const res = await fetch('/api/export/' + d.name, { headers: { Authorization: `Bearer ${S.token}` } });
    if (!res.ok) throw new Error('Export failed');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(await res.blob());
    link.download = `caresync_${d.name}.csv`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 2000);
    toast('Export saved. Upload it to Cognos Analytics.');
  },
};

const REQUEST_ITEMS = {
  Supplies: ['Surgical gloves', 'Face masks', 'Syringes and needles', 'IV fluids', 'IV cannulas', 'Gauze and bandages', 'Hand sanitiser', 'Disposable gowns', 'Oxygen masks', 'Bed linen'],
  Equipment: ['Infusion pump', 'Patient monitor', 'Wheelchair', 'Stretcher', 'Oxygen cylinder', 'BP apparatus', 'Pulse oximeter', 'Thermometer', 'ECG machine', 'Nebuliser', 'Suction machine', 'Equipment repair'],
  'Shift change': ['Swap shift with a colleague', 'Move to morning shift', 'Move to evening shift', 'Move to night shift'],
  Leave: ['Casual leave', 'Sick leave', 'Half-day leave', 'Emergency leave'],
  'Patient transfer': ['Transfer to ICU', 'Transfer to general ward', 'Transfer to another department', 'Transfer to another hospital'],
};
function requestItems(kind) {
  const items = REQUEST_ITEMS[kind] || [];
  if (!items.length) return '';
  return `<div class="hint" style="margin-bottom:8px">Common ${esc(kind.toLowerCase())} requests. Click one to fill it in.</div>
    <div class="chips">${items.map((i) => `<button type="button" class="chip-opt" data-act="pickItem" data-item="${esc(i)}">${esc(i)}</button>`).join('')}</div>`;
}

const pidFrom = (data, form) => (data.pid || ($('[data-q]', form).value.match(/CS-\d{4}-\d+/i) || [''])[0]).toUpperCase();

const FORMS = {
  async login(data) { await startSession(await api('/login', 'POST', data)); },
  async register(data, form) {
    const out = await api('/patients', 'POST', { ...data, age: Number(data.age) });
    form.reset();
    const p = out.patient;
    openModal(`<h2>Patient registered</h2><p class="sub">Give ${esc(p.name)} this ID and PIN. The PIN is shown only once.</p>
      <div class="credential"><div><span>Patient ID</span><b>${esc(p.pid)}</b></div><div><span>PIN</span><b>${esc(out.pin)}</b></div></div>
      <div class="modal-actions"><button class="btn" data-act="close">Done</button>
        <button class="btn primary" data-act="prefillToken" data-pid="${esc(p.pid)}" data-name="${esc(p.name)}">Issue a token now</button></div>`);
  },
  async token(data, form) {
    const pid = pidFrom(data, form);
    if (!pid) throw new Error('Choose a patient from the search results');
    const out = await api('/visits', 'POST', { pid, department: data.department, complaint: data.complaint });
    form.reset();
    openModal(`<h2>Token issued</h2><p class="sub">${esc(out.patient.name)} · ${esc(out.department)}</p>
      <div class="credential"><div><span>Token</span><b>${esc(out.token)}</b></div>
        <div><span>Estimated wait</span><b>${out.est_wait ? '~' + out.est_wait + ' min' : 'No wait'}</b></div></div>
      <p class="hint">${plural(out.ahead, 'patient')} ahead. The patient can follow their place in the queue from their own login.</p>
      <div class="modal-actions" style="margin-top:14px"><button class="btn primary" data-act="close">Done</button></div>`);
    await refreshLive('deptStatus');
  },
  async vitals(data, form) {
    await api(`/visits/${form.dataset.id}/vitals`, 'POST', data);
    closeModal();
    toast('Vitals saved');
    await refreshLive('nurseHome');
  },
  async complete(data, form) {
    const prescriptions = [...form.querySelectorAll('.med-row')].map((row) => ({
      medicine: $('[name=med]', row).value.trim(), dosage: $('[name=dose]', row).value.trim(), duration: $('[name=dur]', row).value.trim(),
    })).filter((m) => m.medicine);
    const out = await api(`/visits/${form.dataset.id}/complete`, 'POST', {
      diagnosis: data.diagnosis, notes: data.notes, prescriptions, refer_to: data.refer_to, refer_reason: data.refer_reason,
    });
    toast(out.referral ? `Visit closed. Referred to ${out.referral.department}, token ${out.referral.token}.` : 'Visit closed');
    go('home');
  },
  async bedAssign(data, form) {
    const pid = pidFrom(data, form);
    if (!pid) throw new Error('Choose a patient from the search results');
    await api('/beds/' + form.dataset.id, 'POST', { status: 'occupied', pid });
    closeModal();
    toast('Patient admitted');
    await refreshLive('beds');
  },
  async request(data) {
    await api('/requests', 'POST', { ...data, doctor_id: data.doctor_id ? Number(data.doctor_id) : null });
    closeModal();
    toast('Request sent for approval');
    S.reqTab = 'mine';
    await refreshLive('requests');
  },
  async decide(data, form) {
    await api(`/requests/${form.dataset.id}/decide`, 'POST', { action: form.dataset.action, note: data.note });
    closeModal();
    toast('Decision recorded');
    await refreshLive('requests');
    refreshNotifs().catch(() => {});
  },
  async task(data) {
    await api('/tasks', 'POST', { ...data, assigned_to: Number(data.assigned_to) });
    closeModal();
    toast('Task assigned');
    await refreshLive('tasks');
  },
  async send(data, form) {
    const input = $('[name=body]', form);
    await api('/messages', 'POST', { to: S.chat, body: data.body });
    input.value = '';
    await Promise.all([refreshLive('thread'), refreshLive('threadList')]);
    input.focus();
  },
  async staffAdd(data, form) {
    const out = await api('/admin/staff', 'POST', data);
    form.reset();
    showCredential('Account created', `Give ${out.user.name} these sign-in details.`, out.user, out.password);
    await refreshLive('staffList');
  },
  async myPassword(data) {
    if (data.new !== data.again) throw new Error('The two new passwords do not match');
    await api('/password', 'POST', { current: data.current, new: data.new });
    closeModal();
    toast('Password changed');
  },
  async bookAppt(data) {
    if (!data.slot) throw new Error('Choose a free time');
    const out = await api('/my/appointments', 'POST', data);
    closeModal();
    toast(`Booked: ${out.department} on ${fmtDay(out.day)} at ${out.time}`);
    await refreshLive('patientHome');
  },
  async settings(data) {
    await api('/settings', 'POST', data);
    toast('Cognos link saved');
  },
};

/* ---------- events ---------- */
document.addEventListener('click', async (e) => {
  if (e.target.id === 'modal') return closeModal();
  const el = e.target.closest('[data-act]');
  if (!el) {
    if (!e.target.closest('.notif-wrap') && $('#notif')) $('#notif').hidden = true;
    if (!e.target.closest('.theme-wrap') && $('#themes')) $('#themes').hidden = true;
    if (!e.target.closest('.picker')) document.querySelectorAll('.picker-results').forEach((r) => { r.innerHTML = ''; });
    return;
  }
  if (el.disabled) return;
  try {
    await ACT[el.dataset.act](el.dataset, el);
  } catch (err) { toast(err.message, true); }
});

document.addEventListener('submit', async (e) => {
  const form = e.target.closest('form[data-form]');
  if (!form) return;
  e.preventDefault();
  const btn = form.querySelector('[type=submit]');
  if (btn && btn.disabled) return;
  if (btn) btn.disabled = true;
  try {
    await FORMS[form.dataset.form](Object.fromEntries(new FormData(form)), form);
  } catch (err) { toast(err.message, true); }
  if (btn && btn.isConnected) btn.disabled = false;
});

let typing;
document.addEventListener('input', (e) => {
  const t = e.target;
  if (t.matches('.picker [data-q]')) {
    const box = t.closest('.picker');
    $('[name=pid]', box).value = '';
    clearTimeout(typing);
    typing = setTimeout(async () => {
      const q = t.value.trim();
      const out = $('.picker-results', box);
      if (!q) { out.innerHTML = ''; return; }
      try {
        const rows = await api('/patients?q=' + encodeURIComponent(q));
        if (t.value.trim() !== q) return;
        out.innerHTML = rows.length ? rows.slice(0, 8).map((p) => `<button type="button" data-act="pick" data-pid="${esc(p.pid)}" data-name="${esc(p.name)}">
          <span>${esc(p.name)} <span class="faint">${p.age} y</span></span><span class="mono faint">${esc(p.pid)}</span></button>`).join('')
          : '<div class="empty" style="padding:12px">No match. Register the patient first.</div>';
      } catch { out.innerHTML = ''; }
    }, 200);
  } else if (t.id === 'psearch') {
    S.pq = t.value;
    clearTimeout(typing);
    typing = setTimeout(async () => {
      const q = S.pq;
      try {
        const rows = await api('/patients?q=' + encodeURIComponent(q));
        if (S.pq === q && $('#presults')) $('#presults').innerHTML = patientRows(rows);
      } catch { /* keep the last results */ }
    }, 200);
  }
});

document.addEventListener('change', (e) => {
  if (e.target.matches('form[data-form=request] [name=kind]')) $('#req-items').innerHTML = requestItems(e.target.value);
  if (e.target.matches('form[data-form=bookAppt] [name=department], form[data-form=bookAppt] [name=day]')) fillSlots(e.target.closest('form'));
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (!$('#modal').hidden) closeModal();
    else if ($('#notif')) $('#notif').hidden = true;
  }
  if (e.key === 'Enter' && e.target.id === 'lookup') {
    const value = e.target.value.trim();
    if (!value) return;
    e.target.value = '';
    if (/^CS-\d{4}-\d+$/i.test(value)) go('patients', value.toUpperCase());
    else { S.pq = value; go('patients'); }
  }
});

/* ---------- floating cards and chart tooltips ---------- */
const FLOAT = '.tile, .ticket, .card:has(.columns), .card:has(.bars)';
const calm = window.matchMedia('(prefers-reduced-motion: reduce)');
let floatFrame = 0;
let pointer = null;

function settle(el) {
  for (const p of ['--near', '--rx', '--ry']) el.style.removeProperty(p);
}
function floatCards() {
  floatFrame = 0;
  for (const el of document.querySelectorAll(FLOAT)) {
    if (!pointer) { settle(el); continue; }
    const r = el.getBoundingClientRect();
    const dx = Math.max(r.left - pointer.x, 0, pointer.x - r.right);
    const dy = Math.max(r.top - pointer.y, 0, pointer.y - r.bottom);
    const gap = Math.hypot(dx, dy);
    if (gap > 90) { settle(el); continue; }
    el.style.setProperty('--near', (1 - gap / 90).toFixed(3));
    if (gap > 0) { el.style.removeProperty('--rx'); el.style.removeProperty('--ry'); continue; }
    const px = (pointer.x - r.left) / r.width;
    const py = (pointer.y - r.top) / r.height;
    const tilt = 3.2 * Math.min(1, 280 / r.width);
    el.style.setProperty('--ry', ((px - 0.5) * tilt).toFixed(2) + 'deg');
    el.style.setProperty('--rx', ((0.5 - py) * tilt).toFixed(2) + 'deg');
    el.style.setProperty('--mx', (px * 100).toFixed(1) + '%');
    el.style.setProperty('--my', (py * 100).toFixed(1) + '%');
  }
}
document.addEventListener('pointermove', (e) => {
  if (e.pointerType !== 'mouse' || calm.matches) return;
  pointer = { x: e.clientX, y: e.clientY };
  if (!floatFrame) floatFrame = requestAnimationFrame(floatCards);
});
document.documentElement.addEventListener('pointerleave', () => {
  pointer = null;
  if (!floatFrame) floatFrame = requestAnimationFrame(floatCards);
});

const tip = document.createElement('div');
tip.className = 'tip';
tip.setAttribute('role', 'tooltip');
tip.hidden = true;
document.body.append(tip);
let tipFor = null;

function hideTip() {
  if (!tipFor) return;
  tipFor.classList.remove('is-on');
  const group = tipFor.closest('[data-group]');
  if (group) group.classList.remove('has-on');
  tipFor = null;
  tip.hidden = true;
}
function showTip(el, x, y) {
  if (tipFor !== el) {
    hideTip();
    tipFor = el;
    el.classList.add('is-on');
    const group = el.closest('[data-group]');
    if (group) group.classList.add('has-on');
    tip.innerHTML = `<b>${esc(el.dataset.val)}</b><span>${esc(el.dataset.tip)}</span>`;
    tip.hidden = false;
  }
  const w = tip.offsetWidth;
  const h = tip.offsetHeight;
  const left = Math.min(Math.max(8, x - w / 2), window.innerWidth - w - 8);
  const top = y - h - 14 < 8 ? y + 20 : y - h - 14;
  tip.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
}
document.addEventListener('pointermove', (e) => {
  if (e.pointerType !== 'mouse') return;
  const el = e.target.closest ? e.target.closest('[data-tip]') : null;
  if (el) showTip(el, e.clientX, e.clientY);
  else hideTip();
});
document.addEventListener('pointerdown', (e) => {
  if (e.pointerType === 'mouse') return;
  const el = e.target.closest('[data-tip]');
  if (el && el !== tipFor) showTip(el, e.clientX, e.clientY);
  else hideTip();
});
window.addEventListener('scroll', hideTip, { passive: true });
window.addEventListener('blur', hideTip);
setInterval(() => { if (tipFor && !tipFor.isConnected) { tipFor = null; tip.hidden = true; } }, 500);

/* ---------- start ---------- */
applyTheme(savedTheme());

async function boot() {
  if (!S.token) return renderLogin();
  try {
    S.meta = await api('/me');
  } catch {
    S.token = null;
    store.set('cs_token', null);
    return renderLogin();
  }
  S.user = S.meta.user;
  S.view = 'home';
  renderShell();
  paint();
  refreshNotifs().catch(() => {});
  clearInterval(S.timer);
  S.timer = setInterval(tick, 6000);
}
boot();
