import { firebaseConfig } from "./firebase-config.js";
import { mountTour } from "./tour.js";

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const RAW = "https://raw.githubusercontent.com/learningnihongo934-byte/mnemo/main";
const CMDS = {
  unix: { prompt: "$", cmd: `curl -fsSL ${RAW}/install.sh | bash`, hint: "Paste into Terminal (macOS or Linux). Takes a few minutes. Then type <code>mnemo</code>." },
  win: { prompt: "PS>", cmd: `irm ${RAW}/install.ps1 | iex`, hint: "Paste into PowerShell. Installs Git, Node and Python if needed, then adds Mnemo to the Start menu." },
};
const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;

function toast(t) { const el = $("#toast"); el.textContent = t; el.classList.add("show"); clearTimeout(el._t); el._t = setTimeout(() => el.classList.remove("show"), 2400); }

mountTour(document.querySelector("#tour"));

// ------------------------------------------------------------- nav
const nav = $("#nav");
addEventListener("scroll", () => nav.classList.toggle("scrolled", scrollY > 30), { passive: true });

// ------------------------------------------------------------- installer (OS-aware, typed)
let os = /Win/.test(navigator.platform) || /Windows/.test(navigator.userAgent) ? "win" : "unix", typing;
function setOS(o, animate = true) {
  os = o;
  $$(".os-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.os === o));
  const c = CMDS[o], code = $("#cmd");
  $("#prompt").textContent = c.prompt; $("#os-hint").innerHTML = c.hint;
  clearInterval(typing); code.classList.remove("typed");
  if (!animate || reduced) { code.textContent = c.cmd; code.classList.add("typed"); return; }
  let i = 0; code.textContent = "";
  typing = setInterval(() => { code.textContent = c.cmd.slice(0, ++i); if (i >= c.cmd.length) { clearInterval(typing); setTimeout(() => code.classList.add("typed"), 900); } }, 18);
}
$$(".os-tabs button").forEach((b) => b.onclick = () => setOS(b.dataset.os));
setTimeout(() => setOS(os), 700);
async function copyCmd(btn) {
  await navigator.clipboard.writeText(CMDS[os].cmd);
  if (btn) { const s = btn.querySelector("span") || btn; const t = s.textContent; s.textContent = "Copied ✓"; btn.classList.add("done");
    setTimeout(() => { s.textContent = t; btn.classList.remove("done"); }, 1600); }
  toast("Install command copied. Paste it into " + (os === "win" ? "PowerShell" : "Terminal") + ".");
}
$("#copy").onclick = () => copyCmd($("#copy"));
$("#cta-install").onclick = () => copyCmd($("#cta-install"));

// ------------------------------------------------------------- living neural net (grows with scroll, reacts to cursor)
const cv = $("#net"), ctx = cv.getContext("2d");
let W, H, DPR, nodes = [], mouse = { x: -1e4, y: -1e4 }, growth = 0;
function resize() {
  DPR = Math.min(2, devicePixelRatio || 1); W = cv.width = innerWidth * DPR; H = cv.height = innerHeight * DPR;
  const target = Math.round(Math.min(150, innerWidth * innerHeight / 9000));
  while (nodes.length < target) nodes.push({ x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - .5) * .25, vy: (Math.random() - .5) * .25, r: Math.random() * 1.6 + .6, born: Math.random() });
  nodes.length = target;
}
addEventListener("resize", resize); resize();
addEventListener("pointermove", (e) => { mouse.x = e.clientX * DPR; mouse.y = e.clientY * DPR; }, { passive: true });
addEventListener("pointerleave", () => { mouse.x = mouse.y = -1e4; });
function frame() {
  ctx.clearRect(0, 0, W, H);
  const alive = nodes.filter((n) => n.born <= .25 + growth * .75), link = (110 + growth * 60) * DPR;
  for (const n of alive) {
    const dx = n.x - mouse.x, dy = n.y - mouse.y, d2 = dx * dx + dy * dy, R = 160 * DPR;
    if (d2 < R * R) { const f = (1 - Math.sqrt(d2) / R) * .9; n.vx += dx / Math.sqrt(d2 + 1) * f * .06; n.vy += dy / Math.sqrt(d2 + 1) * f * .06; }
    n.vx *= .985; n.vy *= .985; n.x += n.vx + (Math.random() - .5) * .05; n.y += n.vy + (Math.random() - .5) * .05;
    if (n.x < 0 || n.x > W) n.vx *= -1; if (n.y < 0 || n.y > H) n.vy *= -1;
  }
  for (let i = 0; i < alive.length; i++) for (let j = i + 1; j < alive.length; j++) {
    const a = alive[i], b = alive[j], dx = a.x - b.x, dy = a.y - b.y, d = Math.hypot(dx, dy);
    if (d < link) {
      const near = Math.max(0, 1 - Math.hypot((a.x + b.x) / 2 - mouse.x, (a.y + b.y) / 2 - mouse.y) / (220 * DPR));
      ctx.strokeStyle = near > 0 ? `rgba(212,255,58,${(1 - d / link) * (.18 + near * .5)})` : `rgba(242,239,230,${(1 - d / link) * .12})`;
      ctx.lineWidth = DPR * .7; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
    }
  }
  for (const n of alive) { ctx.fillStyle = "rgba(242,239,230,.55)"; ctx.beginPath(); ctx.arc(n.x, n.y, n.r * DPR, 0, 7); ctx.fill(); }
  if (!reduced) requestAnimationFrame(frame);
}
frame();

