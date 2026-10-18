/* Mnemo Studio: local image / video / 3D generation. Uses helpers defined in app.js. */
let stData = { models: [] }, stKind = 'image';
const fileUrl = (n) => `http://127.0.0.1:${cfgG.port}/files/creations/${encodeURIComponent(n)}?token=${cfgG.token}`;
const gbStr = (g) => g >= 10 ? Math.round(g) + ' GB' : g.toFixed(1) + ' GB';

async function loadStudio() {
  stData = await api('GET', '/api/studio');
  $('#st-deps').classList.toggle('hidden', stData.deps);
  $('#st-install').disabled = stData.installing;
  renderStudio();
  loadCreations();
}
function renderStudio() {
  const list = stData.models.filter((m) => m.kind === stKind);
  $$('#st-kinds button').forEach((b) => b.classList.toggle('active', b.dataset.k === stKind));
  $('#st-models').innerHTML = list.map((m) => `<div class="model ${m.installed ? 'ready' : ''}" data-id="${m.id}">
      <div class="model-top"><b>${esc(m.name)}</b>
        <span class="lic ${m.commercial ? 'ok' : 'nc'}" title="${esc(m.license)}">${m.commercial ? 'Commercial OK' : 'Non-commercial'}</span></div>
      <p>${esc(m.about)}</p>
      <div class="model-meta"><span>${gbStr(m.gb)} download</span><span class="${m.fits ? '' : 'warnc'}">needs ~${m.ram} GB RAM${m.fits ? '' : ' (more than this computer)'}</span><span>${esc(m.license)}</span></div>
      <div class="bar thin ${m.downloading ? '' : 'hidden'}"><div style="width:0"></div></div>
      <div class="row tight">${m.installed
        ? '<button class="btn small" data-use>Use</button><button class="btn small danger" data-rm>Remove</button>'
        : `<button class="btn small primary" data-dl ${m.downloading || !stData.deps ? 'disabled' : ''}>${m.downloading ? 'Downloading…' : 'Download'}</button>`}</div>
    </div>`).join('');
  $$('#st-models .model').forEach((el) => {
    const id = el.dataset.id, m = stData.models.find((x) => x.id === id);
    el.querySelector('[data-dl]')?.addEventListener('click', async () => {
      if (!m.commercial && !confirm(`${m.name} is licensed ${m.license}: personal and research use only, not commercial use. Download anyway?`)) return;
      if (!m.fits && !confirm(`${m.name} needs about ${m.ram} GB of memory; this computer has ${stData.ram_gb} GB. It may be very slow or fail. Continue?`)) return;
      await api('POST', '/api/studio/download', { id }); m.downloading = true; renderStudio();
    });
    el.querySelector('[data-use]')?.addEventListener('click', () => { $('#st-model').value = id; stPick(); $('#st-prompt').focus(); });
    el.querySelector('[data-rm]')?.addEventListener('click', async () => {
      if (!confirm(`Remove ${m.name} from this computer? You can download it again later.`)) return;
      stData = await api('DELETE', '/api/studio/model/' + id); renderStudio();
    });
  });
  const ready = list.filter((m) => m.installed), prev = $('#st-model').value;
  $('#st-model').innerHTML = ready.length ? ready.map((m) => `<option value="${m.id}">${esc(m.name)}</option>`).join('')
    : `<option value="">Download a ${stKind === '3d' ? '3D' : stKind} model first →</option>`;
  if (ready.some((m) => m.id === prev)) $('#st-model').value = prev;
  $('#st-go').disabled = !ready.length;
  stPick();
}
function stPick() {
  const m = stData.models.find((x) => x.id === $('#st-model').value);
  if (!m) return;
  const d = m.defaults;
  $('#st-steps').value = d.steps; $('#st-guid').value = d.guidance;
  $('#st-w').value = d.width || ''; $('#st-h').value = d.height || ''; $('#st-frames').value = d.frames || '';
  $$('.create-card .wh').forEach((e) => e.classList.toggle('hidden', m.kind === '3d'));
  $$('.create-card .fr').forEach((e) => e.classList.toggle('hidden', m.kind !== 'video'));
  $('#st-prompt').placeholder = m.kind === 'video' ? 'A golden retriever running through autumn leaves, slow motion'
    : m.kind === '3d' ? 'A low-poly wooden treasure chest' : 'A lighthouse on a cliff at sunset, oil painting';
}
$$('#st-kinds button').forEach((b) => b.onclick = () => { stKind = b.dataset.k; renderStudio(); });
$('#st-model').onchange = stPick;
$('#st-install').onclick = async () => { await api('POST', '/api/studio/install'); $('#st-install').disabled = true; $('#st-install').textContent = 'Installing…'; };
$('#st-go').onclick = async () => {
  const num = (id) => $(id).value === '' ? undefined : Number($(id).value);
  try {
    await api('POST', '/api/studio/generate', { id: $('#st-model').value, prompt: $('#st-prompt').value, negative: $('#st-neg').value,
      steps: num('#st-steps'), guidance: num('#st-guid'), width: num('#st-w'), height: num('#st-h'), frames: num('#st-frames'), seed: num('#st-seed') });
    $('#st-status').textContent = 'Queued…'; $('#st-bar-wrap').classList.remove('hidden'); $('#st-bar').style.width = '0';
  } catch (e) { toast(cleanErr(e)); }
};
$('#st-prompt').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) $('#st-go').click(); });

