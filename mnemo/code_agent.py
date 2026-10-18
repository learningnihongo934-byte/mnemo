"""Mnemo Code: Mnemo's own model working on files in a folder you choose.

The model writes one step at a time:

    THINK: what it's about to do and why
    ACTION: ls [path] | read <path> | find <text> | write <path> + ```fenced content```
            | replace <path> + <<<\\nold\\n===\\nnew\\n>>> | delete <path> | mkdir <path> | run <command> | done <message>

Each ACTION runs through a permission check:
  * ask     – every action (even reading) waits for your approval
  * partial – reading is automatic; writing, deleting and running commands ask first
  * full    – everything runs without asking
In every mode, paths are locked to the workspace folder and dangerous commands are refused.
Every change is backed up first so it can be undone.
"""

from __future__ import annotations

import asyncio
import difflib
import fnmatch
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from . import events, modes, tokenizer
from .config import HOME, load_settings, save_settings

BACKUPS = HOME / "code-backups"
READ_ONLY = {"ls", "read", "find"}
SKIP = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", "target", ".idea", ".DS_Store"}
BLOCKED = [r"\bsudo\b", r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\$HOME)(\s|$)", r"\bmkfs", r"\bdd\s+if=", r":\(\)\s*\{", r"\bshutdown\b",
           r"\breboot\b", r"(curl|wget)[^|]*\|\s*(ba|z)?sh", r"\bchmod\s+-R\s+777\s+/", r">\s*/dev/(sd|disk)", r"\bformat\s+[a-z]:",
           r"\bdiskutil\s+erase", r"\bdel\s+/[sq]", r"Remove-Item\s+.*-Recurse.*[A-Z]:\\\\?$"]
MAX_READ = 60_000


class CodeError(Exception):
    pass


