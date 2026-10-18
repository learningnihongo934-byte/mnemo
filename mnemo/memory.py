"""Long-term memory: every page Mnemo reads, searchable with full-text search.

The model's weights have a fixed size at any moment; this store does not. At
chat time the most relevant snippets are pulled from here and placed in the
model's context, so knowledge keeps accumulating without limit. The crawl
frontier (URLs waiting to be visited) also lives here.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
import threading
import time
from urllib.parse import urlparse

from .config import MEMORY_DB

_local = threading.local()

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS docs (
    id INTEGER PRIMARY KEY,
    url TEXT UNIQUE,
    title TEXT,
    source TEXT,
    added REAL,
    chars INTEGER,
    hash TEXT UNIQUE,
    text TEXT,              -- kept until the trainer has tokenized it
    tokenized INTEGER DEFAULT 0,
    topic TEXT DEFAULT 'general'   -- the mode it was learned in (see modes.py)
);
CREATE INDEX IF NOT EXISTS docs_untok ON docs(tokenized);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
    text, title, url UNINDEXED, doc_id UNINDEXED, tokenize='porter unicode61'
);
CREATE TABLE IF NOT EXISTS frontier (
    url TEXT PRIMARY KEY,
    site TEXT,
    depth INTEGER,
    job TEXT,
    priority REAL,
    status INTEGER DEFAULT 0,   -- 0 queued, 1 done, 2 failed/skipped
    added REAL
);
CREATE INDEX IF NOT EXISTS frontier_q ON frontier(job, status, priority);
"""


def db() -> sqlite3.Connection:
    con = getattr(_local, "con", None)
    if con is None:
        MEMORY_DB.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(MEMORY_DB, timeout=30, check_same_thread=False)
        con.row_factory = sqlite3.Row
        con.executescript(SCHEMA)
        try:  # databases created before modes existed
            con.execute("ALTER TABLE docs ADD COLUMN topic TEXT DEFAULT 'general'")
        except sqlite3.OperationalError:
            pass
        _local.con = con
    return con


def chunk_text(text: str, size: int = 1000) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) > size and cur:
            chunks.append(cur)
            cur = ""
        cur = f"{cur}\n{p}" if cur else p
        while len(cur) > size * 1.5:
            chunks.append(cur[:size])
            cur = cur[size:]
    if cur:
        chunks.append(cur)
    return chunks


def add_doc(url: str, title: str, text: str, source: str, *, topic: str = "general", keep_text: bool = True,
            max_chunks: int | None = None, commit: bool = True) -> int | None:
    """Store a document. Returns its id, or None if it's a duplicate/too short."""
    text = text.strip()
    if len(text) < 200:
        return None
    h = hashlib.sha1(re.sub(r"\s+", " ", text.lower()).encode()).hexdigest()
    con = db()
    try:
        cur = con.execute(
            "INSERT INTO docs(url,title,source,added,chars,hash,text,tokenized,topic) VALUES(?,?,?,?,?,?,?,?,?)",
            (url, title, source, time.time(), len(text), h, text if keep_text else None, 0 if keep_text else 1, topic),
        )
    except sqlite3.IntegrityError:
        return None
    doc_id = cur.lastrowid
    pieces = chunk_text(text)
    if max_chunks:
        pieces = pieces[:max_chunks]
    con.executemany(
        "INSERT INTO chunks(text,title,url,doc_id) VALUES(?,?,?,?)",
        [(c, title, url, doc_id) for c in pieces],
    )
    if commit:
        con.commit()
    return doc_id


def commit():
    db().commit()


_WORD = re.compile(r"[A-Za-z0-9]{2,}")
_STOP = set("the a an and or of to in on for is are was were be been with what who how why when where "
            "which do does did you your me my i it its this that can could would should tell about please".split())