// Parameter ticker: the "brain" grows as you scroll down the page.
const STAGES = [12041216, 39061504, 98966272, 210178048, 545292288, 1035689984];
let shown = STAGES[0];
function onScroll() {
  const p = Math.min(1, scrollY / Math.max(1, document.body.scrollHeight - innerHeight));
  growth = p;
  const target = STAGES[0] * Math.pow(STAGES[5] / STAGES[0], p);
  shown += (target - shown) * .2;
  $("#param-count").textContent = Math.round(shown).toLocaleString("en-US");
}
setInterval(onScroll, 50);

// ------------------------------------------------------------- reveal on scroll
const io = new IntersectionObserver((es) => es.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } }), { threshold: .14 });
$$(".reveal").forEach((el, i) => { el.style.setProperty("--d", (i % 4) * .07 + "s"); io.observe(el); });

// Spotlight that follows the cursor on cards.
$$("[data-spot]").forEach((el) => el.addEventListener("pointermove", (e) => {
  const r = el.getBoundingClientRect(); el.style.setProperty("--mx", e.clientX - r.left + "px"); el.style.setProperty("--my", e.clientY - r.top + "px");
}));

// Seamless marquee.
$("#track").innerHTML += $("#track").innerHTML;

// ------------------------------------------------------------- the growing-up story (real outputs from Mnemo's tests)
const CH = [
  { title: "mnemo · day 0", params: "12M", loss: "10.37", read: "0 tokens", curve: [100, 100, 99, 99, 98],
    out: [["a", "TheGP undefined ottom ottom  ·fdn ¬¬ ‡ widow undefined Kraft"]] },
  { title: "mnemo · 40 minutes", params: "12M", loss: "4.95", read: "3.1M tokens", curve: [100, 80, 62, 54, 50, 47],
    out: [["a", "The Python standard library — Python 3.15\nSubs: Oers, szipes some of the and also independent\nediti//C). El. FA—kmandated on:ps—"]] },
  { title: "mnemo · after 8 min of conversation practice", params: "12M", loss: "0.49", read: "4.0M tokens", curve: [100, 70, 48, 30, 18, 12, 9, 8],
    out: [["u", "you  › hi"], ["a", "mnemo › Hey! What's on your mind?"], ["u", "you  › what's your name?"], ["a", "mnemo › My name is Mnemo. I'm a small AI that learns from what I read."],
          ["u", "you  › tell me a joke"], ["a", "mnemo › Why did the computer go to the doctor? It had a virus!"]] },
  { title: "mnemo · grown", params: "1.04B", loss: "2.31", read: "10.4B tokens", curve: [100, 66, 50, 44, 41, 38, 33, 31, 29, 28, 27],
    out: [["a", "stage 0 →   12M  ██░░░░░░░░\nstage 2 →   99M  ████░░░░░░\nstage 4 →  545M  ███████░░░\nstage 5 →  1.04B ██████████\n\ngrowth is function-preserving:\nnothing it learned is lost."]] },
];
let chNow = -1, outTimer;
function curve(pts) {
  const n = pts.length - 1;
  return pts.map((v, i) => `${i ? "L" : "M"}${(i / n) * 300},${8 + (1 - v / 100) * 56}`).join(" ");
}
function showChapter(i) {
  if (i === chNow) return; chNow = i;
  const c = CH[i];
  $("#t-title").textContent = c.title; $("#t-params").textContent = c.params; $("#t-loss").textContent = c.loss; $("#t-read").textContent = c.read;
  $("#t-curve").setAttribute("d", curve(c.curve));
  $$(".chapter").forEach((el) => el.classList.toggle("on", +el.dataset.ch === i));
  const out = $("#t-out"); clearInterval(outTimer); out.innerHTML = "";
  const full = c.out.map(([k, t]) => [k, t + "\n"]);
  if (reduced) { out.innerHTML = full.map(([k, t]) => `<span class="${k}">${t.replace(/</g, "&lt;")}</span>`).join(""); return; }
  let li = 0, ci = 0, span = null;
  outTimer = setInterval(() => {
    if (li >= full.length) { clearInterval(outTimer); out.lastChild?.classList.remove("caret"); return; }
    if (!span) { span = document.createElement("span"); span.className = full[li][0] + " caret"; out.appendChild(span); }
    span.textContent = full[li][1].slice(0, ++ci);
    if (ci >= full[li][1].length) { span.classList.remove("caret"); span = null; li++; ci = 0; }
  }, i === 0 ? 28 : 14);
}
const chIO = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && showChapter(+e.target.dataset.ch)), { rootMargin: "-45% 0px -45% 0px" });
$$(".chapter").forEach((c) => chIO.observe(c));
showChapter(0);

