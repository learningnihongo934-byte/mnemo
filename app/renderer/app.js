/* Mnemo UI: sidebar (chats) · main (chat / learn / memory / settings) · browser */
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const api = (m, r, b) => window.mnemo.api(m, r, b);
let ws, status = {}, settings = {}, ui = {}, cfgG = { port: 0, token: '' };

// ------------------------------------------------------------- icons (inline SVG, stroke style)
const P = {
  plus: '<path d="M12 5v14M5 12h14"/>',
  sidebar: '<rect x="3" y="4" width="18" height="16" rx="3"/><path d="M9 4v16"/>',
  spark: '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/><circle cx="12" cy="12" r="3"/>',
  db: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  up: '<path d="M12 19V5M6 11l6-6 6 6"/>',
  stop: '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor"/>',
  left: '<path d="M15 6l-6 6 6 6"/>', right: '<path d="M9 6l6 6-6 6"/>',
  reload: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>', x: '<path d="M6 6l12 12M18 6L6 18"/>',
  trash: '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/>',
  retry: '<path d="M4 12a8 8 0 0 1 14-5.3M20 4v5h-5M20 12a8 8 0 0 1-14 5.3M4 20v-5h5"/>',
  down: '<path d="M12 4v12M6 11l6 6 6-6M5 20h14"/>',
  image: '<rect x="3" y="4" width="18" height="16" rx="3"/><circle cx="9" cy="10" r="2"/><path d="M21 16l-5-5-9 9"/>',
  code: '<path d="M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16"/>',
  undo: '<path d="M9 14L4 9l5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/>',
  chevron: '<path d="M6 9l6 6 6-6"/>', tool: '<path d="M14.7 6.3a4 4 0 0 0-5.4 5.4L3 18l3 3 6.3-6.3a4 4 0 0 0 5.4-5.4l-2.5 2.5-2.4-.6-.6-2.4z"/>',
};
const icon = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${P[n] || ''}</svg>`;
function paintIcons(root = document) { root.querySelectorAll('i[data-i]').forEach((el) => { el.innerHTML = icon(el.dataset.i); }); }

// ------------------------------------------------------------- helpers
const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
function md(s) {
  let h = esc(s);
  h = h.replace(/```\n?([\s\S]*?)```/g, (_, c) => `<pre>${c}</pre>`);
  h = h.replace(/`([^`]+)`/g, '<code>$1</code>');
  h = h.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/(^|\s)\*(.+?)\*/g, '$1<i>$2</i>');
  h = h.replace(/(^|\n)&gt; (.*)/g, '$1<blockquote>$2</blockquote>');
  // [[audio:file.wav]] from plugins such as rat.audio's /speak: play a Studio creation inline.
  h = h.replace(/\[\[audio:([\w.-]+)\]\]/g, (_, f) =>
    `<audio class="chat-audio" controls preload="metadata" src="http://127.0.0.1:${cfgG.port}/files/creations/${encodeURIComponent(f)}?token=${cfgG.token}"></audio>`);
  return h;
}
const num = (n) => n >= 1e9 ? (n / 1e9).toFixed(2) + 'B' : n >= 1e6 ? (n / 1e6).toFixed(1) + 'M' : n >= 1e3 ? (n / 1e3).toFixed(1) + 'K' : String(n ?? 0);
const gb = (b) => (b / 1e9).toFixed(2) + ' GB';
const name = () => ui.name || 'Mnemo';
function toast(text) {
  const t = $('#toast'); t.textContent = text; t.classList.add('show');
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove('show'), 4200);
}
function notify(text) {
  if (ui.notify && document.visibilityState !== 'visible') { try { new Notification(name(), { body: text }); } catch {} }
}

// ------------------------------------------------------------- appearance + layout
const ACCENTS = ['#7c5cff', '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#ec4899', '#14b8a6'];
const UI_DEFAULTS = { theme: 'dark', accent: '#7c5cff', font: 14, sideW: 260, browserW: 560, threadW: 760, name: 'Mnemo',
  compact: false, browser: true, sidebar: true, notify: true, sounds: true };
function lighten(hex, amt = 0.35) {
  const n = parseInt(hex.slice(1), 16); const c = [n >> 16, (n >> 8) & 255, n & 255].map((v) => Math.round(v + (255 - v) * amt));
  return '#' + c.map((v) => v.toString(16).padStart(2, '0')).join('');
}
function applyUI() {
  const r = document.documentElement;
  const dark = ui.theme === 'dark' || (ui.theme === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
  r.dataset.theme = dark ? 'dark' : 'light';
  r.style.setProperty('--accent', ui.accent); r.style.setProperty('--accent-2', lighten(ui.accent));
  r.style.fontSize = ui.font + 'px';
  r.style.setProperty('--side-w', ui.sideW + 'px');
  r.style.setProperty('--browser-w', ui.browserW + 'px');
  r.style.setProperty('--thread-w', ui.threadW + 'px');
  document.body.classList.toggle('compact', !!ui.compact);
  $('#app').classList.toggle('no-browser', !ui.browser);
  $('#app').classList.toggle('no-side', !ui.sidebar);
  $('#expand').classList.toggle('hidden', !!ui.sidebar);
  $('#toggle-browser').classList.toggle('on', !!ui.browser);
  $('#brand-name').textContent = name();
  $('#input').placeholder = `Message ${name()}, or type / for commands`;
  $$('#theme-seg button').forEach((b) => b.classList.toggle('active', b.dataset.v === ui.theme));
  $('#swatches').innerHTML = ACCENTS.map((c) => `<button style="background:${c}" data-c="${c}" class="${c === ui.accent ? 'active' : ''}"></button>`).join('') +
    `<input type="color" id="ui-accent" value="${ui.accent}" title="Custom color">`;
  $$('#swatches button').forEach((b) => b.onclick = () => setUI({ accent: b.dataset.c }));
  $('#ui-accent').oninput = (e) => setUI({ accent: e.target.value }, false);
  $('#ui-accent').onchange = (e) => setUI({ accent: e.target.value });
  $('#ui-font').value = ui.font; $('#ui-thread').value = ui.threadW; $('#ui-name').value = ui.name;
  $('#ui-compact').checked = !!ui.compact; $('#ui-notify').checked = !!ui.notify; $('#ui-sounds').checked = ui.sounds !== false;
  requestAnimationFrame(sync);
}
let uiSave;
function setUI(patch, save = true) {
  Object.assign(ui, patch); applyUI();
  if (save) { clearTimeout(uiSave); uiSave = setTimeout(() => api('POST', '/api/settings', { ui }), 400); }
}
$$('#theme-seg button').forEach((b) => b.onclick = () => setUI({ theme: b.dataset.v }));
$('#ui-font').oninput = (e) => setUI({ font: Number(e.target.value) });
$('#ui-thread').oninput = (e) => setUI({ threadW: Number(e.target.value) });
$('#ui-name').oninput = (e) => setUI({ name: e.target.value.trim() || 'Mnemo' });
$('#ui-compact').onchange = (e) => setUI({ compact: e.target.checked });
$('#ui-sounds').onchange = (e) => setUI({ sounds: e.target.checked });
$('#ui-notify').onchange = (e) => { setUI({ notify: e.target.checked }); if (e.target.checked) Notification.requestPermission?.(); };
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => ui.theme === 'system' && applyUI());
$('#collapse').onclick = () => setUI({ sidebar: false });
$('#expand').onclick = () => setUI({ sidebar: true });
$('#toggle-browser').onclick = () => setUI({ browser: !ui.browser });

