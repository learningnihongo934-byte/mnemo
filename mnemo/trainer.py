"""Continuous training: Mnemo learns for as long as you leave it running.

Loop: mix batches from the library / web / chat / browser-action shards,
take optimizer steps, feed newly crawled pages into the web shards, save
checkpoints, and grow the model to the next stage once it has read enough
tokens for its current size (as long as the bigger model fits in memory).

Small stages train in fp32 with AdamW. Big stages (where AdamW's 16 bytes per
parameter would not fit) switch to bf16 weights + Lion with stochastic
rounding (~6 bytes per parameter) and gradient checkpointing, which is how a
1B+ model trains on a 16 GB machine.
"""

from __future__ import annotations

import itertools
import os
import json
import math
import threading
import time
from dataclasses import dataclass

import torch

from . import events, library, memory, modes, tokenizer
from .config import (ACTIONS_DIR, ACTIONS_LOG, CHAT_DIR, CKPT_DIR, LIBRARY_DIR, WEB_DIR, load_settings,
                     total_ram_bytes)
from .data import Mixture, ShardWriter
from .model import Mnemo, ModelConfig, grow, growth_schedule

BYTES_ADAM = 16      # fp32 weight + grad + 2 Adam moments
BYTES_LOWMEM = 6     # bf16 weight + grad + Lion momentum
OVERHEAD = 1.35      # activations, logits, allocator slack


def list_devices() -> list[dict]:
    """Every device Mnemo can train on, for the Settings picker."""
    out = [{"id": "auto", "name": "Automatic (best available)"}]
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            p = torch.cuda.get_device_properties(i)
            out.append({"id": f"cuda:{i}", "name": f"{p.name} ({p.total_memory / 1e9:.0f} GB)", "memory": p.total_memory})
    if torch.backends.mps.is_available():
        out.append({"id": "mps", "name": "Apple GPU (Metal)"})
    out.append({"id": "cpu", "name": f"CPU ({os.cpu_count()} threads)"})
    return out


def pick_device() -> torch.device:
    want = str(load_settings().get("device") or "auto")
    if want != "auto":
        ok = (want == "cpu" or (want == "mps" and torch.backends.mps.is_available())
              or (want.startswith("cuda") and torch.cuda.is_available()
                  and int(want.split(":")[1] if ":" in want else 0) < torch.cuda.device_count()))
        if ok:
            return torch.device(want)
    if torch.cuda.is_available():
        return torch.device("cuda:0")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


@dataclass
class Hyper:
    seq_len: int
    micro_batch: int
    accum: int
    lr: float
    lowmem: bool


def hyper_for(cfg: ModelConfig, budget: float) -> Hyper:
    params = cfg.param_count()
    lowmem = params * BYTES_ADAM * OVERHEAD > budget
    d = cfg.d_model
    if d <= 256:
        h = Hyper(512, 16, 2, 1e-3, lowmem)
    elif d <= 512:
        h = Hyper(1024, 8, 4, 6e-4, lowmem)
    elif d <= 768:
        h = Hyper(1024, 8, 4, 4e-4, lowmem)
    elif d <= 1024:
        h = Hyper(2048, 4, 8, 3e-4, lowmem)
    elif d <= 1536:
        h = Hyper(2048, 2, 16, 2.5e-4, lowmem)
    else:
        h = Hyper(2048, 1, 32, 2e-4, lowmem)
    if lowmem:
        h.lr /= 4  # Lion wants a smaller learning rate than AdamW
    return h


def stage_fits(cfg: ModelConfig, budget: float, max_params: int) -> bool:
    p = cfg.param_count()
    if max_params and p > max_params:
        return False
    return p * min(BYTES_ADAM, BYTES_LOWMEM) * OVERHEAD <= budget


class LionSR(torch.optim.Optimizer):
    """Lion optimizer for bf16 weights, with stochastic rounding so tiny updates aren't lost."""

    def __init__(self, params, lr=1e-4, betas=(0.9, 0.99), weight_decay=0.1):
        super().__init__(params, dict(lr=lr, betas=betas, weight_decay=weight_decay))

    @torch.no_grad()
    def step(self):
        for group in self.param_groups:
            lr, (b1, b2), wd = group["lr"], group["betas"], group["weight_decay"]
            for p in group["params"]:
                if p.grad is None:
                    continue
                st = self.state[p]
                if "m" not in st:
                    st["m"] = torch.zeros_like(p)
                m, g = st["m"], p.grad
                update = (m.float() * b1 + g.float() * (1 - b1)).sign_()
                new = p.float()
                if wd:
                    new.mul_(1 - lr * wd)
                new.add_(update, alpha=-lr)
                m.copy_(m.float().mul_(b2).add_(g.float(), alpha=1 - b2))
                if p.dtype == torch.bfloat16:
                    bits = new.view(torch.int32)
                    bits.add_(torch.randint_like(bits, 0, 1 << 16)).bitwise_and_(-65536)
                    p.copy_(bits.view(torch.float32))
                else:
                    p.copy_(new)


