// A 60-second animated tour of Mnemo, rendered live in the browser (no video file).
// Every frame is a pure function of time, so the timeline can be scrubbed. Captions on, sound effects optional.

const $ = (s, r = document) => r.querySelector(s);
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const ease = (x) => 1 - Math.pow(1 - clamp(x), 3);
const esc = (s) => s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));

const ICON = "icon.png";
const SIDEBAR = (active) => `<aside class="t-side"><div class="t-brand"><img src="${ICON}" alt="">Mnemo</div>
  ${["New chat", "Learn", "Mnemo Code", "Studio", "Memory", "Settings"].map((n) => `<div class="t-nav ${n === active ? "on" : ""}">${n}</div>`).join("")}
  <div class="t-recents"><small>Recents</small><div>hi! how are you?</div><div>learn coding</div><div>hello.py</div></div>
  <div class="t-brain"><i></i><span><b id="t-size">12M parameters</b><small id="t-state">learning</small></span></div></aside>`;

// ---------------------------------------------------------------- scenes
const SCENES = [
  { d: 5, cap: "This is Mnemo: an AI you raise from nothing, on your own computer.",
    html: () => `<div class="t-title"><img src="${ICON}" alt=""><h3>mnemo</h3><p>raise an AI from nothing</p></div>`,
    render(t, el) { el.querySelector(".t-title").style.opacity = ease(t * 3); el.querySelector(".t-title img").style.transform = `scale(${0.8 + 0.2 * ease(t * 2)}) rotate(${(1 - ease(t * 2)) * -20}deg)`; },
    sfx: [[0.2, "whoosh"], [1.2, "chime"]] },

  { d: 8, cap: "First, design its brain: how big it starts, how much it can remember.",
    html: () => `<div class="t-win">${SIDEBAR("")}<main class="t-main center"><div class="t-wiz"><div class="t-steps"><i class="on"></i><i class="on"></i><i></i><i></i></div>
      <h4>Design your AI</h4>
      <label>Starting size <b id="w1"></b></label><div class="t-range"><i id="r1"></i></div>
      <label>Grow up to <b id="w2"></b></label><div class="t-range"><i id="r2"></i></div>
      <label>Context length <b id="w3"></b></label><div class="t-range"><i id="r3"></i></div>
      <div class="t-est" id="west"></div><div class="t-cursor" id="cur"></div></div></main></div>`,
    render(t, el) {
      const a = ease((t - .1) / .3), b = ease((t - .35) / .3), c = ease((t - .6) / .25);
      const sizes = ["12M", "39M", "99M"], grow = ["99M", "210M", "545M", "1.04B"], ctx = ["2,048", "8,192", "32,768"];
      $("#w1", el).textContent = sizes[Math.round(a * 2)]; $("#r1", el).style.width = 20 + a * 25 + "%";
      $("#w2", el).textContent = grow[Math.round(b * 3)]; $("#r2", el).style.width = 30 + b * 50 + "%";
      $("#w3", el).textContent = ctx[Math.round(c * 2)] + " tokens"; $("#r3", el).style.width = 20 + c * 45 + "%";
      $("#west", el).innerHTML = `Day one: <b>${sizes[Math.round(a * 2)]}</b> parameters. Grows to <b>${grow[Math.round(b * 3)]}</b> as it learns.`;
      const cy = t < .35 ? 32 : t < .6 ? 50 : 68, cx = 30 + (t < .35 ? a : t < .6 ? b : c) * 40;
      Object.assign($("#cur", el).style, { left: cx + "%", top: cy + "%" });
    },
    sfx: [[0.2, "click"], [2.9, "click"], [4.9, "click"]] },

  { d: 8, cap: "It learns by reading. Watch the loss fall as it gets smarter, then grow.",
    html: () => `<div class="t-win">${SIDEBAR("Learn")}<main class="t-main"><h4>Learn</h4>
      <div class="t-stats"><div><small>Parameters</small><b id="p">12M</b></div><div><small>Tokens read</small><b id="tk">0</b></div><div><small>Loss</small><b id="l">10.4</b></div></div>
      <svg class="t-chart" viewBox="0 0 400 120" preserveAspectRatio="none"><path id="lc"/><line id="grow" x1="0" x2="0" y1="0" y2="120"/></svg>
      <div class="t-sample" id="smp"></div></main></div>`,
    render(t, el) {
      const n = 60, pts = [];
      for (let i = 0; i <= n * t; i++) { const x = i / n; const y = 10 + 95 * Math.exp(-x * 3.2) + (x > .62 ? 6 * Math.exp(-(x - .62) * 12) : 0) + Math.sin(i * 1.7) * 2; pts.push(`${i ? "L" : "M"}${x * 400},${y}`); }
      $("#lc", el).setAttribute("d", pts.join(" "));
      const grown = t > .62;
      $("#grow", el).setAttribute("x1", 248); $("#grow", el).setAttribute("x2", 248); $("#grow", el).style.opacity = grown ? 1 : 0;
      $("#p", el).textContent = grown ? "39M" : "12M"; $("#t-size").textContent = (grown ? "39M" : "12M") + " parameters";
      $("#tk", el).textContent = (t * 4.2).toFixed(1) + "M";
      $("#l", el).textContent = (10.4 * Math.exp(-t * 2.4) + 1.2).toFixed(2);
      const s = t < .3 ? "TheGP ottom ·fdn widow Kraft ¬¬" : t < .62 ? "The Python standard library. Subs: Oers, some of the and" : "The library holds many books, and people read them every day.";
      $("#smp", el).textContent = "What it writes now › " + s;
    },
    sfx: [[5, "chime"]] },

  { d: 9, cap: "Chat with it. After a short conversation course, it actually talks back.",
    html: () => `<div class="t-win">${SIDEBAR("New chat")}<main class="t-main chat"><div class="t-thread" id="th"></div>
      <div class="t-composer"><span id="ci"></span><i class="t-send"></i></div></main></div>`,
    render(t, el) {
      const T = t * 9, msgs = [["u", "hi! how are you?", .4, 2.2], ["a", "I'm doing well, thanks for asking! How about you?", 2.6, 4.6],
        ["u", "tell me a joke", 5, 6.2], ["a", "Why did the computer go to the doctor? It had a virus!", 6.5, 8.6]];
      let html = "", typing = "";
      for (const [who, txt, s, e] of msgs) {
        if (who === "u" && T >= s && T < e) typing = txt.slice(0, Math.floor((T - s) / (e - s - .3) * txt.length));
        if (T >= e - (who === "u" ? .3 : 0) || (who === "a" && T >= s)) {
          const shown = who === "a" ? txt.slice(0, Math.floor(clamp((T - s) / (e - s)) * txt.length)) : txt;
          html += `<div class="t-msg ${who}">${who === "a" ? `<img src="${ICON}" alt="">` : ""}<span>${esc(shown)}</span></div>`;
        }
      }
      $("#th", el).innerHTML = html; $("#ci", el).textContent = typing || "Message Mnemo…"; $("#ci", el).classList.toggle("ph", !typing);
    },
    sfx: [[.5, "type", 1.6], [2.2, "pop"], [5.1, "type", 1.0], [6.2, "pop"]] },

  { d: 7, cap: "/learn coding: it finds the best pages on the web and studies them.",
    html: () => `<div class="t-win">${SIDEBAR("New chat")}<main class="t-main chat narrow"><div class="t-thread"><div class="t-msg u"><span>/learn coding</span></div>
      <div class="t-tool" id="tl"></div></div></main><section class="t-browser"><div class="t-url" id="url"></div><div class="t-page" id="pg"></div></section></div>`,
    render(t, el) {
      const pages = ["Computer programming", "Python tutorial", "JavaScript guide", "Rust book", "Stack Overflow: async/await", "Clean code"];
      const n = Math.floor(clamp((t - .15) / .8) * pages.length);
      $("#tl", el).innerHTML = t < .15 ? "🔎 Searching…" : `📚 Learning <b>coding</b>: found 36 pages. Reading ${n} / 60…`;
      $("#url", el).textContent = ["en.wikipedia.org/wiki/Computer_programming", "docs.python.org/3/tutorial", "developer.mozilla.org/docs/JavaScript", "doc.rust-lang.org/book",
        "stackoverflow.com/questions/…", "en.wikibooks.org/wiki/Clean_code"][Math.min(5, n)];
      $("#pg", el).innerHTML = `<h5>${pages[Math.min(5, n)]}</h5>` + "<i></i>".repeat(7) + pages.slice(0, n).map((p, i) => `<div class="fly" style="--i:${i}">+ ${p}</div>`).join("");
    },
    sfx: [[1.1, "whoosh"], [2.3, "tick"], [3.4, "tick"], [4.5, "tick"], [5.6, "tick"]] },

  { d: 14, cap: ["Mnemo Code: give it a folder and a job.", "It thinks out loud, then proposes a change you can see.", "You approve, deny, or give it full access. Every change can be undone."],
    html: () => `<div class="t-win">${SIDEBAR("Mnemo Code")}<main class="t-main code"><div class="t-codebar"><span class="chip">📁 my-project</span>
      <span class="seg"><i id="pa">Ask</i><i id="pp" class="on">Partial</i><i id="pf">Full access</i></span></div>
      <div class="t-codebody"><div class="t-tree"><div>📁 src</div><div>📝 README.md</div><div id="newf" class="newf">🐍 hello.py</div></div>
      <div class="t-codemain" id="cm"></div></div></main></div>`,
    render(t, el) {
      const T = t * 14, task = "create hello.py that prints hello world";
      let h = `<div class="t-msg u"><span>${esc(T < 2 ? task.slice(0, Math.floor(T / 1.8 * task.length)) : task)}</span></div>`;
      if (T > 2.2) {
        const th = "I need a new Python file with one print statement.";
        h += `<div class="t-think"><b class="${T < 5 ? "shim" : ""}">${T < 4.2 ? "Thinking" : T < 5 ? "Writing" : "Thought for a moment"}</b><p>${esc(th.slice(0, Math.floor(clamp((T - 2.4) / 1.6) * th.length)))}</p></div>`;
      }
      if (T > 5) {
        const ok = T > 7.4;
        h += `<div class="t-card ${ok ? "ok" : "wait"}"><div class="t-ch"><em>write</em> Write hello.py <span>+2 −0</span><s>${ok ? "✓" : ""}</s></div>
          <pre><span class="add">+print("hello world")</span></pre>${ok ? "" : `<div class="t-btns"><u class="${T > 6.8 ? "press" : ""}">Approve ↵</u><u>Deny</u><u>Always allow</u></div>`}</div>`;
      }
      if (T > 8.6) h += `<div class="t-msg u"><span>/run python3 hello.py</span></div>`;
      if (T > 9.6) h += `<div class="t-card ok"><div class="t-ch"><em class="run">run</em> Run python3 hello.py<s>✓</s></div><pre>exit code 0\nhello world</pre></div>`;
      if (T > 11) h += `<div class="t-done">✓ Created hello.py, which prints "hello world". <span>↩ Undo</span></div>`;
      $("#cm", el).innerHTML = h;
      $("#newf", el).classList.toggle("in", T > 7.4);
      const cur = $(".t-cursor", el) || el.querySelector(".t-win").appendChild(Object.assign(document.createElement("div"), { className: "t-cursor" }));
      Object.assign(cur.style, T > 5.8 && T < 7.6 ? { left: "47%", top: "71%", opacity: 1 } : { left: "60%", top: "90%", opacity: 0 });
    },
    sfx: [[.2, "type", 1.6], [2.3, "whoosh"], [6.9, "click"], [7.4, "chime"], [8.7, "type", .6], [9.7, "pop"], [11, "chime"]] },

  { d: 6, cap: "Studio: run open image, video and 3D models locally. Licenses shown up front.",
    html: () => `<div class="t-win">${SIDEBAR("Studio")}<main class="t-main"><h4>Studio <span class="seg mini"><i class="on">Image</i><i>Video</i><i>3D</i></span></h4>
      <div class="t-gallery">${[0, 1, 2, 3, 4, 5].map((i) => `<div class="g g${i}"><b></b><small>${["SSD-1B · Commercial OK", "DreamShaper 8", "Wan 2.1 · video", "Shap-E · 3D", "SD 1.5", "SDXL Turbo · research"][i]}</small></div>`).join("")}</div></main></div>`,
    render(t, el) { el.querySelectorAll(".g").forEach((g, i) => { const k = ease((t - i * .1) / .25); g.style.opacity = k; g.style.transform = `translateY(${(1 - k) * 18}px) scale(${.96 + .04 * k})`; }); },
    sfx: [[.3, "pop"], [.9, "pop"], [1.5, "pop"], [2.1, "pop"]] },

  { d: 3, cap: "One command to install. macOS, Windows and Linux.",
    html: () => `<div class="t-end"><img src="${ICON}" alt=""><h3>mnemo</h3><code>curl -fsSL …/install.sh | bash</code><p>Made by Virat Kaukuntla · mnemo.web.app</p></div>`,
    render(t, el) { el.querySelector(".t-end").style.opacity = ease(t * 3); },
    sfx: [[.1, "chime"]] },
];
const TOTAL = SCENES.reduce((a, s) => a + s.d, 0);   // 60 s
let starts = [], acc = 0;
for (const s of SCENES) { starts.push(acc); acc += s.d; }

