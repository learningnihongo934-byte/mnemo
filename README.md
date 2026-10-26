<p align="center"><img src="docs/icon.png" width="128" alt="Mnemo icon"></p>

# Mnemo

*Made by **Virat Reddy Kaukuntla** ([@learningnihongo934-byte](https://github.com/learningnihongo934-byte))*

**Install** on macOS or Linux (Windows: `irm https://raw.githubusercontent.com/learningnihongo934-byte/mnemo/main/install.ps1 | iex` in PowerShell):

```bash
curl -fsSL https://raw.githubusercontent.com/learningnihongo934-byte/mnemo/main/install.sh | bash
```

Then type `mnemo`. Pick your own size and context with the builder on the website, or flags:
`… | bash -s -- --params 125M --max 1B --context 32768 --seq 1024 --mode code`

**A self-learning AI that starts from nothing.** Mnemo begins with random weights and no vocabulary. It builds
its own tokenizer, reads a library and the live web, trains continuously while you leave it running, **grows its own
brain** (12M → 1B+ parameters) as it learns, remembers every page in an unlimited searchable memory, and drives a
built-in web browser.

No pretrained weights are used. Everything Mnemo knows, it learned on your machine.

> **Be realistic about how smart it gets.** Models trained from scratch on one computer learn slowly. Expect
> gibberish at first, word-like text after hours, and short, semi-coherent sentences after days. Reaching 1B
> parameters takes months of continuous training on a laptop. Big AI labs train for weeks on thousands of GPUs;
> Mnemo is the same idea, small enough to watch happen.

## Features

- **Its own model, from scratch.** A decoder-only transformer (RoPE, grouped-query attention, SwiGLU, RMSNorm) in
  plain PyTorch, plus its own byte-level BPE tokenizer trained on the first text it reads.
- **It grows.** Training starts at 12M parameters. Once it has read 10 tokens per parameter, it grows wider and
  deeper through a *function-preserving* expansion, so nothing it learned is lost (`mnemo/model.py: grow()`, tested
  in `tests/test_model.py`). Stages: 12M → 39M → 99M → 210M → 545M → 1.04B → … up to whatever your RAM allows.
  Large stages switch to bf16 weights plus the Lion optimizer with stochastic rounding (about 6 bytes per parameter),
  so a 1B model trains in 16 GB.
- **100k-token context.** Rotary positions with a large base let the model take prompts up to 100,000 tokens, with
  chunked prefill and a KV cache. It trains on shorter windows (512–2048 tokens), so very long contexts work better
  as it matures.
- **Unlimited memory.** The weights have a fixed size at any moment; memory doesn't. Every page it reads goes into a
  SQLite full-text index, and the most relevant snippets are put in its context when you chat.
- **Learns from the internet.** It explores the web on its own (a polite crawler that respects robots.txt and
  per-site delays) or reads specific websites you give it. New pages flow into training automatically.
- **Built-in browser it controls.** A real Chromium browser in the app. Mnemo can open pages, take a numbered
  snapshot of clickable elements, click, type, scroll, press keys and read pages, with a purple highlight showing
  what it's doing. Every action is logged as a training example, so its own model gradually learns to browse
  (*autopilot*).
- **7 learning modes + your own**: make custom modes with your own sites and keywords (Settings → Custom modes).
- **`/learn <topic>`**: `/learn coding` searches Wikipedia, Stack Exchange, arXiv, Hacker News and more through their
  official APIs, then reads the best pages and nearby on-topic links.
- **Teach it your files**: 📎 attach or drag in files and whole folders (text, Markdown, code, PDF, Word, EPUB, HTML,
  CSV, JSON, notebooks). Attached files are also used as context for that reply.
- **Customizable**: dark/light/system theme, accent color, text size, panel width (or drag the divider), assistant
  name, compact messages, hide the browser, notifications.
- **Comfort features**: saved chat history, a Stop button, a `/` command menu, ↑ to repeat your last message, copy
  buttons, shortcuts (⌘K chat, ⌘L address bar, ⌘N new chat, ⌘1–4 tabs, Esc stop), keep-awake while learning,
  explore on launch, Open data folder, and Reset brain.

## Modes

Switch modes in the title bar, or say "code mode" in chat. A mode changes:

- where the explorer crawls
- which pages it keeps
- which library datasets it downloads
- what training focuses on (5× weight)
- the reply style

Documents are tagged with their mode, so Mnemo learns to answer in that domain's voice.

| Mode | Library (Hugging Face) | Explores |
|---|---|---|
| 🌐 General | Wikipedia, FineWeb-Edu | Wikipedia, Wikibooks, Stanford Encyclopedia of Philosophy, Gutenberg… |
| 💻 Code | GitHub code (MIT/Apache/BSD/ISC/CC0 files only), coding Q&A | Python docs, MDN, Rust book, cppreference, Go docs… (keeps only pages with code) |
| 📚 Literature | Project Gutenberg books | Gutenberg, Standard Ebooks, Wikisource, poetry sites |
| 🔬 Science | arXiv papers, SciQ | NASA, phys.org, ScienceDaily, PLOS, Britannica… |
| ➗ Math | FineMath, GSM8K | ProofWiki, MathWorld, Math Stack Exchange, Brilliant… |
| 📰 News | CC-News | AP, BBC, NPR, Guardian, Al Jazeera… |
| 💬 Conversation | SmolTalk (more) | Stack Exchange Q&A sites |

Every mode also includes some Wikipedia and SmolTalk conversations so it keeps learning language and how to chat.
Add your own modes in `mnemo/modes.py`.

## Install

Requirements: macOS (Apple Silicon recommended), Linux or Windows with Python 3.10+ and Node 18+. On Mac it trains
on the GPU (Metal), and on other systems on CUDA or the CPU.

```bash
./build.sh --app
```

This sets up the Python environment and app, then installs **Mnemo.app** in `/Applications`. To run from source
instead:

```bash
./build.sh && ./run.sh
```

## The `mnemo` command

| Command | What it does |
|---|---|
| `mnemo` | open Mnemo |
| `mnemo headless` | learn in the background with no window |
| `mnemo config` / `mnemo config key=value …` | show / change settings (`start_params`, `allow_growth`, `max_params`, `context_length`, `train_seq_len`, `mode`, …) |
| `mnemo update` | get the newest version |
| `mnemo app` | build Mnemo.app into /Applications on your own Mac (so macOS opens it) |
| `mnemo doctor` · `mnemo bench` · `mnemo data` · `mnemo uninstall` | check setup · speed test · data folder · remove |

## Plugins

Drop a Python file in `~/.mnemo/plugins/` (examples in `plugins/`), then type `/plugins` in Mnemo:

```python
def register(mnemo):
    @mnemo.command("/hello", "say hello")
    def hello(arg, ctx):
        return f"Hello, {arg or 'friend'}!"
```

`ctx` gives you `trainer`, `crawler`, `browser`, `memory` and `settings`. Built in: `/wiki`, `/define`, `/calc`, `/time`,
`/remember`, and **rat.audio** voices.

`/speak` uses [rat.audio](https://rat-audio.web.app) voices with Kokoro-82M, running on your machine:
- `/speak Welcome back!` uses the default voice.
- `/speak rocco-spinelli Howdy, partner.` picks a voice; `/voices` lists them.
- `/speak [am_puck 60, bm_fable 40, pitch -1] Hello` mixes your own voice.

The audio plays in chat and is saved to Studio → Creations as a WAV. The first use installs `kokoro-onnx` and downloads
the model (~340 MB).

## Mnemo Code

Mnemo's own model working on files in a folder you choose (sidebar → **Mnemo Code**). It thinks out loud, then
reads, writes, edits, searches and runs commands, one step at a time, shown as cards with diffs.

| Permission | What it does |
|---|---|
| **Ask** | approve every step, even reading |
| **Partial** | reads freely, asks before changing files or running commands |
| **Full access** | never asks |

In every mode it is locked to the folder, refuses dangerous commands (`sudo`, `rm -rf /`, …), and backs up every change
so **Undo** (⌘Z) always works. A model trained from scratch has to learn tool use: press **Teach Mnemo Code** to run
the practice course. The direct commands `/ls`, `/read`, `/find`, `/run`, `/undo` work from day one.

## Studio (local image, video and 3D)

Studio downloads open generative models and runs them on your machine: SSD-1B, DreamShaper 8, Stable Diffusion 1.5,
SDXL Turbo (images), Wan 2.1, CogVideoX 2B, ModelScope (video) and Shap-E (3D). Each one shows its license; some are
research/non-commercial only. In chat: `/image …`, `/video …`, `/3d …`.

## Hardware

Settings → Hardware & architecture: choose the device (any CUDA GPU, Apple GPU, CPU), precision, optimizer, exact
width/layers, batch size, accumulation, learning rate, CPU threads and a memory cap. Works on macOS, Windows and Linux.

## Website

`website/` is the Firebase site (landing page, model builder, Google sign-in, saved builds). Deploy steps are in
`website/README.md`.

## Using it

1. **Learn** tab → pick a library size → **Check size** → **Download & read**. Mnemo builds its vocabulary, then starts
   training. Starter is about 1–1.5 GB depending on the mode.
2. Press **Start exploring**, or type a site under *Learn a specific website*, to keep it learning from the live web.
3. Leave it running. Watch the loss fall, the sample text improve, and green lines on the chart where it grew.
4. Chat any time. Things you can say:

| You say | Mnemo does |
|---|---|
| `/learn coding` · `/learn docs.python.org` | search and learn a topic · read a whole site |
| `/help` · `/new` · `/stop` | commands · new chat · stop all reading |
| `code mode` / `modes` | switch mode / list modes |
| `explore` · `stop exploring` | crawl the web on its own (in the current mode) |
| `learn from docs.python.org 200 pages` | read one website |
| `go to wikipedia.org` · `search for black holes` | drive the browser |
| `click 12` · `click Sign up` · `type "cats" and press enter` · `scroll down` · `back` | browser actions |
| `show page` | numbered list of what's clickable |
| `learn this page` | save the current page to memory and training |
| `autopilot find the history section` | its own model picks the actions (weak until trained) |
| `status` · `pause training` · `train` | brain status / control |
| anything else | a reply generated by Mnemo's own model, using its memory |

Everything is stored in `~/.mnemo` (set `MNEMO_HOME` to move it): tokenizer, checkpoints, token shards, memory
database and action logs. Delete that folder to start a brand-new Mnemo.

## How it works

```
app/            Electron desktop app: UI + the browser Mnemo controls (main.js, browser-control.js, renderer/)
mnemo/model.py      transformer, KV-cache generation, function-preserving grow()
mnemo/trainer.py    continuous training loop, growth schedule, memory budget, checkpoints, LionSR optimizer
mnemo/tokenizer.py  byte-level BPE trained from scratch, chat format
mnemo/library.py    seed datasets (download, tokenize, tag by topic)
mnemo/crawler.py    explorer + site crawler (robots.txt, politeness, extraction)
mnemo/memory.py     SQLite FTS5 memory + crawl frontier
mnemo/modes.py      the 7 learning modes
mnemo/agent.py      chat: commands, memory retrieval, generation, autopilot
mnemo/browser.py    browser bridge + action logging (training data for browsing)
mnemo/server.py     local API (127.0.0.1 only, per-launch token)
```

## Responsible crawling

The crawler identifies itself as `MnemoBot`. It obeys robots.txt, waits at least 2 seconds between requests to the
same site, skips login/cart/account pages and private network addresses, and never submits forms. Autopilot refuses
to type into password fields. Please keep these defaults if you fork it.

## Data licenses

Mnemo is proprietary, source-available software: free to use, but you may not redistribute, sell or publish modified versions without written permission from Virat Kaukuntla (see [LICENSE](LICENSE)). Datasets and Studio models keep their own licenses, which the app shows before downloading:
Wikipedia (CC BY-SA 4.0), FineWeb-Edu and FineMath (ODC-BY), SmolTalk (Apache-2.0), self-oss-instruct (ODC-BY),
GSM8K (MIT), Gutenberg English (public domain texts), GitHub code (only permissively licensed files are used),
SciQ (CC BY-NC 3.0, non-commercial), and CC-News and arXiv (license unspecified, research use). If you
redistribute trained weights, check these first.

## Speed test

```bash
.venv/bin/python scripts/benchmark.py        # 12M–210M sizes
.venv/bin/python scripts/benchmark.py 5      # the 1B size (close other apps first)
```

## Tests

```bash
.venv/bin/python -m pytest -q tests
```