// Drag either divider to resize the sidebar or the browser.
function resizer(el, apply) {
  el.addEventListener('mousedown', (e) => {
    e.preventDefault(); el.classList.add('dragging'); document.body.classList.add('resizing');
    const move = (ev) => apply(ev.clientX);
    const up = () => { el.classList.remove('dragging'); document.body.classList.remove('resizing');
      removeEventListener('mousemove', move); removeEventListener('mouseup', up); setUI({}); };
    addEventListener('mousemove', move); addEventListener('mouseup', up);
  });
  el.addEventListener('dblclick', () => apply(null));
}
resizer($('#div-left'), (x) => setUI({ sideW: x === null ? 260 : Math.max(200, Math.min(420, x)) }, false));
resizer($('#div-right'), (x) => setUI({ browserW: x === null ? 560 : Math.max(320, Math.min(window.innerWidth - (ui.sidebar ? ui.sideW : 0) - 400, window.innerWidth - x)) }, false));

// ------------------------------------------------------------- views
let view = 'chat';
function showView(v) {
  view = v;
  $$('.view').forEach((s) => s.classList.toggle('active', s.id === 'view-' + v));
  $$('.nav[data-view]').forEach((b) => b.classList.toggle('active', b.dataset.view === v));
  $('#title').textContent = v === 'chat' ? (chat.title || 'New chat') : v[0].toUpperCase() + v.slice(1);
  renderRecents();
  if (v === 'learn') drawChart();
  if (v === 'memory') loadRecent();
  if (v === 'settings') loadSettings();
  if (v === 'studio') loadStudio();
  if (v === 'code') loadCode();
  if (v === 'chat') setTimeout(() => $('#input').focus(), 0);
}
$$('.nav[data-view]').forEach((b) => b.onclick = () => showView(b.dataset.view));
$('#brain-card').onclick = () => showView('learn');

// ------------------------------------------------------------- chats
let chat = { id: '', title: '', messages: [] }, chats = [], streaming = null, busy = false, attachments = [], sent = [], sentIdx = -1;
const newId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
const modelHistory = () => chat.messages.filter((m) => m.kind === 'user' || m.kind === 'mnemo')
  .map((m) => ({ role: m.kind === 'user' ? 'user' : 'assistant', content: m.text }));

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? 'Up late?' : h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}
function renderMsg(m) {
  const d = document.createElement('div');
  d.className = 'msg ' + m.kind;
  if (m.kind === 'user') {
    d.innerHTML = esc(m.text) + (m.files?.length ? `<div class="files-note">📎 ${m.files.map(esc).join(', ')}</div>` : '');
  } else if (m.kind === 'tool') {
    d.innerHTML = `<i data-i="tool"></i><div class="tb">${md(m.text)}</div>`;
  } else {
    d.innerHTML = `<img class="av" src="../build/icon-1024.png" alt=""><div class="body"><div class="txt">${
      m.text.trim() ? esc(m.text.trim()) : '<span class="muted">(no words yet, I\'m still learning)</span>'}</div>` +
      (m.sources?.length ? '<div class="sources">' + m.sources.map((s) => `<span title="${esc(s.url)}">${esc((s.title || '').slice(0, 42))}</span>`).join('') + '</div>' : '') +
      `<div class="acts"><button class="ibtn" data-act="copy" title="Copy"><i data-i="copy"></i></button>
       <button class="ibtn" data-act="retry" title="Try again"><i data-i="retry"></i></button></div></div>`;
    d.querySelector('[data-act=copy]').onclick = () => { navigator.clipboard.writeText(m.text); toast('Copied'); };
    d.querySelector('[data-act=retry]').onclick = () => retry(m);
  }
  paintIcons(d);
  return d;
}
function renderChat() {
  $('#view-chat').classList.toggle('empty', !chat.messages.length);
  $('#hero-title').textContent = greeting();
  $('#thread').innerHTML = '';
  chat.messages.forEach((m) => $('#thread').appendChild(renderMsg(m)));
  scrollDown();
  if (view === 'chat') $('#title').textContent = chat.title || 'New chat';
}
const scrollDown = () => { $('#scroller').scrollTop = 1e9; };
function push(m) {
  $('#view-chat').classList.remove('empty');
  chat.messages.push(m);
  $('#thread').appendChild(renderMsg(m));
  scrollDown();
  saveChat();
}
let saveTimer;
function saveChat() {
  if (!chat.messages.length) return;
  if (!chat.id) chat.id = newId();
  chat.title = chat.title || (chat.messages.find((m) => m.kind === 'user')?.text || 'Chat').slice(0, 60);
  if (view === 'chat') $('#title').textContent = chat.title;
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => { await api('POST', '/api/chats', { ...chat, updated: Date.now() }); loadChatList(); }, 500);
}
async function loadChatList() { chats = await api('GET', '/api/chats'); renderRecents(); }
function renderRecents() {
  const q = ($('#chat-search')?.value || '').toLowerCase();
  const shown = chats.filter((c) => !q || (c.title || '').toLowerCase().includes(q));
  $('#recents').innerHTML = shown.length ? shown.map((c) => `<div class="recent ${c.id === chat.id && view === 'chat' ? 'active' : ''}" data-id="${esc(c.id)}">
    <span title="${esc(c.title)}">${esc(c.title || 'Chat')}</span><button class="ibtn" data-del="${esc(c.id)}" title="Delete"><i data-i="trash"></i></button></div>`).join('')
    : `<div class="empty">${q ? 'No chats match.' : 'Your chats will show up here.'}</div>`;
  paintIcons($('#recents'));
  $$('.recent').forEach((el) => el.onclick = async (e) => {
    if (e.target.closest('[data-del]')) return;
    chat = await api('GET', '/api/chats/' + el.dataset.id); showView('chat'); renderChat();
  });
  $$('.recent [data-del]').forEach((b) => b.onclick = async () => {
    if (!confirm('Delete this chat?')) return;
    await api('DELETE', '/api/chats/' + b.dataset.del);
    if (b.dataset.del === chat.id) newChat(); else loadChatList();
  });
}
function newChat() { chat = { id: '', title: '', messages: [] }; showView('chat'); renderChat(); loadChatList(); }
$('#new-chat').onclick = newChat;

