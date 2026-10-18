"""Bridge to the built-in browser in the desktop app.

The Electron app connects to /ws/browser and executes commands on its
browser view: navigate, snapshot (numbered list of clickable elements),
click, type, scroll, key, read text, screenshot, back/forward. Every action
is logged as a training example, so Mnemo gradually learns to drive the
browser itself.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import time

from fastapi import WebSocket

from . import events
from .config import ACTIONS_LOG


class BrowserBridge:
    def __init__(self):
        self.ws: WebSocket | None = None
        self.pending: dict[int, asyncio.Future] = {}
        self.ids = itertools.count(1)
        self.goal = ""

    @property
    def connected(self) -> bool:
        return self.ws is not None

    async def attach(self, ws: WebSocket):
        self.ws = ws
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                fut = self.pending.pop(msg.get("id"), None)
                if fut and not fut.done():
                    if msg.get("error"):
                        fut.set_exception(RuntimeError(msg["error"]))
                    else:
                        fut.set_result(msg.get("result"))
                elif msg.get("event"):
                    events.emit("browser", **msg)
        finally:
            self.ws = None
            for fut in self.pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("browser disconnected"))
            self.pending.clear()

    async def call(self, method: str, timeout: float = 30, **params):
        if not self.ws:
            raise RuntimeError("The browser isn't open (start the Mnemo desktop app).")
        i = next(self.ids)
        fut = asyncio.get_running_loop().create_future()
        self.pending[i] = fut
        await self.ws.send_text(json.dumps({"id": i, "method": method, "params": params}))
        return await asyncio.wait_for(fut, timeout)

    # Convenience wrappers ----------------------------------------------------
    async def snapshot(self) -> dict:
        return await self.call("snapshot")

    async def act(self, action: str, goal: str = "", **params):
        """Run an action and record it (with the page it was taken on) as training data."""
        before = None
        if action in ("click", "type", "scroll", "key", "navigate", "back", "forward"):
            try:
                before = await self.snapshot()
            except Exception:
                before = None
        result = await self.call(action, **params)
        if before is not None:
            log_action(goal or self.goal, before, action, params)
        events.emit("browser", event="action", action=action, params=params)
        return result


def page_text_for_model(snap: dict, limit: int = 40) -> str:
    lines = [f"url: {snap.get('url', '')}", f"title: {snap.get('title', '')}"]
    for el in snap.get("elements", [])[:limit]:
        lines.append(f"[{el['ref']}] {el['role']} \"{el['name'][:60]}\"")
    return "\n".join(lines)


def action_text(action: str, params: dict) -> str:
    if action == "navigate":
        return f"navigate {params.get('url', '')}"
    if action == "click":
        return f"click {params.get('ref')}"
    if action == "type":
        return f"type {params.get('ref')} {json.dumps(params.get('text', ''))}" + (" submit" if params.get("submit") else "")
    if action == "scroll":
        return f"scroll {params.get('direction', 'down')}"
    if action == "key":
        return f"key {params.get('key')}"
    return action


def log_action(goal: str, snap: dict, action: str, params: dict):
    ex = {"time": time.time(), "goal": goal or "browse", "page": page_text_for_model(snap),
          "action": action_text(action, params)}
    with open(ACTIONS_LOG, "a") as f:
        f.write(json.dumps(ex) + "\n")


def parse_action(text: str) -> tuple[str, dict] | None:
    """Parse an action string the model generated, e.g. 'click 12' or 'type 3 "cats" submit'."""
    parts = text.strip().split(" ", 1)
    if not parts or not parts[0]:
        return None
    verb, rest = parts[0].lower(), (parts[1] if len(parts) > 1 else "").strip()
    try:
        if verb == "navigate" and rest:
            return "navigate", {"url": rest.split()[0]}
        if verb == "click" and rest:
            return "click", {"ref": int(rest.split()[0])}
        if verb == "type" and rest:
            ref, txt = rest.split(" ", 1)
            submit = txt.endswith(" submit")
            txt = txt[: -len(" submit")] if submit else txt
            return "type", {"ref": int(ref), "text": json.loads(txt) if txt.startswith('"') else txt, "submit": submit}
        if verb == "scroll":
            return "scroll", {"direction": rest or "down"}
        if verb == "key" and rest:
            return "key", {"key": rest}
        if verb in ("back", "forward", "done"):
            return verb, {}
    except (ValueError, json.JSONDecodeError):
        return None
    return None
