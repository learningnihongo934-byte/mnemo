"""The seed library: clean, openly available text Mnemo reads first, so it
learns language much faster than from raw web pages alone. Which datasets get
downloaded depends on the active mode (see modes.py).
"""

from __future__ import annotations

import json
import random
import threading
from pathlib import Path

import httpx
import pyarrow.parquet as pq

from . import events, memory, modes, tokenizer
from .config import CHAT_DIR, LIBRARY_DIR, RAW_DIR, load_settings
from .data import ShardWriter

HF = "https://huggingface.co"
PERMISSIVE = {"mit", "apache-2.0", "bsd-3-clause", "bsd-2-clause", "isc", "cc0-1.0", "unlicense"}


def _code_text(r):
    if r.get("license") not in PERMISSIVE or len(r["code"]) > 30000:
        return None
    return f"# {r['path']} ({r['language']})\n{r['code']}"


# kind "text" -> one document per row; kind "chat" -> one conversation per row.
# `memory` = how many chunks of each document also go into searchable memory.
SOURCES = {
    "wikipedia": {"repo": "wikimedia/wikipedia", "path": "20231101.en", "match": "train-", "kind": "text",
                  "topic": "general", "license": "CC BY-SA 4.0", "columns": ["text", "title", "url"], "memory": 3,
                  "text": lambda r: r["text"]},
    "fineweb-edu": {"repo": "HuggingFaceFW/fineweb-edu", "path": "sample/10BT", "match": ".parquet", "kind": "text",
                    "topic": "general", "license": "ODC-BY", "columns": ["text"], "text": lambda r: r["text"]},
    "smoltalk": {"repo": "HuggingFaceTB/smol-smoltalk", "path": "data", "match": "train-", "kind": "chat",
                 "topic": "conversation", "license": "Apache-2.0", "columns": ["messages"],
                 "chat": lambda r: r["messages"]},
    "code": {"repo": "codeparrot/github-code-clean", "path": "data", "match": "train-", "kind": "text",
             "topic": "code", "license": "per-file (only MIT/Apache/BSD/ISC/CC0 files are used)",
             "columns": ["code", "path", "language", "license"], "text": _code_text},
    "code-instruct": {"repo": "bigcode/self-oss-instruct-sc2-exec-filter-50k", "path": "data", "match": "train-",
                      "kind": "chat", "topic": "code", "license": "ODC-BY", "columns": ["instruction", "response"],
                      "chat": lambda r: [{"role": "user", "content": r["instruction"]},
                                         {"role": "assistant", "content": r["response"]}]},
    "finemath": {"repo": "HuggingFaceTB/finemath", "path": "finemath-4plus", "match": ".parquet", "kind": "text",
                 "topic": "math", "license": "ODC-BY", "columns": ["text"], "text": lambda r: r["text"]},
    "gsm8k": {"repo": "openai/gsm8k", "path": "main", "match": "train-", "kind": "chat", "topic": "math",
              "license": "MIT", "columns": ["question", "answer"],
              "chat": lambda r: [{"role": "user", "content": r["question"]},
                                 {"role": "assistant", "content": r["answer"].replace("####", "Answer:")}]},
    "gutenberg": {"repo": "sedthh/gutenberg_english", "path": "data", "match": "train-", "kind": "text",
                  "topic": "literature", "license": "public domain texts (dataset MIT)", "columns": ["TEXT"],
                  "text": lambda r: r["TEXT"]},
    "cc-news": {"repo": "vblagoje/cc_news", "path": "plain_text", "match": "train-", "kind": "text",
                "topic": "news", "license": "unspecified (news articles, research use)", "memory": 2,
                "columns": ["title", "text", "url"], "text": lambda r: f"{r['title']}\n\n{r['text']}"},
    "arxiv": {"repo": "ccdv/arxiv-summarization", "path": "document", "match": "train-", "kind": "text",
              "topic": "science", "license": "unspecified (arXiv papers, research use)", "memory": 1,
              "columns": ["article", "abstract"], "text": lambda r: f"{r['abstract']}\n\n{r['article']}"},
    "sciq": {"repo": "allenai/sciq", "path": "data", "match": "train-", "kind": "chat", "topic": "science",
             "license": "CC BY-NC 3.0 (non-commercial)", "columns": ["question", "correct_answer", "support"],
             "chat": lambda r: [{"role": "user", "content": r["question"]},
                                {"role": "assistant", "content": f"{r['correct_answer']}. {r['support']}".strip()}]},
}

MANIFEST = LIBRARY_DIR / "manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {"done": []}


def _save_manifest(m: dict):
    MANIFEST.write_text(json.dumps(m, indent=2))


def list_files(source: str) -> list[dict]:
    s = SOURCES[source]
    r = httpx.get(f"{HF}/api/datasets/{s['repo']}/tree/main/{s['path']}", timeout=30, follow_redirects=True)
    r.raise_for_status()
    files = [f for f in r.json() if f["type"] == "file" and s["match"] in f["path"] and f["path"].endswith(".parquet")]
    return [{"source": source, "path": f["path"], "size": f.get("size", 0),
             "url": f"{HF}/datasets/{s['repo']}/resolve/main/{f['path']}"} for f in sorted(files, key=lambda f: f["path"])]


def plan(preset: str, mode: str = "general") -> list[dict]:
    """Files this mode's preset would download (skipping ones already processed)."""
    done = set(_manifest()["done"])
    out = []
    for source, n in modes.get(mode)["library"][preset].items():
        files = [f for f in list_files(source) if f["url"] not in done]
        out += files[:n]
    return out


