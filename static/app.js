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
  staff: [], assignable: [], pq: '', timer: null, stream: null,
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
  { id: 'coastal', name: 'Modern coastal stone', light: true, sw: ['#E8E0D3', '#355B5A', '#B7A18A'] },
  { id: 'bronze', name: 'Dark bronze', light: false, sw: ['#202522', '#343A35', '#A87C4F'] },
  { id: 'teal', name: 'Midnight teal', light: false, sw: ['#071221', '#142033', '#5fe3c6'] },
];
/* Modern coastal stone is the default, and the only theme before sign-in. After sign-in a theme the person
   picked earlier is restored; it is saved only when they choose one themselves. */
const DEFAULT_THEME = 'coastal';
function savedTheme() {
  let id = null;
  try { id = localStorage.getItem('cs_theme'); } catch { /* storage blocked */ }
  return THEMES.some((t) => t.id === id) ? id : DEFAULT_THEME;
}
function applyTheme(id, remember = false) {
  const theme = THEMES.find((t) => t.id === id) || THEMES.find((t) => t.id === DEFAULT_THEME);
  const el = document.documentElement;
  el.dataset.theme = theme.id;
  if (theme.light) el.dataset.light = '1';
  else delete el.dataset.light;
  if (remember) { try { localStorage.setItem('cs_theme', theme.id); } catch { /* storage blocked */ } }
  S.theme = theme.id;
}
const swatch = (t) => `<span class="swatch">${t.sw.map((c) => `<i style="background:${c}"></i>`).join('')}</span>`;
function renderThemePanel() {
  const panel = $('#themes');
  if (panel) panel.innerHTML = `<h3>Colour theme</h3>${THEMES.map((t) => `<button class="theme-opt${S.theme === t.id ? ' on' : ''}" data-act="setTheme" data-id="${t.id}">${swatch(t)}${esc(t.name)}</button>`).join('')}`;
}

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
  siren: '<path d="M7 18v-6a5 5 0 0 1 10 0v6"/><path d="M5 21h14v-3H5zM12 3v2M4.2 6.2l1.4 1.4M19.8 6.2l-1.4 1.4"/>',
  box: '<path d="M21 8 12 3 3 8v8l9 5 9-5z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0 5 5l-8.9 8.9a2.1 2.1 0 0 1-3-3l8.9-8.9a4 4 0 0 1-2-2z"/>',
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

function openModal(html, wide) {
  const m = $('#modal');
  m.innerHTML = `<div class="modal-card glass${wide ? ' wide' : ''}" role="dialog" aria-modal="true">${html}</div>`;
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
  applyTheme(DEFAULT_THEME);
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
  stopStream();
  Object.assign(S, { token: null, user: null, view: 'home', arg: null, lastNotif: null, chat: null, badges: {}, reqTab: 'inbox', pq: '', staff: [], assignable: [], notif: { unread: 0, items: [] } });
  store.set('cs_token', null);
  closeModal();
  renderLogin();
}

/* ---------- shell and routing ---------- */
const NAV = {
  patient: ['home'],
  receptionist: ['home', 'emergency', 'queue', 'patients', 'beds', 'requests', 'tasks', 'messages'],
  nurse: ['home', 'emergency', 'patients', 'beds', 'equipment', 'requests', 'tasks', 'messages'],
  doctor: ['home', 'emergency', 'patients', 'equipment', 'requests', 'tasks', 'messages'],
  dean: ['home', 'analytics', 'emergency', 'queue', 'patients', 'beds', 'equipment', 'staff', 'requests', 'tasks', 'messages'],
  chairman: ['home', 'analytics', 'emergency', 'queue', 'patients', 'beds', 'equipment', 'staff', 'requests', 'tasks', 'messages', 'admin'],
  admin: ['home', 'emergency', 'queue', 'beds', 'equipment', 'requests', 'tasks', 'messages'],
  coordinator: ['home', 'requests', 'tasks', 'messages'],
};
const HOME_LABEL = { patient: 'My visit', receptionist: 'Front desk', nurse: 'Ward queue', doctor: 'My queue', dean: 'Overview', chairman: 'Overview', admin: 'Operations', coordinator: 'Stores and dispatch' };
const LABEL = { analytics: 'Analytics', queue: 'Live queue', patients: 'Patient records', beds: 'Beds', staff: 'Staff accounts', requests: 'Approvals', tasks: 'Tasks', messages: 'Messages', admin: 'Admin and audit', consult: 'Consultation', emergency: 'Emergencies', equipment: 'Equipment & supplies' };
const EQUIP_LABEL = { dean: 'Equipment requests', chairman: 'Procurement', admin: 'Procurement' };
const ICON = { home: 'home', analytics: 'chart', queue: 'queue', patients: 'users', beds: 'bed', staff: 'idcard', requests: 'check', tasks: 'list', messages: 'chat', admin: 'shield', emergency: 'siren', equipment: 'box' };
const label = (view) => (view === 'home' ? HOME_LABEL[S.user.role] : view === 'equipment' ? EQUIP_LABEL[S.user.role] || LABEL.equipment
  : view === 'requests' && !['doctor', 'dean', 'chairman'].includes(S.user.role) ? 'Requests' : LABEL[view]);

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
      <div id="er-banner" class="er-banner" aria-live="assertive"></div>
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
  if (S.view === 'consult' && view !== 'consult') saveDraft().catch(() => {});  // keep what the doctor typed
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
async function tick(force) {
  if (!S.user || (document.hidden && !force)) return;
  try { await refreshNotifs(); } catch { return; }
  refreshEmergency().catch(() => {});
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
  if (S.lastNotif !== null && newest > S.lastNotif && !n.items[0].read) {
    toast(n.items[0].text, n.items[0].kind === 'emergency');
    if (n.items[0].kind === 'emergency') alarm();
  }
  S.lastNotif = newest;
  S.notif = n;
  const dot = $('#bell-dot');
  if (dot) { dot.hidden = !n.unread; dot.textContent = n.unread > 9 ? '9+' : n.unread; }
  if (b && JSON.stringify(b) !== JSON.stringify(S.badges)) { S.badges = b; renderNav(); }
  if ($('#notif') && !$('#notif').hidden) renderNotifs();
}
function renderNotifs() {
  $('#notif').innerHTML = `<h3>Notifications</h3>${S.notif.items.length ? S.notif.items.map((n) => `
    <button class="${n.read ? '' : 'unread'}${n.kind === 'emergency' ? ' urgent' : ''}" data-act="go" data-view="${esc(n.view || 'home')}" data-ref="${esc(n.ref || '')}">${esc(n.text)}<small>${ago(n.at)}</small></button>`).join('')
    : '<div class="empty">Nothing new</div>'}`;
}

/* ---------- shared pieces ---------- */
const STATUS_PILL = { waiting: ['warn', 'Waiting'], in_consultation: ['good', 'With doctor'], done: ['', 'Completed'] };
const statusPill = (s) => `<span class="pill ${STATUS_PILL[s][0]}">${STATUS_PILL[s][1]}</span>`;
const PRIORITY_PILL = { critical: ['bad prio', 'Critical emergency'], urgent: ['warn prio', 'Urgent'] };
const priorityPill = (p) => (PRIORITY_PILL[p] ? `<span class="pill ${PRIORITY_PILL[p][0]}">${PRIORITY_PILL[p][1]}</span>` : '');

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
  return `<div class="item${v.status === 'in_consultation' ? ' hot' : ''}${v.priority === 'critical' ? ' critical' : v.priority === 'urgent' ? ' urgent' : ''}">
    <div class="item-head"><span class="token">${esc(v.token)}</span>${priorityPill(v.priority)}
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
  <div class="stack">
    <div class="card glass er-raise"><div class="spread"><div><b style="font-size:16.5px;font-weight:600">Critical emergency arriving?</b>
      <div class="hint">Raise a Critical Emergency Alert. The emergency team, the assigned doctor, the dean, the chairman and the administrator are alerted at once.</div></div>
      <button class="btn danger-solid" data-act="raiseAlert">${ic('siren')} Critical Emergency Alert</button></div></div>
    <div class="grid cols-2">
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
        ${priorityField()}
        <button class="btn primary" type="submit">Register and create patient ID</button>
      </form></div>
    <div class="card glass"><div class="card-head"><h2>Issue a queue token</h2></div>
      <form class="form" data-form="token" id="token-form">
        <label class="field">Patient${picker('Search by name or patient ID')}</label>
        <label class="field">Department<select name="department">${S.meta.departments.map((d) => `<option>${esc(d)}</option>`).join('')}</select></label>
        <label class="field">Reason for visit<input name="complaint" maxlength="240" placeholder="Short description"></label>
        ${priorityField()}
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
  S.draft = visit.draft || '';
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
        <span class="hint" id="draft-state">${visit.draft ? 'Draft restored. It is saved as you type.' : 'Your notes are saved as a draft as you type.'}</span>
      </form></div></div>
  </div>`;
};

