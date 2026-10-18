/* Mnemo Code: Mnemo's own model working on files in a folder you choose. Uses helpers from app.js. */
let codeCfg = {}, codeRun = null, codeBusy = false, curViewer = '';

async function loadCode() {
  codeCfg = await api('GET', '/api/code');
  $('#ws-name').textContent = codeCfg.workspace ? codeCfg.workspace.split(/[\\/]/).pop() : 'Choose folder';
  $('#ws-btn').title = codeCfg.workspace || 'Choose the folder Mnemo Code works in';
  $$('#perm button').forEach((b) => b.classList.toggle('active', b.dataset.p === codeCfg.permission));
  $('#code-undo').disabled = !codeCfg.can_undo;
  $('#code-meta').textContent = { ask: 'Asks before everything', partial: 'Asks before changes', full: 'Full access' }[codeCfg.permission] || '';
  $$('[data-c]').forEach((el) => { const v = codeCfg[el.dataset.c.replace('code_', '')] ?? settings[el.dataset.c];
    if (el.type === 'checkbox') el.checked = !!v; else el.value = v; });
  if (!$('#code-thread').children.length) codeWelcome();
  loadTree();
}

function codeWelcome() {
  $('#code-thread').innerHTML = `<div class="code-welcome">
    <h3>Mnemo Code</h3>
    <p>Give your own AI a folder and a job. It thinks out loud, then reads, writes, edits, searches and runs commands there.
      You decide how much it may do on its own.</p>
    <div class="perm-explain">
      <div><b>Ask</b><span>Approve every step, even reading.</span></div>
      <div><b>Partial</b><span>Reads freely; asks before changes or commands.</span></div>
      <div><b>Full access</b><span>Never asks. Still locked to the folder, with dangerous commands blocked.</span></div>
    </div>
    <p class="muted">Mnemo starts with no idea how to use tools. Press <b>Teach Mnemo Code</b> to practice, and use the direct commands
      <code>/ls</code> <code>/read file</code> <code>/find text</code> <code>/run cmd</code> <code>/undo</code>, which always work.</p>
    <div class="hint"><button class="chip" data-try="list the files">list the files</button>
      <button class="chip" data-try="create hello.py that prints hello world">create hello.py that prints hello world</button>
      <button class="chip" data-try="find all TODO comments">find all TODO comments</button></div></div>`;
  $$('[data-try]').forEach((b) => b.onclick = () => codeSend(b.dataset.try));
}