// ---------------------------------------------------------------- sound effects (synthesized, no files)
let ctx, muted = true;
function noise(dur, freq, q = 1, gain = .05) {
  const len = Math.floor(ctx.sampleRate * dur), buf = ctx.createBuffer(1, len, ctx.sampleRate), d = buf.getChannelData(0);
  for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len);
  const src = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
  src.buffer = buf; f.type = "bandpass"; f.frequency.value = freq; f.Q.value = q; g.gain.value = gain;
  src.connect(f); f.connect(g); g.connect(ctx.destination); src.start();
  return f;
}
function tone(f1, f2, dur = .3, gain = .06, type = "sine") {
  const o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime;
  o.type = type; o.frequency.setValueAtTime(f1, t); o.frequency.exponentialRampToValueAtTime(f2, t + dur * .5);
  g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(gain, t + .015); g.gain.exponentialRampToValueAtTime(.0001, t + dur);
  o.connect(g); g.connect(ctx.destination); o.start(t); o.stop(t + dur + .05);
}
function play(kind, len = 0) {
  if (muted) return;
  ctx = ctx || new AudioContext();
  if (kind === "click") { noise(.03, 3000, 2, .12); tone(1200, 900, .05, .03); }
  else if (kind === "tick") tone(1500, 1700, .06, .025);
  else if (kind === "pop") tone(500, 900, .12, .05);
  else if (kind === "chime") { tone(880, 880, .5, .045); setTimeout(() => !muted && tone(1320, 1320, .6, .035), 110); }
  else if (kind === "whoosh") { const f = noise(.5, 400, .7, .06); f.frequency.exponentialRampToValueAtTime(3000, ctx.currentTime + .45); }
  else if (kind === "type") { for (let i = 0; i < len * 12; i++) setTimeout(() => !muted && noise(.012, 2500 + Math.random() * 2000, 3, .05), i * 83 + Math.random() * 30); }
}

