/* Starting tutorial: a spotlight tour of the app. Runs after setup; replay with /tutorial or Settings. */
const TOUR = [
  { title: () => `Welcome to ${name()} 👋`, text: 'A quick tour, about a minute. You can skip any time with Esc.', center: true },
  { sel: '#composer', place: 'top', title: 'Talk here',
    text: 'Chat with your AI. Type / for commands. Drop files or folders here to teach it. Esc stops a reply.' },
  { sel: '#thread', place: 'top', title: 'Watch it think',
    text: 'While it answers you see each step live: searching memory, planning, thinking, writing. Click the summary to see what it used.', view: 'chat' },
  { sel: '#mode-btn', place: 'bottom', title: 'Pick a focus',
    text: 'Modes steer what it reads and studies most: Code, Science, Literature, Math… or make your own.' },
  { sel: '.nav[data-view="learn"]', place: 'right', title: 'Teach it',
    text: 'Learn is where it grows: the conversation course, /learn topics, the reading library, the web, and your files.' },
  { sel: '#brain-card', place: 'right', title: 'Its brain',
    text: 'Live status of training: size, loss and when it will grow next. Click it any time.' },
  { sel: '.nav[data-view="code"]', place: 'right', title: 'Mnemo Code',
    text: 'Give it a folder and a job. Choose Ask, Partial or Full access. Every change shows as a diff and can be undone.' },
  { sel: '.nav[data-view="studio"]', place: 'right', title: 'Studio',
    text: 'Download open image, video and 3D models and run them on this computer. Licenses are shown up front.' },
  { sel: '#browser', place: 'left', title: 'Its browser',
    text: 'A real browser it can drive. Say “go to wikipedia.org” or “learn this page”. ⌘B hides it; drag the divider to resize.' },
  { sel: '#recents', place: 'right', title: 'Your chats',
    text: 'Every chat is saved here. Search them, double-click a title to rename, export as Markdown.' },
  { sel: '.nav[data-view="settings"]', place: 'right', title: 'Make it yours',
    text: 'Theme, colors, name, hardware (GPU, precision, layers), plugins and more. Replay this tour from there.' },
  { title: "You're set ✨", text: 'Try “hi!”, /talk to teach it conversation, or /learn coding. Tip: /tips lists every shortcut.', center: true, last: true },
];
let tstep = 0, touring = false;

function tourEls() {
  if (!$('#tour-hole')) {
    document.body.insertAdjacentHTML('beforeend', `<div id="tour-hole"></div><div id="tour-card" role="dialog" aria-live="polite">
      <div class="tc-top"><span id="tc-count"></span><button id="tc-skip">Skip tour</button></div>
      <h4 id="tc-title"></h4><p id="tc-text"></p>
      <div class="tc-nav"><div class="tc-dots" id="tc-dots"></div><button class="btn small" id="tc-back">Back</button><button class="btn small primary" id="tc-next">Next</button></div></div>`);
    $('#tc-skip').onclick = () => endTour();
    $('#tc-back').onclick = () => showStep(tstep - 1);
    $('#tc-next').onclick = () => (TOUR[tstep].last ? endTour() : showStep(tstep + 1));
  }
}
function startTour() {
  tourEls(); touring = true; document.body.classList.add('touring');
  showView('chat'); if (!ui.browser) setUI({ browser: true }, false); if (!ui.sidebar) setUI({ sidebar: true }, false);
  requestAnimationFrame(sync); showStep(0);
}
function showStep(i) {
  tstep = Math.max(0, Math.min(TOUR.length - 1, i));
  const s = TOUR[tstep], hole = $('#tour-hole'), card = $('#tour-card');
  if (s.view) showView(s.view);
  $('#tc-title').textContent = typeof s.title === 'function' ? s.title() : s.title;
  $('#tc-text').textContent = s.text;
  $('#tc-count').textContent = `${tstep + 1} of ${TOUR.length}`;
  $('#tc-dots').innerHTML = TOUR.map((_, k) => `<i class="${k === tstep ? 'on' : ''}"></i>`).join('');
  $('#tc-back').style.visibility = tstep ? 'visible' : 'hidden';
  $('#tc-next').textContent = s.last ? 'Start using it' : 'Next';
  const el = s.sel && document.querySelector(s.sel);
  card.className = ''; card.style.cssText = '';
  if (!el || s.center) {
    hole.style.cssText = 'left:50%;top:50%;width:0;height:0';
    card.classList.add('center');
  } else {
    const r = el.getBoundingClientRect(), pad = 6;
    Object.assign(hole.style, { left: r.left - pad + 'px', top: r.top - pad + 'px', width: r.width + pad * 2 + 'px', height: r.height + pad * 2 + 'px' });
    const cw = 320, gap = 14, W = innerWidth, H = innerHeight;
    let x, y;
    if (s.place === 'right') { x = r.right + gap; y = r.top + r.height / 2 - 80; }
    else if (s.place === 'left') { x = r.left - cw - gap; y = r.top + 60; }
    else if (s.place === 'bottom') { x = r.left + r.width / 2 - cw / 2; y = r.bottom + gap; }
    else { x = r.left + r.width / 2 - cw / 2; y = r.top - gap - 170; }
    card.style.left = Math.max(12, Math.min(W - cw - 12, x)) + 'px';
    card.style.top = Math.max(12, Math.min(H - 200, y)) + 'px';
  }
  if (window.fun) fun.sfx('pop');
  $('#tc-next').focus();
}
async function endTour() {
  touring = false; document.body.classList.remove('touring');
  $('#tour-hole')?.remove(); $('#tour-card')?.remove();
  requestAnimationFrame(sync);
  settings = await api('POST', '/api/settings', { tutorial_done: true });
  $('#input').focus();
}
document.addEventListener('keydown', (e) => {
  if (!touring) return;
  if (e.key === 'Escape') { e.preventDefault(); endTour(); }
  if (e.key === 'ArrowRight' || e.key === 'Enter') { e.preventDefault(); TOUR[tstep].last ? endTour() : showStep(tstep + 1); }
  if (e.key === 'ArrowLeft') { e.preventDefault(); showStep(tstep - 1); }
}, true);
addEventListener('resize', () => touring && showStep(tstep));

// Run once after setup (and for anyone who finished setup before tutorials existed).
function maybeTour() { if (settings.setup_done && !settings.tutorial_done && !overlayOpen() && !touring) setTimeout(startTour, 600); }

$('#replay-tour').onclick = () => startTour();