// --- workspace -------------------------------------------------------------------------
async function chooseFolder() {
  const [dir] = await window.mnemo.pick('folder');
  if (!dir) return;
  try { await api('POST', '/api/code/workspace', { path: dir }); $('#viewer').classList.add('hidden'); toast(`Mnemo Code is working in ${dir.split(/[\\/]/).pop()}`); loadCode(); }
  catch (e) { toast(cleanErr(e)); }
}
$('#ws-btn').onclick = (e) => {
  e.stopPropagation();
  const m = $('#ws-menu');
  m.innerHTML = `<button data-open><span class="mi">📂</span><span><b>Open folder…</b><small>Pick any project folder</small></span></button>` +
    (codeCfg.recent || []).map((r) => `<button data-ws="${esc(r)}"><span class="mi">🕘</span><span><b>${esc(r.split(/[\\/]/).pop())}</b><small>${esc(r)}</small></span></button>`).join('');
  m.classList.toggle('hidden');
  m.querySelector('[data-open]').onclick = () => { m.classList.add('hidden'); chooseFolder(); };
  $$('#ws-menu [data-ws]').forEach((b) => b.onclick = async () => {
    m.classList.add('hidden');
    try { await api('POST', '/api/code/workspace', { path: b.dataset.ws }); loadCode(); } catch (err) { toast(cleanErr(err)); }
  });
};
$$('#perm button').forEach((b) => b.onclick = async () => {
  const p = b.dataset.p;
  if (p === 'full' && !confirm('Full access lets Mnemo Code change files and run commands in this folder without asking.\n\n' +
    'It stays locked to the folder, blocks dangerous commands and backs up every change, but a young model can still make mistakes. Continue?')) return;
  await api('POST', '/api/settings', { code_permission: p });
  loadCode();
});
$('#code-gear').onclick = (e) => { e.stopPropagation(); $('#code-settings').classList.toggle('hidden'); };
document.addEventListener('click', (e) => {
  if (!e.target.closest('.ws-wrap')) { $('#ws-menu').classList.add('hidden'); $('#code-settings').classList.add('hidden'); }
});
$$('[data-c]').forEach((el) => el.addEventListener('change', async () => {
  await api('POST', '/api/settings', { [el.dataset.c]: el.type === 'checkbox' ? el.checked : Number(el.value) });
  codeCfg = await api('GET', '/api/code');
}));
$('#code-forget').onclick = async () => { await api('POST', '/api/code/workspace', { path: codeCfg.workspace }); toast('Mnemo Code will ask again.'); };
$('#code-undo').onclick = async () => {
  const r = await api('POST', '/api/code/undo'); codeNote('↩ ' + r.text); $('#code-undo').disabled = !r.can_undo; loadTree(); refreshViewer();
};
$('#code-teach').onclick = async () => {
  const minutes = Number(prompt('Practice Mnemo Code tool use for how many minutes? (20 is a good start)', '20'));
  if (!minutes) return;
  try { await api('POST', '/api/code/teach', { minutes }); toast(`Practicing Mnemo Code for ${minutes} minutes`); } catch (e) { toast(cleanErr(e)); }
};

// --- file tree + viewer ----------------------------------------------------------------
async function loadTree() {
  if (!codeCfg.workspace) { $('#ftree').innerHTML = '<div class="empty">Choose a folder to see its files.</div>'; return; }
  $('#ftree').innerHTML = `<div class="ftree-head">${esc(codeCfg.workspace.split(/[\\/]/).pop())}</div>`;
  await addTree($('#ftree'), '.', 0);
}
async function addTree(parent, path, depth) {
  let items;
  try { items = await api('GET', '/api/code/tree?path=' + encodeURIComponent(path)); } catch { return; }
  const box = document.createElement('div');
  box.innerHTML = items.map((i) => `<div class="fnode ${i.dir ? 'dir' : ''}" data-path="${esc(i.path)}" style="padding-left:${10 + depth * 14}px">
    <span class="tw">${i.dir ? '▸' : ''}</span>${i.dir ? '📁' : fileIcon(i.name)} ${esc(i.name)}</div>`).join('') || `<div class="empty" style="padding-left:${10 + depth * 14}px">empty</div>`;
  parent.appendChild(box);
  box.querySelectorAll(':scope > .fnode').forEach((el) => el.onclick = async (e) => {
    e.stopPropagation();
    if (el.classList.contains('dir')) {
      const open = el.classList.toggle('open');
      el.querySelector('.tw').textContent = open ? '▾' : '▸';
      if (open) { const holder = document.createElement('div'); holder.className = 'sub'; el.after(holder); addTree(holder, el.dataset.path, depth + 1); }
      else el.nextElementSibling?.classList.contains('sub') && el.nextElementSibling.remove();
    } else openViewer(el.dataset.path);
  });
}
const fileIcon = (n) => ({ py: '🐍', js: '📜', ts: '📘', md: '📝', json: '🧾', html: '🌐', css: '🎨', sh: '⚙️', txt: '📄', png: '🖼', jpg: '🖼' }[n.split('.').pop()] || '📄');
async function openViewer(path) {
  try {
    const f = await api('GET', '/api/code/file?path=' + encodeURIComponent(path));
    curViewer = path;
    $('#viewer-name').textContent = path;
    $('#viewer-code').innerHTML = f.too_big ? '<span class="muted">File too large to preview.</span>'
      : f.text.split('\n').map((l, i) => `<span class="ln">${i + 1}</span>${esc(l)}`).join('\n');
    $('#viewer').classList.remove('hidden');
  } catch (e) { toast(cleanErr(e)); }
}
const refreshViewer = () => curViewer && !$('#viewer').classList.contains('hidden') && openViewer(curViewer);
$('#viewer-x').onclick = () => { $('#viewer').classList.add('hidden'); curViewer = ''; };
$('#viewer-ask').onclick = () => { $('#code-input').value = `explain ${curViewer}`; $('#code-input').focus(); };

