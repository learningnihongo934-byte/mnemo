"""Plugins: drop a .py file into ~/.mnemo/plugins/ (or the repo's plugins/ folder) to add chat commands.

    # ~/.mnemo/plugins/hello.py
    def register(mnemo):
        @mnemo.command("/hello", "say hello")
        def hello(arg, ctx):
            return f"Hello, {arg or 'friend'}!"

A command gets the text after the command and a `ctx` with `trainer`, `crawler`, `browser`,
`memory` and `settings`. It may be sync or async and returns Markdown to show in chat
(or None). Plugins run with your own permissions, so only install ones you trust.
"""

from __future__ import annotations

import importlib.util
import inspect
import traceback
from pathlib import Path

from . import events
from .config import HOME

DIRS = [Path(__file__).resolve().parent.parent / "plugins", HOME / "plugins"]


class Registry:
    def __init__(self):
        self.commands: dict[str, tuple[str, object, str]] = {}  # name -> (help, fn, plugin)
        self.loaded: list[dict] = []
        self._current = ""

    def command(self, name: str, help: str = ""):
        def deco(fn):
            self.commands[name.lower()] = (help, fn, self._current)
            return fn
        return deco

    def load(self):
        self.commands.clear()
        self.loaded.clear()
        for d in DIRS:
            d.mkdir(parents=True, exist_ok=True) if d == HOME / "plugins" else None
            for f in sorted(d.glob("*.py")) if d.exists() else []:
                if f.name.startswith("_"):
                    continue
                self._current = f.stem
                try:
                    spec = importlib.util.spec_from_file_location(f"mnemo_plugin_{f.stem}", f)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    mod.register(self)
                    self.loaded.append({"name": f.stem, "path": str(f), "ok": True,
                                        "about": (mod.__doc__ or "").strip().split("\n")[0]})
                except Exception as e:
                    self.loaded.append({"name": f.stem, "path": str(f), "ok": False, "error": f"{type(e).__name__}: {e}"})
        events.log("plugins", f"{len(self.commands)} plugin commands loaded")

    async def run(self, text: str, ctx) -> str | None | bool:
        """Run a plugin command. Returns False if `text` isn't one."""
        name, _, arg = text.strip().partition(" ")
        entry = self.commands.get(name.lower())
        if not entry:
            return False
        _, fn, plugin = entry
        try:
            out = fn(arg.strip(), ctx)
            if inspect.isawaitable(out):
                out = await out
            return out
        except Exception:
            return f"⚠️ Plugin `{plugin}` failed:\n```\n{traceback.format_exc(limit=3)}```"


registry = Registry()
