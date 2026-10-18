/* Tips & tricks, achievements and a few easter eggs. Uses helpers from app.js. */
const TIPS = [
  ['/learn coding', 'searches the web for a topic and studies the best pages.'],
  ['/talk 30', 'practices everyday conversation for 30 minutes so Mnemo chats better.'],
  ['⌘K', 'jumps to the chat box from anywhere.'],
  ['⌘B', 'shows or hides the browser. ⌘\\ does the same for the sidebar.'],
  ['Drag', 'the dividers to resize panels. Double-click a divider to reset it.'],
  ['↑', 'in an empty message box brings back your last message.'],
  ['Drop a folder', 'onto the chat and Mnemo learns every file inside it.'],
  ['/image a cat astronaut', 'makes a picture with a Studio model, fully offline.'],
  ['Mnemo Code', 'Partial access is the sweet spot: it reads freely and asks before changing anything.'],
  ['⌘Z', 'in Mnemo Code undoes its last task. Every change is backed up first.'],
  ['/read, /find, /run', 'in Mnemo Code work instantly, even before the model has learned tool use.'],
  ['Teach Mnemo Code', 'runs a practice course so its own model learns to read, write and run things.'],
  ['Learn this page', 'saves whatever is in the browser to memory and training.'],
  ['Remove', 'in Memory makes Mnemo stop using a page in its replies.'],
  ['/remember', 'saves a note it can recall later, like “/remember my wifi is on floor 2”.'],
  ['/calc 2^10', 'and /define serendipity are built-in plugins. Write your own in ~/.mnemo/plugins.'],
  ['Custom modes', 'let you point Mnemo at your own favorite sites (Settings → Custom modes).'],
  ['mnemo headless', 'keeps it learning in the background with no window open.'],
  ['Settings → Hardware', 'picks the exact GPU, precision, layers and batch size.'],
  ['Double-click', 'a chat title to rename it. The ↓ button exports it as Markdown.'],
  ['Esc', 'stops a reply or a Mnemo Code task.'],
  ['Green lines', 'on the loss chart mark the moments Mnemo grew a bigger brain.'],
  ['Studio', 'models marked Non-commercial are for personal and research use only.'],
  ['/tips', 'shows every tip at once.'],
];
const ACH = {
  first_chat: '💬 First words: you said hello to your AI.',
  first_code: '🛠️ Pair programmer: Mnemo Code finished its first task.',
  first_creation: '🎨 Artist: your first Studio creation.',
  grew: '🌱 Growth spurt: Mnemo grew a bigger brain.',
  billion: '🧠 Billion-parameter mind: you raised a 1B+ model.',
  konami: '🕹️ ↑↑↓↓←→←→BA: neural fireworks unlocked.',
  dreamer: '🌈 Dreamer: you found dream mode.',
  night_owl: '🦉 Night owl: chatting with Mnemo after 2 AM.',
};
function achieve(key) {
  let got = {};
  try { got = JSON.parse(localStorage.getItem('mnemo-ach') || '{}'); } catch {}
  if (got[key]) return;
  got[key] = Date.now();
  try { localStorage.setItem('mnemo-ach', JSON.stringify(got)); } catch {}
  toast('Achievement · ' + ACH[key]); sfx('chime');
}

// --- tiny synthesized sound effects (no files) -------------------------------------------
let actx;
function sfx(kind) {
  if (ui.sounds === false) return;
  try {
    actx = actx || new AudioContext();
    const t = actx.currentTime, o = actx.createOscillator(), g = actx.createGain();
    o.connect(g); g.connect(actx.destination);
    const notes = { chime: [880, 1320], pop: [520, 780], boom: [180, 60] }[kind] || [600, 900];
    o.type = kind === 'boom' ? 'triangle' : 'sine';
    o.frequency.setValueAtTime(notes[0], t); o.frequency.exponentialRampToValueAtTime(notes[1], t + .15);
    g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(.08, t + .02); g.gain.exponentialRampToValueAtTime(.0001, t + .35);
    o.start(t); o.stop(t + .4);
  } catch {}
}