// ------------------------------------------------------------- sending, attachments, stop
function setBusy(b) {
  busy = b;
  const s = $('#send'); s.classList.toggle('stop', b); s.title = b ? 'Stop (Esc)' : 'Send (Enter)';
  s.innerHTML = icon(b ? 'stop' : 'up');
}
function renderAttachments() {
  $('#attachments').classList.toggle('hidden', !attachments.length);
  $('#attachments').innerHTML = attachments.map((p, i) => `<span>📄 ${esc(p.split('/').pop())} <button type="button" data-i="${i}">✕</button></span>`).join('');
  $$('#attachments button').forEach((b) => b.onclick = () => { attachments.splice(Number(b.dataset.i), 1); renderAttachments(); });
}
async function send(text) {
  text = text.trim();
  if (window.fun && fun.intercept(text)) { $('#input').value = ''; return; }
  if (text === '/new' || text === '/clear') { newChat(); return; }
  if ((!text && !attachments.length) || !ws || ws.readyState !== 1) return;
  showView('chat');
  sent.push(text); sentIdx = -1;
  const paths = attachments.splice(0); renderAttachments();
  let files = [];
  push({ kind: 'user', text: text || '(files)', files: paths.map((p) => p.split('/').pop()) });
  if (paths.length) {
    const r = await api('POST', '/api/upload', { paths });
    files = r.urls || [];
    push({ kind: 'tool', text: `Learned **${r.learned}** file${r.learned === 1 ? '' : 's'} (${num(r.chars)} characters)` + (r.skipped ? `, skipped ${r.skipped}` : '') + '.' });
    if (!text) return;
  }
  setBusy(true);
  ws.send(JSON.stringify({ type: 'chat', text, history: modelHistory().slice(0, -1), files }));
}
function retry(m) {
  const i = chat.messages.indexOf(m);
  const prev = chat.messages.slice(0, i).reverse().find((x) => x.kind === 'user');
  if (!prev || busy) return;
  chat.messages.splice(i, 1); renderChat(); setBusy(true);
  const hist = modelHistory(); const idx = hist.map((h) => h.content).lastIndexOf(prev.text);
  ws.send(JSON.stringify({ type: 'chat', text: prev.text, history: hist.slice(0, idx), files: [] }));
}
$('#composer').onsubmit = (e) => {
  e.preventDefault();
  if (busy) { ws.send(JSON.stringify({ type: 'stop' })); setBusy(false); return; }
  if (slashOpen()) { pickSlash(); return; }
  send($('#input').value); $('#input').value = ''; autosize(); closeSlash();
};
const autosize = () => { const t = $('#input'); t.style.height = 'auto'; t.style.height = Math.min(220, t.scrollHeight) + 'px'; };
$('#attach').onclick = async () => { attachments.push(...await window.mnemo.pick('files')); renderAttachments(); $('#input').focus(); };
$('#attach-folder').onclick = async () => { attachments.push(...await window.mnemo.pick('folder')); renderAttachments(); $('#input').focus(); };
document.addEventListener('click', (e) => {
  if (e.target.classList.contains('chip')) send(e.target.textContent);
  if (!e.target.closest('.mode-wrap')) $('#mode-menu').classList.add('hidden');
});

// Drop files/folders anywhere on the chat.
const main = $('#main');
main.addEventListener('dragover', (e) => { e.preventDefault(); $('#drop').classList.remove('hidden'); });
main.addEventListener('dragleave', (e) => { if (!main.contains(e.relatedTarget)) $('#drop').classList.add('hidden'); });
main.addEventListener('drop', (e) => {
  e.preventDefault(); $('#drop').classList.add('hidden');
  const paths = [...e.dataTransfer.files].map((f) => window.mnemo.pathForFile(f)).filter(Boolean);
  if (!paths.length) return;
  showView('chat'); attachments.push(...paths); renderAttachments(); $('#input').focus();
});

// Live activity while Mnemo answers: real steps (memory, planning, thinking, writing) with a timer.
let act = null;
const STEP_ICON = { files: '📎', memory: '🧠', plan: '🗺️', think: '💭', write: '✍️' };
function onStatus(m) {
  if (m.step === 'done') {
    if (!act) return;
    clearInterval(act.timer);
    const secs = ((performance.now() - act.t0) / 1000).toFixed(1);
    act.el.querySelectorAll('li.now').forEach((li) => { li.classList.remove('now'); li.classList.add('ok'); });
    act.el.querySelector('summary').innerHTML = `<span>Thought for ${secs}s</span><small>${m.memories ? ` · used ${m.memories} memor${m.memories === 1 ? 'y' : 'ies'}` : ''}${m.tokens ? ` · ${m.tokens} tokens` : ''}</small>`;
    act.el.open = false; act = null;
    return;
  }
  if (!act) {
    $('#view-chat').classList.remove('empty');
    const el = document.createElement('details');
    el.className = 'activity'; el.open = true;
    el.innerHTML = '<summary><span class="shimmer"></span><small class="act-time">0.0s</small></summary><ul></ul>';
    $('#thread').appendChild(el);
    act = { el, t0: performance.now(), steps: {} };
    act.timer = setInterval(() => { const t = act && act.el.querySelector('.act-time'); if (t) t.textContent = ((performance.now() - act.t0) / 1000).toFixed(1) + 's'; }, 100);
  }
  act.el.querySelector('.shimmer').textContent = m.text;
  act.el.querySelectorAll('li.now').forEach((li) => { if (li.dataset.step !== m.step) { li.classList.remove('now'); li.classList.add('ok'); } });
  let li = act.steps[m.step];
  if (!li) { li = document.createElement('li'); li.dataset.step = m.step; act.el.querySelector('ul').appendChild(li); act.steps[m.step] = li; }
  li.className = m.done ? 'ok' : 'now';
  li.innerHTML = `<i>${STEP_ICON[m.step] || '•'}</i><span>${esc(m.text)}</span>` +
    (m.items && m.items.length ? `<div class="act-items">${m.items.map((x) => `<em>${esc(String(x).slice(0, 60))}</em>`).join('')}</div>` : '');
  scrollDown();
}

function onChat(m) {
  if (m.type === 'status') { onStatus(m); return; }
  if (m.type === 'tool') { push({ kind: 'tool', text: m.text }); if (!m.text.startsWith('🔎')) setBusy(false); }
  if (m.type === 'reply_start') {
    $('#view-chat').classList.remove('empty');
    streaming = renderMsg({ kind: 'mnemo', text: ' ' }); streaming.querySelector('.txt').classList.add('typing');
    streaming.querySelector('.txt').textContent = ''; streaming._text = ''; $('#thread').appendChild(streaming);
  }
  if (m.type === 'reply_delta' && streaming) {
    streaming._text += m.text; streaming.querySelector('.txt').textContent = streaming._text; scrollDown();
  }
  if (m.type === 'reply') {
    streaming?.remove(); streaming = null;
    push({ kind: 'mnemo', text: m.text, sources: m.sources || [] });
    setBusy(false);
  }
}

// ------------------------------------------------------------- slash commands
const COMMANDS = [
  ['/learn ', 'search the web for a topic and learn it (e.g. /learn coding)'],
  ['/talk', 'practice basic conversation for 15 minutes'],
  ['/explore', 'explore the web on my own in the current mode'],
  ['/stop', 'stop all reading'],
  ['/mode ', 'switch mode: general, code, literature, science, math, news…'],
  ['/modes', 'list modes'],
  ['/open ', 'open a website in the browser'],
  ['/search ', 'search in the browser'],
  ['/autopilot ', 'let my own model drive the browser'],
  ['/status', 'brain status'],
  ['/train', 'start training'],
  ['/pause', 'pause training'],
  ['/new', 'start a new chat'],
  ['/help', 'all commands'],
];
let slashSel = 0, slashItems = [];
const slashOpen = () => !$('#slash').classList.contains('hidden');
function closeSlash() { $('#slash').classList.add('hidden'); }
function updateSlash() {
  const v = $('#input').value;
  if (!v.startsWith('/') || v.includes(' ')) { closeSlash(); return; }
  slashItems = COMMANDS.filter(([c]) => c.startsWith(v) && c.trim() !== v);
  if (!slashItems.length) { closeSlash(); return; }
  slashSel = Math.min(slashSel, slashItems.length - 1);
  $('#slash').innerHTML = slashItems.map(([c, d], i) => `<div class="${i === slashSel ? 'sel' : ''}" data-i="${i}"><b>${esc(c.trim())}</b><span>${esc(d)}</span></div>`).join('');
  $$('#slash div').forEach((el) => el.onmousedown = (e) => { e.preventDefault(); slashSel = Number(el.dataset.i); pickSlash(); });
  $('#slash').classList.remove('hidden');
}
function pickSlash() {
  const [c] = slashItems[slashSel]; $('#input').value = c; closeSlash(); $('#input').focus();
  if (!c.endsWith(' ')) $('#composer').requestSubmit();
}
$('#input').addEventListener('input', () => { autosize(); slashSel = 0; updateSlash(); });
$('#input').addEventListener('keydown', (e) => {
  if (slashOpen() && ['ArrowDown', 'ArrowUp', 'Tab'].includes(e.key)) {
    e.preventDefault(); slashSel = (slashSel + (e.key === 'ArrowUp' ? -1 : 1) + slashItems.length) % slashItems.length; updateSlash(); return;
  }
  if (slashOpen() && e.key === 'Escape') { closeSlash(); return; }
  if (e.key === 'ArrowUp' && !$('#input').value && sent.length) {
    e.preventDefault(); sentIdx = sentIdx < 0 ? sent.length - 1 : Math.max(0, sentIdx - 1); $('#input').value = sent[sentIdx]; return;
  }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#composer').requestSubmit(); }
});