// --- running tasks ----------------------------------------------------------------------
function codeNote(text) {
  const d = document.createElement('div'); d.className = 'cnote'; d.innerHTML = md(text);
  $('#code-thread').appendChild(d); scrollCode();
}
const scrollCode = () => { $('#code-thread').scrollTop = 1e9; };
function setCodeBusy(b) { codeBusy = b; $('#code-send').innerHTML = icon(b ? 'stop' : 'up'); $('#code-send').classList.toggle('stop', b); }
function codeSend(text) {
  text = text.trim();
  if (!text || !ws || ws.readyState !== 1) return;
  if (!codeCfg.workspace) { chooseFolder(); return; }
  if (window.fun && fun.codeIntercept(text)) return;
  $('.code-welcome')?.remove();
  const u = document.createElement('div'); u.className = 'msg user'; u.textContent = text;
  $('#code-thread').appendChild(u); scrollCode();
  if (!text.startsWith('/')) setCodeBusy(true);
  ws.send(JSON.stringify({ type: 'code_task', text }));
}
$('#code-form').onsubmit = (e) => {
  e.preventDefault();
  if (codeBusy) { ws.send(JSON.stringify({ type: 'code_stop' })); setCodeBusy(false); return; }
  codeSend($('#code-input').value); $('#code-input').value = ''; $('#code-input').style.height = 'auto';
};
$('#code-input').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('#code-form').requestSubmit(); } });
$('#code-input').addEventListener('input', (e) => { e.target.style.height = 'auto'; e.target.style.height = Math.min(200, e.target.scrollHeight) + 'px'; });

