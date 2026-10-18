"""Tiny thread-safe pub/sub so background workers can stream status to the UI."""

from __future__ import annotations

import asyncio
import threading
import time

_subs: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []
_lock = threading.Lock()


def subscribe() -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    with _lock:
        _subs.append((asyncio.get_running_loop(), q))
    return q


def unsubscribe(q: asyncio.Queue):
    with _lock:
        _subs[:] = [(l, s) for l, s in _subs if s is not q]


def emit(kind: str, **data):
    msg = {"type": kind, "time": time.time(), **data}
    with _lock:
        subs = list(_subs)
    for loop, q in subs:
        def put(q=q):
            if not q.full():
                q.put_nowait(msg)
        try:
            loop.call_soon_threadsafe(put)
        except RuntimeError:
            pass  # loop closed


def log(source: str, text: str):
    emit("log", source=source, text=text)