// ------------------------------------------------------------- keyboard shortcuts
document.addEventListener('keydown', (e) => {
  const mod = e.metaKey || e.ctrlKey, k = e.key.toLowerCase();
  if (mod && k === 'k') { e.preventDefault(); showView('chat'); }
  else if (mod && k === 'l') { e.preventDefault(); if (!ui.browser) setUI({ browser: true }); $('#b-url').focus(); $('#b-url').select(); }
  else if (mod && k === 'n') { e.preventDefault(); newChat(); }
  else if (mod && k === 'b') { e.preventDefault(); setUI({ browser: !ui.browser }); }
  else if (mod && e.key === '\\') { e.preventDefault(); setUI({ sidebar: !ui.sidebar }); }
  else if (mod && ['1', '2', '3', '4', '5', '6'].includes(e.key)) { e.preventDefault(); showView(['chat', 'learn', 'memory', 'settings', 'studio', 'code'][Number(e.key) - 1]); }
  else if (e.key === 'Escape' && busy) { ws.send(JSON.stringify({ type: 'stop' })); setBusy(false); }
});

// ------------------------------------------------------------- learn
$('#basics-go').onclick = async () => {
  const minutes = Number($('#basics-min').value);
  $('#basics-go').disabled = true;
  try { await api('POST', '/api/basics', { minutes }); toast(`Practicing conversation for ${minutes} minutes. Chat with ${name()} after!`); }
  catch (e) { toast(e.message); }
  $('#basics-go').disabled = false;
};

function onTrainer(s) {
  status = s;
  const on = s.state === 'learning' || s.state.startsWith('practicing');
  $('#brain-dot').classList.toggle('on', on);
  $('#brain-size').textContent = s.params ? `${num(s.params)} parameters` : 'No brain yet';
  const eta = s.grow_at && s.tok_per_sec > 0 && s.stage_tokens < s.grow_at ? ' · grows in ' + fmtT((s.grow_at - s.stage_tokens) / s.tok_per_sec) : '';
  $('#brain-state').textContent = s.params ? `${s.state}${s.loss ? ' · loss ' + s.loss.toFixed(2) : ''}${eta}` : s.state;
  $('#s-params').textContent = num(s.params);
  $('#s-stage').textContent = s.stage;
  $('#s-max').textContent = num(s.max_params);
  $('#s-tokens').textContent = num(s.tokens_seen);
  $('#s-loss').textContent = s.loss ? s.loss.toFixed(3) : '–';
  $('#s-speed').textContent = s.tok_per_sec ? num(Math.round(s.tok_per_sec)) + ' tok/s' : '–';
  $('#s-shape').textContent = s.d_model ? `${s.n_layers} layers × ${s.d_model}` : '–';
  $('#s-context').textContent = num(s.context) + (s.train_seq_len ? ` (trains at ${num(s.train_seq_len)})` : '');
  $('#s-prec').textContent = s.precision || '–';
  $('#grow-bar').style.width = s.grow_at ? Math.min(100, 100 * s.stage_tokens / s.grow_at) + '%' : '0';
  const d = s.data || {};
  $('#s-state').textContent = `State: ${s.state} · on ${s.device} · data: library ${num(d.library)}, web ${num(d.web)}, chat ${num(d.chat)}, actions ${num(d.actions)} tokens`;
  if (s.sample) $('#sample').textContent = s.sample;
  const topics = Object.entries(s.topics || {}).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
  $('#s-topics').textContent = topics.length ? 'Knowledge by topic: ' + topics.map(([k, v]) => `${k} ${num(v)}`).join(' · ') + ' tokens' : '';
  if (s.mode && s.mode !== currentMode && modeList.length) { currentMode = s.mode; renderModes(); }
  $('#train-toggle').textContent = s.running ? 'Pause' : 'Start learning';
}
$('#train-toggle').onclick = () => api('POST', status.running ? '/api/train/pause' : '/api/train/start').then(onTrainer);

async function drawChart() {
  let data;
  try { data = await api('GET', '/api/history'); } catch { return; }
  const c = $('#chart'), ctx = c.getContext('2d');
  c.width = c.clientWidth * devicePixelRatio; c.height = 120 * devicePixelRatio;
  ctx.scale(devicePixelRatio, devicePixelRatio);
  const W = c.clientWidth, H = 120, css = getComputedStyle(document.documentElement);
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = css.getPropertyValue('--muted'); ctx.font = '11px system-ui';
  if (data.length < 2) { ctx.fillText('Loss over time appears here once training starts.', 10, 20); return; }
  const ys = data.map((h) => h[2]), min = Math.min(...ys), max = Math.max(...ys);
  const x = (i) => 8 + (W - 16) * i / (data.length - 1), y = (v) => 10 + (H - 24) * (1 - (v - min) / (max - min || 1));
  ctx.strokeStyle = css.getPropertyValue('--accent'); ctx.lineWidth = 1.6; ctx.beginPath();
  data.forEach((h, i) => (i ? ctx.lineTo(x(i), y(h[2])) : ctx.moveTo(x(i), y(h[2]))));
  ctx.stroke();
  for (let i = 1; i < data.length; i++) if (data[i][3] > data[i - 1][3]) {
    ctx.strokeStyle = '#3ecf8e88'; ctx.beginPath(); ctx.moveTo(x(i), 0); ctx.lineTo(x(i), H); ctx.stroke();
  }
  ctx.fillText(`loss ${max.toFixed(2)} → ${ys[ys.length - 1].toFixed(2)}  (green lines = grew)`, 10, H - 4);
}
setInterval(() => view === 'learn' && drawChart(), 15000);

async function learnTopic() {
  const topic = $('#topic').value.trim();
  if (!topic) return;
  $('#topic-go').disabled = true;
  try { await api('POST', '/api/learn-topic', { topic }); $('#topic').value = ''; toast(`Searching and reading about “${topic}”…`); }
  catch (e) { toast(e.message); }
  $('#topic-go').disabled = false;
}
$('#topic-go').onclick = learnTopic;
$('#topic').addEventListener('keydown', (e) => e.key === 'Enter' && learnTopic());