/* ---------- queue, patients, beds ---------- */
LIVE.queueAll = async () => {
  const q = await api('/queue');
  return `<div class="grid cols-3">${S.meta.departments.map((d) => {
    const rows = q.visits.filter((v) => v.department === d);
    return `<div class="card glass"><div class="card-head"><h2>${esc(d)}</h2><span class="grow"></span><span class="pill plain">${rows.length}</span></div>
      ${rows.length ? `<div class="list">${rows.map((v) => `<div class="item${v.status === 'in_consultation' ? ' hot' : ''}${v.priority === 'critical' ? ' critical' : ''}"><div class="item-head">
        <span class="token">${esc(v.token)}</span><span class="grow"><b>${esc(v.patient.name)}</b></span>${priorityPill(v.priority)}</div>
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
    applyTheme(d.id, true);
    renderThemePanel();
    document.querySelectorAll('.theme-dot').forEach((b) => b.classList.toggle('on', b.dataset.id === d.id));
  },
  go(d) { closeModal(); go(d.view, d.ref ? (/^\d+$/.test(d.ref) ? Number(d.ref) : null) : null); },
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
    if (d.priority) $('[name=priority]', form).value = d.priority;
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
    const { priority, ...fields } = data;
    const out = await api('/patients', 'POST', { ...fields, age: Number(fields.age) });
    form.reset();
    const p = out.patient;
    if (priority === 'critical') return ACT.raiseAlert({ pid: p.pid, name: p.name, pin: out.pin });
    openModal(`<h2>Patient registered</h2><p class="sub">Give ${esc(p.name)} this ID and PIN. The PIN is shown only once.</p>
      <div class="credential"><div><span>Patient ID</span><b>${esc(p.pid)}</b></div><div><span>PIN</span><b>${esc(out.pin)}</b></div></div>
      <div class="modal-actions"><button class="btn" data-act="close">Done</button>
        <button class="btn primary" data-act="prefillToken" data-pid="${esc(p.pid)}" data-name="${esc(p.name)}" data-priority="${esc(priority || 'normal')}">Issue a token now</button></div>`);
  },
  async token(data, form) {
    const pid = pidFrom(data, form);
    if (!pid) throw new Error('Choose a patient from the search results');
    if (data.priority === 'critical') {
      return ACT.raiseAlert({ pid, name: $('[data-q]', form).value.split(' · ')[0], complaint: data.complaint, team: data.department });
    }
    const out = await api('/visits', 'POST', { pid, department: data.department, complaint: data.complaint, priority: data.priority });
    form.reset();
    openModal(`<h2>Token issued</h2><p class="sub">${esc(out.patient.name)} · ${esc(out.department)}${out.priority === 'urgent' ? ' · <b>Urgent</b>' : ''}</p>
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

/* ---------- live updates ---------- */
/* A server-sent event stream tells the app when its notifications, emergencies or equipment data changed.
   The six-second polling stays on as a fallback, so nothing depends on the stream staying connected. */
async function startStream() {
  stopStream();
  if (!S.token || !window.ReadableStream) return;
  const ctrl = new AbortController();
  S.stream = ctrl;
  let wait = 2000;
  while (S.stream === ctrl) {
    try {
      const res = await fetch('/api/stream', { headers: { Authorization: `Bearer ${S.token}` }, signal: ctrl.signal });
      if (res.status === 401) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      wait = 2000;
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let cut;
        while ((cut = buf.indexOf('\n\n')) >= 0) {
          const chunk = buf.slice(0, cut);
          buf = buf.slice(cut + 2);
          if (/^event: change/m.test(chunk)) tick(true);
          if (/^event: bye/m.test(chunk)) return;
        }
      }
    } catch { if (ctrl.signal.aborted) return; }
    await new Promise((r) => setTimeout(r, wait));
    wait = Math.min(wait * 2, 30000);
  }
}
function stopStream() {
  if (S.stream) S.stream.abort();
  S.stream = null;
}

/* ---------- emergency alert sound ---------- */
let audio = null;
const soundOn = () => { try { return localStorage.getItem('cs_er_sound') !== 'off'; } catch { return true; } };
document.addEventListener('pointerdown', () => {
  if (!audio && (window.AudioContext || window.webkitAudioContext)) audio = new (window.AudioContext || window.webkitAudioContext)();
  if (audio && audio.state === 'suspended') audio.resume();
}, { capture: true });
function alarm() {
  if (!audio || !soundOn() || audio.state !== 'running') return;  // browsers allow sound only after the user has clicked
  const t0 = audio.currentTime;
  for (let i = 0; i < 3; i++) {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = 'square';
    osc.frequency.value = i % 2 ? 660 : 880;
    gain.gain.setValueAtTime(0.0001, t0 + i * 0.32);
    gain.gain.exponentialRampToValueAtTime(0.12, t0 + i * 0.32 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + i * 0.32 + 0.26);
    osc.connect(gain).connect(audio.destination);
    osc.start(t0 + i * 0.32);
    osc.stop(t0 + i * 0.32 + 0.28);
  }
}

/* ---------- emergencies ---------- */
const ER_ROLES = ['receptionist', 'doctor', 'nurse', 'dean', 'chairman', 'admin'];
const ER_STATUS_PILL = { alert_created: 'bad', notification_sent: 'bad', acknowledged: 'warn', response_started: 'info',
  under_care: 'info', transferred: 'good', admitted: 'good', closed: '' };
const uid = () => (window.crypto && crypto.randomUUID ? crypto.randomUUID().replace(/-/g, '') : Date.now().toString(36) + Math.random().toString(36).slice(2, 14));
const erStatus = (a) => `<span class="pill ${ER_STATUS_PILL[a.status]}">${esc(a.status_label)}</span>`;
const erPrio = (p) => `<span class="pill ${p === 'critical' ? 'bad' : p === 'urgent' ? 'warn' : 'plain'} prio">${p === 'critical' ? 'Critical' : p === 'urgent' ? 'Urgent' : 'Normal'}</span>`;
const erWho = (a) => (a.restricted ? `<span class="mono">${esc(a.patient.pid)}</span> <span class="faint">(details restricted)</span>`
  : `<b>${esc(a.patient.name)}</b> <span class="mono faint">${esc(a.patient.pid)}</span>${a.patient.age != null ? ` · ${a.patient.age} y · ${esc(a.patient.gender)}` : ''}`);
const mins = (n) => (n < 60 ? `${n} min` : `${Math.floor(n / 60)} h ${n % 60} min`);
S.erSeen = new Set();
S.erRang = {};

function priorityField() {
  return `<label class="field">Priority<select name="priority">
    <option value="normal">Normal</option><option value="urgent">Urgent</option><option value="critical">Critical Emergency</option></select></label>`;
}

async function refreshEmergency() {
  const el = $('#er-banner');
  if (!el || !S.user || !ER_ROLES.includes(S.user.role)) return;
  const data = await api('/emergencies/active');
  const now = Date.now();
  for (const a of data.alerts) {
    if (!S.erSeen.has(a.id)) {  // the alert is on screen now: record delivery for this person
      S.erSeen.add(a.id);
      api(`/emergencies/${a.id}/received`, 'POST').catch(() => S.erSeen.delete(a.id));
    }
    if (a.must_ack && (!S.erRang[a.id] || now - S.erRang[a.id] > 30000)) { S.erRang[a.id] = now; alarm(); }
  }
  const html = data.alerts.slice(0, 3).map((a) => (a.must_ack ? `
    <div class="er-alert must" role="alert">
      <div class="er-head">${ic('siren')}<b>${a.priority === 'critical' ? 'CRITICAL EMERGENCY ALERT' : 'URGENT EMERGENCY ALERT'}</b>
        <span class="mono">${esc(a.ern)}</span><span class="grow"></span><span>Waiting ${mins(a.elapsed_minutes)}</span></div>
      <div class="er-body"><div>${erWho(a)}</div>
        <div>${esc(a.emergency_type)}${a.description ? ' · ' + esc(a.description) : ''}</div>
        <div class="er-meta">Location <b>${esc(a.location || 'not set')}</b> · Arrived ${fmtTime(a.arrival_at)} · ${esc(a.status_label)}${a.escalation_level ? ` · Escalated (level ${a.escalation_level})` : ''}</div>
        <div class="er-need">This patient needs immediate clinical attention. Acknowledge to tell the team you are responding.${S.view === 'consult' ? ' Your open consultation and its notes are kept.' : ''}</div></div>
      <div class="row">
        <button class="btn er-ack" data-act="erAck" data-id="${a.id}">Acknowledge emergency</button>
        <button class="btn small" data-act="erView" data-id="${a.id}">View patient</button>
        <button class="btn small" data-act="erAssign" data-id="${a.id}">Respond / assign backup</button>
        <button class="link er-sound" data-act="erSound">${soundOn() ? 'Mute sound' : 'Turn sound on'}</button></div>
    </div>` : `
    <div class="er-alert" role="status">${ic('siren')}<span class="grow"><b>${a.priority === 'critical' ? 'Critical emergency' : 'Urgent emergency'}</b>
      <span class="mono">${esc(a.ern)}</span> · ${erWho(a)} · ${esc(a.emergency_type)} · ${esc(a.location || 'location not set')} ·
      ${esc(a.assigned_doctor || a.team + ' team')} · ${esc(a.status_label)} · ${mins(a.elapsed_minutes)}</span>
      <button class="btn small" data-act="erView" data-id="${a.id}">View</button>
      <button class="btn small" data-act="erSeenNow" data-id="${a.id}">Dismiss</button></div>`)).join('')
    + (data.alerts.length > 3 ? `<button class="link" data-act="go" data-view="emergency">${data.alerts.length - 3} more open emergencies</button>` : '');
  if (el.innerHTML !== html) el.innerHTML = html;
}

LIVE.erBoard = async () => {
  const tab = S.erTab || 'open';
  const data = await api('/emergencies?scope=' + (tab === 'open' ? 'open' : 'history'));
  S.erMeta = data;
  const tabs = [['open', `Open (${tab === 'open' ? data.alerts.length : '…'})`], ['history', 'Alert history']];
  if (data.can_report) tabs.push(['report', 'Acknowledgement report']);
  let body;
  if (tab === 'report') body = await erReport(data);
  else {
    const rows = data.alerts;
    body = rows.length ? `<div class="list">${rows.map((a) => `<div class="item${a.priority === 'critical' && a.status !== 'closed' ? ' critical' : ''}">
      <div class="item-head">${erPrio(a.priority)}<span class="mono">${esc(a.ern)}</span><span class="grow">${erWho(a)}</span>${erStatus(a)}
        ${a.escalation_level ? `<span class="pill warn">Escalated ×${a.escalation_level}</span>` : ''}</div>
      <div class="meta">${esc(a.emergency_type)}${a.triage_level ? ' · Triage ' + esc(a.triage_level) : ''} · ${esc(a.location || 'Location not set')} · ${esc(a.assigned_doctor || a.team + ' team')}
        · Arrived ${fmtTime(a.arrival_at)} ${fmtShort(a.arrival_at.slice(0, 10))} · ${a.status === 'closed' ? 'Closed after ' : 'Waiting '}${mins(a.elapsed_minutes)}
        ${a.acknowledged_at ? ` · Acknowledged by ${esc(a.acknowledged_by)} in ${Math.round(a.ack_seconds / 6) / 10} min` : ' · <b class="bad-text">Not acknowledged</b>'}</div>
      <div class="row">
        <button class="btn small" data-act="erView" data-id="${a.id}">View</button>
        ${a.can_ack ? `<button class="btn small primary" data-act="erAck" data-id="${a.id}">Acknowledge</button>` : ''}
        ${a.can_update ? `<button class="btn small" data-act="erStatus" data-id="${a.id}">Update status</button>
          <button class="btn small" data-act="erTriage" data-id="${a.id}">Triage priority</button>` : ''}
        ${a.can_assign ? `<button class="btn small" data-act="erAssign" data-id="${a.id}">Assign clinician</button>
          ${a.status === 'alert_created' || a.status === 'notification_sent' ? `<button class="btn small" data-act="erEscalate" data-id="${a.id}">Escalate</button>` : ''}` : ''}
      </div></div>`).join('')}</div>` : `<div class="card glass"><div class="empty">${tab === 'open' ? 'No open emergencies' : 'No emergency alerts yet'}</div></div>`;
  }
  return `<div class="spread" style="align-items:flex-start"><div class="tabs">${tabs.map(([k, t]) => `<button data-act="erTab" data-tab="${k}" class="${tab === k ? 'on' : ''}">${t}</button>`).join('')}</div>
    ${data.can_raise ? `<button class="btn danger-solid" data-act="raiseAlert">${ic('siren')} Critical Emergency Alert</button>` : ''}</div>${body}`;
};
async function erReport(data) {
  const r = await api('/emergencies/report');
  const p = r.policy;
  return `<div class="stack"><div class="grid cols-4">
      <div class="tile glass"><div class="label">Alerts</div><div class="value">${r.total}</div><div class="foot">${r.open} open</div></div>
      <div class="tile glass"><div class="label">Average time to acknowledge</div><div class="value">${r.avg_ack_seconds == null ? '–' : Math.round(r.avg_ack_seconds / 6) / 10}<small>min</small></div><div class="foot">From alert to the assigned doctor</div></div>
      <div class="tile glass"><div class="label">Within policy</div><div class="value">${r.within_policy}<small>of ${r.acknowledged}</small></div><div class="foot">Acknowledged within ${p.ack_seconds} s</div></div>
      <div class="tile glass"><div class="label">Escalated</div><div class="value">${r.escalated}</div><div class="foot">Not acknowledged in time</div></div></div>
    <div class="card glass"><div class="card-head"><h2>Alert history</h2></div><div class="scroll-x"><table>
      <thead><tr><th>ERN</th><th>Arrived</th><th>Type</th><th>Priority</th><th>Doctor</th><th class="num">Ack time</th><th class="num">Escalations</th><th>Status</th></tr></thead>
      <tbody>${r.alerts.map((a) => `<tr><td><button class="link mono" data-act="erView" data-id="${a.id}">${esc(a.ern)}</button></td><td class="hint">${fmtShort(a.arrival_at.slice(0, 10))} ${fmtTime(a.arrival_at)}</td>
        <td>${esc(a.emergency_type)}</td><td>${erPrio(a.priority)}</td><td>${esc(a.assigned_doctor || '–')}</td>
        <td class="num">${a.ack_seconds == null ? '–' : a.ack_seconds + ' s'}</td><td class="num">${a.escalation_level}</td><td>${erStatus(a)}</td></tr>`).join('')}</tbody></table></div></div>
    <div class="card glass"><div class="card-head"><h2>Response policy</h2><span class="grow"></span><span class="hint">Set by the hospital; applied to every new and open alert</span></div>
      ${data.can_policy ? `<form class="form" data-form="erPolicy">
        <div class="three"><label class="field">Escalate if not acknowledged in (seconds)<input name="ack_seconds" type="number" min="15" max="3600" value="${p.ack_seconds}" required></label>
          <label class="field">Escalate again every (seconds)<input name="repeat_seconds" type="number" min="15" max="3600" value="${p.repeat_seconds}" required></label>
          <label class="field">Highest escalation level<input name="max_level" type="number" min="0" max="6" value="${p.max_level}" required></label></div>
        <div class="two"><label class="field">Retry undelivered alerts after (seconds)<input name="retry_seconds" type="number" min="5" max="600" value="${p.retry_seconds}" required></label>
          <label class="field">Delivery attempts per person<input name="max_attempts" type="number" min="1" max="10" value="${p.max_attempts}" required></label></div>
        <p class="hint">Level 1 alerts the emergency team, dean, administrator and reception again. Level 2 and above also alerts every available doctor and the chairman.</p>
        <div><button class="btn primary" type="submit">Save policy</button></div></form>`
        : `<dl class="kv"><dt>Escalate after</dt><dd>${p.ack_seconds} s without acknowledgement, then every ${p.repeat_seconds} s up to level ${p.max_level}</dd>
          <dt>Retry</dt><dd>Undelivered alerts every ${p.retry_seconds} s, up to ${p.max_attempts} attempts</dd></dl>`}</div></div>`;
}

VIEW.emergency = async () => {
  if (!S.arg) return live('erBoard');
  const a = await api('/emergencies/' + S.arg);
  return `<div class="stack">
    <div><button class="btn small" data-act="go" data-view="emergency">${ic('back')} All emergencies</button></div>
    <div class="grid split"><div class="stack">
      <div class="card glass${a.status !== 'closed' && a.priority === 'critical' ? ' er-card' : ''}"><div class="card-head">${erPrio(a.priority)}<h2 class="mono">${esc(a.ern)}</h2><span class="grow"></span>${erStatus(a)}</div>
        <div style="margin-bottom:12px">${erWho(a)}</div>
        ${a.patient.allergies ? `<div class="alert" style="margin-bottom:12px">Allergy: ${esc(a.patient.allergies)}</div>` : ''}
        <dl class="kv"><dt>Emergency</dt><dd>${esc(a.emergency_type)}</dd>
          ${a.description ? `<dt>Description</dt><dd>${esc(a.description)}</dd>` : ''}
          <dt>Triage</dt><dd>${esc(a.priority)}${a.triage_level ? ' · ' + esc(a.triage_level) : ' · not yet recorded by the clinical team'}</dd>
          <dt>Location</dt><dd>${esc(a.location || 'Not set')}</dd><dt>Team</dt><dd>${esc(a.team)}</dd>
          <dt>Doctor</dt><dd>${esc(a.assigned_doctor || 'Not assigned')}</dd>
          <dt>Arrived</dt><dd>${fmtDate(a.arrival_at)} ${fmtTime(a.arrival_at)}</dd>
          <dt>Alert raised</dt><dd>${fmtTime(a.created_at)} by ${esc(a.created_by)}</dd>
          <dt>Received</dt><dd>${a.received_at ? fmtTime(a.received_at) + ' on the assigned doctor\'s screen' : 'Not yet shown to the assigned doctor'}</dd>
          <dt>Acknowledged</dt><dd>${a.acknowledged_at ? `${fmtTime(a.acknowledged_at)} by ${esc(a.acknowledged_by)}` : '<b class="bad-text">Not yet</b>'}</dd>
          <dt>Escalation</dt><dd>${a.escalation_level ? 'Level ' + a.escalation_level : 'None'}</dd></dl>
        <div class="row" style="margin-top:16px">
          ${a.can_ack ? `<button class="btn primary" data-act="erAck" data-id="${a.id}">Acknowledge emergency</button>` : ''}
          ${a.can_update ? `<button class="btn small" data-act="erStatus" data-id="${a.id}">Update status</button><button class="btn small" data-act="erTriage" data-id="${a.id}">Triage priority</button>` : ''}
          ${a.can_assign ? `<button class="btn small" data-act="erAssign" data-id="${a.id}">Assign clinician</button>` : ''}
          ${!a.restricted && S.meta.clinical ? `<button class="btn small" data-act="openPatient" data-pid="${esc(a.patient.pid)}">Open full record</button>` : ''}
        </div></div>
      <div class="card glass"><div class="card-head"><h2>Notification delivery</h2><span class="grow"></span><span class="hint">Delivered means the person's app showed it</span></div>
        <div class="scroll-x"><table><thead><tr><th>Recipient</th><th>Sent</th><th>Delivered</th><th>Acknowledged</th><th class="num">Attempts</th></tr></thead>
        <tbody>${a.deliveries.map((d) => `<tr><td>${esc(d.who)} <span class="hint" style="text-transform:capitalize">${esc(d.role)}</span>${d.escalation ? ' <span class="pill warn plain">escalation</span>' : ''}</td>
          <td class="hint">${fmtTime(d.sent_at)}</td><td>${d.delivered_at ? fmtTime(d.delivered_at) : '<span class="pill warn plain">pending</span>'}</td>
          <td>${d.acked_at ? fmtTime(d.acked_at) : '–'}</td><td class="num">${d.attempts}</td></tr>`).join('')}</tbody></table></div></div>
    </div>
    <div class="card glass"><div class="card-head"><h2>Audit trail</h2></div>
      <div class="timeline">${a.events.map((e) => `<div class="item"><div class="item-head"><span class="grow"><b>${esc(erEventText(e))}</b>
        <div class="meta">${esc(e.who)} · ${fmtTime(e.at)} ${fmtShort(e.at.slice(0, 10))}</div></span></div>${e.note ? `<div class="meta">${esc(e.note)}</div>` : ''}</div>`).join('')}</div></div>
    </div></div>`;
};
const ER_LABEL = Object.fromEntries([['alert_created', 'Alert created'], ['notification_sent', 'Notification sent'], ['acknowledged', 'Acknowledged'],
  ['response_started', 'Clinical response started'], ['under_care', 'Patient under emergency care'], ['transferred', 'Transferred'], ['admitted', 'Admitted'], ['closed', 'Closed']]);
function erEventText(e) {
  if (e.action === 'status') return `Status: ${ER_LABEL[e.to] || e.to}`;
  if (e.action === 'created') return 'Alert raised';
  if (e.action === 'assigned') return `Assigned to ${e.to}${e.from ? ' (was ' + e.from + ')' : ''}`;
  if (e.action === 'triage') return `Triage: ${e.from} → ${e.to}`;
  if (e.action === 'escalated') return `Escalated to level ${e.to}`;
  if (e.action === 'received') return 'Shown on the assigned doctor\'s screen';
  if (e.action === 'seen') return 'Notification acknowledged';
  return e.action;
}

async function doctorOptions(team, selected) {
  const staff = (await api('/staff')).filter((u) => u.role === 'doctor');
  staff.sort((a, b) => (b.department === team) - (a.department === team) || b.available - a.available || a.name.localeCompare(b.name));
  return staff.map((u) => `<option value="${u.id}"${u.id === selected ? ' selected' : ''}>${esc(u.name)} · ${esc(u.department)}${u.available ? '' : ' (away)'}</option>`).join('');
}

Object.assign(ACT, {
  async raiseAlert(d = {}) {
    const meta = S.erMeta || await api('/emergencies');
    S.erMeta = meta;
    const team = d.team && S.meta.departments.includes(d.team) ? d.team : 'Emergency';
    const docs = await doctorOptions(team);
    const local = new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 16);
    openModal(`<h2 class="bad-text">${ic('siren')} Critical Emergency Alert</h2><p class="sub">Alerts the emergency team, the assigned doctor, the dean, the chairman, the administrator and reception straight away. It does not replace the triage protocol or the emergency team's assessment.</p>
      <form class="form" data-form="raiseAlert">
        <input type="hidden" name="idem_key" value="${uid()}">
        ${d.pid ? `<input type="hidden" name="pid" value="${esc(d.pid)}"><div class="note"><small>Patient</small>${esc(d.name || '')} <span class="mono">${esc(d.pid)}</span>${d.pin ? ` · new patient PIN <b class="mono">${esc(d.pin)}</b>` : ''}</div>`
        : `<div class="tabs" style="margin-bottom:0"><button type="button" class="on" data-act="erMode" data-mode="find">Registered patient</button><button type="button" data-act="erMode" data-mode="new">New or unidentified patient</button></div>
          <div data-mode="find"><label class="field">Patient${picker('Search by name or patient ID')}</label></div>
          <div data-mode="new" hidden><div class="three"><label class="field">Name<input name="np_name" maxlength="120" placeholder="e.g. Unknown male"></label>
            <label class="field">Age (approx.)<input name="np_age" type="number" min="0" max="120"></label>
            <label class="field">Gender<select name="np_gender"><option>Male</option><option>Female</option><option>Other</option><option>Unknown</option></select></label></div></div>`}
        <div class="two"><label class="field">Emergency type<select name="emergency_type" required>${meta.types.map((t) => `<option>${esc(t)}</option>`).join('')}</select></label>
          <label class="field">Priority<select name="priority"><option value="critical">Critical emergency</option><option value="urgent">Urgent</option></select></label></div>
        <label class="field">Brief description<textarea name="description" maxlength="600" placeholder="What happened, what the team should know">${esc(d.complaint || '')}</textarea></label>
        <div class="two"><label class="field">Arrival time<input name="arrival_at" type="datetime-local" value="${local}" required></label>
          <label class="field">Location<input name="location" list="er-locations" maxlength="60" value="Emergency bay 1" required>
            <datalist id="er-locations">${['Emergency bay 1', 'Emergency bay 2', 'Emergency bay 3', 'Emergency bay 4', 'Resuscitation room', 'Ambulance bay', 'Triage desk'].map((l) => `<option>${l}</option>`).join('')}</datalist></label></div>
        <div class="two"><label class="field">Responsible team<select name="team">${S.meta.departments.map((x) => `<option${x === team ? ' selected' : ''}>${esc(x)}</option>`).join('')}</select></label>
          <label class="field">Assigned doctor<select name="assigned_doctor_id"><option value="">First available on the team</option>${docs}</select></label></div>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn danger-solid" type="submit">Send emergency alert</button></div>
      </form>`, true);
  },
  erMode(d, el) {
    const form = el.closest('form');
    form.querySelectorAll('[data-act=erMode]').forEach((b) => b.classList.toggle('on', b === el));
    form.querySelectorAll('div[data-mode]').forEach((x) => {
      x.hidden = x.dataset.mode !== d.mode;
      x.querySelectorAll('input, select').forEach((i) => { i.disabled = x.hidden; });  // hidden fields must not block submit
    });
    form.dataset.mode = d.mode;
  },
  async erTab(d) { S.erTab = d.tab; await refreshLive('erBoard'); },
  erView(d) {
    closeModal();
    go('emergency', Number(d.id));
  },
  async erAck(d) {
    const out = await api(`/emergencies/${d.id}/ack`, 'POST', {});
    toast(out.result === 'acknowledged' ? `Acknowledged ${out.alert.ern}. The team can see you are responding.` : 'Marked as seen');
    await Promise.all([refreshEmergency(), refreshLive('erBoard')]);
    if (S.view === 'emergency' && S.arg) paint();
  },
  async erSeenNow(d) {
    await api(`/emergencies/${d.id}/ack`, 'POST', {});
    await refreshEmergency();
  },
  erSound() {
    try { localStorage.setItem('cs_er_sound', soundOn() ? 'off' : 'on'); } catch { /* storage blocked */ }
    refreshEmergency().catch(() => {});
  },
  async erAssign(d) {
    const a = await api('/emergencies/' + d.id);
    openModal(`<h2>Respond / assign backup</h2><p class="sub">${esc(a.ern)} · ${esc(a.emergency_type)} · now with ${esc(a.assigned_doctor || 'nobody')}</p>
      <form class="form" data-form="erAssign" data-id="${a.id}">
        <label class="field">Emergency clinician<select name="doctor_id">${await doctorOptions(a.team, null)}</select></label>
        <label class="field">Note<input name="note" maxlength="400" placeholder="e.g. Dr. Arjun is in a procedure"></label>
        <p class="hint">The new clinician is alerted and must acknowledge. Everything is kept in the audit trail.</p>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn primary" type="submit">Assign</button></div></form>`);
  },
  async erStatus(d) {
    const a = await api('/emergencies/' + d.id);
    const order = S.erMeta ? S.erMeta.statuses : Object.entries(ER_LABEL).map(([id, label]) => ({ id, label }));
    const at = order.findIndex((s) => s.id === a.status);
    openModal(`<h2>Update emergency status</h2><p class="sub">${esc(a.ern)} · now ${esc(a.status_label)}</p>
      <form class="form" data-form="erStatus" data-id="${a.id}">
        <label class="field">New status<select name="status">${order.slice(Math.max(2, at + 1)).map((s) => `<option value="${s.id}">${esc(s.label)}</option>`).join('')}</select></label>
        <label class="field">Note (required to close)<textarea name="note" maxlength="400"></textarea></label>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn primary" type="submit">Save status</button></div></form>`);
  },
  async erTriage(d) {
    const a = await api('/emergencies/' + d.id);
    openModal(`<h2>Triage priority</h2><p class="sub">Record the priority from the hospital's approved triage protocol. The system does not decide it.</p>
      <form class="form" data-form="erTriage" data-id="${a.id}">
        <div class="two"><label class="field">Priority<select name="priority">${['critical', 'urgent', 'normal'].map((p) => `<option value="${p}"${p === a.priority ? ' selected' : ''}>${p[0].toUpperCase() + p.slice(1)}</option>`).join('')}</select></label>
          <label class="field">Triage level (protocol)<input name="triage_level" maxlength="60" value="${esc(a.triage_level)}" placeholder="e.g. Level 1 - Resuscitation"></label></div>
        <label class="field">Reason<textarea name="note" maxlength="400" required></textarea></label>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn primary" type="submit">Save triage</button></div></form>`);
  },
  erEscalate(d) {
    openModal(`<h2>Escalate now?</h2><p class="sub">The emergency team, the dean, the administrator and reception are alerted again, and each further level widens the alert.</p>
      <form class="form" data-form="erEscalate" data-id="${esc(d.id)}"><label class="field">Reason<input name="note" maxlength="400" placeholder="e.g. Assigned doctor not reachable"></label>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn danger-solid" type="submit">Escalate</button></div></form>`);
  },
});