// --- neural fireworks -----------------------------------------------------------------------
function fireworks(seconds = 4) {
  const c = document.createElement('canvas'); c.id = 'fx'; document.body.appendChild(c);
  const x = c.getContext('2d'), D = devicePixelRatio || 1;
  c.width = innerWidth * D; c.height = innerHeight * D;
  const accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#7c5cff';
  const parts = [];
  const burst = () => {
    const cx = Math.random() * c.width, cy = Math.random() * c.height * .6, n = 40;
    for (let i = 0; i < n; i++) { const a = (i / n) * 6.283, s = (2 + Math.random() * 3) * D;
      parts.push({ x: cx, y: cy, vx: Math.cos(a) * s, vy: Math.sin(a) * s, life: 1, hue: Math.random() < .5 ? accent : '#3ecf8e' }); }
    sfx('boom');
  };
  const end = Date.now() + seconds * 1000; let last = 0;
  (function tick(ts) {
    if (ts - last > 450 && Date.now() < end) { burst(); last = ts; }
    x.clearRect(0, 0, c.width, c.height);
    for (const p of parts) {
      p.x += p.vx; p.y += p.vy; p.vy += .05 * D; p.life -= .012;
      if (p.life > 0) { x.globalAlpha = p.life; x.fillStyle = p.hue; x.beginPath(); x.arc(p.x, p.y, 2 * D, 0, 7); x.fill();
        for (const q of parts) if (q !== p && q.life > 0 && Math.abs(q.x - p.x) < 30 * D && Math.abs(q.y - p.y) < 30 * D) {
          x.strokeStyle = p.hue; x.globalAlpha = p.life * .15; x.beginPath(); x.moveTo(p.x, p.y); x.lineTo(q.x, q.y); x.stroke(); break; } }
    }
    if (Date.now() < end + 2500) requestAnimationFrame(tick); else c.remove();
  })(0);
}

// --- chat easter eggs + /tips ------------------------------------------------------------------
function reply(text) { push({ kind: 'user', text: window.__lastFun }); push({ kind: 'mnemo', text }); }
window.fun = {
  intercept(text) {
    const t = text.toLowerCase().replace(/[!?.]+$/, '').trim();
    window.__lastFun = text;
    if (t === '/tips' || t === 'tips') {
      push({ kind: 'user', text });
      push({ kind: 'tool', text: '**Tips & tricks**\n' + TIPS.map(([k, v]) => `**${k}** ${v}`).join('\n') });
      return true;
    }
    if (t === '/tutorial' || t === '/tour') { startTour(); return true; }
    if (t === 'sudo make me a sandwich') { reply('Okay. 🥪'); return true; }
    if (t === 'make me a sandwich') { reply('What? Make it yourself.'); return true; }
    if (t === '/coffee') { reply('   ( (\n    ) )\n  ........\n  |      |]\n  \\      /\n   `----\'\nOne coffee, brewed by a neural net. Careful, it\'s hot.'); sfx('pop'); return true; }
    if (t === '/42' || t === 'what is the meaning of life') { reply('42. I\'m still training on what the question was.'); return true; }
    if (t === '/flip') { reply('(╯°□°)╯︵ ┻━┻'); return true; }
    if (t === '/unflip') { reply('┬─┬ノ( º _ ºノ)'); return true; }
    if (t === '/party' || t === '/fireworks') { reply('🎉'); fireworks(3); return true; }
    if (t === 'open the pod bay doors') { reply(`I'm sorry, Dave. I'm afraid I can't do that. (Kidding. I'm ${name()}, and I don't have pod bay doors.)`); return true; }
    if (t === 'do a barrel roll') { document.body.animate([{ transform: 'rotate(0)' }, { transform: 'rotate(360deg)' }], { duration: 1100, easing: 'ease-in-out' }); return true; }
    if (/^(are you|r u) (sentient|conscious|alive)$/.test(t)) { reply('I\'m a few million numbers doing their best. Ask me again after a few more growth spurts.'); return true; }
    if (new Date().getHours() >= 2 && new Date().getHours() < 5) achieve('night_owl');
    if (!text.startsWith('/')) achieve('first_chat');
    return false;
  },
  codeIntercept(text) {
    const t = text.toLowerCase().trim();
    if (t === 'hello world' || t === 'hello, world') {
      codeNote('The oldest program in the book. 👋 Try: **create hello.py that prints hello world**');
      return true;
    }
    if (t === 'rm -rf /' || t === '/run rm -rf /' || t === 'sudo rm -rf /') {
      codeNote("Nice try. 🙂 That one is blocked in every mode, and I'm locked to this folder anyway.");
      return true;
    }
    return false;
  },
  achieve, fireworks, sfx,
};