$('#lib-check').onclick = async () => {
  $('#lib-plan').innerHTML = '<div class="plan">Checking…</div>';
  try {
    const p = await api('GET', '/api/library/plan?preset=' + $('#preset').value);
    if (!p.files.length) { $('#lib-plan').innerHTML = '<div class="plan">Everything in this preset is already downloaded and read.</div>'; return; }
    $('#lib-plan').innerHTML = `<div class="plan">For <b>${esc(p.mode)} mode</b> this downloads <b>${p.files.length} files (${gb(p.bytes)})</b> from huggingface.co:
      <ul>${p.files.map((f) => `<li>${esc(f.source)}: ${esc(f.path.split('/').pop())} (${gb(f.size)}) · ${esc(f.license)}</li>`).join('')}</ul>
      Downloads are deleted after Mnemo reads them. <div class="row"><button class="btn primary" id="lib-go">Download & read</button></div></div>`;
    $('#lib-go').onclick = async () => {
      await api('POST', '/api/library/build', { preset: $('#preset').value });
      $('#lib-plan').innerHTML = '<div class="row"><button class="btn" id="lib-stop">Stop (resume later)</button></div>';
      $('#lib-stop').onclick = () => api('POST', '/api/library/stop');
      $('#lib-bar-wrap').classList.remove('hidden');
    };
  } catch (e) { $('#lib-plan').innerHTML = `<div class="plan">Couldn't reach Hugging Face: ${esc(e.message)}</div>`; }
};
function onLibrary(m) {
  const s = $('#lib-status');
  $('#lib-bar-wrap').classList.remove('hidden');
  if (m.stage === 'download') {
    $('#lib-bar').style.width = m.total ? (100 * m.done / m.total) + '%' : '0';
    s.textContent = `Downloading ${m.file.split('/').pop()}: ${gb(m.done || 0)} / ${gb(m.total || 0)}`;
  } else if (m.stage === 'tokenizer') s.textContent = m.text;
  else if (m.stage === 'tokenize') s.textContent = `Reading ${m.file.split('/').pop()}: ${m.docs.toLocaleString()} documents, ${num(m.tokens)} tokens`;
  else if (m.stage === 'done') { s.textContent = m.text; $('#lib-plan').innerHTML = ''; $('#lib-bar').style.width = '100%'; toast(m.text); notify(m.text); }
  else if (m.stage === 'stopped') { s.textContent = 'Stopped. Press Check size → Download to resume.'; $('#lib-plan').innerHTML = ''; }
  else if (m.stage === 'error') { s.textContent = '⚠️ ' + m.text; $('#lib-plan').innerHTML = ''; }
}

let exploring = false;
$('#explore-btn').onclick = async () => {
  if (exploring) await api('POST', '/api/crawl/stop', { job: 'auto' }); else await api('POST', '/api/crawl/auto');
};
$('#site-btn').onclick = async () => {
  const url = $('#site-url').value.trim();
  if (!url) return;
  try { await api('POST', '/api/crawl/site', { url, max_pages: Number($('#site-pages').value) }); $('#site-url').value = ''; }
  catch (e) { toast(e.message); }
};
function renderJobs(jobs) {
  exploring = jobs.some((j) => j.kind === 'auto');
  $('#explore-btn').textContent = exploring ? 'Stop exploring' : 'Start exploring';
  const label = (j) => j.kind === 'auto' ? `🌍 Exploring (${esc(j.mode)} mode)` : j.kind === 'topic' ? `🔎 Learning “${esc(j.topic)}”` : '📚 ' + esc(j.id.slice(5));
  $('#jobs').innerHTML = jobs.map((j) => `<div class="job"><span>${label(j)} · ${j.pages}${j.max ? '/' + j.max : ''} pages</span>
    <button class="btn small" data-stop="${esc(j.id)}">Stop</button></div>`).join('');
  $$('[data-stop]').forEach((b) => b.onclick = () => api('POST', '/api/crawl/stop', { job: b.dataset.stop }));
}
function feedItem(m) {
  const d = document.createElement('div'); d.className = 'item';
  d.innerHTML = `<a>${esc(m.title || m.url)}</a><small>${esc(m.url)} · ${num(m.chars)} chars · ${esc(m.topic || m.source || 'web')}</small>`;
  $('#feed').prepend(d);
  while ($('#feed').children.length > 80) $('#feed').lastChild.remove();
}
function onCrawl(m) {
  if (m.stage === 'jobs') renderJobs(m.jobs);
  if (m.stage === 'learned') feedItem(m);
  if (m.stage === 'finished') {
    const what = m.job.startsWith('learn:') ? m.job.slice(6) : m.job.slice(5);
    toast(`Finished reading ${what} (${m.pages} pages)`); notify(`Finished reading ${what}: ${m.pages} pages`);
  }
}

async function uploadPaths(paths) {
  if (!paths.length) return;
  $('#up-status').textContent = `Reading ${paths.length} item(s)…`;
  const r = await api('POST', '/api/upload', { paths });
  $('#up-status').textContent = `Learned ${r.learned} of ${r.files} files (${num(r.chars)} characters)` + (r.skipped ? `, skipped ${r.skipped} (already known, empty or unsupported)` : '');
}
$('#up-files').onclick = async () => uploadPaths(await window.mnemo.pick('files'));
$('#up-folder').onclick = async () => uploadPaths(await window.mnemo.pick('folder'));
function onUpload(m) {
  if (!m.finished) $('#up-status').textContent = `Reading files: ${m.done}/${m.total} (learned ${m.learned}) · ${m.file}`;
}

// ------------------------------------------------------------- memory
async function loadRecent() {
  const st = await api('GET', '/api/status');
  $('#mem-stats').textContent = `${st.memory.docs.toLocaleString()} documents · ${num(st.memory.chars)} characters`;
  if ($('#mem-q').value.trim()) return;
  const rows = await api('GET', '/api/memory/recent');
  $('#mem-results').innerHTML = rows.map((r) => `<div class="item">${forgetBtn(r.url)}<a>${esc(r.title || r.url)}</a><small>${esc(r.url)} · ${esc(r.topic || 'general')} · ${esc(r.source)}</small></div>`).join('')
    || '<p class="muted">Nothing yet. Download the library, explore, /learn a topic or add files.</p>';
}
$('#mem-go').onclick = async () => {
  const q = $('#mem-q').value.trim();
  if (!q) return loadRecent();
  const rows = await api('GET', '/api/memory/search?q=' + encodeURIComponent(q));
  $('#mem-results').innerHTML = rows.length ? rows.map((r) => `<div class="item">${forgetBtn(r.url)}<a>${esc(r.title)}</a><small>${esc(r.url)} · ${esc(r.topic)}</small><p>${esc(r.text.slice(0, 400))}…</p></div>`).join('')
    : '<p class="muted">Nothing in memory about that yet.</p>';
};
$('#mem-q').addEventListener('keydown', (e) => e.key === 'Enter' && $('#mem-go').click());

const forgetBtn = (url) => `<button class="btn small danger forget" data-url="${esc(url)}" title="Remove from memory">Remove</button>`;
$('#mem-results').addEventListener('click', async (e) => {
  const b = e.target.closest('.forget');
  if (!b || !confirm('Remove this from memory? Mnemo will stop using it in replies.')) return;
  await api('POST', '/api/memory/forget', { urls: [b.dataset.url] });
  b.closest('.item').remove(); toast('Removed from memory');
});