async function erDone(message, id) {
  closeModal();
  toast(message);
  await Promise.all([refreshEmergency(), refreshLive('erBoard')]);
  if (S.view === 'emergency' && S.arg === Number(id)) paint();
}

Object.assign(FORMS, {
  async raiseAlert(data, form) {
    const body = { idem_key: data.idem_key, emergency_type: data.emergency_type, description: data.description, priority: data.priority,
      location: data.location, team: data.team, arrival_at: data.arrival_at ? new Date(data.arrival_at).toISOString() : '',
      assigned_doctor_id: data.assigned_doctor_id ? Number(data.assigned_doctor_id) : null };
    if (form.dataset.mode === 'new') {
      if (!data.np_name || data.np_age === '') throw new Error('Enter a name (or "Unknown") and an approximate age');
      body.new_patient = { name: data.np_name, age: Number(data.np_age), gender: data.np_gender };
    } else {
      body.pid = data.pid || pidFrom(data, form);
      if (!body.pid) throw new Error('Choose the patient, or switch to New or unidentified patient');
    }
    const out = await api('/emergencies', 'POST', body);
    const a = out.alert;
    openModal(`<h2 class="bad-text">${ic('siren')} Emergency alert sent</h2><p class="sub">${esc(a.patient.name)} · ${esc(a.emergency_type)} · ${esc(a.location)}</p>
      <div class="credential"><div><span>Emergency number</span><b>${esc(a.ern)}</b></div>
        ${out.pin ? `<div><span>New patient ID and PIN</span><b>${esc(a.patient.pid)}</b><span class="mono">PIN ${esc(out.pin)}</span></div>` : `<div><span>Assigned doctor</span><b style="font-size:16px">${esc(a.assigned_doctor || a.team + ' team')}</b></div>`}</div>
      <p class="hint">${out.duplicate ? 'This alert was already sent; no second alert was created.' : 'Saved and sent. You can follow acknowledgement and status on the Emergencies page.'}</p>
      <div class="modal-actions" style="margin-top:14px"><button class="btn" data-act="close">Done</button><button class="btn primary" data-act="erView" data-id="${a.id}">Follow this emergency</button></div>`);
    refreshEmergency().catch(() => {});
    refreshLive('erBoard').catch(() => {});
  },
  async erAssign(data, form) {
    const a = await api(`/emergencies/${form.dataset.id}/assign`, 'POST', { doctor_id: Number(data.doctor_id), note: data.note });
    await erDone(`${a.ern} assigned to ${a.assigned_doctor}`, form.dataset.id);
  },
  async erStatus(data, form) {
    const a = await api(`/emergencies/${form.dataset.id}/status`, 'POST', data);
    await erDone(`${a.ern}: ${a.status_label}`, form.dataset.id);
  },
  async erTriage(data, form) {
    const a = await api(`/emergencies/${form.dataset.id}/triage`, 'POST', data);
    await erDone(`${a.ern}: triage saved`, form.dataset.id);
  },
  async erEscalate(data, form) {
    const a = await api(`/emergencies/${form.dataset.id}/escalate`, 'POST', data);
    await erDone(`${a.ern} escalated to level ${a.escalation_level}`, form.dataset.id);
  },
  async erPolicy(data) {
    const body = Object.fromEntries(Object.entries(data).map(([k, v]) => [k, Number(v)]));
    await api('/emergencies/policy/current', 'POST', body);
    toast('Response policy saved');
  },
});

