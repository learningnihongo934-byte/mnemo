"""Chat: turns your messages into either browser/learning commands or a reply
written by Mnemo's own model (with relevant memories placed in its context)."""

from __future__ import annotations

import asyncio
import re
import threading
from urllib.parse import quote_plus

from types import SimpleNamespace

from . import basics, events, memory, modes, plugins, search, studio, tokenizer
from .browser import BrowserBridge, action_text, page_text_for_model, parse_action
from .config import load_settings, save_settings

SEARCH_URL = "https://duckduckgo.com/?q="

HELP = """**Commands** (type / to see this list as you type)
`/learn <topic>`: search the web for a topic and learn the best pages (e.g. `/learn coding`)
`/learn <site>`: read a whole website (e.g. `/learn docs.python.org`)
`/talk [minutes]`: practice basic conversation so I can talk (default 15 min)
`/explore` · `/stop`: explore the web on my own in the current mode, or stop all reading
`/mode <name>` · `/modes`: switch learning mode, or list modes
`/open <url>` · `/search <words>` · `show page` · `click 12` · `type "text" and press enter` · `scroll down` · `back`
`learn this page`: save what's in the browser
`/autopilot <goal>`: let my own model drive the browser
`/image <prompt>` · `/video <prompt>` · `/3d <prompt>`: create with a local model from Studio
`/status` · `/train` · `/pause`: brain status and training
`/new`: start a new chat · `/tips`: tips & tricks · `/help`: this list
**Mnemo Code** (sidebar): let me work on files in a folder, with Ask / Partial / Full access.
📎 Attach or drop files/folders to teach me from them."""


def to_url(s: str) -> str:
    s = s.strip().strip("\"'")
    if re.match(r"^https?://", s):
        return s
    if re.match(r"^[\w-]+(\.[\w-]+)+(/.*)?$", s):
        return "https://" + s
    return SEARCH_URL + quote_plus(s)