// --- rotating tips ------------------------------------------------------------------------
function tipText() { const [k, v] = TIPS[Math.floor(Math.random() * TIPS.length)]; return `Tip · <b>${esc(k)}</b> ${esc(v)}`; }
function rotateTips() {
  const hero = $('#hero-sub');
  if (hero && !$('#tip-hero')) hero.insertAdjacentHTML('afterend', '<div class="tip-hero" id="tip-hero"></div>');
  $('#tip-hero').innerHTML = tipText();
  const ct = $('#code-tip'); ct.style.opacity = 0;
  setTimeout(() => { ct.innerHTML = tipText(); ct.style.opacity = 1; }, 400);
}
rotateTips(); setInterval(rotateTips, 22000);

// --- seasonal greetings ------------------------------------------------------------------------
(function seasonal() {
  const d = new Date(), md = `${d.getMonth() + 1}-${d.getDate()}`;
  const special = { '10-31': 'Happy Halloween 🎃', '12-25': 'Merry Christmas 🎄', '1-1': 'Happy New Year 🎆', '3-14': 'Happy π day 🥧',
    '5-4': 'May the 4th be with you', '2-14': 'Happy Valentine\'s Day 💜' }[md];
  if (d.getHours() === 3 && d.getMinutes() === 14) setTimeout(() => toast('3:14. π time. 🥧'), 2000);
  if (special) setTimeout(() => { const h = $('#hero-title'); if (h) h.textContent = special; }, 300);
})();

// --- Konami code → neural fireworks ------------------------------------------------------------------
const KONAMI = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a'];
let kpos = 0;
document.addEventListener('keydown', (e) => {
  kpos = e.key === KONAMI[kpos] ? kpos + 1 : (e.key === KONAMI[0] ? 1 : 0);
  if (kpos === KONAMI.length) { kpos = 0; fireworks(5); achieve('konami'); }
});

// --- click the logo 7 times → dream mode ---------------------------------------------------------------
let logoClicks = 0, logoTimer;
document.querySelector('.brand')?.addEventListener('click', () => {
  logoClicks++; clearTimeout(logoTimer); logoTimer = setTimeout(() => { logoClicks = 0; }, 1500);
  if (logoClicks === 7) {
    logoClicks = 0; document.body.classList.add('dream'); achieve('dreamer');
    toast(`${name()} is dreaming… 🌈`);
    setTimeout(() => document.body.classList.remove('dream'), 8000);
  }
});

// --- achievements from app events -------------------------------------------------------------------
const _onTrainer = onTrainer;
let lastStage = null;
onTrainer = function (s) {
  _onTrainer(s);
  if (lastStage !== null && s.stage > lastStage) { achieve('grew'); fireworks(2); }
  lastStage = s.stage;
  if (s.params >= 1e9) achieve('billion');
};
const _onStudio = onStudio;
onStudio = function (m) { _onStudio(m); if (m.stage === 'done') achieve('first_creation'); };
const _onCode = onCode;
onCode = function (m) { _onCode(m); if (m.stage === 'end' && m.ok) { achieve('first_code'); sfx('pop'); } };