/* ---------- consultation drafts (kept when a doctor is interrupted) ---------- */
function draftOf(form) {
  const meds = [...form.querySelectorAll('.med-row')].map((row) => [$('[name=med]', row).value, $('[name=dose]', row).value, $('[name=dur]', row).value]);
  return JSON.stringify({ diagnosis: form.diagnosis.value, notes: form.notes.value, refer_to: form.refer_to.value, refer_reason: form.refer_reason.value, meds });
}
let draftTimer;
async function saveDraft() {
  clearTimeout(draftTimer);
  const form = $('form[data-form=complete]');
  if (!form) return;
  const draft = draftOf(form);
  if (draft === S.draft) return;
  await api(`/visits/${form.dataset.id}/draft`, 'POST', { draft });
  S.draft = draft;
  const el = $('#draft-state');
  if (el) el.textContent = `Draft saved ${fmtTime(new Date().toISOString())}`;
}
AFTER.consult = () => {
  const form = $('form[data-form=complete]');
  if (!form || !S.draft) return;
  try {
    const d = JSON.parse(S.draft);
    form.diagnosis.value = d.diagnosis || '';
    form.notes.value = d.notes || '';
    form.refer_to.value = d.refer_to || '';
    form.refer_reason.value = d.refer_reason || '';
    const rows = (d.meds || []).filter((m) => m.some(Boolean));
    if (rows.length) {
      $('#meds').innerHTML = rows.map(() => medRow()).join('');
      [...$('#meds').children].forEach((row, i) => { $('[name=med]', row).value = rows[i][0]; $('[name=dose]', row).value = rows[i][1]; $('[name=dur]', row).value = rows[i][2]; });
    }
  } catch { /* old or empty draft */ }
};
document.addEventListener('input', (e) => {
  if (e.target.closest('form[data-form=complete]')) {
    clearTimeout(draftTimer);
    draftTimer = setTimeout(() => saveDraft().catch(() => {}), 1200);
  }
});

/* ---------- equipment and supplies ---------- */
const EQ_PILL = { pending_dean: 'warn', clarification: 'warn', rejected: 'bad', approved: 'info', sourcing_required: 'warn', sourcing: 'info',
  backorder: 'warn', ready_for_dispatch: 'good', dispatched: 'info', partially_fulfilled: 'warn', fulfilled: 'good', cancelled: '', servicing: 'info' };
const eqPill = (r) => `<span class="pill ${EQ_PILL[r.status] || ''}">${esc(r.status_label)}</span>`;
const urgPill = (u) => `<span class="pill ${u === 'critical' ? 'bad' : u === 'urgent' ? 'warn' : 'plain'}">${u[0].toUpperCase() + u.slice(1)}</span>`;
const human = (s) => String(s || '').replace(/_/g, ' ');
const isOps = () => ['coordinator', 'admin'].includes(S.user.role);
S.eq = { q: '', status: '', department: '', urgency: '', category: '', date_from: '', date_to: '', sort: 'created_at', dir: 'desc', page: 1, open_only: false };
S.eqTab = null;