async function loadCreations() {
  const items = await api('GET', '/api/studio/creations');
  $('#st-gallery').innerHTML = items.length ? items.map((c) => {
    const f = c.files[0];
    const media = c.kind === 'image' ? `<img src="${fileUrl(f)}" alt="" loading="lazy">`
      : c.kind === 'video' ? `<video src="${fileUrl(f)}" muted loop playsinline></video>`
      : `<div class="mesh">3D<small>${c.files.map((x) => x.split('.').pop()).join(' · ')}</small></div>`;
    return `<figure data-job="${c.job}">${media}<figcaption><span title="${esc(c.prompt)}">${esc(c.prompt)}</span>
      <small>${esc(c.model_name)} · seed ${c.seed} · ${c.seconds}s${c.commercial ? '' : ' · non-commercial'}</small>
      <div class="fig-acts"><button data-show="${esc(f)}">Show file</button><button data-again>Reuse</button><button data-del>Delete</button></div></figcaption></figure>`;
  }).join('') : '<p class="muted">Nothing yet. Pick a model, describe something, press Generate.</p>';
  $$('#st-gallery figure').forEach((el) => {
    const c = items.find((x) => x.job === el.dataset.job);
    const v = el.querySelector('video');
    if (v) { el.onmouseenter = () => v.play(); el.onmouseleave = () => v.pause(); }
    el.querySelector('[data-show]').onclick = (e) => window.mnemo.openCreation(e.target.dataset.show);
    el.querySelector('[data-again]').onclick = () => {
      stKind = c.kind; renderStudio(); $('#st-model').value = c.model; stPick();
      $('#st-prompt').value = c.prompt; $('#st-neg').value = c.negative || ''; $('#st-seed').value = c.seed; $('#view-studio').scrollTop = 0;
    };
    el.querySelector('[data-del]').onclick = async () => { await api('DELETE', '/api/studio/creations/' + c.job); el.remove(); };
  });
}
function onStudio(m) {
  if (m.stage === 'install') $('#st-status').textContent = m.text;
  if (m.stage === 'install-done') { toast(m.text); $('#st-install').textContent = 'Install'; loadStudio(); }
  if (m.stage === 'download') {
    const bar = $(`#st-models [data-id="${m.id}"] .bar div`);
    if (bar) bar.style.width = Math.min(98, 100 * m.done / m.total) + '%';
  }
  if (m.stage === 'downloaded' || (m.stage === 'error' && m.id)) { toast(m.text); loadStudio(); }
  if (m.stage === 'loading') { $('#st-status').textContent = m.text; $('#st-bar-wrap').classList.remove('hidden'); }
  if (m.stage === 'step') { $('#st-bar').style.width = (100 * m.step / m.total) + '%'; $('#st-status').textContent = `Step ${m.step} of ${m.total}`; }
  if (m.stage === 'done') {
    $('#st-bar').style.width = '100%'; $('#st-status').textContent = `Done in ${m.seconds}s`;
    setTimeout(() => $('#st-bar-wrap').classList.add('hidden'), 1500);
    if (view === 'studio') loadCreations(); else toast(`Your ${m.kind} is ready in Studio`);
    notify(`Your ${m.kind} is ready`);
  }
  if (m.stage === 'error' && m.job) { $('#st-status').textContent = '⚠️ ' + m.text; toast('Generation failed'); }
}
