"""Paths and user settings. Everything Mnemo learns lives in MNEMO_HOME (default ~/.mnemo)."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

HOME = Path(os.environ.get("MNEMO_HOME", Path.home() / ".mnemo")).expanduser()
LIBRARY_DIR = HOME / "library"          # tokenized seed library shards
RAW_DIR = HOME / "library" / "raw"      # downloaded parquet files (deleted after use)
WEB_DIR = HOME / "web"                  # tokenized pages learned from the live web
CHAT_DIR = HOME / "chat"                # tokenized conversations
ACTIONS_DIR = HOME / "actions"          # tokenized browser-control demonstrations
CKPT_DIR = HOME / "checkpoints"
CHATS_PATH = HOME / "chats.json"
TOKENIZER_PATH = HOME / "tokenizer.json"
MEMORY_DB = HOME / "memory.db"
ACTIONS_LOG = HOME / "actions.jsonl"
SETTINGS_PATH = HOME / "settings.json"

VERSION = "0.1.0"

DEFAULTS = {
    # Learning
    "mode": "general",                  # see modes.py: general, code, literature, science, math, news, conversation
    "setup_done": False,
    "tutorial_done": False,             # starting tutorial seen                # first-run setup wizard finished
    "custom_modes": {},                 # your own modes: {id: {name, icon, blurb, seeds, domains, keywords, temperature}}
    "auto_explore": False,              # start exploring the web when the app opens
    "keep_awake": True,                 # stop the Mac from sleeping while Mnemo is open
    "learn_pages": 60,                  # pages read per /learn topic
    "ui": {},                           # appearance: theme, accent, font size, panel width…
    "auto_train": True,                 # start training as soon as there's data
    "start_params": 0,                  # size the brain starts at (0 = smallest, ~12M); e.g. 125_000_000
    "allow_growth": True,               # grow bigger as it learns (off = stay at the starting size)
    "context_length": 100_000,          # longest prompt the model accepts, in tokens
    "train_seq_len": 0,                 # tokens per training window (0 = automatic for the size)
    # Hardware & architecture (0 / "auto" = let Mnemo decide)
    "device": "auto",                   # auto, cpu, mps, cuda:0, cuda:1, …
    "precision": "auto",                # auto, fp32, bf16
    "optimizer": "auto",                # auto, adamw, lion
    "grad_checkpoint": "auto",          # auto, on, off (on = less memory, slower)
    "custom_d_model": 0,                # exact width (multiple of 64); with custom_layers overrides start_params
    "custom_layers": 0,
    "micro_batch": 0,                   # rows per forward pass
    "grad_accum": 0,                    # micro-batches per optimizer step
    "learning_rate": 0,
    "cpu_threads": 0,
    "memory_budget_gb": 0,              # hard memory cap for training (0 = share of RAM / GPU memory)
    "studio_keep_loaded": False,
    # Mnemo Code
    "code_workspace": "",               # folder Mnemo Code works in
    "code_recent": [],
    "code_permission": "ask",           # ask (everything) · partial (asks before changes) · full (never asks)
    "code_allow_commands": True,        # let it run terminal commands (always inside the workspace)
    "code_max_steps": 10,
    "code_show_thinking": True,
    "code_temperature": 0.3,        # keep the last Studio model in memory between creations
    "growth_tokens_per_param": 10,      # grow once it has read this many tokens per parameter
    "memory_budget_frac": 0.6,          # share of system RAM training may use (sets the max size)
    "max_params": 0,                    # 0 = no cap besides memory
    "mix": {"library": 0.65, "web": 0.22, "chat": 0.10, "actions": 0.03},
    # Crawling
    "crawl_delay_sec": 2.0,             # minimum gap between requests to the same site
    "crawl_max_pages": 500,             # per targeted-site crawl
    "crawl_seeds": [],                  # extra start pages, added to the active mode's own seeds
    "crawl_blocklist": [],
    "user_agent": f"MnemoBot/{VERSION} (self-learning AI; respects robots.txt; https://mnemoai.web.app)",
    # Chat
    "temperature": 0,                   # 0 = use the active mode's own setting
    "max_reply_tokens": 300,
    "use_memory": True,
    "memory_snippets": 4,
}

_lock = threading.Lock()


def ensure_dirs():
    for d in (HOME, LIBRARY_DIR, RAW_DIR, WEB_DIR, CHAT_DIR, ACTIONS_DIR, CKPT_DIR):
        d.mkdir(parents=True, exist_ok=True)


def load_settings() -> dict:
    ensure_dirs()
    s = json.loads(json.dumps(DEFAULTS))
    if SETTINGS_PATH.exists():
        try:
            s.update(json.loads(SETTINGS_PATH.read_text()))
        except json.JSONDecodeError:
            pass
    return s


def save_settings(updates: dict) -> dict:
    with _lock:
        s = load_settings()
        s.update({k: v for k, v in updates.items() if k in DEFAULTS})
        SETTINGS_PATH.write_text(json.dumps(s, indent=2))
        return s


def total_ram_bytes() -> int:
    if os.name == "nt":
        import ctypes

        class MemStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        m = MemStatus(dwLength=ctypes.sizeof(MemStatus))
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            return int(m.ullTotalPhys)
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return 16 * 1024**3
