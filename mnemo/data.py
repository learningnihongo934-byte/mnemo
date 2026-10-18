"""Token shards on disk and the sampler that mixes them into training batches.

Each group (library / web / chat / actions) is a folder of append-only .bin
files of uint16 token ids named <prefix>-NNN.bin, e.g. wikipedia-000.bin or
web-code-002.bin. Each prefix is one source with a topic; the active mode's
topic is sampled more often. Files can keep growing while training runs.
"""

from __future__ import annotations

import os
import random
import threading
from pathlib import Path

import numpy as np
import torch

DTYPE = np.uint16


class ShardWriter:
    """Append tokens to <dir>/<name>-NNN.bin, rolling to a new file every ~1 GB."""

    def __init__(self, directory: Path, name: str, max_bytes: int = 1 << 30):
        self.dir, self.name, self.max_bytes = Path(directory), name, max_bytes
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _current(self) -> Path:
        files = sorted(f for f in self.dir.glob(f"{self.name}-*.bin") if shard_prefix(f) == self.name)
        if files and files[-1].stat().st_size < self.max_bytes:
            return files[-1]
        return self.dir / f"{self.name}-{len(files):03d}.bin"

    def append(self, ids) -> int:
        arr = np.asarray(ids, dtype=DTYPE)
        if not arr.size:
            return 0
        with self._lock, open(self._current(), "ab") as f:
            f.write(arr.tobytes())
        return int(arr.size)


def shard_prefix(path: Path) -> str:
    return path.stem.rsplit("-", 1)[0]


class Source:
    def __init__(self, directory: Path, prefix: str):
        self.dir, self.prefix = Path(directory), prefix
        self.maps: list[np.memmap] = []
        self.sizes: list[int] = []
        self.refresh()

    def refresh(self):
        maps, sizes = [], []
        for f in sorted(self.dir.glob("*.bin")):
            if shard_prefix(f) != self.prefix:
                continue
            n = os.path.getsize(f) // np.dtype(DTYPE).itemsize
            if n > 1:
                maps.append(np.memmap(f, dtype=DTYPE, mode="r", shape=(n,)))
                sizes.append(n)
        self.maps, self.sizes = maps, sizes

    @property
    def tokens(self) -> int:
        return sum(self.sizes)

    def sample(self, length: int) -> np.ndarray | None:
        usable = [(m, n) for m, n in zip(self.maps, self.sizes) if n > length + 1]
        if not usable:
            # Small source: tile what we have.
            if not self.maps:
                return None
            data = np.concatenate([np.asarray(m) for m in self.maps])
            if data.size < 2:
                return None
            reps = (length + 1) // data.size + 1
            data = np.tile(data, reps)
            start = random.randrange(0, data.size - length - 1 + 1)
            return data[start:start + length + 1].astype(np.int64)
        weights = [n for _, n in usable]
        m, n = random.choices(usable, weights=weights)[0]
        start = random.randrange(0, n - length - 1)
        return np.asarray(m[start:start + length + 1], dtype=np.int64)


class Mixture:
    def __init__(self, dirs: dict[str, Path], weights: dict[str, float], topic_of=lambda prefix: "general",
                 mode: str = "general", boost: float = 5.0):
        self.dirs, self.weights, self.topic_of = dirs, weights, topic_of
        self.mode, self.boost = mode, boost
        self.only: set[tuple[str, str]] | None = None  # focused practice: train on just these sources
        self.sources: dict[tuple[str, str], Source] = {}
        self.refresh()

    def refresh(self):
        for group, d in self.dirs.items():
            for f in Path(d).glob("*.bin"):
                key = (group, shard_prefix(f))
                if key not in self.sources:
                    self.sources[key] = Source(d, key[1])
        for s in self.sources.values():
            s.refresh()

    def stats(self) -> dict[str, int]:
        out = {g: 0 for g in self.dirs}
        for (g, _), s in self.sources.items():
            out[g] += s.tokens
        return out

    def topic_stats(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for (_, prefix), s in self.sources.items():
            t = self.topic_of(prefix)
            out[t] = out.get(t, 0) + s.tokens
        return out

    def source_weights(self) -> dict[tuple[str, str], float]:
        """Group weight, shared among its sources by size, with the active mode's topic boosted."""
        out = {}
        if self.only:
            focus = {k: 1.0 for k in self.only if k in self.sources and self.sources[k].tokens > 64}
            if focus:
                return focus
        for group in self.dirs:
            gw = self.weights.get(group, 0)
            items = [(k, s) for k, s in self.sources.items() if k[0] == group and s.tokens > 64]
            if not gw or not items:
                continue
            boosted = {k: s.tokens * (self.boost if self.mode != "general" and self.topic_of(k[1]) == self.mode else 1.0)
                       for k, s in items}
            total = sum(boosted.values())
            for k, v in boosted.items():
                out[k] = gw * v / total
        return out

    def available(self) -> dict:
        return self.source_weights()

    def batch(self, batch_size: int, seq_len: int, device) -> tuple[torch.Tensor, torch.Tensor] | None:
        avail = self.source_weights()
        if not avail:
            return None
        keys, w = list(avail), list(avail.values())
        rows = []
        for _ in range(batch_size):
            row = self.sources[random.choices(keys, weights=w)[0]].sample(seq_len)
            if row is not None:
                rows.append(row)
        if not rows:
            return None
        arr = torch.from_numpy(np.stack(rows))
        x, y = arr[:, :-1], arr[:, 1:]
        return x.to(device, non_blocking=True), y.to(device, non_blocking=True)