def _download(f: dict, stop: threading.Event) -> Path | None:
    dest = RAW_DIR / f"{f['source']}__{Path(f['path']).name}"
    part = dest.with_suffix(".part")
    if dest.exists():
        return dest
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    with httpx.stream("GET", f["url"], headers=headers, timeout=60, follow_redirects=True) as r:
        if r.status_code == 200:
            have = 0  # server ignored the range; start over
        elif r.status_code != 206:
            r.raise_for_status()
        total = have + int(r.headers.get("content-length", 0))
        last = 0
        with open(part, "ab" if have else "wb") as out:
            for chunk in r.iter_bytes(1 << 20):
                if stop.is_set():
                    return None
                out.write(chunk)
                have += len(chunk)
                if have - last > 16 << 20:
                    last = have
                    events.emit("library", stage="download", file=f["path"], done=have, total=total)
    part.rename(dest)
    return dest


def _rows(path: Path, source: str):
    """Yield ("text", str, row) or ("chat", messages, row) for each usable row."""
    spec = SOURCES[source]
    pf = pq.ParquetFile(path)
    cols = [c for c in spec["columns"] if c in pf.schema_arrow.names]
    for batch in pf.iter_batches(batch_size=256, columns=cols):
        for row in batch.to_pylist():
            try:
                item = spec["chat"](row) if spec["kind"] == "chat" else spec["text"](row)
            except (KeyError, TypeError):
                continue
            if item:
                yield spec["kind"], item, row


def _train_tokenizer(files: list[tuple[Path, str]], budget_chars: int = 120_000_000):
    events.emit("library", stage="tokenizer", text="Building Mnemo's vocabulary from scratch…")

    def sample():
        share = budget_chars // max(1, len(files))
        for p, source in files:
            got = 0
            for kind, item, _ in _rows(p, source):
                text = " ".join(m["content"] for m in item) if kind == "chat" else item
                yield text
                got += len(text)
                if got > share:
                    break
    tokenizer.train(sample())


def tagged_ids(tok, topic: str, text: str) -> list[int]:
    """<|system|>mode: topic<|end|> text <|endoftext|>"""
    sid = lambda t: tokenizer.sid(tok, t)
    return ([sid(tokenizer.SYSTEM)] + tok.encode(modes.tag(topic)).ids + [sid(tokenizer.END)]
            + tok.encode(text).ids + [sid(tokenizer.EOT)])


def _process(path: Path, f: dict, tok, stop: threading.Event):
    spec = SOURCES[f["source"]]
    topic = spec["topic"]
    writer = ShardWriter(CHAT_DIR if spec["kind"] == "chat" else LIBRARY_DIR, f["source"])
    head = ([tokenizer.sid(tok, tokenizer.SYSTEM)] + tok.encode(modes.tag(topic)).ids + [tokenizer.sid(tok, tokenizer.END)])
    eot = tokenizer.sid(tok, tokenizer.EOT)
    buf, n_docs, n_tok = [], 0, 0

    def flush():
        nonlocal n_tok
        ids = []
        if spec["kind"] == "chat":
            for msgs in buf:
                ids += tokenizer.chat_training_ids(tok, [{"role": "system", "content": modes.tag(topic)}] + list(msgs))
        else:
            for enc in tok.encode_batch([text for text, _ in buf]):
                ids += head + enc.ids + [eot]
            if spec.get("memory"):
                for text, row in buf:
                    title = row.get("title") or text.split("\n", 1)[0][:120]
                    memory.add_doc(row.get("url") or f"{f['source']}:{hash(text)}", title, text, "library",
                                   topic=topic, keep_text=False, max_chunks=spec["memory"], commit=False)
                memory.commit()
        n_tok += writer.append(ids)
        buf.clear()

    for kind, item, row in _rows(path, f["source"]):
        if stop.is_set():
            return False
        buf.append(item if kind == "chat" else (item, row))
        n_docs += 1
        if len(buf) >= 256:
            flush()
            if n_docs % 10240 == 0:
                events.emit("library", stage="tokenize", file=f["path"], docs=n_docs, tokens=n_tok)
    if buf:
        flush()
    events.emit("library", stage="tokenize", file=f["path"], docs=n_docs, tokens=n_tok)
    return True


def build(preset: str, stop: threading.Event, files: list[dict] | None = None, mode: str = "general"):
    """Download + tokenize a preset. Safe to stop and resume later."""
    files = files if files is not None else plan(preset, mode)
    if not files:
        events.emit("library", stage="done", text="Library already complete for this preset.")
        return
    paths = []
    for i, f in enumerate(files):
        events.emit("library", stage="download", file=f["path"], index=i, count=len(files), done=0, total=f["size"])
        p = _download(f, stop)
        if p is None:
            events.emit("library", stage="stopped")
            return
        paths.append((p, f))

    tok = tokenizer.load()
    if tok is None:
        _train_tokenizer([(p, f["source"]) for p, f in paths])
        tok = tokenizer.load()

    m = _manifest()
    keep_raw = load_settings().get("keep_raw", False)
    random.shuffle(paths)  # interleave sources across shards
    for p, f in paths:
        if f["url"] in m["done"]:
            continue
        if not _process(p, f, tok, stop):
            events.emit("library", stage="stopped")
            return
        m["done"].append(f["url"])
        _save_manifest(m)
        if not keep_raw:
            p.unlink(missing_ok=True)
    events.emit("library", stage="done", text="Library ready. Mnemo can start learning.")