class Agent:
    def __init__(self, trainer, crawler, browser: BrowserBridge):
        self.trainer, self.crawler, self.browser = trainer, crawler, browser
        self.stop_flag = threading.Event()

    def set_mode(self, mode: str) -> dict:
        if mode not in modes.all_modes():
            raise ValueError(f"Unknown mode “{mode}”. Modes: {', '.join(modes.all_modes())}")
        save_settings({"mode": mode})
        self.trainer.mixture.mode = mode
        exploring = any(j["kind"] == "auto" for j in self.crawler.status())
        if exploring:
            self.crawler.start_auto(mode)  # keep exploring, now on this mode's topics
        m = modes.get(mode)
        events.emit("mode", mode=mode, name=m["name"], icon=m["icon"], blurb=m["blurb"])
        return m

    # ------------------------------------------------------------------ entry
    async def learn_topic(self, topic: str, send=None) -> str | None:
        """/learn <topic>: find good pages with official search APIs, then read them and nearby on-topic pages."""
        s = load_settings()
        mode = search.guess_mode(topic, s["mode"])
        md = modes.get(mode)
        if send:
            await send({"type": "tool", "text": f"🔎 Searching for pages about **{topic}**…"})
        urls = await asyncio.to_thread(search.find_pages, topic, mode)
        if not urls:
            if send:
                await send({"type": "tool", "text": "I couldn't find pages about that right now. Try other words."})
            return None
        job = self.crawler.crawl_topic(topic, urls, mode, int(s["learn_pages"]))
        hosts = sorted({u.split("/")[2].replace("www.", "") for u in urls})[:6]
        if send:
            tip = "" if mode == s["mode"] else f" Tip: switch to {md['icon']} {md['name']} mode so training focuses on it."
            await send({"type": "tool", "text": f"📚 Learning **{topic}** as {md['icon']} {md['name']}: found {len(urls)} "
                        f"pages ({', '.join(hosts)}…). Reading up to {s['learn_pages']} pages plus related links; "
                        f"watch the **Learn** tab.{tip}"})
        return job

    async def handle(self, text: str, history: list[dict], send, files: list[str] | None = None):
        """`send(dict)` streams messages back to the UI. `files` = attached file URLs to use as context."""
        self.stop_flag.clear()
        self.files = files or []
        text = text.strip()
        try:
            if await self._command(text, send):
                return
        except Exception as e:
            await send({"type": "tool", "text": f"⚠️ {e}"})
            return
        await self._reply(text, history, send)

    # --------------------------------------------------------------- commands
    async def _command(self, text: str, send) -> bool:
        t = text.lower().rstrip(".!? ")
        b = self.browser
        tool = lambda msg, **kw: send({"type": "tool", "text": msg, **kw})

        if t.startswith("/") and t.split()[0] in plugins.registry.commands:
            ctx = SimpleNamespace(trainer=self.trainer, crawler=self.crawler, browser=self.browser, memory=memory,
                                  settings=load_settings())
            out = await plugins.registry.run(text, ctx)
            if out:
                await tool(str(out))
            return True
        if m := re.match(r"^/(image|img|video|3d)\s+(.+)$", text, re.I):
            kind = {"img": "image"}.get(m.group(1).lower(), m.group(1).lower())
            ready = [x for x in studio.CATALOG if x["kind"] == kind and studio.installed(x["id"])]
            if not ready:
                await tool(f"No {kind} model downloaded yet. Open **Studio** in the sidebar and pick one.")
                return True
            pick = load_settings().get(f"studio_default_{kind}")
            mdl = next((x for x in ready if x["id"] == pick), ready[0])
            studio.submit(self.trainer, {"id": mdl["id"], "prompt": m.group(2)})
            await tool(f"🎨 Making a {kind} with **{mdl['name']}**: “{m.group(2)}”. It'll appear in **Studio** when done.")
            return True
        if t in ("/plugins", "plugins"):
            plugins.registry.load()
            rows = [f"`{n}`: {h} *({p})*" for n, (h, _, p) in sorted(plugins.registry.commands.items())]
            bad = [f"⚠️ {p['name']}: {p['error']}" for p in plugins.registry.loaded if not p["ok"]]
            await tool("**Plugins** (reloaded; add .py files to ~/.mnemo/plugins):\n" + "\n".join(rows + bad or ["none"]))
            return True
        if t in ("/help", "help", "/commands", "commands", "/?"):
            extra = "\n".join(f"`{n}`: {h}" for n, (h, _, _) in sorted(plugins.registry.commands.items()))
            await tool(HELP + ("\n\n**Plugin commands**\n" + extra if extra else ""))
            return True
        if t in ("mode", "modes", "/mode", "/modes", "list modes", "what modes"):
            cur = load_settings()["mode"]
            await tool("**Modes** (say e.g. *code mode*):\n" + "\n".join(
                f"{m['icon']} **{m['name']}**{' (active)' if k == cur else ''}: {m['blurb']}" for k, m in modes.all_modes().items()))
            return True
        if m := re.match(r"^(?:/talk|/basics|teach me to talk|learn to talk|practice talking|practice conversation)(?:\s+(\d+))?", t):
            minutes = float(m.group(1) or 15)
            await tool(f"💬 Practicing basic conversation for {minutes:g} minutes. Chat with me when it's done!")
            await basics.teach(self.trainer, minutes)
            return True
        if t in ("/stop", "stop"):
            self.crawler.stop()
            await tool("⏹️ Stopped all reading.")
            return True
        if m := re.match(r"^(?:/learn|learn about|teach yourself|study up on|go learn about)\s+(.+)$", text, re.I):
            arg = m.group(1).strip()
            site = re.match(r"^(\S+\.[a-z]{2,}\S*)(?:\s+(\d+)\s*pages?)?$", arg, re.I)
            if site and " " not in site.group(1):
                job = self.crawler.crawl_site(site.group(1), int(site.group(2)) if site.group(2) else None)
                await tool(f"📚 Reading **{site.group(1)}** (job `{job}`). New pages go into memory and training.")
            else:
                await self.learn_topic(arg, send)
            return True
        if m := re.match(r"^(?:/mode\s+|switch to\s+|use\s+|change to\s+|go into\s+|enter\s+)?([\w-]+)\s*(?:mode)?$", t):
            name = m.group(1)
            if name in modes.all_modes() and (t.endswith("mode") or t.startswith(("/mode", "switch", "use", "change", "go into", "enter"))):
                md = self.set_mode(name)
                await tool(f"{md['icon']} Switched to **{md['name']} mode**: {md['blurb']} Exploring, the library, "
                           "training focus and my replies now follow this mode.")
                return True
        if m := re.match(r"^(?:/autopilot|autopilot|browse for|use the browser to)\s+(.+)$", text, re.I):
            await self._autopilot(m.group(1), send)
            return True
        if m := re.match(r"^(?:/crawl|crawl|learn from|learn everything (?:on|from)|read the (?:web)?site|study)\s+"
                         r"(?:the )?(?:website |site )?(\S+\.\S+?)(?:\s+(\d+)\s*pages?)?$", text, re.I):
            job = self.crawler.crawl_site(m.group(1), int(m.group(2)) if m.group(2) else None)
            await tool(f"📚 Reading **{m.group(1)}** (job `{job}`). New pages go into memory and training.")
            return True
        if re.match(r"^(/explore|explore|start exploring|learn from the internet|go learn|keep learning)", t):
            self.crawler.start_auto()
            md = modes.get(load_settings()["mode"])
            await tool(f"🌍 Exploring the web on my own in {md['icon']} **{md['name']} mode**. "
                       "Open the **Learn** tab to watch what I read.")
            return True
        if re.match(r"^(/stop exploring|stop exploring|stop crawling|stop reading)", t):
            self.crawler.stop()
            await tool("⏹️ Stopped all crawling.")
            return True
        if re.match(r"^(/train|start training|train|start learning)$", t):
            self.trainer.start()
            await tool("🧠 Training is on.")
            return True
        if re.match(r"^(/pause|pause training|stop training)$", t):
            self.trainer.pause()
            await tool("⏸️ Training paused.")
            return True
        if re.match(r"^(/status|status|how big are you|how smart are you|stats)$", t):
            s = self.trainer.status()
            ms = memory.stats()
            await tool(f"🧠 {s['params']/1e6:.1f}M parameters (stage {s['stage']}, can grow to "
                       f"{s['max_params']/1e9:.2f}B here) · read {s['tokens_seen']/1e6:.1f}M tokens · "
                       f"loss {s['loss'] or 0:.2f} · {ms['docs']:,} documents in memory · state: {s['state']}")
            return True

        # ---- browser commands
        if m := re.match(r"^(?:/open|/go|go to|open|visit|navigate to)\s+(.+)$", text, re.I):
            url = to_url(m.group(1))
            b.goal = text
            await b.act("navigate", goal=text, url=url)
            await tool(f"🌐 Opened {url}")
            return True
        if m := re.match(r"^(?:/search|search(?: for)?|google|look up)\s+(.+)$", text, re.I):
            url = SEARCH_URL + quote_plus(m.group(1))
            await b.act("navigate", goal=text, url=url)
            await tool(f"🔎 Searching for “{m.group(1)}”")
            return True
        if m := re.match(r"^click\s+(?:on\s+)?(?:\[)?(\d+)(?:\])?$", t):
            await b.act("click", goal=text, ref=int(m.group(1)))
            await tool(f"🖱️ Clicked [{m.group(1)}]")
            return True
        if m := re.match(r"^click\s+(?:on\s+)?(?:the\s+)?[\"']?(.+?)[\"']?(?:\s+(?:link|button))?$", text, re.I):
            ref = await self._find(m.group(1))
            if ref is None:
                await tool(f"I couldn't find “{m.group(1)}” on this page. Say **show page** to see what's clickable.")
            else:
                await b.act("click", goal=text, ref=ref)
                await tool(f"🖱️ Clicked “{m.group(1)}” [{ref}]")
            return True
        if m := re.match(r"^type\s+[\"'](.+)[\"'](?:\s+(?:in|into)\s+\[?(\d+)\]?)?(\s+and (?:press enter|submit|search))?$", text, re.I):
            ref = int(m.group(2)) if m.group(2) else await self._first_textbox()
            if ref is None:
                await tool("There's no text box on this page.")
                return True
            await b.act("type", goal=text, ref=ref, text=m.group(1), submit=bool(m.group(3)))
            await tool(f"⌨️ Typed “{m.group(1)}” into [{ref}]" + (" and pressed Enter" if m.group(3) else ""))
            return True
        if m := re.match(r"^scroll\s*(up|down)?", t):
            await b.act("scroll", goal=text, direction=m.group(1) or "down")
            await tool(f"↕️ Scrolled {m.group(1) or 'down'}")
            return True
        if t in ("back", "go back"):
            await b.act("back", goal=text)
            await tool("⬅️ Back")
            return True
        if t in ("forward", "go forward"):
            await b.act("forward", goal=text)
            await tool("➡️ Forward")
            return True
        if t in ("show page", "what can i click", "list links", "snapshot"):
            snap = await b.snapshot()
            await tool("```\n" + page_text_for_model(snap, 60) + "\n```")
            return True
        if t in ("learn this page", "read this page", "remember this page", "learn this", "read this"):
            page = await b.call("read")
            doc = self.crawler.learn_page(page["url"], page["title"], page["text"])
            first = page["text"].strip().split("\n")[0][:300]
            await tool(f"📖 Read **{page['title']}** ({len(page['text']):,} characters)"
                       + (" and saved it to memory. I'll learn from it in training." if doc else
                          " (already in memory or too short).") + (f"\n\n> {first}" if first else ""))
            return True
        return False

    async def _find(self, name: str) -> int | None:
        snap = await self.browser.snapshot()
        name = name.lower()
        best = None
        for el in snap.get("elements", []):
            n = el["name"].lower()
            if n == name:
                return el["ref"]
            if name in n and best is None:
                best = el["ref"]
        return best

    async def _first_textbox(self) -> int | None:
        snap = await self.browser.snapshot()
        for el in snap.get("elements", []):
            if el["role"] in ("textbox", "searchbox", "combobox") and not el.get("password"):
                return el["ref"]
        return None

    # --------------------------------------------------------------- autopilot
    async def _autopilot(self, goal: str, send, max_steps: int = 8):
        """Mnemo's own model chooses browser actions. Early on it is mostly guessing."""
        tok = tokenizer.load()
        if tok is None or self.trainer.model is None:
            await send({"type": "tool", "text": "I don't have a brain yet. Let me learn first."})
            return
        await send({"type": "tool", "text": f"🤖 Autopilot: “{goal}” (my own model is choosing each action)"})
        self.browser.goal = goal
        for step in range(max_steps):
            if self.stop_flag.is_set():
                return
            snap = await self.browser.snapshot()
            s = lambda t: tokenizer.sid(tok, t)
            prompt = ([s(tokenizer.GOAL)] + tok.encode(goal).ids + [s(tokenizer.PAGE_OPEN)] +
                      tok.encode(page_text_for_model(snap)).ids + [s(tokenizer.PAGE_CLOSE), s(tokenizer.ACTION)])
            out = await asyncio.to_thread(self._generate_ids, prompt, 24, 0.3, {s(tokenizer.END), s(tokenizer.EOT)})
            text = tok.decode(out).strip()
            parsed = parse_action(text)
            if not parsed:
                await send({"type": "tool", "text": f"Step {step+1}: I wrote `{text[:80] or '(nothing)'}`, which isn't a "
                            "valid action yet. I learn from every action you do with me, so I'll get better at this."})
                return
            verb, params = parsed
            if verb == "done":
                await send({"type": "tool", "text": "✅ I think the goal is done."})
                return
            if verb == "type" and any(e["ref"] == params["ref"] and e.get("password") for e in snap["elements"]):
                await send({"type": "tool", "text": "🔒 I won't type into password fields."})
                return
            try:
                await self.browser.act(verb, goal=goal, **params)
            except Exception as e:
                await send({"type": "tool", "text": f"Step {step+1}: `{action_text(verb, params)}` failed ({e})."})
                return
            await send({"type": "tool", "text": f"Step {step+1}: `{action_text(verb, params)}`"})
            await asyncio.sleep(1.2)

    # ------------------------------------------------------------------- reply
    def _generate_ids(self, prompt_ids, max_new, temperature, stop_ids, on_token=None):
        tr = self.trainer
        tr.chat_waiting.set()
        try:
            with tr.lock:
                tr.model.eval()
                out = []
                for t in tr.model.generate(prompt_ids, max_new_tokens=max_new, temperature=temperature,
                                           stop_ids=stop_ids, should_stop=self.stop_flag.is_set):
                    out.append(t)
                    if on_token:
                        on_token(out)
                return out
        finally:
            tr.chat_waiting.clear()

    async def _reply(self, text: str, history: list[dict], send):
        tok = tokenizer.load()
        if tok is None or not self.trainer.ensure_model():
            await send({"type": "reply", "text": "…(I haven't read anything yet, so I can't form words. Open the "
                        "**Learn** tab and download the library, or tell me to *explore*.)", "done": True})
            return
        s = load_settings()
        mode = s["mode"]
        mem_text, sources = "", []
        for url in getattr(self, "files", [])[:5]:  # attached files come first
            for c in memory.chunks_for_url(url, 2):
                mem_text += f"{c['title']}: {c['text'][:900]}\n\n"
                sources.append({"title": c["title"], "url": url})
        if s["use_memory"]:
            hits = memory.search(text, s["memory_snippets"], topic=mode)
            if hits:
                mem_text += "\n\n".join(f"{h['title']}: {h['text'][:700]}" for h in hits)
                sources += [{"title": h["title"], "url": h["url"]} for h in hits]
        msgs = ([{"role": "system", "content": modes.tag(mode)}] +
                [m for m in history if m.get("role") in ("user", "assistant")][-30:] + [{"role": "user", "content": text}])
        ids = tokenizer.encode_chat(tok, msgs, mem_text) + [tokenizer.sid(tok, tokenizer.ASSISTANT)]
        stop = {tokenizer.sid(tok, tokenizer.END), tokenizer.sid(tok, tokenizer.EOT), tokenizer.sid(tok, tokenizer.USER)}
        loop = asyncio.get_running_loop()
        await send({"type": "reply_start", "sources": sources})
        last = [""]

        def on_token(out):
            full = tok.decode(out)
            delta, last[0] = full[len(last[0]):], full
            if delta:
                asyncio.run_coroutine_threadsafe(send({"type": "reply_delta", "text": delta}), loop)

        temperature = float(s["temperature"]) or modes.get(mode)["temperature"]
        await asyncio.to_thread(self._generate_ids, ids, int(s["max_reply_tokens"]), temperature,
                                stop, on_token)
        await send({"type": "reply", "text": last[0], "done": True, "sources": sources})
        events.emit("chat", text=text)