def search(query: str, k: int = 4, topic: str | None = None) -> list[dict]:
    """Full-text search. Results learned in `topic`'s mode rank higher."""
    words = [w for w in _WORD.findall(query.lower()) if w not in _STOP][:12]
    if not words:
        return []
    q = " OR ".join(f'"{w}"' for w in words)
    rows = db().execute(
        "SELECT chunks.text AS text, chunks.title AS title, chunks.url AS url, bm25(chunks, 1.0, 2.0) AS score, "
        "docs.topic AS topic FROM chunks LEFT JOIN docs ON docs.id = chunks.doc_id "
        "WHERE chunks MATCH ? ORDER BY score LIMIT ?", (q, k * 6)).fetchall()
    scored = []
    for r in rows:
        score = -r["score"] * (2.0 if topic and topic != "general" and r["topic"] == topic else 1.0)
        scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    out, seen = [], set()
    for score, r in scored:
        if r["url"] in seen:
            continue
        seen.add(r["url"])
        out.append({"text": r["text"], "title": r["title"], "url": r["url"], "score": score,
                    "topic": r["topic"] or "general"})
        if len(out) >= k:
            break
    return out


def chunks_for_url(url: str, limit: int = 3) -> list[dict]:
    rows = db().execute("SELECT text, title, url FROM chunks WHERE url=? LIMIT ?", (url, limit)).fetchall()
    return [dict(r) for r in rows]


def forget(url: str) -> int:
    """Remove a document from memory (it stops being used in replies). Returns docs removed."""
    con = db()
    con.execute("DELETE FROM chunks WHERE url=?", (url,))
    n = con.execute("DELETE FROM docs WHERE url=?", (url,)).rowcount
    con.commit()
    return n


def untokenized(limit: int = 200) -> list[sqlite3.Row]:
    return db().execute("SELECT id, title, text, topic FROM docs WHERE tokenized=0 LIMIT ?", (limit,)).fetchall()


def mark_tokenized(ids: list[int]):
    con = db()
    con.executemany("UPDATE docs SET tokenized=1, text=NULL WHERE id=?", [(i,) for i in ids])
    con.commit()


def stats() -> dict:
    con = db()
    docs = con.execute("SELECT COUNT(*), COALESCE(SUM(chars),0) FROM docs").fetchone()
    by = dict(con.execute("SELECT source, COUNT(*) FROM docs GROUP BY source").fetchall())
    topics = dict(con.execute("SELECT COALESCE(topic,'general'), COUNT(*) FROM docs GROUP BY topic").fetchall())
    queued = con.execute("SELECT COUNT(*) FROM frontier WHERE status=0").fetchone()[0]
    return {"docs": docs[0], "chars": docs[1], "by_source": by, "by_topic": topics, "frontier": queued}


def recent(limit: int = 30) -> list[dict]:
    rows = db().execute("SELECT title, url, source, added, chars, topic FROM docs ORDER BY id DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


def known_url(url: str) -> bool:
    return db().execute("SELECT 1 FROM docs WHERE url=?", (url,)).fetchone() is not None


# --- crawl frontier -----------------------------------------------------------

def enqueue(urls: list[str], job: str, depth: int, priority: float = 0.0):
    con = db()
    rows = [(u, urlparse(u).netloc, depth, job, priority, time.time()) for u in urls]
    con.executemany(
        "INSERT OR IGNORE INTO frontier(url,site,depth,job,priority,status,added) VALUES(?,?,?,?,?,0,?)", rows)
    con.commit()


def next_urls(job: str, limit: int = 50) -> list[sqlite3.Row]:
    return db().execute(
        "SELECT url, site, depth FROM frontier WHERE job=? AND status=0 ORDER BY priority DESC, added LIMIT ?",
        (job, limit)).fetchall()


def mark_url(url: str, status: int):
    con = db()
    con.execute("UPDATE frontier SET status=? WHERE url=?", (status, url))
    con.commit()


def requeue(urls: list[str]):
    con = db()
    con.executemany("UPDATE frontier SET status=0 WHERE url=?", [(u,) for u in urls])
    con.commit()


def clear_job(job: str):
    con = db()
    con.execute("DELETE FROM frontier WHERE job=? AND status=0", (job,))
    con.commit()