async function catalog() {
  if (!S.catalog) S.catalog = await api('/equipment/catalog');
  return S.catalog;
}
function progress(r) {
  if (r.dean_status !== 'approved' || !r.qty_approved) return '';
  const pct = Math.min(100, Math.round((100 * r.qty_delivered) / r.qty_approved));
  return `<div class="eq-progress"><div class="meter"><i style="width:${pct}%"></i></div><span class="hint">${r.qty_delivered} of ${r.qty_approved} delivered${r.qty_dispatched > r.qty_delivered ? ` · ${r.qty_dispatched - r.qty_delivered} on the way` : ''}${r.qty_reserved ? ` · ${r.qty_reserved} ready in stores` : ''}</span></div>`;
}
function eqCard(r) {
  return `<div class="item${r.urgency === 'critical' && !['fulfilled', 'cancelled', 'rejected'].includes(r.status) ? ' critical' : ''}"><div class="item-head">
      <span class="mono">${esc(r.ref)}</span><span class="grow"><b>${esc(r.item_name)}</b> × ${r.quantity}
      <div class="meta">${esc(r.request_type_label)} · ${esc(r.category)} · ${esc(r.doctor)} · ${ago(r.created_at)}</div></span>${urgPill(r.urgency)}${eqPill(r)}</div>
    ${progress(r)}
    ${r.awaiting_my_answer ? '<div class="alert">A question is waiting for your answer.</div>' : ''}
    <div class="row"><button class="btn small" data-act="eqOpen" data-id="${r.id}">View request</button>
      ${r.awaiting_my_answer ? `<button class="btn small primary" data-act="eqRespond" data-id="${r.id}">Answer question</button>` : ''}</div></div>`;
}
function eqFilters(departments) {
  const f = S.eq;
  const cat = S.catalog;
  const cats = [...new Set(cat.sections.flatMap((s) => s.categories.map((c) => c.category)))].sort();
  const opt = (v, label, cur) => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(label)}</option>`;
  return `<div class="filters" data-filters>
    <input data-f="q" placeholder="Search ID, item or category" value="${esc(f.q)}">
    ${departments ? `<select data-f="department">${opt('', 'All departments', f.department)}${S.meta.departments.map((d) => opt(d, d, f.department)).join('')}</select>` : ''}
    <select data-f="category">${opt('', 'All categories', f.category)}${cats.map((c) => opt(c, c, f.category)).join('')}</select>
    <select data-f="urgency">${opt('', 'Any urgency', f.urgency)}${cat.urgency.map((u) => opt(u, u[0].toUpperCase() + u.slice(1), f.urgency)).join('')}</select>
    <select data-f="status">${opt('', 'Any status', f.status)}${cat.statuses.map((s) => opt(s.id, s.label, f.status)).join('')}</select>
    <label class="mini">From<input type="date" data-f="date_from" value="${esc(f.date_from)}"></label>
    <label class="mini">To<input type="date" data-f="date_to" value="${esc(f.date_to)}"></label>
    <label class="mini check"><input type="checkbox" data-f="open_only"${f.open_only ? ' checked' : ''}> Open only</label>
  </div>`;
}
function eqQuery(extra = {}) {
  const f = { ...S.eq, ...extra };
  return Object.entries(f).filter(([, v]) => v !== '' && v !== false && v != null).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
}
const COLS = [['ref', 'Request ID'], ['created_at', 'Requested'], [null, 'Doctor'], ['department', 'Department'], ['item_name', 'Item'], [null, 'Category'],
  ['quantity', 'Requested', 'num'], [null, 'Approved', 'num'], [null, 'Sourced', 'num'], [null, 'Dispatched', 'num'], [null, 'Delivered', 'num'],
  ['urgency', 'Urgency'], [null, 'Dean'], [null, 'Procurement'], [null, 'Dispatch'], ['expected_date', 'Expected'], [null, 'Supplier'],
  ['updated_at', 'Last updated'], [null, 'Actions']];
function nextAction(r) {
  if (!r.can_operate) return '';
  if (['repair', 'servicing'].includes(r.request_type) && r.status === 'approved') return ['eqService', 'Schedule service'];
  if (r.status === 'ready_for_dispatch' || r.qty_reserved > 0) return ['eqDispatch', 'Dispatch'];
  if (r.status === 'approved') return ['eqStock', 'Check stock'];
  if (r.status === 'sourcing_required') return ['eqSource', 'Source item'];
  return '';
}
function eqTable(page, full) {
  const sortBtn = ([key, title, cls]) => `<th class="${cls || ''}">${key ? `<button class="th-sort${S.eq.sort === key ? ' on' : ''}" data-act="eqSort" data-key="${key}">${esc(title)}${S.eq.sort === key ? (S.eq.dir === 'asc' ? ' ↑' : ' ↓') : ''}</button>` : esc(title)}</th>`;
  const cols = full ? COLS : COLS.filter(([, t]) => !['Sourced', 'Dispatched', 'Dean', 'Procurement', 'Dispatch', 'Supplier', 'Expected'].includes(t));
  const pages = Math.max(1, Math.ceil(page.total / page.size));
  const cell = (r, t) => ({
    'Request ID': `<span class="mono">${esc(r.ref)}</span>`, Requested: null, Doctor: esc(r.doctor), Department: esc(r.department),
    Item: `<b style="font-weight:500">${esc(r.item_name)}</b><div class="hint">${esc(r.request_type_label)}</div>`, Category: esc(r.category),
    Approved: r.qty_approved || '–', Sourced: r.qty_sourced || '–', Dispatched: r.qty_dispatched || '–', Delivered: r.qty_delivered || '–',
    Urgency: urgPill(r.urgency), Dean: `<span class="pill ${r.dean_status === 'approved' ? 'good' : r.dean_status === 'rejected' ? 'bad' : 'warn'} plain">${esc(human(r.dean_status))}</span>`,
    Procurement: esc(human(r.procurement_status)), Dispatch: esc(human(r.dispatch_status)), Expected: esc(r.expected_date || '–'),
    Supplier: esc(r.supplier || '–'), 'Last updated': `<span class="hint">${ago(r.updated_at)}</span>`,
  }[t]);
  const rows = page.rows.map((r) => {
    const next = nextAction(r);
    return `<tr class="${r.urgency === 'critical' && !['fulfilled', 'cancelled', 'rejected'].includes(r.status) ? 'hot-row' : ''}">${cols.map(([, t, cls]) => {
      if (t === 'Requested' && cls) return `<td class="num">${r.quantity}</td>`;
      if (t === 'Requested') return `<td class="hint" style="white-space:nowrap">${fmtShort(r.created_at.slice(0, 10))}</td>`;
      if (t === 'Actions') return `<td style="white-space:nowrap"><button class="btn small" data-act="eqOpen" data-id="${r.id}">View</button>${next ? ` <button class="btn small primary" data-act="${next[0]}" data-id="${r.id}">${next[1]}</button>` : ''}</td>`;
      if (t === 'Dean' || t === 'Item') return `<td>${cell(r, t)}</td>`;
      return `<td class="${cls || ''}">${cell(r, t)}</td>`;
    }).join('')}<td style="display:none"></td></tr>`;
  }).join('');
  return `<div class="scroll-x"><table class="eq-table"><thead><tr>${cols.map(sortBtn).join('')}</tr></thead>
    <tbody>${rows || `<tr><td colspan="${cols.length}"><div class="empty">No requests match these filters</div></td></tr>`}</tbody></table></div>
    <div class="spread" style="margin-top:12px"><span class="hint">${page.total} request${page.total === 1 ? '' : 's'} · page ${page.page} of ${pages}</span>
      <span class="row"><button class="btn small" data-act="eqPage" data-step="-1" ${page.page <= 1 ? 'disabled' : ''}>Previous</button>
      <button class="btn small" data-act="eqPage" data-step="1" ${page.page >= pages ? 'disabled' : ''}>Next</button></span></div>`;
}

LIVE.eqDoctor = async () => {
  await catalog();
  const tab = S.eqTab || (S.user.role === 'doctor' ? 'mine' : 'department');
  const [list, tickets] = await Promise.all([api('/equipment/requests?size=50&scope=' + (tab === 'mine' ? 'mine' : 'department')), api('/equipment/maintenance?status=open')]);
  const incoming = [];
  for (const r of list.rows.filter((x) => x.qty_dispatched > x.qty_delivered)) {
    const det = await api('/equipment/requests/' + r.id);
    det.dispatches.filter((d) => d.can_confirm).forEach((d) => incoming.push({ ...d, item: r.item_name }));
  }
  const tabs = S.user.role === 'doctor' ? [['mine', 'My requests'], ['department', `${S.user.department} requests`]] : [['department', `${S.user.department} requests`]];
  return `<div class="stack">
    <div class="spread" style="align-items:flex-start"><div class="tabs">${tabs.map(([k, t]) => `<button data-act="eqTab" data-tab="${k}" class="${tab === k ? 'on' : ''}">${t}</button>`).join('')}</div>
      <span class="row">${S.user.role === 'doctor' ? `<button class="btn primary" data-act="eqNew">${ic('plus')} New request</button>` : ''}
        <button class="btn" data-act="eqFault">${ic('wrench')} Report faulty equipment</button></span></div>
    ${incoming.length ? `<div class="card glass"><div class="card-head"><h2>Deliveries to confirm</h2></div><div class="list">${incoming.map((d) => `<div class="item"><div class="item-head">
        <span class="mono">${esc(d.ref)}</span><span class="grow"><b>${esc(d.item)}</b> × ${d.qty}<div class="meta">Sent ${ago(d.dispatched_at)} to ${esc(d.destination)}, carried by ${esc(d.handled_by)}${d.asset_tags ? ' · ' + esc(d.asset_tags) : ''}</div></span>
        <button class="btn small primary" data-act="eqConfirm" data-id="${d.id}" data-qty="${d.qty}">Confirm receipt</button></div></div>`).join('')}</div></div>` : ''}
    <div class="grid split"><div class="card glass"><div class="card-head"><h2>Requests</h2><span class="grow"></span><span class="pill plain">${list.total}</span></div>
      ${list.rows.length ? `<div class="list">${list.rows.map(eqCard).join('')}</div>` : '<div class="empty">No requests yet. Use New request to ask for equipment or supplies.</div>'}</div>
      <div class="card glass"><div class="card-head"><h2>Equipment under repair</h2></div>${ticketList(tickets)}</div></div>
  </div>`;
};
function ticketList(tickets, manage) {
  return tickets.length ? `<div class="list">${tickets.map((t) => `<div class="item${t.unsafe ? ' critical' : ''}"><div class="item-head"><span class="mono">${esc(t.ref)}</span>
      <span class="grow"><b>${esc(t.item_name)}</b>${t.asset_tag ? ` <span class="mono faint">${esc(t.asset_tag)}</span>` : ''}<div class="meta">${esc(t.department || 'Stores')} · reported by ${esc(t.reported_by)} ${ago(t.created_at)}</div></span>
      ${t.unsafe ? '<span class="pill bad">Unsafe, out of use</span>' : ''}<span class="pill ${t.status === 'completed' ? 'good' : 'info'}">${esc(t.status_label)}</span></div>
    <div class="meta">${esc(t.issue)}</div>
    ${t.technician || t.provider || t.scheduled_for ? `<div class="meta">${[t.technician, t.provider, t.scheduled_for && 'scheduled ' + t.scheduled_for].filter(Boolean).map(esc).join(' · ')}</div>` : ''}
    ${t.findings ? `<div class="meta">Findings: ${esc(t.findings)}${t.parts_used ? ' · Parts: ' + esc(t.parts_used) : ''}${t.cost != null ? ' · Cost ' + esc(t.cost) : ''}</div>` : ''}
    ${manage && t.can_manage ? `<div class="row"><button class="btn small" data-act="mtManage" data-id="${t.id}">Manage repair</button></div>` : ''}</div>`).join('')}</div>`
    : '<div class="empty">Nothing under repair</div>';
}

LIVE.eqDean = async () => {
  await catalog();
  const [page, ov] = await Promise.all([api('/equipment/requests?size=15&' + eqQuery()), api('/equipment/overview')]);
  return `<div class="stack">
    <div class="grid cols-4">
      <div class="tile glass"><div class="label">Awaiting your approval</div><div class="value">${ov.stages.pending_dean}</div><div class="foot">Including clarifications</div></div>
      <div class="tile glass"><div class="label">Approved, being sourced</div><div class="value">${ov.stages.awaiting_sourcing + ov.stages.procurement}</div><div class="foot">${ov.stages.delayed} delayed</div></div>
      <div class="tile glass"><div class="label">On the way or partial</div><div class="value">${ov.stages.in_transit + ov.stages.partial + ov.stages.ready_for_dispatch}</div><div class="foot">${ov.stages.ready_for_dispatch} ready in stores</div></div>
      <div class="tile glass"><div class="label">Completed</div><div class="value">${ov.stages.completed}</div><div class="foot">${ov.stages.servicing} service jobs open</div></div></div>
    <div class="card glass"><div class="card-head"><h2>Equipment requests</h2><span class="grow"></span><button class="link" data-act="eqPreset" data-status="pending_dean">Show pending approvals</button></div>
      ${eqFilters(true)}${eqTable(page, false)}</div>
    <div class="card glass"><div class="card-head"><h2>Outstanding needs by department</h2></div>${deptDemand(ov)}</div></div>`;
};
function deptDemand(ov) {
  return ov.by_department.length ? `<div class="scroll-x"><table><thead><tr><th>Department</th><th class="num">Open requests</th><th class="num">Units outstanding</th><th class="num">Awaiting dean</th><th class="num">Critical</th></tr></thead>
    <tbody>${ov.by_department.map((d) => `<tr><td>${esc(d.department)}</td><td class="num">${d.open}</td><td class="num">${d.units_outstanding}</td><td class="num">${d.awaiting_dean}</td>
      <td class="num">${d.critical ? `<span class="pill bad plain">${d.critical}</span>` : 0}</td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">No outstanding needs</div>';
}
function procurementTiles(ov) {
  const st = ov.stages;
  const tile = (label, n, foot, status) => `<button class="tile glass tile-btn" data-act="eqPreset" data-status="${status || ''}"><div class="label">${label}</div><div class="value">${n}</div><div class="foot">${foot}</div></button>`;
  return `<div class="grid cols-4">
    ${tile('Awaiting dean approval', st.pending_dean, 'Departmental requests', 'pending_dean,clarification')}
    ${tile('Approved, awaiting sourcing', st.awaiting_sourcing, 'Stock check or supplier needed', 'approved,sourcing_required')}
    ${tile('Procurement in progress', st.procurement, `${st.delayed} delayed`, 'sourcing,backorder')}
    ${tile('Ready for dispatch', st.ready_for_dispatch, 'Reserved in stores', 'ready_for_dispatch')}
    ${tile('In transit', st.in_transit, 'Dispatched, not yet confirmed', 'dispatched')}
    ${tile('Partially fulfilled', st.partial, 'Some units still outstanding', 'partially_fulfilled')}
    ${tile('Completed deliveries', st.completed, 'Fulfilled requests', 'fulfilled')}
    ${tile('Servicing and repairs', st.servicing, `${ov.unsafe_open} unsafe item${ov.unsafe_open === 1 ? '' : 's'} out of use`, 'servicing')}</div>`;
}
LIVE.eqOverview = async () => {
  await catalog();
  const [ov, page] = await Promise.all([api('/equipment/overview'), api('/equipment/requests?size=15&' + eqQuery())]);
  return `<div class="stack">${procurementTiles(ov)}
    <div class="grid cols-2"><div class="card glass"><div class="card-head"><h2>Department-wise demand</h2></div>${deptDemand(ov)}</div>
      <div class="card glass"><div class="card-head"><h2>Delayed and low stock</h2></div>
        ${ov.delayed.length || ov.low_stock.length ? `<div class="list">${ov.delayed.map((o) => `<div class="item"><div class="item-head"><span class="mono">${esc(o.request)}</span><span class="grow">${esc(o.supplier)} · ref ${esc(o.reference || '–')}</span><span class="pill warn">Expected ${esc(o.expected_date)}</span></div></div>`).join('')}
          ${ov.low_stock.map((i) => `<div class="item"><div class="item-head"><span class="grow"><b>${esc(i.name)}</b> <span class="mono faint">${esc(i.code)}</span></span><span class="pill bad">${i.available} left, minimum ${i.min_stock}</span></div></div>`).join('')}</div>`
          : '<div class="empty">Nothing delayed or low</div>'}</div></div>
    <div class="card glass"><div class="card-head"><h2>All requests</h2></div>${eqFilters(true)}${eqTable(page, true)}</div></div>`;
};

/* Coordinator (and administrator) workspace */
LIVE.stores = async () => {
  await catalog();
  const tab = S.storeTab || 'requests';
  const tabs = [['requests', 'Requests'], ['inventory', 'Inventory'], ['maintenance', 'Maintenance'], ['suppliers', 'Suppliers'], ['ledger', 'Stock movements']];
  let body = '';
  if (tab === 'requests') {
    const [page, ov] = await Promise.all([api('/equipment/requests?' + eqQuery()), api('/equipment/overview')]);
    body = `${procurementTiles(ov)}<div class="card glass" style="margin-top:18px"><div class="card-head"><h2>Request management</h2></div>${eqFilters(true)}${eqTable(page, true)}</div>`;
  } else if (tab === 'inventory') {
    const rows = await api('/equipment/inventory?q=' + encodeURIComponent(S.invQ || ''));
    body = `<div class="card glass"><div class="card-head"><h2>Equipment inventory</h2><span class="grow"></span>
        <input data-inv-q placeholder="Search item, code or model" value="${esc(S.invQ || '')}" style="max-width:260px">
        <button class="btn small primary" data-act="invNew">${ic('plus')} Add item</button></div>
      <div class="scroll-x"><table class="eq-table"><thead><tr><th>Item ID</th><th>Equipment</th><th>Category</th><th>Tracking</th><th class="num">Total</th><th class="num">Available</th><th class="num">Reserved</th>
        <th class="num">In service</th><th class="num">Maintenance</th><th class="num">Damaged</th><th>Location</th><th>Next service</th><th>Condition</th><th></th></tr></thead>
      <tbody>${rows.map((i) => `<tr class="${i.low ? 'hot-row' : ''}"><td class="mono">${esc(i.code)}</td><td><b style="font-weight:500">${esc(i.name)}</b><div class="hint">${esc(i.model)}</div></td>
        <td>${esc(i.category)}</td><td class="hint">${i.tracking === 'asset' ? 'Tagged assets' : 'Quantity'}</td><td class="num">${i.total}</td>
        <td class="num">${i.low ? `<span class="pill bad plain">${i.available}</span>` : i.available}</td><td class="num">${i.reserved}</td><td class="num">${i.in_service}</td>
        <td class="num">${i.maintenance}</td><td class="num">${i.damaged}</td><td class="hint">${esc(i.location)}</td>
        <td>${i.next_maintenance ? `<span class="${i.service_due ? 'pill warn plain' : 'hint'}">${esc(i.next_maintenance)}</span>` : '–'}</td>
        <td>${i.condition === 'unsafe' ? '<span class="pill bad">Unsafe</span>' : esc(i.condition)}</td>
        <td><button class="btn small" data-act="invOpen" data-id="${i.id}">Open</button></td></tr>`).join('')}</tbody></table></div></div>`;
  } else if (tab === 'maintenance') {
    const tickets = await api('/equipment/maintenance?status=open');
    body = `<div class="card glass"><div class="card-head"><h2>Open maintenance and repairs</h2><span class="grow"></span><button class="btn small" data-act="eqFault">${ic('wrench')} Log an issue</button></div>${ticketList(tickets, true)}</div>`;
  } else if (tab === 'suppliers') {
    const rows = await api('/equipment/suppliers');
    body = `<div class="grid split"><div class="card glass"><div class="card-head"><h2>Suppliers and service providers</h2></div>
      <div class="scroll-x"><table><thead><tr><th>Name</th><th>Type</th><th>Contact</th><th>Phone</th><th>Email</th></tr></thead>
      <tbody>${rows.map((s) => `<tr><td>${esc(s.name)}</td><td class="hint">${s.kind === 'service' ? 'Service provider' : 'Supplier'}</td><td>${esc(s.contact)}</td><td class="mono hint">${esc(s.phone)}</td><td class="hint">${esc(s.email)}</td></tr>`).join('')}</tbody></table></div></div>
      <div class="card glass"><div class="card-head"><h2>Add a supplier</h2></div><form class="form" data-form="supplier">
        <label class="field">Name<input name="name" required minlength="2" maxlength="120"></label>
        <label class="field">Type<select name="kind"><option value="supplier">Supplier</option><option value="service">Service provider</option></select></label>
        <div class="two"><label class="field">Contact person<input name="contact" maxlength="120"></label><label class="field">Phone<input name="phone" maxlength="30"></label></div>
        <label class="field">Email<input name="email" maxlength="120" type="email"></label><div><button class="btn primary" type="submit">Add supplier</button></div></form></div></div>`;
  } else {
    const rows = await api('/equipment/transactions');
    body = `<div class="card glass"><div class="card-head"><h2>Stock movements</h2><span class="grow"></span><span class="hint">Every reserve, receipt, dispatch, return and repair</span></div>
      <div class="scroll-x"><table><thead><tr><th>When</th><th>Item</th><th>Movement</th><th class="num">Qty</th><th>From → to</th><th>Assets</th><th>By</th><th>Note</th></tr></thead>
      <tbody>${rows.map((t) => `<tr><td class="hint" style="white-space:nowrap">${fmtShort(t.at.slice(0, 10))} ${fmtTime(t.at)}</td><td>${esc(t.item)} <span class="mono faint">${esc(t.code)}</span></td>
        <td>${esc(human(t.kind))}</td><td class="num">${t.qty}</td><td class="hint">${esc(human(t.from))} → ${esc(human(t.to))}</td><td class="mono hint" style="font-size:12px">${esc(t.tags)}</td><td>${esc(t.who)}</td><td class="hint">${esc(t.note)}</td></tr>`).join('')}</tbody></table></div></div>`;
  }
  return `<div class="tabs">${tabs.map(([k, t]) => `<button data-act="storeTab" data-tab="${k}" class="${tab === k ? 'on' : ''}">${t}</button>`).join('')}</div>${body}`;
};

HOME.coordinator = () => live('stores');
LIVE.adminHome = async () => {
  const [st, er, ov] = await Promise.all([api('/status'), api('/emergencies'), api('/equipment/overview')]);
  return `<div class="stack">
    <div class="grid cols-4">
      <div class="tile glass"><div class="label">Open emergencies</div><div class="value">${er.alerts.length}</div><div class="foot">${er.alerts.filter((a) => !a.acknowledged_at).length} not yet acknowledged</div></div>
      <div class="tile glass"><div class="label">Patients waiting</div><div class="value">${st.departments.reduce((n, d) => n + d.waiting, 0)}</div><div class="foot">Across all departments</div></div>
      <div class="tile glass"><div class="label">Equipment awaiting dean</div><div class="value">${ov.stages.pending_dean}</div><div class="foot">${ov.stages.awaiting_sourcing} approved, awaiting sourcing</div></div>
      <div class="tile glass"><div class="label">Delayed or low stock</div><div class="value">${ov.stages.delayed + ov.low_stock.length}</div><div class="foot">${ov.unsafe_open} unsafe items out of use</div></div></div>
    <div class="grid cols-2"><div class="card glass"><div class="card-head"><h2>Emergency response</h2><span class="grow"></span><button class="link" data-act="go" data-view="emergency">Open emergencies</button></div>
        ${er.alerts.length ? `<div class="list">${er.alerts.map((a) => `<div class="item${a.priority === 'critical' ? ' critical' : ''}"><div class="item-head">${erPrio(a.priority)}<span class="mono">${esc(a.ern)}</span><span class="grow">${erWho(a)}</span>${erStatus(a)}</div>
          <div class="meta">${esc(a.emergency_type)} · ${esc(a.location)} · ${esc(a.assigned_doctor || a.team + ' team')} · ${mins(a.elapsed_minutes)}</div></div>`).join('')}</div>` : '<div class="empty">No open emergencies</div>'}</div>
      <div class="card glass"><div class="card-head"><h2>Departments right now</h2></div>${deptTable(st)}</div></div>
    <div class="card glass"><div class="card-head"><h2>Resource needs by department</h2><span class="grow"></span><button class="link" data-act="go" data-view="equipment">Procurement</button></div>${deptDemand(ov)}</div></div>`;
};
HOME.admin = () => live('adminHome');

VIEW.equipment = () => {
  const role = S.user.role;
  if (role === 'doctor' || role === 'nurse') return live('eqDoctor');
  if (role === 'dean') return live('eqDean');
  if (role === 'admin') return S.adminStores ? live('stores').then((h) => `<div class="row" style="margin-bottom:14px"><button class="btn small" data-act="adminStores" data-on="0">${ic('back')} Procurement overview</button></div>${h}`)
    : live('eqOverview').then((h) => `<div class="row" style="margin-bottom:14px;justify-content:flex-end"><button class="btn small primary" data-act="adminStores" data-on="1">Open stores and dispatch</button></div>${h}`);
  return live('eqOverview');
};

async function refreshEq() {
  await Promise.all(['eqDoctor', 'eqDean', 'eqOverview', 'stores', 'adminHome'].map((n) => refreshLive(n).catch(() => {})));
}

async function openRequest(id) {
  const r = await api('/equipment/requests/' + id);
  const role = S.user.role;
  const qty = [['Requested', r.quantity], ['Approved', r.qty_approved], ['Reserved', r.qty_reserved], ['Sourced', r.qty_sourced], ['Received', r.qty_received],
    ['Dispatched', r.qty_dispatched], ['Delivered', r.qty_delivered], ['Returned', r.qty_returned]];
  const act = (a, label, cls = '') => `<button class="btn small ${cls}" data-act="${a}" data-id="${r.id}">${label}</button>`;
  const actions = [];
  if (r.can_decide) actions.push(act('eqDecide', 'Approve', 'primary'), act('eqClarifyDean', 'Request clarification'), act('eqReject', 'Reject', 'danger'));
  if (r.awaiting_my_answer) actions.push(act('eqRespond', 'Answer question', 'primary'));
  if (r.can_operate) {
    actions.push(act('eqStock', 'Check stock'), act('eqReserve', 'Reserve stock'), act('eqSource', 'Source item'));
    if (r.qty_reserved) actions.push(act('eqDispatch', 'Dispatch', 'primary'), act('eqRelease', 'Release reservation'));
    if (['repair', 'servicing', 'replacement'].includes(r.request_type)) actions.push(act('eqService', 'Schedule service'));
    actions.push(act('eqBackorder', 'Backorder'), act('eqAsk', 'Ask the doctor'));
  }
  if (r.qty_delivered && (isOps() || (['doctor', 'nurse'].includes(role) && S.user.department === r.department))) actions.push(act('eqReturn', 'Record a return'));
  if (r.can_cancel) actions.push(act('eqCancel', 'Cancel request', 'danger'));
  openModal(`<div class="spread"><div><h2><span class="mono">${esc(r.ref)}</span> · ${esc(r.item_name)}</h2>
      <p class="sub" style="margin-bottom:10px">${esc(r.request_type_label)} · ${esc(r.category)} · ${esc(r.department)}, ${esc(r.location)} · requested by ${esc(r.doctor)} on ${fmtDate(r.created_at)}</p></div>
      <button class="icon-btn" data-act="close" aria-label="Close">${ic('x')}</button></div>
    <div class="row" style="margin-bottom:12px">${urgPill(r.urgency)}${eqPill(r)}<span class="pill plain">Dean: ${esc(human(r.dean_status))}</span>
      <span class="pill plain">Procurement: ${esc(human(r.procurement_status))}</span><span class="pill plain">Dispatch: ${esc(human(r.dispatch_status))}</span>
      ${r.emergency_policy ? '<span class="pill bad plain">Emergency procurement policy</span>' : ''}</div>
    <div class="qty-grid">${qty.map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join('')}</div>
    ${progress(r)}
    <dl class="kv" style="margin:14px 0"><dt>Justification</dt><dd style="white-space:pre-wrap">${esc(r.justification)}</dd>
      ${r.decision_note ? `<dt>Dean's note</dt><dd>${esc(r.decision_note)} (${esc(r.decided_by)})</dd>` : ''}
      ${r.supplier ? `<dt>Supplier</dt><dd>${esc(r.supplier)}</dd>` : ''}${r.expected_date ? `<dt>Expected</dt><dd>${esc(r.expected_date)}</dd>` : ''}
      ${r.attachment ? `<dt>Attachment</dt><dd><button class="link" data-act="eqAttachment" data-id="${r.id}" data-name="${esc(r.attachment)}">${esc(r.attachment)}</button></dd>` : ''}
      ${r.reserved_tags.length ? `<dt>Reserved assets</dt><dd class="mono" style="font-size:13px">${esc(r.reserved_tags.join(', '))}</dd>` : ''}</dl>
    ${actions.length ? `<div class="row eq-actions">${actions.join('')}</div>` : ''}
    ${r.sourcing.length ? `<h3 class="sec">Sourcing</h3><div class="list">${r.sourcing.map((o) => `<div class="item"><div class="item-head"><span class="grow"><b>${esc(o.supplier)}</b> · ref ${esc(o.reference || '–')} · ${o.qty_ordered} ordered
        <div class="meta">${o.qty_arrived} arrived · ${o.qty_accepted} accepted · ${o.qty_rejected} rejected${o.expected_date ? ' · expected ' + esc(o.expected_date) : ''}${o.inspection_note ? ' · ' + esc(o.inspection_note) : ''}</div></span>
        <span class="pill ${o.status === 'delayed' || o.overdue ? 'warn' : o.status === 'received' ? 'good' : 'info'}">${esc(o.overdue && o.status === 'ordered' ? 'overdue' : o.status)}</span></div>
        ${isOps() && ['ordered', 'delayed', 'arrived'].includes(o.status) ? `<div class="row">
          ${o.qty_arrived < o.qty_ordered ? `<button class="btn small primary" data-act="soArrive" data-id="${o.id}" data-max="${o.qty_ordered - o.qty_arrived}" data-req="${r.id}">Mark received</button>` : ''}
          ${o.qty_arrived > o.qty_accepted + o.qty_rejected ? `<button class="btn small primary" data-act="soInspect" data-id="${o.id}" data-max="${o.qty_arrived - o.qty_accepted - o.qty_rejected}" data-req="${r.id}" data-tracking="${esc(r.reserved_tags.length || r.catalog_id ? 'check' : '')}">Inspect</button>` : ''}
          <button class="btn small" data-act="soUpdate" data-id="${o.id}" data-req="${r.id}">Update date or status</button></div>` : ''}</div>`).join('')}</div>` : ''}
    ${r.dispatches.length ? `<h3 class="sec">Dispatches</h3><div class="list">${r.dispatches.map((d) => `<div class="item"><div class="item-head"><span class="grow"><b>${d.qty}</b> to ${esc(d.destination)}
        <div class="meta">${fmtDate(d.dispatched_at)} ${fmtTime(d.dispatched_at)} by ${esc(d.dispatched_by)}, carried by ${esc(d.handled_by)}${d.asset_tags ? ' · ' + esc(d.asset_tags) : ''}
        ${d.delivered_at ? `<br>${d.qty_delivered} received by ${esc(d.received_by)} at ${fmtTime(d.delivered_at)} (confirmed by ${esc(d.confirmed_by)})` : ''}</div></span>
        <span class="pill ${d.status === 'delivered' ? 'good' : d.status === 'short' ? 'warn' : 'info'}">${esc(human(d.status))}</span>
        ${d.can_confirm ? `<button class="btn small primary" data-act="eqConfirm" data-id="${d.id}" data-qty="${d.qty}" data-req="${r.id}">Confirm delivery</button>` : ''}</div></div>`).join('')}</div>` : ''}
    ${r.tickets.length ? `<h3 class="sec">Service</h3>${ticketList(r.tickets, true)}` : ''}
    <h3 class="sec">History</h3><div class="timeline">${r.history.map((h) => `<div class="item"><div class="item-head"><span class="grow"><b>${esc(h.action[0].toUpperCase() + h.action.slice(1))}</b>${h.qty != null ? ` · ${h.qty}` : ''}
      <div class="meta">${esc(h.who)} · ${fmtShort(h.at.slice(0, 10))} ${fmtTime(h.at)}${h.to && h.from !== h.to ? ` · ${esc(human(h.from) || 'new')} → ${esc(human(h.to))}` : ''}</div></span></div>${h.note ? `<div class="meta">${esc(h.note)}</div>` : ''}</div>`).join('')}</div>`, true);
}

function formModal(title, sub, form, fields, submit, cls = 'primary') {
  openModal(`<h2>${esc(title)}</h2><p class="sub">${sub}</p><form class="form" data-form="${form.name}" ${Object.entries(form).filter(([k]) => k !== 'name').map(([k, v]) => `data-${k}="${esc(v)}"`).join(' ')}>
    ${fields}<div class="modal-actions"><button type="button" class="btn" data-act="${form.back ? 'eqOpen' : 'close'}" data-id="${esc(form.back || '')}">Back</button><button class="btn ${cls}" type="submit">${esc(submit)}</button></div></form>`);
}

Object.assign(ACT, {
  eqOpen(d) { return openRequest(d.id); },
  async eqTab(d) { S.eqTab = d.tab; await refreshLive('eqDoctor'); },
  async storeTab(d) { S.storeTab = d.tab; await refreshLive('stores'); },
  adminStores(d) { S.adminStores = d.on === '1'; paint(); },
  async eqSort(d) {
    S.eq.dir = S.eq.sort === d.key && S.eq.dir === 'desc' ? 'asc' : 'desc';
    S.eq.sort = d.key;
    S.eq.page = 1;
    await refreshEq();
  },
  async eqPage(d) { S.eq.page = Math.max(1, S.eq.page + Number(d.step)); await refreshEq(); },
  async eqPreset(d) {
    Object.assign(S.eq, { status: d.status || '', page: 1 });
    if (S.user.role === 'coordinator' || S.adminStores) S.storeTab = 'requests';
    await refreshEq();
    const table = $('.eq-table');
    if (table) table.scrollIntoView({ behavior: 'smooth', block: 'center' });
  },
  async eqNew() {
    const cat = await catalog();
    const mine = cat.sections.filter((s) => s.for_me && !s.shared);
    const shared = cat.sections.filter((s) => s.shared);
    const other = cat.sections.filter((s) => !s.for_me);
    const group = (label, rows) => (rows.length ? `<optgroup label="${esc(label)}">${rows.map((s) => `<option>${esc(s.section)}</option>`).join('')}</optgroup>` : '');
    openModal(`<h2>New equipment or supplies request</h2><p class="sub">For ${esc(S.user.department)}. It goes to the dean for approval, then to the equipment coordinator.</p>
      <form class="form" data-form="eqNew"><input type="hidden" name="idem_key" value="${uid()}">
        <label class="field">Catalogue department<select name="section">${group(`For ${S.user.department}`, mine)}${group('Hospital-wide services', shared)}${group('Other departments', other)}
          <option value="__other">Not in the catalogue</option></select></label>
        <div class="two"><label class="field">Category<select name="category"></select></label><label class="field">Item<select name="catalog_id"></select></label></div>
        <div data-other hidden class="two"><label class="field">Item name<input name="item_name" maxlength="120"></label><label class="field">Category<input name="other_category" maxlength="60" placeholder="e.g. Diagnostic"></label></div>
        <div class="three"><label class="field">Request type<select name="request_type">${cat.request_types.map((t) => `<option value="${t.id}">${esc(t.label)}</option>`).join('')}</select></label>
          <label class="field">Quantity<input name="quantity" type="number" min="1" max="10000" value="1" required></label>
          <label class="field">Urgency<select name="urgency"><option value="routine">Routine</option><option value="urgent">Urgent</option><option value="critical">Critical</option></select></label></div>
        <label class="field">Location<input name="location" maxlength="80" value="${esc(S.user.department)} ward"></label>
        <label class="field">Justification<textarea name="justification" required minlength="5" maxlength="2000" placeholder="Why it is needed, for how many patients, what happens without it"></textarea></label>
        <label class="field">Supporting document (optional, up to 3 MB)<input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx,.txt,.csv"></label>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn primary" type="submit">Send to the dean</button></div></form>`, true);
    fillCatalog($('form[data-form=eqNew]'));
  },
  eqDecide(d) {
    return api('/equipment/requests/' + d.id).then((r) => formModal('Approve request', `${esc(r.ref)} · ${r.quantity} × ${esc(r.item_name)} for ${esc(r.department)}`, { name: 'eqDecide', id: r.id, action: 'approve', back: r.id },
      `<label class="field">Approved quantity<input name="qty_approved" type="number" min="1" max="10000" value="${r.quantity}" required></label>
       <label class="field">Note (needed if you approve more than requested)<textarea name="note" maxlength="400"></textarea></label>
       <p class="hint">Approving forwards the request to the equipment coordinator for stock, sourcing and dispatch.</p>`, 'Approve and forward'));
  },
  eqReject(d) {
    formModal('Reject request', 'The doctor sees your reason.', { name: 'eqDecide', id: d.id, action: 'reject', back: d.id },
      '<label class="field">Reason<textarea name="note" required minlength="3" maxlength="400"></textarea></label>', 'Reject', 'danger');
  },
  eqClarifyDean(d) {
    formModal('Request clarification', 'The request goes back to the doctor until they answer.', { name: 'eqDecide', id: d.id, action: 'clarify', back: d.id },
      '<label class="field">Question for the doctor<textarea name="note" required minlength="3" maxlength="400"></textarea></label>', 'Send question');
  },
  async eqRespond(d) {
    const r = await api('/equipment/requests/' + d.id);
    const q = [...r.history].reverse().find((h) => h.action === 'clarification requested');
    formModal('Answer the question', q ? `${esc(q.who)}: ${esc(q.note)}` : '', { name: 'eqRespond', id: r.id, back: r.id },
      `<label class="field">Your answer<textarea name="note" required minlength="2" maxlength="400"></textarea></label>
       ${r.dean_status === 'clarification' ? `<label class="field">Quantity<input name="quantity" type="number" min="1" max="10000" value="${r.quantity}"></label>` : ''}`, 'Send answer');
  },
  eqAsk(d) {
    formModal('Ask the doctor', 'For example, which model or what can be used meanwhile.', { name: 'eqAsk', id: d.id, back: d.id },
      '<label class="field">Question<textarea name="note" required minlength="2" maxlength="400"></textarea></label>', 'Send question');
  },
  async eqStock(d) {
    const out = await api(`/equipment/requests/${d.id}/check-stock`, 'POST');
    const r = out.request;
    openModal(`<h2>Stock for ${esc(r.item_name)}</h2><p class="sub">${out.needed} still needed for ${esc(r.ref)} · ${out.available} available in stores${out.available < out.needed ? ` · <b class="bad-text">short by ${out.needed - out.available}</b>` : ''}</p>
      ${out.items.length ? `<div class="list">${out.items.map((i) => `<div class="item"><div class="item-head"><span class="grow"><b>${esc(i.name)}</b> <span class="mono faint">${esc(i.code)}</span>
          <div class="meta">${i.available} available · ${i.reserved} reserved · ${i.in_service} in service · ${i.maintenance} in maintenance · ${esc(i.location)}</div></span>
          ${i.condition === 'unsafe' ? '<span class="pill bad">Unsafe</span>' : ''}
          ${i.available && out.needed && i.condition !== 'unsafe' ? `<button class="btn small primary" data-act="eqReserve" data-id="${r.id}" data-inv="${i.id}" data-qty="${Math.min(i.available, out.needed)}" data-tracking="${i.tracking}">Reserve ${Math.min(i.available, out.needed)}</button>` : ''}</div></div>`).join('')}</div>`
        : '<div class="empty">This item is not stocked yet</div>'}
      <div class="modal-actions" style="margin-top:14px"><button class="btn" data-act="eqOpen" data-id="${r.id}">Back to request</button>
        ${out.available < out.needed ? `<button class="btn primary" data-act="eqSource" data-id="${r.id}" data-qty="${out.needed - out.available}">Source ${out.needed - out.available} externally</button>` : ''}</div>`, true);
    refreshEq();
  },
  async eqReserve(d) {
    let inv = d.inv;
    let qty = d.qty;
    if (!inv) {
      const out = await api(`/equipment/requests/${d.id}/check-stock`, 'POST');
      const best = out.items.find((i) => i.available && i.condition !== 'unsafe');
      if (!best) throw new Error('Nothing available in stores. Source it externally.');
      inv = best.id;
      qty = Math.min(best.available, out.needed);
    }
    formModal('Reserve stock', 'Reserved units are held for this request and are no longer offered to anyone else.', { name: 'eqReserve', id: d.id, inv, back: d.id },
      `<label class="field">Quantity to reserve<input name="qty" type="number" min="1" value="${esc(qty)}" required></label>
       <label class="field">Specific asset tags (optional, comma separated)<input name="asset_tags" placeholder="Leave empty to take the first available units"></label>`, 'Reserve');
  },
  async eqSource(d) {
    const [r, sup] = await Promise.all([api('/equipment/requests/' + d.id), api('/equipment/suppliers')]);
    const need = d.qty || Math.max(1, r.qty_approved - r.qty_reserved - r.qty_dispatched - r.sourcing.filter((o) => ['ordered', 'delayed', 'arrived'].includes(o.status)).reduce((n, o) => n + o.qty_ordered - o.qty_accepted - o.qty_rejected, 0));
    formModal('Source externally', `${esc(r.ref)} · ${esc(r.item_name)}`, { name: 'eqSource', id: r.id, back: r.id },
      `<label class="field">Supplier or service provider<input name="supplier_name" list="sup-list" required placeholder="Choose or type a new one"><datalist id="sup-list">${sup.map((s) => `<option>${esc(s.name)}</option>`).join('')}</datalist></label>
       <div class="three"><label class="field">Quantity<input name="qty" type="number" min="1" value="${need}" required></label>
         <label class="field">PO / reference<input name="reference" maxlength="60"></label>
         <label class="field">Expected arrival<input name="expected_date" type="date"></label></div>`, 'Record order');
  },
  soArrive(d) {
    formModal('Mark received', 'Items that arrive are held for inspection before they enter stock.', { name: 'soArrive', id: d.id, back: d.req },
      `<label class="field">Quantity that arrived<input name="qty" type="number" min="1" max="${esc(d.max)}" value="${esc(d.max)}" required></label>
       <label class="field">Note<input name="note" maxlength="400" placeholder="Delivery note, condition of packaging"></label>`, 'Record arrival');
  },
  soInspect(d) {
    formModal('Inspect delivery', 'Accepted units go into stock and are reserved for this request. Rejected units are not stocked and are sourced again.', { name: 'soInspect', id: d.id, back: d.req },
      `<div class="two"><label class="field">Accepted<input name="accepted" type="number" min="0" max="${esc(d.max)}" value="${esc(d.max)}" required></label>
        <label class="field">Rejected<input name="rejected" type="number" min="0" max="${esc(d.max)}" value="0" required></label></div>
       <label class="field">Asset tags for accepted tagged equipment (one per unit, comma separated)<input name="asset_tags" placeholder="e.g. CS-MON-031, CS-MON-032"></label>
       <label class="field">Inspection findings<textarea name="note" required minlength="2" maxlength="400"></textarea></label>`, 'Save inspection');
  },
  soUpdate(d) {
    formModal('Update sourcing order', 'Doctors and the dean are told about delays.', { name: 'soUpdate', id: d.id, back: d.req },
      `<div class="two"><label class="field">New expected date<input name="expected_date" type="date"></label>
        <label class="field">Status<select name="status"><option value="">Unchanged</option><option value="delayed">Delayed</option><option value="ordered">On track</option><option value="cancelled">Cancel this order</option></select></label></div>
       <label class="field">Note (needed to cancel)<input name="note" maxlength="400"></label>`, 'Save');
  },
  async eqDispatch(d) {
    const r = await api('/equipment/requests/' + d.id);
    formModal('Dispatch to department', `${esc(r.ref)} · ${r.qty_reserved} reserved for ${esc(r.department)}${r.reserved_tags.length ? ' · ' + esc(r.reserved_tags.join(', ')) : ''}`, { name: 'eqDispatch', id: r.id, back: r.id, key: uid() },
      `<div class="two"><label class="field">Quantity<input name="qty" type="number" min="1" max="${r.qty_reserved}" value="${r.qty_reserved}" required></label>
        <label class="field">Destination<input name="destination" maxlength="120" value="${esc(r.location || r.department)}" required></label></div>
       <label class="field">Carried by (responsible staff)<input name="handled_by" maxlength="120" required minlength="2" value="${esc(S.user.name)}"></label>`, 'Dispatch');
  },
  eqConfirm(d) {
    formModal('Confirm receipt', 'Count what actually arrived. Anything missing is reported to stores.', { name: 'eqConfirm', id: d.id, back: d.req || '' },
      `<div class="two"><label class="field">Quantity received<input name="qty_delivered" type="number" min="1" max="${esc(d.qty)}" value="${esc(d.qty)}" required></label>
        <label class="field">Received by<input name="received_by" maxlength="120" value="${esc(S.user.name)}" required></label></div>
       <label class="field">Note<input name="note" maxlength="400"></label>`, 'Confirm');
  },
  eqRelease(d) {
    formModal('Release reservation', 'Released units go back to available stock.', { name: 'eqRelease', id: d.id, back: d.id },
      `<label class="field">Quantity<input name="qty" type="number" min="1" value="1" required></label><label class="field">Reason<input name="reason" required minlength="3" maxlength="400"></label>`, 'Release');
  },
  eqReturn(d) {
    formModal('Record a return', 'Returned units go back to stores. Damaged ones are kept out of use.', { name: 'eqReturn', id: d.id, back: d.id },
      `<div class="two"><label class="field">Quantity<input name="qty" type="number" min="1" value="1" required></label>
        <label class="field">Condition<select name="condition"><option value="good">Good</option><option value="damaged">Damaged</option></select></label></div>
       <label class="field">Reason<input name="reason" required minlength="3" maxlength="400"></label>`, 'Record return');
  },
  eqBackorder(d) {
    formModal('Mark as backordered', 'The doctor and dean are told.', { name: 'eqBackorder', id: d.id, back: d.id },
      '<label class="field">Reason<input name="reason" required minlength="3" maxlength="400"></label><label class="field">Expected date<input name="expected_date" type="date"></label>', 'Save');
  },
  eqCancel(d) {
    formModal('Cancel this request?', 'Reserved stock is released and open supplier orders are cancelled. This cannot be undone.', { name: 'eqCancel', id: d.id, back: d.id },
      '<label class="field">Reason<input name="reason" required minlength="3" maxlength="400"></label>', 'Cancel request', 'danger');
  },
  async eqService(d) {
    const sup = (await api('/equipment/suppliers')).filter((s) => s.kind === 'service');
    formModal('Schedule service', 'Opens a maintenance ticket linked to this request.', { name: 'eqService', id: d.id, back: d.id },
      `<div class="two"><label class="field">Technician<input name="technician" maxlength="120"></label>
        <label class="field">Service provider<input name="provider_name" list="svc-list" maxlength="120"><datalist id="svc-list">${sup.map((s) => `<option>${esc(s.name)}</option>`).join('')}</datalist></label></div>
       <label class="field">Date<input name="scheduled_for" type="date"></label>`, 'Schedule');
  },
  async eqAttachment(d) {
    const res = await fetch(`/api/equipment/requests/${d.id}/attachment`, { headers: { Authorization: `Bearer ${S.token}` } });
    if (!res.ok) throw new Error('Attachment not found');
    const link = document.createElement('a');
    link.href = URL.createObjectURL(await res.blob());
    link.download = d.name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 2000);
  },
  async eqFault() {
    let items = [];
    if (isOps()) items = await api('/equipment/inventory');
    openModal(`<h2>Report faulty or unsafe equipment</h2><p class="sub">Unsafe equipment is taken out of use straight away and only returns after a verified repair.</p>
      <form class="form" data-form="eqFault"><input type="hidden" name="idem_key" value="${uid()}">
        <div class="two"><label class="field">Asset tag (if it has one)<input name="asset_tag" maxlength="40" placeholder="e.g. CS-INF-004"></label>
          ${items.length ? `<label class="field">Or stock item<select name="inventory_id"><option value="">Choose</option>${items.map((i) => `<option value="${i.id}">${esc(i.name)} · ${esc(i.code)}</option>`).join('')}</select></label>`
          : '<label class="field">Equipment name<input name="item_name" maxlength="120" placeholder="If there is no tag"></label>'}</div>
        <div class="two"><label class="field">Type<select name="kind"><option value="repair">Repair</option><option value="servicing">Servicing</option><option value="calibration">Calibration</option><option value="inspection">Inspection</option></select></label>
          <label class="field">Quantity<input name="qty" type="number" min="1" max="1000" value="1"></label></div>
        <label class="field">What is wrong<textarea name="issue" required minlength="5" maxlength="600"></textarea></label>
        <label class="check-line"><input type="checkbox" name="unsafe" value="1"> It is unsafe for clinical use</label>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn primary" type="submit">Report</button></div></form>`);
  },
  async mtManage(d) {
    const sup = await api('/equipment/suppliers');
    openModal(`<h2>Manage repair</h2><p class="sub">Each step is recorded. Equipment goes back into use only after verification.</p>
      <form class="form" data-form="mtUpdate" data-id="${esc(d.id)}">
        <label class="field">Step<select name="action"><option value="assign">Assign technician or provider</option><option value="schedule">Schedule</option><option value="start">Start work (mark unavailable)</option>
          <option value="findings">Record findings, parts and cost</option><option value="complete">Repair finished, needs verification</option><option value="verify">Verified, restore to service</option><option value="cancel">Cancel ticket</option></select></label>
        <div class="two"><label class="field">Technician<input name="technician" maxlength="120"></label>
          <label class="field">Service provider<input name="provider_name" list="mt-sup" maxlength="120"><datalist id="mt-sup">${sup.map((s) => `<option>${esc(s.name)}</option>`).join('')}</datalist></label></div>
        <div class="two"><label class="field">Date<input name="scheduled_for" type="date"></label><label class="field">Cost<input name="cost" type="number" min="0" step="0.01"></label></div>
        <label class="field">Inspection findings<textarea name="findings" maxlength="600"></textarea></label>
        <label class="field">Parts used<input name="parts_used" maxlength="300"></label>
        <label class="field">Note (for verification: what was checked)<input name="note" maxlength="400"></label>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn primary" type="submit">Save step</button></div></form>`);
  },
  async invOpen(d) {
    const i = await api('/equipment/inventory/' + d.id);
    openModal(`<div class="spread"><div><h2>${esc(i.name)} <span class="mono faint">${esc(i.code)}</span></h2><p class="sub" style="margin-bottom:10px">${esc(i.category)} · ${esc(i.model || 'model not set')} · ${esc(i.location)}</p></div>
      <button class="icon-btn" data-act="close" aria-label="Close">${ic('x')}</button></div>
      <div class="qty-grid">${[['Total', i.total], ['Available', i.available], ['Reserved', i.reserved], ['In service', i.in_service], ['Maintenance', i.maintenance], ['Damaged', i.damaged], ['Minimum', i.min_stock]].map(([k, v]) => `<div><span>${k}</span><b>${v}</b></div>`).join('')}</div>
      <dl class="kv" style="margin:14px 0"><dt>Supplier</dt><dd>${esc(i.supplier || '–')}</dd><dt>Warranty</dt><dd>${esc(i.warranty || '–')}</dd>
        <dt>Last service</dt><dd>${esc(i.last_maintenance || '–')}</dd><dt>Next service</dt><dd>${esc(i.next_maintenance || '–')}</dd><dt>Condition</dt><dd>${esc(i.condition)}</dd></dl>
      ${isOps() ? `<form class="form" data-form="invAdjust" data-id="${i.id}"><div class="three"><label class="field">Stock change<select name="kind"><option value="receive">Receive new stock</option><option value="damage">Mark damaged</option><option value="repair">Send damaged for repair</option><option value="write_off">Write off damaged</option></select></label>
          <label class="field">Quantity<input name="qty" type="number" min="1" value="1" required></label><label class="field">Reason<input name="note" required minlength="3" maxlength="300"></label></div>
          ${i.tracking === 'asset' ? '<label class="field">Asset tags (needed when receiving tagged equipment)<input name="asset_tags" placeholder="CS-XXX-001, CS-XXX-002"></label>' : ''}
          <div class="row"><button class="btn small primary" type="submit">Record stock change</button></div></form>
        <form class="form" data-form="invEdit" data-id="${i.id}" style="margin-top:14px"><div class="three"><label class="field">Minimum stock<input name="min_stock" type="number" min="0" value="${i.min_stock}"></label>
          <label class="field">Location<input name="location" maxlength="80" value="${esc(i.location)}"></label><label class="field">Next service<input name="next_maintenance" type="date" value="${esc(i.next_maintenance)}"></label></div>
          <div class="row"><button class="btn small" type="submit">Save details</button></div></form>` : ''}
      ${i.assets.length ? `<h3 class="sec">Tagged assets</h3><div class="scroll-x"><table><thead><tr><th>Asset tag</th><th>Serial</th><th>State</th><th>Department</th><th>Condition</th><th>Warranty until</th></tr></thead>
        <tbody>${i.assets.map((a) => `<tr><td class="mono">${esc(a.asset_tag)}</td><td class="mono hint">${esc(a.serial)}</td><td>${esc(human(a.state))}${a.request ? ' <span class="hint">(request)</span>' : ''}</td><td>${esc(a.department || '–')}</td>
          <td>${a.condition === 'unsafe' ? '<span class="pill bad">Unsafe</span>' : esc(a.condition)}</td><td class="hint">${esc(a.warranty_until || '–')}</td></tr>`).join('')}</tbody></table></div>` : ''}
      <h3 class="sec">Recent movements</h3><div class="scroll-x"><table><thead><tr><th>When</th><th>Movement</th><th class="num">Qty</th><th>From → to</th><th>By</th><th>Note</th></tr></thead>
        <tbody>${i.transactions.map((t) => `<tr><td class="hint" style="white-space:nowrap">${fmtShort(t.at.slice(0, 10))} ${fmtTime(t.at)}</td><td>${esc(human(t.kind))}</td><td class="num">${t.qty}</td><td class="hint">${esc(human(t.from))} → ${esc(human(t.to))}</td><td>${esc(t.who)}</td><td class="hint">${esc(t.note)}</td></tr>`).join('')}</tbody></table></div>`, true);
  },
  async invNew() {
    const cat = await catalog();
    const opts = cat.sections.map((s) => `<optgroup label="${esc(s.section)}">${s.categories.flatMap((c) => c.items.map((i) => `<option value="${i.id}" data-name="${esc(i.name)}" data-cat="${esc(c.category)}" data-tracking="${i.tracking}">${esc(i.name)}</option>`)).join('')}</optgroup>`).join('');
    openModal(`<h2>Add an inventory item</h2><p class="sub">Tagged equipment is tracked unit by unit; consumables by quantity.</p>
      <form class="form" data-form="invNew"><label class="field">Catalogue item<select name="catalog_id">${opts}</select></label>
        <div class="three"><label class="field">Model<input name="model" maxlength="80"></label><label class="field">Opening quantity<input name="initial_qty" type="number" min="0" value="0"></label>
          <label class="field">Minimum stock<input name="min_stock" type="number" min="0" value="0"></label></div>
        <div class="two"><label class="field">Location<input name="location" maxlength="80" value="Central stores"></label><label class="field">Next service<input name="next_maintenance" type="date"></label></div>
        <label class="field">Asset tags for tagged equipment (one per unit, comma separated)<input name="asset_tags"></label>
        <div class="modal-actions"><button type="button" class="btn" data-act="close">Cancel</button><button class="btn primary" type="submit">Add item</button></div></form>`, true);
  },
});