// ------------------------------------------------------------- plugin code types itself when visible
const CODE = [["c", "# ~/.mnemo/plugins/hello.py\n"], ["k", "def "], ["", "register(mnemo):\n    @mnemo.command("], ["s", '"/hello"'], ["", ", "], ["s", '"say hello"'],
  ["", ")\n    "], ["k", "def "], ["", "hello(arg, ctx):\n        "], ["k", "return "], ["s", 'f"Hello, {arg or \'friend\'}!"']];
new IntersectionObserver((es, o) => es.forEach((e) => {
  if (!e.isIntersecting) return; o.disconnect();
  const el = $("#code"); let p = 0, c = 0;
  if (reduced) { el.innerHTML = CODE.map(([k, t]) => `<span class="${k}">${t}</span>`).join(""); return; }
  const t = setInterval(() => {
    if (p >= CODE.length) return clearInterval(t);
    if (c === 0) { const s = document.createElement("span"); s.className = CODE[p][0]; el.appendChild(s); }
    el.lastChild.textContent = CODE[p][1].slice(0, ++c);
    if (c >= CODE[p][1].length) { p++; c = 0; }
  }, 22);
}), { threshold: .4 }).observe($("#code"));

// ------------------------------------------------------------- Firebase: Google sign-in + Pro waitlist
const ready = firebaseConfig.apiKey && firebaseConfig.projectId;
let fb = null, user = null;
async function loadFirebase() {
  if (fb || !ready) return fb;
  const V = "11.0.2";
  const [{ initializeApp }, auth, store] = await Promise.all([
    import(`https://www.gstatic.com/firebasejs/${V}/firebase-app.js`),
    import(`https://www.gstatic.com/firebasejs/${V}/firebase-auth.js`),
    import(`https://www.gstatic.com/firebasejs/${V}/firebase-firestore.js`),
  ]);
  const app = initializeApp(firebaseConfig);
  fb = { auth, store, a: auth.getAuth(app), db: store.getFirestore(app) };
  auth.onAuthStateChanged(fb.a, (u) => { user = u; renderAuth(); });
  return fb;
}
function renderAuth() {
  $("#auth").querySelector(".me")?.remove();
  $("#signin").classList.toggle("hidden", !!user);
  if (!user) return;
  $("#auth").insertAdjacentHTML("beforeend", `<span class="me" style="display:flex;align-items:center;gap:8px">${user.photoURL ? `<img src="${user.photoURL}" alt="" referrerpolicy="no-referrer">` : ""}
    <button class="pill-btn" id="signout">Sign out</button></span>`);
  $("#signout").onclick = () => fb.auth.signOut(fb.a);
}
async function signIn() {
  if (!ready) { toast("Sign-in opens soon."); return; }
  const f = await loadFirebase();
  try { await f.auth.signInWithPopup(f.a, new f.auth.GoogleAuthProvider()); toast("Signed in"); }
  catch (e) { if (e.code !== "auth/popup-closed-by-user") toast("Sign-in failed: " + (e.code || e.message)); }
}
$("#signin").onclick = signIn;
$("#waitlist").onclick = async () => {
  if (!user) { await signIn(); if (!user) return; }
  await fb.store.setDoc(fb.store.doc(fb.db, "waitlist", user.uid), { email: user.email, name: user.displayName || "", joined: fb.store.serverTimestamp() });
  toast("You're on the Pro waitlist.");
};
if (ready) loadFirebase();