function thinkBlock() {
  const d = document.createElement('details'); d.className = 'think'; d.open = true;
  d.innerHTML = '<summary><span class="shimmer">Thinking</span></summary><pre></pre>';
  $('#code-thread').appendChild(d); scrollCode();
  return d;
}
function diffHtml(diff) {
  return diff.split('\n').map((l) => `<span class="${l.startsWith('+') ? 'add' : l.startsWith('-') ? 'del' : l.startsWith('@@') ? 'hunk' : ''}">${esc(l)}</span>`).join('\n');
}
function actionCard(m) {
  const a = m.action, p = m.preview || {};
  const d = document.createElement('div'); d.className = 'acard'; d.id = 'step-' + m.id;
  const tag = ['ls', 'read', 'find'].includes(a.tool) ? 'read' : a.tool === 'run' ? 'run' : 'change';
  d.innerHTML = `<div class="ahead"><span class="atag ${tag}">${a.tool}</span><b>${esc(m.label)}</b>
      ${p.added != null ? `<span class="pm"><i class="add">+${p.added}</i> <i class="del">−${p.removed}</i></span>` : ''}<span class="astate"></span></div>
    ${p.warning ? `<div class="awarn">${esc(p.warning)}</div>` : ''}
    ${p.diff ? `<pre class="diff">${diffHtml(p.diff)}</pre>` : ''}
    ${a.tool === 'run' ? `<pre class="cmd">$ ${esc(a.arg)}</pre>` : ''}
    <div class="aout hidden"></div>`;
  return d;
}
function onCode(m) {
  const th = $('#code-thread');
  if (m.stage === 'start') { codeRun = { n: 0 }; }
  if (m.stage === 'thinking') { codeRun = codeRun || {}; codeRun.think = thinkBlock(); }
  if (m.stage === 'stream' && codeRun?.think) {
    const thinkPart = m.text.split('ACTION:')[0].replace(/^THINK:\s*/, '');
    codeRun.think.querySelector('pre').textContent = thinkPart;
    if (/ACTION:\s*(write|replace)/.test(m.text)) codeRun.think.querySelector('.shimmer').textContent = 'Writing';
    else if (/ACTION:/.test(m.text)) codeRun.think.querySelector('.shimmer').textContent = 'Deciding';
    scrollCode();
  }
  if (m.stage === 'approve' || m.stage === 'running') {
    if (codeRun?.think) { codeRun.think.open = false; codeRun.think.querySelector('summary').innerHTML = 'Thought for a moment'; codeRun.think = null; }
    let card = $('#step-' + m.id);
    if (!card) { card = actionCard(m); th.appendChild(card); }
    if (m.stage === 'approve') {
      card.classList.add('waiting');
      const bar = document.createElement('div'); bar.className = 'abtns';
      bar.innerHTML = `<button class="btn small primary" data-ok>Approve <kbd>↵</kbd></button><button class="btn small" data-no>Deny <kbd>esc</kbd></button>
        <button class="btn small ghost" data-always>Always allow “${esc(m.action.tool)}”</button>`;
      card.appendChild(bar);
      const answer = (ok, always = false) => {
        ws.send(JSON.stringify({ type: 'code_approve', id: m.id, ok, always, tool: m.action.tool }));
        bar.remove(); card.classList.remove('waiting'); document.removeEventListener('keydown', keys);
      };
      const keys = (e) => { if (view !== 'code' || document.activeElement === $('#code-input') && $('#code-input').value) return;
        if (e.key === 'Enter') { e.preventDefault(); answer(true); } if (e.key === 'Escape') answer(false); };
      document.addEventListener('keydown', keys);
      bar.querySelector('[data-ok]').onclick = () => answer(true);
      bar.querySelector('[data-no]').onclick = () => answer(false);
      bar.querySelector('[data-always]').onclick = () => answer(true, true);
      if (document.visibilityState !== 'visible' || view !== 'code') notify(`Mnemo Code wants to: ${m.label}`);
    } else card.querySelector('.astate').innerHTML = '<span class="spin"></span>';
    scrollCode();
  }
  if (m.stage === 'result') {
    const card = $('#step-' + m.id) || (() => { const c = actionCard({ id: m.id, action: m.action || { tool: '?' }, label: m.label || '' }); th.appendChild(c); return c; })();
    card.classList.add(m.ok ? 'ok' : 'bad');
    card.querySelector('.astate').textContent = m.ok ? '✓' : '✕';
    if (m.text) { const o = card.querySelector('.aout'); o.classList.remove('hidden'); o.innerHTML = `<pre>${esc(m.text).slice(0, 20000)}</pre>`; }
    scrollCode(); refreshViewer();
  }
  if (m.stage === 'end') {
    if (codeRun?.think) { codeRun.think.open = false; codeRun.think.querySelector('summary').textContent = 'Thought'; }
    const d = document.createElement('div'); d.className = 'cend ' + (m.ok ? 'ok' : 'bad');
    d.innerHTML = md(m.text) + (m.raw ? `<details><summary>What the model wrote</summary><pre>${esc(m.raw)}</pre></details>` : '');
    th.appendChild(d); scrollCode(); setCodeBusy(false); codeRun = null;
    api('GET', '/api/code').then((c) => { codeCfg = c; $('#code-undo').disabled = !c.can_undo; });
  }
  if (m.stage === 'note') { codeNote(m.text); setCodeBusy(false); }
  if (m.stage === 'tree' || m.stage === 'changed') { loadTree(); $('#code-undo').disabled = false; }
}
document.addEventListener('keydown', (e) => {
  if (view === 'code' && (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'z' && document.activeElement !== $('#code-input') && !$('#code-undo').disabled) {
    e.preventDefault(); $('#code-undo').click();
  }
});