function fillCatalog(form, which) {
  const cat = S.catalog;
  const sectionName = form.section.value;
  const other = sectionName === '__other';
  $('[data-other]', form).hidden = !other;
  form.category.closest('.two').hidden = other;
  if (other) return;
  const section = cat.sections.find((s) => s.section === sectionName);
  if (which !== 'category') form.category.innerHTML = section.categories.map((c) => `<option>${esc(c.category)}</option>`).join('');
  const category = section.categories.find((c) => c.category === form.category.value) || section.categories[0];
  form.catalog_id.innerHTML = category.items.map((i) => `<option value="${i.id}">${esc(i.name)}${i.tracking === 'quantity' ? ' (consumable)' : ''}</option>`).join('');
}
document.addEventListener('change', (e) => {
  const form = e.target.closest('form[data-form=eqNew]');
  if (form && e.target.name === 'section') fillCatalog(form);
  if (form && e.target.name === 'category') fillCatalog(form, 'category');
  const f = e.target.dataset && e.target.dataset.f;
  if (f && f !== 'q') {
    S.eq[f] = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
    S.eq.page = 1;
    refreshEq();
  }
});
let eqTyping;
document.addEventListener('input', (e) => {
  if (e.target.dataset && e.target.dataset.f === 'q') {
    clearTimeout(eqTyping);
    eqTyping = setTimeout(() => { S.eq.q = e.target.value; S.eq.page = 1; refreshEq().then(() => { const el = $('[data-f=q]'); if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } }); }, 300);
  }
  if (e.target.matches && e.target.matches('[data-inv-q]')) {
    clearTimeout(eqTyping);
    eqTyping = setTimeout(() => { S.invQ = e.target.value; refreshLive('stores').then(() => { const el = $('[data-inv-q]'); if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); } }); }, 300);
  }
});
/* Live regions skip refreshing while someone types in them; filters are part of the table, so allow it there. */