// ---------------------------------------------------------------- player
export function mountTour(root) {
  root.innerHTML = `<div class="tour-stage" id="stage"><div class="tour-scene" id="scene"></div><div class="tour-cap" id="cap"></div>
      <button class="tour-big" id="big" aria-label="Play">▶</button></div>
    <div class="tour-ctrl"><button id="pp" aria-label="Play or pause">▶</button><div class="tour-bar" id="bar"><i id="fill"></i>
      ${SCENES.map((s, i) => `<b style="left:${starts[i] / TOTAL * 100}%"></b>`).join("")}</div>
      <span class="tour-time" id="time">0:00 / 1:00</span><button id="snd" aria-label="Sound">🔇 Sound</button></div>`;
  const stage = $("#stage", root), scene = $("#scene", root), cap = $("#cap", root);
  let t = 0, playing = false, last = 0, cur = -1, lastFx = 0;
  new ResizeObserver(() => { stage.style.fontSize = stage.clientWidth / 64 + "px"; }).observe(stage);

  function draw(time, fx) {
    const i = Math.max(0, starts.findLastIndex((s) => s <= time)), s = SCENES[i], local = (time - starts[i]) / s.d;
    if (i !== cur) { cur = i; scene.innerHTML = s.html(); scene.firstElementChild?.classList.add("enter"); }
    s.render(clamp(local), scene);
    const caps = Array.isArray(s.cap) ? s.cap : [s.cap];
    const c = caps[Math.min(caps.length - 1, Math.floor(clamp(local) * caps.length))];
    if (cap.textContent !== c) { cap.textContent = c; cap.classList.remove("show"); void cap.offsetWidth; cap.classList.add("show"); }
    if (fx) for (const [at, kind, len] of s.sfx || []) { const abs = starts[i] + at; if (abs > lastFx && abs <= time) play(kind, len); }
    lastFx = time;
    $("#fill", root).style.width = time / TOTAL * 100 + "%";
    const f = (x) => `${Math.floor(x / 60)}:${String(Math.floor(x % 60)).padStart(2, "0")}`;
    $("#time", root).textContent = `${f(time)} / ${f(TOTAL)}`;
  }
  function loop(ts) {
    if (!playing) return;
    const dt = last ? (ts - last) / 1000 : 0; last = ts;
    t = Math.min(TOTAL, t + dt);
    draw(t, true);
    if (t >= TOTAL) { setPlaying(false); $("#big", root).textContent = "↻"; $("#big", root).classList.remove("hide"); return; }
    requestAnimationFrame(loop);
  }
  function setPlaying(p) {
    playing = p; last = 0; $("#pp", root).textContent = p ? "❚❚" : "▶";
    $("#big", root).classList.toggle("hide", p);
    if (p) { if (t >= TOTAL) { t = 0; lastFx = 0; } requestAnimationFrame(loop); }
  }
  $("#pp", root).onclick = () => setPlaying(!playing);
  $("#big", root).onclick = () => setPlaying(true);
  stage.onclick = (e) => { if (e.target === stage || e.target.closest(".tour-scene")) setPlaying(!playing); };
  $("#snd", root).onclick = () => { muted = !muted; $("#snd", root).textContent = muted ? "🔇 Sound" : "🔊 Sound"; if (!muted) { ctx = ctx || new AudioContext(); ctx.resume(); play("pop"); } };
  const bar = $("#bar", root);
  const seek = (e) => { const r = bar.getBoundingClientRect(); t = clamp((e.clientX - r.left) / r.width) * TOTAL; lastFx = t; draw(t, false); };
  bar.addEventListener("pointerdown", (e) => { seek(e); const mv = (ev) => seek(ev); addEventListener("pointermove", mv); addEventListener("pointerup", () => removeEventListener("pointermove", mv), { once: true }); });
  root.addEventListener("keydown", (e) => { if (e.key === " ") { e.preventDefault(); setPlaying(!playing); } });
  draw(0, false);
  // Autoplay (muted) the first time it scrolls into view.
  let auto = false;
  new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting && !auto && !matchMedia("(prefers-reduced-motion: reduce)").matches) { auto = true; setPlaying(true); }
    if (!e.isIntersecting && playing) setPlaying(false);
  }), { threshold: .5 }).observe(stage);
}