// ------------------------------------------------------------- settings
async function loadSettings() {
  const hw = await api('GET', '/api/hardware');
  $('#hw-device').innerHTML = hw.devices.map((d) => `<option value="${esc(d.id)}">${esc(d.name)}</option>`).join('');
  $('#hw-info').textContent = `This computer: ${hw.devices.slice(1).map((d) => d.name).join(' · ')} · ${hw.ram_gb} GB RAM. Training on ${hw.current}. Leave anything on Automatic to let Mnemo decide.`;
  settings = await api('GET', '/api/settings');
  $$('#settings-form [data-k]').forEach((el) => {
    const v = settings[el.dataset.k];
    if (el.type === 'checkbox') el.checked = !!v; else if (el.hasAttribute('data-list')) el.value = (v || []).join('\n'); else el.value = v ?? '';
  });
  const st = await api('GET', '/api/status');
  $('#home-path').textContent = 'Everything Mnemo learns is stored in ' + st.home;
  renderCustomModes();
}
$('#save-settings').onclick = async () => {
  const body = {};
  $$('#settings-form [data-k]').forEach((el) => {
    body[el.dataset.k] = el.type === 'checkbox' ? el.checked
      : el.hasAttribute('data-list') ? el.value.split('\n').map((x) => x.trim()).filter(Boolean)
      : el.hasAttribute('data-str') ? el.value : Number(el.value);
  });
  settings = await api('POST', '/api/settings', body);
  window.mnemo.keepAwake(!!settings.keep_awake);
  $('#settings-status').textContent = 'Saved.';
  setTimeout(() => $('#settings-status').textContent = '', 2000);
};
$('#open-data').onclick = () => window.mnemo.openData();
$('#reset-brain').onclick = async () => {
  const typed = prompt('This forgets everything the brain has learned (memory and downloads are kept). Type "reset" to confirm.');
  if (typed !== 'reset') return;
  await api('POST', '/api/reset', { confirm: 'reset' }); toast('Brain reset. Learning starts over.');
};

// Custom modes
let editing = null;
function renderCustomModes() {
  const custom = modeList.filter((m) => m.custom);
  $('#cm-list').innerHTML = custom.length ? custom.map((m) => `<div class="cm"><div>${m.icon} <b>${esc(m.name)}</b><small>${esc(m.blurb)}</small></div>
    <div class="row tight"><button class="btn small" data-edit="${esc(m.id)}">Edit</button><button class="btn small danger" data-del="${esc(m.id)}">Delete</button></div></div>`).join('')
    : '<p class="muted">No custom modes yet.</p>';
  $$('[data-edit]').forEach((b) => b.onclick = () => openModeForm(modeList.find((m) => m.id === b.dataset.edit)));
  $$('[data-del]').forEach((b) => b.onclick = async () => {
    if (!confirm('Delete this mode? What it learned stays in memory.')) return;
    await api('DELETE', '/api/custom-mode/' + b.dataset.del); await loadModes();
  });
}
function openModeForm(m) {
  editing = m ? m.id : null;
  $('#cm-form').classList.remove('hidden');
  $('#cm-icon').value = m?.icon || '✨'; $('#cm-name').value = m?.name || ''; $('#cm-blurb').value = m?.blurb || '';
  $('#cm-seeds').value = (m?.seeds || []).join('\n'); $('#cm-domains').value = (m?.domains || []).join('\n');
  $('#cm-keywords').value = (m?.keywords || []).join('\n'); $('#cm-temp').value = m?.temperature || 0.7;
  $('#cm-name').focus();
}
$('#cm-new').onclick = () => openModeForm(null);
$('#cm-cancel').onclick = () => $('#cm-form').classList.add('hidden');
$('#cm-save').onclick = async () => {
  try {
    const r = await api('POST', '/api/custom-mode', {
      id: editing, name: $('#cm-name').value, icon: $('#cm-icon').value, blurb: $('#cm-blurb').value,
      seeds: $('#cm-seeds').value, domains: $('#cm-domains').value, keywords: $('#cm-keywords').value, temperature: Number($('#cm-temp').value),
    });
    $('#cm-form').classList.add('hidden'); await loadModes();
    toast(`Saved mode “${$('#cm-name').value}”. Pick it in the title bar.`);
    return r;
  } catch (e) { toast(e.message); }
};

// ------------------------------------------------------------- modes
let modeList = [], currentMode = 'general';
function renderModes() {
  const m = modeList.find((x) => x.id === currentMode) || { icon: '🌐', name: 'General', blurb: '' };
  $('#mode-btn').innerHTML = `${m.icon} ${esc(m.name)} <i data-i="chevron" style="width:13px;height:13px"></i>`;
  $('#composer-meta').textContent = `${m.icon} ${m.name} mode`;
  $('#mode-menu').innerHTML = modeList.map((x) => `<button data-mode="${esc(x.id)}" class="${x.id === currentMode ? 'active' : ''}">
    <span class="mi">${x.icon}</span><span><b>${esc(x.name)}${x.custom ? ' <span class="muted">· custom</span>' : ''}</b><small>${esc(x.blurb)}</small></span></button>`).join('') +
    `<button data-new-mode><span class="mi">＋</span><span><b>Create a mode…</b><small>Your own sites and keywords</small></span></button>`;
  paintIcons($('#mode-btn'));
  $$('#mode-menu [data-mode]').forEach((b) => b.onclick = () => {
    $('#mode-menu').classList.add('hidden');
    api('POST', '/api/mode', { mode: b.dataset.mode }).catch((e) => toast(e.message));
  });
  $('#mode-menu [data-new-mode]').onclick = () => { $('#mode-menu').classList.add('hidden'); showView('settings'); openModeForm(null); };
  $('#mode-banner').innerHTML = `${m.icon} <b>${esc(m.name)} mode</b>: ${esc(m.blurb)} Exploring, the library below and training focus follow this mode.`;
  renderCustomModes();
}
$('#mode-btn').onclick = () => $('#mode-menu').classList.toggle('hidden');
async function loadModes() {
  const r = await api('GET', '/api/modes');
  modeList = r.modes; currentMode = r.mode; renderModes();
}
function onMode(m) { currentMode = m.mode; renderModes(); $('#lib-plan').innerHTML = ''; toast(`${m.icon} ${m.name} mode: ${m.blurb}`); }