def _param_groups(model, wd):
    decay = [p for n, p in model.named_parameters() if p.dim() >= 2]
    no_decay = [p for n, p in model.named_parameters() if p.dim() < 2]
    return [{"params": decay, "weight_decay": wd}, {"params": no_decay, "weight_decay": 0.0}]


class Trainer:
    def __init__(self):
        self.device = pick_device()
        self.lock = threading.RLock()        # held during each micro-step and during chat generation
        self.chat_waiting = threading.Event()
        self.running = threading.Event()
        self.thread: threading.Thread | None = None
        self.model: Mnemo | None = None
        self.opt = None
        self.hp: Hyper | None = None
        self.stage = 0
        self.step = 0
        self.tokens_seen = 0
        self.stage_tokens = 0
        self.warmup_left = 0
        self.loss_ema: float | None = None
        self.history: list[tuple[int, int, float, int]] = []  # step, tokens, loss, params
        self.tok_per_sec = 0.0
        self.last_sample = ""
        self.status_text = "idle"
        self.focus_until = 0.0
        self.focus_label = ""
        s = load_settings()
        self.mixture = Mixture({"library": LIBRARY_DIR, "web": WEB_DIR, "chat": CHAT_DIR, "actions": ACTIONS_DIR},
                               s["mix"], topic_of=topic_of, mode=s["mode"], boost=modes.FOCUS_BOOST)
        self.web_writers: dict[str, ShardWriter] = {}
        self.act_writer = ShardWriter(ACTIONS_DIR, "actions")
        self._load_checkpoint()

    # --- budget -------------------------------------------------------------
    @property
    def budget(self) -> float:
        """Bytes training may use: a share of GPU memory on NVIDIA, of system RAM elsewhere (shared memory)."""
        s = load_settings()
        if int(s.get("memory_budget_gb") or 0) > 0:
            return float(s["memory_budget_gb"]) * 1e9
        if self.device.type == "cuda":
            return 0.85 * torch.cuda.get_device_properties(self.device).total_memory
        return s["memory_budget_frac"] * total_ram_bytes()

    def max_reachable_params(self) -> int:
        s = load_settings()
        best = 0
        for cfg in itertools.islice(growth_schedule(tokenizer.VOCAB_SIZE), 40):
            if not stage_fits(cfg, self.budget, s["max_params"]):
                break
            best = cfg.param_count()
        return best

    # --- model lifecycle ----------------------------------------------------
    def _stage_cfg(self, i: int) -> ModelConfig:
        vocab = tokenizer.load().get_vocab_size() if tokenizer.load() else tokenizer.VOCAB_SIZE
        cfg = next(itertools.islice(growth_schedule(vocab), i, None))
        cfg.max_context = int(load_settings()["context_length"])
        return cfg

    def _start_stage(self) -> int:
        """First stage at least as big as the chosen starting size (and that fits in memory)."""
        s = load_settings()
        want = int(s.get("start_params") or 0)
        best = 0
        for i in range(40):
            cfg = self._stage_cfg(i)
            if not stage_fits(cfg, self.budget, s["max_params"]):
                break
            best = i
            if cfg.param_count() >= want:
                break
        return best

    def _setup(self, model: Mnemo):
        """Move model to device in the right precision and build the optimizer."""
        self.hp = hyper_for(model.cfg, self.budget)
        s = load_settings()
        if int(s.get("train_seq_len") or 0) > 0:
            # Same tokens per step, longer windows: fewer rows per micro-batch.
            want = min(int(s["train_seq_len"]), model.cfg.max_context)
            self.hp.micro_batch = max(1, self.hp.micro_batch * self.hp.seq_len // want)
            self.hp.seq_len = want
        # Manual overrides from Settings → Hardware & architecture (0 / "auto" = automatic).
        if int(s.get("micro_batch") or 0) > 0:
            self.hp.micro_batch = int(s["micro_batch"])
        if int(s.get("grad_accum") or 0) > 0:
            self.hp.accum = int(s["grad_accum"])
        prec, optim = s.get("precision", "auto"), s.get("optimizer", "auto")
        if prec in ("fp32", "bf16"):
            self.hp.lowmem = prec == "bf16"
        use_lion = optim == "lion" or (optim == "auto" and self.hp.lowmem)
        if float(s.get("learning_rate") or 0) > 0:
            self.hp.lr = float(s["learning_rate"])
        elif use_lion and not self.hp.lowmem:
            self.hp.lr /= 4
        if int(s.get("cpu_threads") or 0) > 0:
            torch.set_num_threads(int(s["cpu_threads"]))
        dtype = torch.bfloat16 if self.hp.lowmem else torch.float32
        model = model.to(device=self.device, dtype=dtype)
        ck = s.get("grad_checkpoint", "auto")
        model.grad_checkpoint = (ck == "on") or (ck == "auto" and (self.hp.lowmem or model.cfg.d_model >= 1024))
        self.model = model
        if use_lion:
            self.opt = LionSR(_param_groups(model, 1.0), lr=self.hp.lr, betas=(0.9, 0.99))
        else:
            self.opt = torch.optim.AdamW(_param_groups(model, 0.1), lr=self.hp.lr, betas=(0.9, 0.95), eps=1e-8)
        self.warmup_left = 100

    def ensure_model(self) -> bool:
        if self.model is not None:
            return True
        if tokenizer.load() is None:
            return False
        with self.lock:
            s = load_settings()
            d, layers = int(s.get("custom_d_model") or 0), int(s.get("custom_layers") or 0)
            if d >= 64 and layers >= 1:
                # Custom shape: grow later into the first schedule stage that is bigger in both directions.
                d -= d % 64
                cfg = self._stage_cfg(0)
                cfg = ModelConfig(vocab_size=cfg.vocab_size, d_model=d, n_layers=layers, max_context=cfg.max_context)
                nxt = next((i for i in range(40) if self._stage_cfg(i).d_model >= d and self._stage_cfg(i).n_layers >= layers
                            and self._stage_cfg(i).param_count() > cfg.param_count()), 40)
                self.stage = nxt - 1
                self._setup(Mnemo(cfg))
            else:
                self.stage = self._start_stage()
                self._setup(Mnemo(self._stage_cfg(self.stage)))
        events.emit("model", text=f"Mnemo is born: {self.model.num_params()/1e6:.1f}M parameters, knows nothing yet.")
        return True

    def _maybe_grow(self):
        s = load_settings()
        cur = self.model.cfg.param_count()
        if not s.get("allow_growth", True) or self.stage_tokens < s["growth_tokens_per_param"] * cur:
            return
        nxt = self._stage_cfg(self.stage + 1)
        if not stage_fits(nxt, self.budget, s["max_params"]):
            return  # at the biggest size this machine allows; keep learning at this size
        with self.lock:
            old_params = self.model.num_params()
            self.model.float()
            bigger = grow(self.model.cpu(), nxt)
            self.model = None
            self.opt = None
            if self.device.type == "mps":
                torch.mps.empty_cache()
            self._setup(bigger)
            self.stage += 1
            self.stage_tokens = 0
        events.emit("model", text=f"Mnemo grew: {old_params/1e6:.0f}M → {self.model.num_params()/1e6:.0f}M parameters "
                                  f"(stage {self.stage}). Everything it learned is kept.")
        self.save()

    def reset_brain(self):
        """Forget all learned weights (memory, tokenizer and downloaded data are kept)."""
        with self.lock:
            self.model = self.opt = self.hp = None
            self.stage = self.step = self.tokens_seen = self.stage_tokens = 0
            self.loss_ema, self.history, self.last_sample = None, [], ""
            for f in CKPT_DIR.glob("*.pt"):
                f.unlink()
        events.emit("model", text="Brain reset: Mnemo starts again from random weights.")

    # --- checkpoints --------------------------------------------------------
    def save(self):
        if self.model is None:
            return
        with self.lock:
            state = {
                "cfg": self.model.cfg.to_dict(), "stage": self.stage, "step": self.step,
                "tokens_seen": self.tokens_seen, "stage_tokens": self.stage_tokens,
                "history": self.history[-5000:], "model": self.model.state_dict(),
                "opt": self.opt.state_dict(), "lowmem": self.hp.lowmem,
            }
            tmp = CKPT_DIR / "latest.tmp"
            torch.save(state, tmp)
            latest = CKPT_DIR / "latest.pt"
            if latest.exists():
                latest.replace(CKPT_DIR / "previous.pt")
            tmp.replace(latest)
        events.emit("model", text=f"Saved checkpoint at step {self.step}.", quiet=True)

    def _load_checkpoint(self):
        for name in ("latest.pt", "previous.pt"):
            path = CKPT_DIR / name
            if not path.exists():
                continue
            try:
                st = torch.load(path, map_location="cpu", weights_only=False)
            except Exception:
                continue
            model = Mnemo(ModelConfig.from_dict(st["cfg"]))
            model.load_state_dict({k: v.float() for k, v in st["model"].items()})
            self._setup(model)
            try:
                self.opt.load_state_dict(st["opt"])
                self.warmup_left = 0
            except (ValueError, KeyError):
                pass
            self.stage, self.step = st["stage"], st["step"]
            self.tokens_seen, self.stage_tokens = st["tokens_seen"], st["stage_tokens"]
            self.history = [tuple(h) for h in st.get("history", [])]
            if self.history:
                self.loss_ema = self.history[-1][2]
            return

    # --- feeding new knowledge ------------------------------------------------
    def feed_new_pages(self) -> int:
        tok = tokenizer.load()
        if tok is None:
            return 0
        total = 0
        while True:
            rows = memory.untokenized(200)
            if not rows:
                break
            by_topic: dict[str, list[int]] = {}
            for r in rows:
                topic = r["topic"] or "general"
                by_topic.setdefault(topic, []).extend(library.tagged_ids(tok, topic, f"{r['title']}\n\n{r['text']}"))
            for topic, ids in by_topic.items():
                if topic not in self.web_writers:
                    self.web_writers[topic] = ShardWriter(WEB_DIR, f"web-{topic}")
                total += self.web_writers[topic].append(ids)
            memory.mark_tokenized([r["id"] for r in rows])
        total += self._feed_actions(tok)
        if total:
            self.mixture.refresh()
        return total

    def _feed_actions(self, tok) -> int:
        if not ACTIONS_LOG.exists():
            return 0
        offset_file = ACTIONS_DIR / "offset.txt"
        done = int(offset_file.read_text()) if offset_file.exists() else 0
        lines = ACTIONS_LOG.read_text().splitlines()
        new = lines[done:]
        if not new:
            return 0
        ids = []
        for line in new:
            try:
                ids += action_ids(tok, json.loads(line))
            except (json.JSONDecodeError, KeyError):
                continue
        offset_file.write_text(str(len(lines)))
        return self.act_writer.append(ids)

    # --- the loop -------------------------------------------------------------
    def start(self):
        if self.thread and self.thread.is_alive():
            self.running.set()
            return
        self.running.set()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="trainer")
        self.thread.start()

    def focus(self, sources: set, minutes: float, label: str):
        """Practice on specific data only (e.g. the conversation course) for a while, then go back to normal."""
        self.mixture.refresh()
        self.mixture.only = set(sources)
        self.focus_until = time.time() + minutes * 60
        self.focus_label = label
        self.start()

    def pause(self):
        self.running.clear()
        self.status_text = "paused"
        self.emit_status()

    def _loop(self):
        last_feed = last_save = last_status = last_sample = 0.0
        tokens_window, t_window = 0, time.time()
        while True:
            if not self.running.is_set():
                time.sleep(0.5)
                continue
            if self.chat_waiting.is_set():
                time.sleep(0.05)
                continue
            now = time.time()
            if now - last_feed > 30:
                last_feed = now
                if self.feed_new_pages() or self.step % 500 == 0:
                    self.mixture.refresh()
                s = load_settings()
                self.mixture.weights, self.mixture.mode = s["mix"], s["mode"]
            if not self.ensure_model():
                self.status_text = "waiting for text (download the library or start crawling)"
                self._idle_status()
                continue
            batch_ok = self._train_step()
            if not batch_ok:
                self.status_text = "waiting for text (download the library or start crawling)"
                self._idle_status()
                continue
            if self.focus_until and time.time() > self.focus_until:
                self.focus_until, self.mixture.only = 0.0, None
                events.emit("model", text=f"Finished practicing {self.focus_label}. Back to normal learning.")
                self._sample()
                self.save()
            self.status_text = (f"practicing {self.focus_label} ({max(0, int(self.focus_until - time.time()) // 60) + 1} min left)"
                                if self.focus_until else "learning")
            step_tokens = self.hp.micro_batch * self.hp.seq_len * self.hp.accum
            tokens_window += step_tokens
            if time.time() - t_window > 5:
                self.tok_per_sec = tokens_window / (time.time() - t_window)
                tokens_window, t_window = 0, time.time()
            if time.time() - last_status > 2:
                last_status = time.time()
                self.emit_status()
            if time.time() - last_sample > 600 or self.step == 50:
                last_sample = time.time()
                self._sample()
            if time.time() - last_save > 600:
                last_save = time.time()
                self.save()
            self._maybe_grow()

    def _idle_status(self):
        self.emit_status()
        time.sleep(3)

    def _train_step(self) -> bool:
        hp = self.hp
        total_loss = 0.0
        for _ in range(hp.accum):
            while self.chat_waiting.is_set():
                time.sleep(0.05)
            b = self.mixture.batch(hp.micro_batch, hp.seq_len, self.device)
            if b is None:
                return False
            x, y = b
            with self.lock:
                self.model.train()
                _, loss = self.model(x, y)
                (loss / hp.accum).backward()
            total_loss += float(loss.detach()) / hp.accum
        with self.lock:
            lr = hp.lr * min(1.0, (101 - self.warmup_left) / 100) if self.warmup_left else hp.lr
            self.warmup_left = max(0, self.warmup_left - 1)
            for g in self.opt.param_groups:
                g["lr"] = lr
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
            self.opt.step()
            self.opt.zero_grad(set_to_none=True)
        if math.isfinite(total_loss):
            self.loss_ema = total_loss if self.loss_ema is None else 0.98 * self.loss_ema + 0.02 * total_loss
        self.step += 1
        n = hp.micro_batch * hp.seq_len * hp.accum
        self.tokens_seen += n
        self.stage_tokens += n
        if self.step % 10 == 0:
            self.history.append((self.step, self.tokens_seen, round(self.loss_ema, 4), self.model.num_params()))
            self.history = self.history[-5000:]
        return True

    def _sample(self):
        tok = tokenizer.load()
        if tok is None or self.model is None:
            return
        mode = load_settings()["mode"]
        start = {"code": "def ", "math": "Theorem", "literature": "Once upon a time", "news": "Breaking:",
                 "science": "Scientists", "conversation": "Hi! "}.get(mode, "The")
        sid = lambda t: tokenizer.sid(tok, t)
        ids = [sid(tokenizer.SYSTEM)] + tok.encode(modes.tag(mode)).ids + [sid(tokenizer.END)] + tok.encode(start).ids
        with self.lock:
            self.model.eval()
            out = list(self.model.generate(ids, max_new_tokens=60, temperature=0.8))
        self.last_sample = start + tok.decode(out)
        events.emit("sample", text=self.last_sample, step=self.step)

    def status(self) -> dict:
        m = self.model
        s = load_settings()
        params = m.num_params() if m else 0
        target = s["growth_tokens_per_param"] * (m.cfg.param_count() if m else 0)
        return {
            "ram_gb": round(total_ram_bytes() / 1e9), "state": self.status_text, "running": self.running.is_set(), "device": self.device.type,
            "params": params, "stage": self.stage, "step": self.step, "tokens_seen": self.tokens_seen,
            "stage_tokens": self.stage_tokens, "grow_at": target,
            "loss": self.loss_ema, "tok_per_sec": self.tok_per_sec,
            "d_model": m.cfg.d_model if m else 0, "n_layers": m.cfg.n_layers if m else 0,
            "context": m.cfg.max_context if m else 100_000, "train_seq_len": self.hp.seq_len if self.hp else 0,
            "precision": ("bf16 + Lion" if self.hp.lowmem else "fp32 + AdamW") if self.hp else "",
            "max_params": self.max_reachable_params(), "data": self.mixture.stats(),
            "topics": self.mixture.topic_stats(), "mode": s["mode"],
            "sample": self.last_sample,
        }

    def emit_status(self):
        events.emit("trainer", **self.status())


def topic_of(prefix: str) -> str:
    """Topic of a shard prefix: 'web-code' -> code, 'gutenberg' -> literature, 'actions' -> general."""
    if prefix.startswith("web-"):
        return prefix[4:]
    spec = library.SOURCES.get(prefix)
    return spec["topic"] if spec else "general"


def action_ids(tok, ex: dict) -> list[int]:
    """Format one browser-control demonstration for training."""
    s = lambda t: tokenizer.sid(tok, t)
    return ([s(tokenizer.GOAL)] + tok.encode(ex["goal"]).ids +
            [s(tokenizer.PAGE_OPEN)] + tok.encode(ex["page"][:3000]).ids + [s(tokenizer.PAGE_CLOSE)] +
            [s(tokenizer.ACTION)] + tok.encode(ex["action"]).ids + [s(tokenizer.END), s(tokenizer.EOT)])