class Workspace:
    def __init__(self, root: str):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise CodeError(f"Folder not found: {root}")
        if self.root == Path.home().resolve() or self.root == Path(self.root.anchor):
            raise CodeError("Pick a project folder, not your whole home folder or drive.")

    def path(self, rel: str) -> Path:
        rel = (rel or ".").strip().strip("'\"")
        p = (self.root / rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise CodeError(f"“{rel}” is outside the workspace. Mnemo Code only works inside {self.root.name}/.")
        if ".git" in p.relative_to(self.root).parts and p.name != ".gitignore":
            raise CodeError("Mnemo Code doesn't touch .git internals.")
        return p

    def rel(self, p: Path) -> str:
        return str(p.relative_to(self.root)) or "."

    def tree(self, rel: str = ".", depth: int = 1) -> list[dict]:
        base = self.path(rel)
        out = []
        for c in sorted(base.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if c.name in SKIP or (c.name.startswith(".") and c.name not in (".gitignore", ".env.example")):
                continue
            item = {"name": c.name, "path": self.rel(c), "dir": c.is_dir()}
            if not c.is_dir():
                item["size"] = c.stat().st_size
            out.append(item)
        return out[:500]

    def listing(self, limit: int = 60) -> list[str]:
        files = []
        for dp, dirs, fs in os.walk(self.root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP and not d.startswith("."))
            for f in sorted(fs):
                if not f.startswith("."):
                    files.append(self.rel(Path(dp) / f))
                if len(files) >= limit:
                    return files
        return files


# ------------------------------------------------------------------- parsing the model's step
ACTION_RE = re.compile(r"ACTION:\s*(\w+)\s*(.*)", re.S)


def parse_step(text: str) -> tuple[str, dict]:
    """Returns (thinking, action dict). Raises CodeError if there's no usable ACTION."""
    think = ""
    m = re.search(r"THINK:\s*(.*?)(?=\nACTION:|$)", text, re.S)
    if m:
        think = m.group(1).strip()
    a = ACTION_RE.search(text)
    if not a:
        raise CodeError("no ACTION line")
    verb, rest = a.group(1).lower(), a.group(2)
    first, _, body = rest.partition("\n")
    arg = first.strip()
    if verb in ("ls", "read", "delete", "mkdir", "find", "run", "done"):
        return think, {"tool": verb, "arg": arg if verb != "done" else rest.strip()}
    if verb == "write":
        fm = re.search(r"```[\w+-]*\n(.*?)```", body, re.S)
        if not arg or not fm:
            raise CodeError("write needs a path and a ``` block")
        return think, {"tool": "write", "arg": arg, "content": fm.group(1)}
    if verb == "replace":
        rm = re.search(r"<<<\n(.*?)\n===\n(.*?)\n>>>", body, re.S)
        if not arg or not rm:
            raise CodeError("replace needs a path and <<< old === new >>>")
        return think, {"tool": "replace", "arg": arg, "old": rm.group(1), "new": rm.group(2)}
    raise CodeError(f"unknown action “{verb}”")


def describe(a: dict) -> str:
    t, arg = a["tool"], a.get("arg", "")
    return {"ls": f"List {arg or 'the workspace'}", "read": f"Read {arg}", "find": f"Search for “{arg}”",
            "write": f"Write {arg}", "replace": f"Edit {arg}", "delete": f"Delete {arg}", "mkdir": f"Create folder {arg}",
            "run": f"Run `{arg}`", "done": "Finish"}.get(t, t)


# ------------------------------------------------------------------- the session
class CodeSession:
    def __init__(self):
        self.pending: dict[str, asyncio.Future] = {}
        self.always: set[str] = set()       # tools approved for the rest of this session
        self.undo_stack: list[list[tuple[str, str | None]]] = []   # per task: (abs path, backup path or None if new)
        self.stop = False
        self.running = False

    # --- settings ------------------------------------------------------------
    @staticmethod
    def cfg() -> dict:
        s = load_settings()
        return {"workspace": s.get("code_workspace", ""), "permission": s.get("code_permission", "ask"),
                "allow_commands": s.get("code_allow_commands", True), "max_steps": int(s.get("code_max_steps", 10)),
                "show_thinking": s.get("code_show_thinking", True), "recent": s.get("code_recent", []),
                "temperature": float(s.get("code_temperature", 0.3))}

    def workspace(self) -> Workspace:
        ws = self.cfg()["workspace"]
        if not ws:
            raise CodeError("Choose a folder for Mnemo Code first.")
        return Workspace(ws)

    @staticmethod
    def set_workspace(path: str) -> dict:
        ws = Workspace(path)
        recent = [str(ws.root)] + [r for r in load_settings().get("code_recent", []) if r != str(ws.root)]
        save_settings({"code_workspace": str(ws.root), "code_recent": recent[:8]})
        return {"workspace": str(ws.root), "recent": recent[:8]}

    # --- permissions -----------------------------------------------------------
    def needs_approval(self, tool: str) -> bool:
        if tool == "done" or tool in self.always:
            return False
        mode = self.cfg()["permission"]
        if mode == "full":
            return False
        if mode == "partial":
            return tool not in READ_ONLY
        return True

    async def approve(self, send, step: dict) -> bool:
        if not self.needs_approval(step["action"]["tool"]):
            return True
        fut = asyncio.get_running_loop().create_future()
        self.pending[step["id"]] = fut
        await send({"type": "code", "stage": "approve", **step})
        try:
            ok = await fut
        finally:
            self.pending.pop(step["id"], None)
        return ok

    def answer(self, step_id: str, ok: bool, always: bool = False, tool: str = ""):
        if always and tool:
            self.always.add(tool)
        fut = self.pending.get(step_id)
        if fut and not fut.done():
            fut.set_result(ok)

    # --- tools -------------------------------------------------------------------
    def _backup(self, p: Path, changes: list):
        if p.exists() and p.is_file():
            dest = BACKUPS / time.strftime("%Y%m%d-%H%M%S") / uuid.uuid4().hex[:6] / p.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
            changes.append((str(p), str(dest)))
        elif not p.exists():
            changes.append((str(p), None))

    def preview(self, ws: Workspace, a: dict) -> dict:
        """Extra detail shown on the action card (diffs for edits)."""
        t = a["tool"]
        if t in ("write", "replace"):
            p = ws.path(a["arg"])
            old = p.read_text(errors="replace") if p.exists() else ""
            new = a["content"] if t == "write" else old.replace(a["old"], a["new"], 1)
            if t == "replace" and a["old"] not in old:
                return {"warning": "The text to replace wasn't found in the file."}
            diff = list(difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=2))[2:]
            return {"diff": "\n".join(diff[:400]), "new_file": not p.exists(),
                    "added": sum(1 for d in diff if d.startswith("+")), "removed": sum(1 for d in diff if d.startswith("-"))}
        if t == "delete":
            return {"warning": "This deletes the file (a backup is kept for Undo)."}
        if t == "run":
            return {"cwd": ws.root.name}
        return {}

    def execute(self, ws: Workspace, a: dict, changes: list) -> str:
        t, arg = a["tool"], a.get("arg", "")
        if t == "ls":
            items = ws.tree(arg or ".")
            return "\n".join(("📁 " if i["dir"] else "   ") + i["path"] for i in items) or "(empty)"
        if t == "read":
            p = ws.path(arg)
            if not p.is_file():
                raise CodeError(f"{arg} is not a file")
            text = p.read_text(errors="replace")
            return text[:MAX_READ] + ("\n… (truncated)" if len(text) > MAX_READ else "")
        if t == "find":
            hits = []
            for rel in ws.listing(2000):
                p = ws.root / rel
                if p.stat().st_size > 2_000_000:
                    continue
                try:
                    for n, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                        if arg.lower() in line.lower() or fnmatch.fnmatch(rel, arg):
                            hits.append(f"{rel}:{n}: {line.strip()[:160]}")
                            if len(hits) >= 60:
                                return "\n".join(hits)
                except OSError:
                    pass
            return "\n".join(hits) or "no matches"
        if t == "write":
            p = ws.path(arg)
            self._backup(p, changes)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(a["content"])
            return f"wrote {arg} ({a['content'].count(chr(10)) + 1} lines)"
        if t == "replace":
            p = ws.path(arg)
            text = p.read_text()
            if a["old"] not in text:
                raise CodeError(f"the text to replace wasn't found in {arg}")
            self._backup(p, changes)
            p.write_text(text.replace(a["old"], a["new"], 1))
            return f"edited {arg}"
        if t == "delete":
            p = ws.path(arg)
            if p.is_dir():
                raise CodeError("Mnemo Code only deletes files, not folders.")
            self._backup(p, changes)
            p.unlink()
            return f"deleted {arg}"
        if t == "mkdir":
            ws.path(arg).mkdir(parents=True, exist_ok=True)
            return f"created folder {arg}"
        if t == "run":
            if not self.cfg()["allow_commands"]:
                raise CodeError("Running commands is turned off in Mnemo Code settings.")
            for pat in BLOCKED:
                if re.search(pat, arg, re.I):
                    raise CodeError("That command is blocked for safety.")
            r = subprocess.run(arg, shell=True, cwd=ws.root, capture_output=True, text=True, timeout=120)
            out = (r.stdout + r.stderr).strip()
            return f"exit code {r.returncode}\n{out[-8000:]}" if out else f"exit code {r.returncode}"
        raise CodeError(f"unknown tool {t}")

    def undo(self) -> str:
        if not self.undo_stack:
            return "Nothing to undo."
        changes = self.undo_stack.pop()
        for path, backup in reversed(changes):
            p = Path(path)
            if backup is None:
                p.unlink(missing_ok=True)
            else:
                p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup, p)
        return f"Undid {len(changes)} change{'s' if len(changes) != 1 else ''}."

    # --- direct commands (work regardless of how well the model is trained) ------
    async def direct(self, text: str, send) -> bool:
        m = re.match(r"^/(ls|read|find|run|delete|mkdir|undo)\b\s*(.*)$", text.strip(), re.S)
        if not m:
            return False
        tool, arg = m.group(1), m.group(2).strip()
        if tool == "undo":
            await send({"type": "code", "stage": "note", "text": self.undo()})
            return True
        await self.run_action(send, {"tool": tool, "arg": arg}, "", [])
        return True

    async def run_action(self, send, action: dict, think: str, changes: list) -> tuple[bool, str]:
        ws = self.workspace()
        step = {"id": uuid.uuid4().hex[:8], "action": action, "label": describe(action), "think": think}
        try:
            step["preview"] = self.preview(ws, action)
        except CodeError as e:
            step["preview"] = {"warning": str(e)}
        if not await self.approve(send, step):
            await send({"type": "code", "stage": "result", "id": step["id"], "ok": False, "text": "Denied by you."})
            return False, "DENIED by the user"
        if action["tool"] != "done":
            await send({"type": "code", "stage": "running", **step})
        try:
            out = await asyncio.to_thread(self.execute, ws, action, changes) if action["tool"] != "done" else action["arg"]
            await send({"type": "code", "stage": "result", "id": step["id"], "ok": True, "text": out, "action": action,
                        "label": step["label"]})
            if changes and action["tool"] in ("write", "replace", "delete"):
                await send({"type": "code", "stage": "tree"})
            return True, out
        except (CodeError, OSError, subprocess.TimeoutExpired) as e:
            msg = str(e) if isinstance(e, CodeError) else f"{type(e).__name__}: {e}"
            await send({"type": "code", "stage": "result", "id": step["id"], "ok": False, "text": msg})
            return False, "ERROR: " + msg

    # --- the agent loop ------------------------------------------------------------
    async def task(self, agent, task: str, send):
        cfg = self.cfg()
        ws = self.workspace()
        tok = tokenizer.load()
        if tok is None or not agent.trainer.ensure_model():
            await send({"type": "code", "stage": "end", "ok": False,
                        "text": "Mnemo has no brain yet. Teach it first (Learn), then try again."})
            return
        self.running, self.stop = True, False
        changes: list = []
        files = ws.listing(40)
        convo = [{"role": "system", "content": modes.tag("code-agent")},
                 {"role": "user", "content": f"TASK: {task}\nFILES: {', '.join(files) or '(empty folder)'}"}]
        stops = {tokenizer.sid(tok, tokenizer.END), tokenizer.sid(tok, tokenizer.EOT), tokenizer.sid(tok, tokenizer.USER)}
        await send({"type": "code", "stage": "start", "task": task, "workspace": ws.root.name})
        finished, ok = False, True
        try:
            for n in range(cfg["max_steps"]):
                if self.stop:
                    break
                ids = tokenizer.encode_chat(tok, convo) + [tokenizer.sid(tok, tokenizer.ASSISTANT)]
                await send({"type": "code", "stage": "thinking", "n": n + 1})
                loop = asyncio.get_running_loop()
                shown = [""]

                def on_token(out):
                    full = tok.decode(out)
                    if cfg["show_thinking"] and full != shown[0]:
                        shown[0] = full
                        asyncio.run_coroutine_threadsafe(send({"type": "code", "stage": "stream", "text": full}), loop)

                out = await asyncio.to_thread(agent._generate_ids, ids[-6000:], 400, cfg["temperature"], stops, on_token)
                text = tok.decode(out)
                try:
                    think, action = parse_step(text)
                except CodeError as e:
                    await send({"type": "code", "stage": "end", "ok": False, "raw": text[:600],
                                "text": f"My own model wrote something I can't turn into an action yet ({e}). "
                                        "Mnemo Code improves after **Teach Mnemo Code**; meanwhile the direct commands "
                                        "(`/read`, `/ls`, `/find`, `/run`, `/undo`) always work."})
                    return
                convo.append({"role": "assistant", "content": text.strip()})
                if action["tool"] == "done":
                    await send({"type": "code", "stage": "end", "ok": True, "text": action["arg"] or "Done.", "think": think})
                    finished = True
                    break
                good, result = await self.run_action(send, action, think, changes)
                ok = ok and good
                convo.append({"role": "user", "content": "RESULT:\n" + result[:4000]})
            if not finished:
                await send({"type": "code", "stage": "end", "ok": False,
                            "text": "Stopped." if self.stop else f"Reached the step limit ({cfg['max_steps']})."})
        finally:
            if changes:
                self.undo_stack.append(changes)
                events.emit("code", stage="changed", count=len(changes))
            self.running = False