const tagsOf = (s) => String(s || '').split(',').map((t) => t.trim()).filter(Boolean);
async function eqAfter(message, requestId) {
  toast(message);
  await refreshEq();
  if (requestId) await openRequest(requestId); else closeModal();
}
function readFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('The file could not be read'));
    reader.readAsDataURL(file);
  });
}

Object.assign(FORMS, {
  async eqNew(data, form) {
    const body = { idem_key: data.idem_key, request_type: data.request_type, quantity: Number(data.quantity), urgency: data.urgency,
      justification: data.justification, location: data.location };
    if (data.section === '__other') Object.assign(body, { item_name: data.item_name, category: data.other_category });
    else body.catalog_id = Number(data.catalog_id);
    const file = form.file.files[0];
    if (file) {
      if (file.size > 3 * 1024 * 1024) throw new Error('Attachments can be up to 3 MB');
      body.attachment = { name: file.name, data: await readFile(file) };
    }
    const out = await api('/equipment/requests', 'POST', body);
    closeModal();
    toast(`${out.request.ref} sent to the dean${out.duplicate ? ' (already sent)' : ''}`);
    S.eqTab = 'mine';
    await refreshEq();
  },
  async eqDecide(data, form) {
    const body = { action: form.dataset.action, note: data.note || '' };
    if (data.qty_approved) body.qty_approved = Number(data.qty_approved);
    const r = await api(`/equipment/requests/${form.dataset.id}/decide`, 'POST', body);
    await eqAfter(`${r.ref}: ${r.status_label}`, r.id);
  },
  async eqRespond(data, form) {
    const r = await api(`/equipment/requests/${form.dataset.id}/respond`, 'POST', { note: data.note, quantity: data.quantity ? Number(data.quantity) : null });
    await eqAfter('Answer sent', r.id);
  },
  async eqAsk(data, form) {
    const r = await api(`/equipment/requests/${form.dataset.id}/clarify`, 'POST', { note: data.note });
    await eqAfter('Question sent to the doctor', r.id);
  },
  async eqReserve(data, form) {
    const r = await api(`/equipment/requests/${form.dataset.id}/reserve`, 'POST', { inventory_id: Number(form.dataset.inv), qty: Number(data.qty), asset_tags: tagsOf(data.asset_tags) });
    await eqAfter(`${data.qty} reserved for ${r.ref}`, r.id);
  },
  async eqSource(data, form) {
    const r = await api(`/equipment/requests/${form.dataset.id}/source`, 'POST', { ...data, qty: Number(data.qty) });
    await eqAfter(`Order recorded with ${data.supplier_name}`, r.id);
  },
  async soArrive(data, form) {
    const r = await api(`/equipment/sourcing/${form.dataset.id}/arrive`, 'POST', { qty: Number(data.qty), note: data.note });
    await eqAfter('Arrival recorded. Inspect it next.', r.id);
  },
  async soInspect(data, form) {
    const r = await api(`/equipment/sourcing/${form.dataset.id}/inspect`, 'POST', { accepted: Number(data.accepted), rejected: Number(data.rejected), note: data.note, asset_tags: tagsOf(data.asset_tags) });
    await eqAfter('Inspection saved', r.id);
  },
  async soUpdate(data, form) {
    const r = await api(`/equipment/sourcing/${form.dataset.id}/update`, 'POST', data);
    await eqAfter('Order updated', r.id);
  },
  async eqDispatch(data, form) {
    const out = await api(`/equipment/requests/${form.dataset.id}/dispatch`, 'POST', { idem_key: form.dataset.key, qty: Number(data.qty), destination: data.destination, handled_by: data.handled_by });
    await eqAfter(out.duplicate ? 'Already dispatched' : `${data.qty} dispatched to ${data.destination}`, Number(form.dataset.id));
  },
  async eqConfirm(data, form) {
    const r = await api(`/equipment/dispatches/${form.dataset.id}/confirm`, 'POST', { ...data, qty_delivered: Number(data.qty_delivered) });
    await eqAfter(`Receipt confirmed: ${r.status_label}`, form.dataset.back ? r.id : null);
  },
  async eqRelease(data, form) {
    const r = await api(`/equipment/requests/${form.dataset.id}/release`, 'POST', { qty: Number(data.qty), reason: data.reason });
    await eqAfter('Reservation released', r.id);
  },
  async eqReturn(data, form) {
    const r = await api(`/equipment/requests/${form.dataset.id}/return`, 'POST', { ...data, qty: Number(data.qty) });
    await eqAfter('Return recorded', r.id);
  },
  async eqBackorder(data, form) {
    const r = await api(`/equipment/requests/${form.dataset.id}/backorder`, 'POST', data);
    await eqAfter('Marked as backordered', r.id);
  },
  async eqCancel(data, form) {
    const r = await api(`/equipment/requests/${form.dataset.id}/cancel`, 'POST', data);
    await eqAfter(`${r.ref} cancelled`, r.id);
  },
  async eqService(data, form) {
    const r = await api(`/equipment/requests/${form.dataset.id}/schedule-service`, 'POST', { action: 'schedule', ...data });
    await eqAfter('Service scheduled', r.id);
  },
  async eqFault(data) {
    const t = await api('/equipment/maintenance', 'POST', { idem_key: data.idem_key, asset_tag: data.asset_tag || '', item_name: data.item_name || '',
      inventory_id: data.inventory_id ? Number(data.inventory_id) : null, qty: Number(data.qty || 1), issue: data.issue, unsafe: data.unsafe === '1', kind: data.kind });
    closeModal();
    toast(`${t.ref} reported${t.unsafe ? '. It is marked unsafe and out of use.' : ''}`);
    await refreshEq();
  },
  async mtUpdate(data, form) {
    const body = { ...data, cost: data.cost === '' ? null : Number(data.cost) };
    const t = await api(`/equipment/maintenance/${form.dataset.id}/update`, 'POST', body);
    closeModal();
    toast(`${t.ref}: ${t.status_label}`);
    await refreshEq();
  },
  async invAdjust(data, form) {
    await api(`/equipment/inventory/${form.dataset.id}/adjust`, 'POST', { kind: data.kind, qty: Number(data.qty), note: data.note, asset_tags: tagsOf(data.asset_tags) });
    toast('Stock updated');
    await refreshEq();
    await ACT.invOpen({ id: form.dataset.id });
  },
  async invEdit(data, form) {
    await api(`/equipment/inventory/${form.dataset.id}`, 'POST', { min_stock: Number(data.min_stock), location: data.location, next_maintenance: data.next_maintenance });
    toast('Details saved');
    await refreshEq();
  },
  async invNew(data, form) {
    const opt = form.catalog_id.selectedOptions[0];
    const i = await api('/equipment/inventory', 'POST', { catalog_id: Number(data.catalog_id), name: opt.dataset.name, category: opt.dataset.cat, tracking: opt.dataset.tracking,
      model: data.model, initial_qty: Number(data.initial_qty), min_stock: Number(data.min_stock), location: data.location, next_maintenance: data.next_maintenance,
      asset_tags: tagsOf(data.asset_tags), unit: opt.dataset.tracking === 'asset' ? 'unit' : 'pack' });
    closeModal();
    toast(`${i.code} added`);
    await refreshEq();
  },
  async supplier(data, form) {
    await api('/equipment/suppliers', 'POST', data);
    form.reset();
    toast('Supplier added');
    await refreshLive('stores');
  },
});

/* ---------- start ---------- */
applyTheme(DEFAULT_THEME);

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
  applyTheme(savedTheme());
  renderShell();
  paint();
  refreshNotifs().catch(() => {});
  refreshEmergency().catch(() => {});
  clearInterval(S.timer);
  S.timer = setInterval(tick, 6000);
  startStream();
}
boot();