// ------------------------------------------------------------- browser
const slot = $('#browser-slot');
function sync() {
  if (!ui.browser || overlayOpen()) { window.mnemo.setBrowserBounds({ x: 0, y: 0, width: 0, height: 0 }); return; }
  const r = slot.getBoundingClientRect();
  window.mnemo.setBrowserBounds({ x: r.left, y: r.top, width: r.width, height: r.height });
}
new ResizeObserver(sync).observe(slot); window.addEventListener('resize', sync);
$('#b-back').onclick = () => window.mnemo.browser('back');
$('#b-fwd').onclick = () => window.mnemo.browser('forward');
$('#b-reload').onclick = () => window.mnemo.browser('reload');
$('#b-form').onsubmit = (e) => {
  e.preventDefault();
  let v = $('#b-url').value.trim();
  if (!v) return;
  if (!/^https?:\/\//.test(v)) v = /^[\w-]+(\.[\w-]+)+(\/.*)?$/.test(v) ? 'https://' + v : 'https://duckduckgo.com/?q=' + encodeURIComponent(v);
  window.mnemo.browser('navigate', v);
  $('#b-url').blur();
};
$('#b-learn').onclick = async () => {
  const page = await window.mnemo.browser('read');
  const r = await api('POST', '/api/learn', page);
  toast(r.saved ? `Learned “${page.title}” (${num(page.text.length)} chars)` : 'Already in memory or too little text.');
};
window.mnemo.on('nav', (n) => {
  if (document.activeElement !== $('#b-url')) $('#b-url').value = n.url;
  $('#b-back').disabled = !n.canBack; $('#b-fwd').disabled = !n.canForward;
  $('#b-reload').innerHTML = icon(n.loading ? 'x' : 'reload');
});
let agentTimer;
window.mnemo.on('agent-action', (a) => {
  if (['snapshot', 'read'].includes(a.method)) return;
  if (!ui.browser) setUI({ browser: true });
  $('#agent-bar').classList.remove('hidden');
  $('#agent-bar').textContent = `${name()} is using the browser: ${a.method} ${a.params && (a.params.url || a.params.ref || a.params.direction || '') || ''}`;
  clearTimeout(agentTimer); agentTimer = setTimeout(() => { $('#agent-bar').classList.add('hidden'); requestAnimationFrame(sync); }, 3000);
  requestAnimationFrame(sync);
});

// ------------------------------------------------------------- chat search, rename, export, updates
$('#chat-search').addEventListener('input', renderRecents);
$('#title').addEventListener('dblclick', () => {
  if (view !== 'chat' || !chat.messages.length) return;
  const t = prompt('Rename chat', chat.title);
  if (t && t.trim()) { chat.title = t.trim().slice(0, 80); $('#title').textContent = chat.title; saveChat(); }
});
$('#export-chat').onclick = () => {
  if (!chat.messages.length) { toast('Nothing to export yet.'); return; }
  const md = `# ${chat.title}\n\n` + chat.messages.map((m) => m.kind === 'user' ? `**You:** ${m.text}`
    : m.kind === 'mnemo' ? `**${name()}:** ${m.text}` : `> ${m.text.replace(/\n/g, '\n> ')}`).join('\n\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([md], { type: 'text/markdown' }));
  a.download = (chat.title || 'chat').replace(/[^\w -]+/g, '').slice(0, 50) + '.md'; a.click();
};
async function checkUpdate() {
  try {
    const v = await api('GET', '/api/version');
    if (v.behind > 0) {
      $('#update-bar').innerHTML = `A new version of Mnemo is out (${v.behind} update${v.behind > 1 ? 's' : ''}). Run <code>mnemo update</code> in a terminal, then reopen. <button class="ibtn" id="upd-x"><i data-i="x"></i></button>`;
      paintIcons($('#update-bar')); $('#update-bar').classList.remove('hidden');
      $('#upd-x').onclick = () => $('#update-bar').classList.add('hidden');
    }
  } catch {}
}

// ------------------------------------------------------------- account gate (sign up before using Mnemo)
let account = { signed_in: false, configured: false }, gateMode = 'signup', googleTimer = null;
const overlayOpen = () => !$('#gate').classList.contains('hidden') || !$('#wizard').classList.contains('hidden') || document.body.classList.contains('touring');

function showGate(on) {
  $('#gate').classList.toggle('hidden', !on);
  requestAnimationFrame(sync);
  if (on) setGateMode(gateMode);
}
function setGateMode(m) {
  gateMode = m;
  const up = m === 'signup';
  $('#gate-title').textContent = up ? 'Welcome to Mnemo' : 'Welcome back';
  $('#gate-sub').textContent = up ? 'Create a free account to start raising your AI.' : 'Sign in to continue.';
  $('#g-name').classList.toggle('hidden', !up);
  $('#g-pass').autocomplete = up ? 'new-password' : 'current-password';
  $('#g-submit').textContent = up ? 'Create account' : 'Sign in';
  $('#g-switch').textContent = up ? 'Already have an account? Sign in' : 'New here? Create an account';
  $('#g-forgot').classList.toggle('hidden', up);
  $('#g-err').textContent = '';
}
$('#g-switch').onclick = (e) => { e.preventDefault(); setGateMode(gateMode === 'signup' ? 'signin' : 'signup'); };
$('#g-form').onsubmit = async (e) => {
  e.preventDefault();
  const btn = $('#g-submit'); btn.disabled = true; $('#g-err').textContent = '';
  try {
    account = await api('POST', gateMode === 'signup' ? '/api/account/signup' : '/api/account/signin',
      { name: $('#g-name').value, email: $('#g-email').value, password: $('#g-pass').value });
    $('#g-pass').value = '';
    afterSignIn();
  } catch (err) { $('#g-err').textContent = cleanErr(err); }
  btn.disabled = false;
};
$('#g-forgot').onclick = async (e) => {
  e.preventDefault();
  const email = $('#g-email').value.trim();
  if (!email) { $('#g-err').textContent = 'Type your email first.'; return; }
  try { await api('POST', '/api/account/reset', { email }); $('#g-err').textContent = 'Check your inbox for a reset link.'; }
  catch (err) { $('#g-err').textContent = cleanErr(err); }
};
$('#g-google').onclick = async () => {
  $('#g-err').textContent = '';
  try {
    const { url } = await api('POST', '/api/account/google');
    window.mnemo.openExternal(url);
    $('#g-wait').classList.remove('hidden');
    clearInterval(googleTimer);
    googleTimer = setInterval(async () => {  // also arrives as an 'account' event; this is a fallback
      const a = await api('GET', '/api/account');
      if (a.signed_in) { account = a; afterSignIn(); }
    }, 2000);
  } catch (err) { $('#g-err').textContent = cleanErr(err); }
};
$('#g-cancel').onclick = (e) => { e.preventDefault(); clearInterval(googleTimer); $('#g-wait').classList.add('hidden'); };
const cleanErr = (e) => String(e.message || e).replace(/^Error invoking remote method 'api': Error: /, '');

function afterSignIn() {
  clearInterval(googleTimer); $('#g-wait').classList.add('hidden');
  showGate(false); renderAccount();
  toast(`Signed in as ${account.email}`);
  if (!settings.setup_done) openWizard(); else maybeTour();
}
function renderAccount() {
  const el = $('#acct-row');
  if (!el) return;
  el.innerHTML = account.signed_in
    ? `<div class="acct-line"><span>Signed in as <b>${esc(account.name || account.email)}</b> <span class="muted">${esc(account.name ? account.email : '')}</span></span>
       <button class="btn small" id="sign-out">Sign out</button></div>`
    : `<p class="muted">Accounts aren't set up for this copy of Mnemo (no Firebase config).</p>`;
  const so = $('#sign-out');
  if (so) so.onclick = async () => { account = await api('POST', '/api/account/signout'); showGate(true); };
}
async function checkAccount() {
  account = await api('GET', '/api/account');
  renderAccount();
  if (account.configured && !account.signed_in) { showGate(true); return false; }
  return true;
}

// ------------------------------------------------------------- first-run setup wizard
const VOCAB = 32000;
function stageList() {
  const out = [[256, 6], [512, 8], [768, 12], [1024, 16], [1536, 20], [2048, 22]];
  let [d, L] = out[out.length - 1];
  while (out.length < 13) { L += 4; out.push([d, L]); d += 512; out.push([d, L]); }
  return out.map(([d, L]) => {
    const kv = Math.max(1, Math.floor(d / 256)) * 64, h = Math.ceil(8 * d / 3 / 64) * 64;
    return { d, L, p: VOCAB * d + L * (2 * d * d + 2 * d * kv + 3 * d * h + 2 * d) + d };
  });
}
const WSTAGES = stageList(), WCTX = [2048, 4096, 8192, 16384, 32768, 65536, 100000, 131072], WSEQ = [0, 512, 1024, 2048, 4096, 8192];
const WPRESETS = { tiny: ['Tiny', 'learns words in minutes', 0, 2, 2], small: ['Small', 'recommended', 0, 5, 6],
  medium: ['Medium', 'needs 16 GB+', 2, 6, 6], large: ['Large', 'needs 32 GB+', 3, 8, 6] };
const fmtP = (p) => p >= 1e9 ? (p / 1e9).toFixed(2).replace(/\.?0+$/, '') + 'B' : Math.round(p / 1e6) + 'M';
const fmtT = (s) => s < 3600 ? Math.max(1, Math.round(s / 60)) + ' min' : s < 172800 ? (s / 3600).toFixed(1) + ' hours'
  : s < 5184000 ? Math.round(s / 86400) + ' days' : Math.round(s / 2592000) + ' months';
let wstep = 0, wmode = 'general';

function openWizard() {
  $('#w-presets').innerHTML = Object.entries(WPRESETS).map(([k, [n, s]]) => `<button data-wp="${k}" class="${k === 'small' ? 'active' : ''}">${n}<small>${s}</small></button>`).join('');
  $$('#w-presets button').forEach((b) => b.onclick = () => wPreset(b.dataset.wp));
  $('#w-modes').innerHTML = modeList.map((m) => `<button data-wm="${esc(m.id)}" class="${m.id === wmode ? 'active' : ''}"><b>${m.icon} ${esc(m.name)}</b><small>${esc(m.blurb)}</small></button>`).join('');
  $$('#w-modes button').forEach((b) => b.onclick = () => { wmode = b.dataset.wm; $$('#w-modes button').forEach((x) => x.classList.toggle('active', x === b)); });
  $('#w-name').value = ui.name || '';
  wPreset('small'); wGo(0);
  $('#wizard').classList.remove('hidden'); requestAnimationFrame(sync);
}
function wPreset(k) {
  const [, , s, m, c] = WPRESETS[k];
  $('#w-start').value = s; $('#w-max').value = m; $('#w-ctx').value = c; $('#w-seq').value = 0; $('#w-growth').checked = true;
  $$('#w-presets button').forEach((b) => b.classList.toggle('active', b.dataset.wp === k));
  wUpdate();
}
function wUpdate() {
  let s = +$('#w-start').value, m = +$('#w-max').value;
  if (m < s) { m = s; $('#w-max').value = s; }
  const grow = $('#w-growth').checked, ram = status.ram_gb || 16, budget = 0.6 * ram * 1e9;
  $('#w-max').disabled = !grow;
  $('#wv-start').textContent = fmtP(WSTAGES[s].p);
  $('#wv-max').textContent = fmtP(WSTAGES[m].p);
  $('#wv-ctx').textContent = WCTX[$('#w-ctx').value].toLocaleString() + ' tokens';
  $('#wv-seq').textContent = WSEQ[$('#w-seq').value] ? WSEQ[$('#w-seq').value].toLocaleString() + ' tokens' : 'automatic';
  const top = grow ? WSTAGES[m].p : WSTAGES[s].p, startP = WSTAGES[s].p;
  const mem = top * (top * 16 * 1.35 <= budget ? 16 : 6) * 1.35;
  const flops = status.device === 'cuda' ? 40e12 : status.device === 'mps' ? 3e12 : 0.4e12;
  const est = $('#w-est');
  est.classList.toggle('bad', mem > budget);
  est.innerHTML = `Day one: <b>${fmtP(startP)}</b> parameters, learns its size well in about <b>${fmtT(20 * startP * 6 * startP / flops)}</b>.<br>` +
    (grow ? `Grows to <b>${fmtP(top)}</b>, needing about <b>${(mem / 1e9).toFixed(1)} GB</b> of your ${ram} GB memory.` : 'Stays at this size.') +
    (mem > budget ? `<br>That's more than this computer can train, so Mnemo will stop growing at the biggest size that fits.` : '');
}
['w-start', 'w-max', 'w-growth', 'w-ctx', 'w-seq'].forEach((id) => $('#' + id).addEventListener('input', () => {
  $$('#w-presets button').forEach((b) => b.classList.remove('active')); wUpdate();
}));
function wGo(n) {
  wstep = n;
  $$('.wstep').forEach((s) => s.classList.toggle('hidden', +s.dataset.s !== n));
  $$('#w-steps i').forEach((i, k) => i.classList.toggle('on', k <= n));
  $('#w-back').style.visibility = n ? 'visible' : 'hidden';
  $('#w-next').textContent = n === 3 ? 'Start' : 'Next';
}
$('#w-back').onclick = () => wGo(Math.max(0, wstep - 1));
$('#w-next').onclick = async () => {
  if (wstep < 3) { wGo(wstep + 1); return; }
  const s = +$('#w-start').value, grow = $('#w-growth').checked;
  const body = { start_params: s ? WSTAGES[s].p : 0, allow_growth: grow, max_params: grow ? WSTAGES[+$('#w-max').value].p : 0,
    context_length: WCTX[$('#w-ctx').value], train_seq_len: WSEQ[$('#w-seq').value], setup_done: true };
  settings = await api('POST', '/api/settings', body);
  await api('POST', '/api/mode', { mode: wmode }).catch(() => {});
  const nm = $('#w-name').value.trim();
  if (nm) setUI({ name: nm });
  $('#wizard').classList.add('hidden'); requestAnimationFrame(sync);
  maybeTour();
  const first = document.querySelector('input[name=w-first]:checked').value;
  if (first === 'talk') { await api('POST', '/api/basics', { minutes: 15 }); toast(`${name()} is practicing conversation for 15 minutes.`); }
  if (first === 'library') { showView('learn'); $('#lib-check').click(); }
  if (first === 'explore') { await api('POST', '/api/crawl/auto'); toast(`${name()} is exploring the web.`); }
  if (first === 'none') toast('All set. Open Learn whenever you are ready.');
};
$('#redo-setup')?.addEventListener('click', openWizard);

// ------------------------------------------------------------- connection
async function boot() {
  settings = await api('GET', '/api/settings');
  ui = { ...UI_DEFAULTS, ...(settings.ui || {}) };
  applyUI();
  window.mnemo.keepAwake(!!settings.keep_awake);
  await loadModes();
  renderChat(); loadChatList();
  if (await checkAccount()) { if (!settings.setup_done) openWizard(); else maybeTour(); }
  setTimeout(checkUpdate, 4000);
}
function connect(cfg) {
  cfgG = cfg;
  if (ws && ws.readyState <= 1) return;
  boot().catch(() => {});
  ws = new WebSocket(`ws://127.0.0.1:${cfg.port}/ws/ui?token=${cfg.token}`);
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.type === 'trainer') onTrainer(m);
    else if (m.type === 'library') onLibrary(m);
    else if (m.type === 'crawl') onCrawl(m);
    else if (m.type === 'upload') onUpload(m);
    else if (m.type === 'sample') $('#sample').textContent = m.text;
    else if (m.type === 'mode') onMode(m);
    else if (m.type === 'modes') loadModes();
    else if (m.type === 'studio') onStudio(m);
    else if (m.type === 'code') onCode(m);
    else if (m.type === 'account') { account = { signed_in: true, configured: true, ...m }; afterSignIn(); }
    else if (m.type === 'model' && !m.quiet) { toast(m.text); notify(m.text); }
    else onChat(m);
  };
  ws.onclose = () => { setBusy(false); setTimeout(() => connect(cfg), 1500); };
}
ui = { ...UI_DEFAULTS }; paintIcons(); applyUI(); renderChat(); renderRecents(); setBusy(false);
window.mnemo.on('ready', connect);
window.mnemo.on('brain-exit', (code) => { $('#brain-size').textContent = 'Brain stopped'; $('#brain-state').textContent = String(code); $('#brain-dot').classList.remove('on'); });
window.mnemo.config().then((cfg) => cfg.port && connect(cfg));
