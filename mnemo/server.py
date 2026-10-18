"""Local API server the desktop app talks to (127.0.0.1 only).

Run:  python -m mnemo.server --port 8765
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect

from . import account, basics, events, files, library, memory, modes, plugins, studio
from .agent import Agent
from .browser import BrowserBridge
from .config import CHATS_PATH, HOME, ensure_dirs, load_settings, save_settings
from .crawler import Crawler
from .trainer import Trainer

TOKEN = os.environ.get("MNEMO_TOKEN", "")
state: dict = {}


@asynccontextmanager
async def lifespan(_app):
    startup()
    yield
    shutdown()


app = FastAPI(title="Mnemo", lifespan=lifespan)


def _check(token: str | None):
    if TOKEN and token != TOKEN:
        raise HTTPException(403, "bad token")


@app.middleware("http")
async def auth(request: Request, call_next):
    open_paths = request.url.path == "/auth/callback" or (
        request.url.path.startswith("/files/") and request.query_params.get("token") == TOKEN)
    if TOKEN and not open_paths and request.headers.get("x-mnemo-token") != TOKEN:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "forbidden"}, status_code=403)
    return await call_next(request)


def startup():
    ensure_dirs()
    state["trainer"] = Trainer()
    state["crawler"] = Crawler()
    state["browser"] = BrowserBridge()
    state["agent"] = Agent(state["trainer"], state["crawler"], state["browser"])
    state["library_stop"] = threading.Event()
    state["library_thread"] = None
    plugins.registry.load()
    s = load_settings()
    if s["auto_train"]:
        state["trainer"].start()
    if s["auto_explore"]:
        state["crawler"].start_auto()
    events.log("server", f"Mnemo data folder: {HOME}")


def shutdown():
    state["crawler"].stop()
    state["trainer"].pause()
    state["trainer"].save()


# ---------------------------------------------------------------- REST
@app.get("/api/status")
def status():
    return {"trainer": state["trainer"].status(), "memory": memory.stats(),
            "crawl": state["crawler"].status(), "browser": state["browser"].connected,
            "library": bool(state["library_thread"] and state["library_thread"].is_alive()), "home": str(HOME)}


@app.post("/api/train/{action}")
def train(action: str):
    tr = state["trainer"]
    if action == "start":
        tr.start()
    elif action == "pause":
        tr.pause()
    elif action == "save":
        threading.Thread(target=tr.save, daemon=True).start()
    return tr.status()


@app.get("/api/modes")
def get_modes():
    return {"mode": load_settings()["mode"], "modes": modes.public_list()}


@app.post("/api/mode")
def set_mode(body: dict):
    try:
        state["agent"].set_mode(body["mode"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    return get_modes()


@app.post("/api/custom-mode")
def save_custom_mode(body: dict):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Give the mode a name")
    key = body.get("id") or modes.slug(name)
    if key in modes.MODES:
        key += "-custom"
    custom = dict(load_settings().get("custom_modes") or {})
    custom[key] = {k: body.get(k) for k in ("name", "icon", "blurb", "seeds", "domains", "keywords", "temperature")}
    save_settings({"custom_modes": custom})
    modes.invalidate()
    events.emit("modes", modes=modes.public_list())
    return {"id": key, **get_modes()}


@app.delete("/api/custom-mode/{key}")
def delete_custom_mode(key: str):
    custom = dict(load_settings().get("custom_modes") or {})
    custom.pop(key, None)
    save_settings({"custom_modes": custom})
    modes.invalidate()
    if load_settings()["mode"] == key:
        state["agent"].set_mode("general")
    events.emit("modes", modes=modes.public_list())
    return get_modes()


@app.post("/api/upload")
async def upload(body: dict):
    paths = [p for p in body.get("paths", []) if isinstance(p, str)]
    if not paths:
        raise HTTPException(400, "no files")
    return await asyncio.to_thread(files.learn_files, paths, load_settings()["mode"])


@app.post("/api/learn-topic")
async def learn_topic(body: dict):
    topic = (body.get("topic") or "").strip()
    if not topic:
        raise HTTPException(400, "no topic")
    job = await state["agent"].learn_topic(topic)
    if not job:
        raise HTTPException(404, "No pages found for that topic right now")
    return {"job": job}


@app.post("/api/basics")
async def teach_basics(body: dict):
    """Teach basic conversation: build the course (and a vocabulary if there isn't one) then practice on it."""
    return await basics.teach(state["trainer"], float(body.get("minutes", 15)))


@app.post("/api/reset")
def reset(body: dict):
    if body.get("confirm") != "reset":
        raise HTTPException(400, "confirmation required")
    state["trainer"].reset_brain()
    return state["trainer"].status()


# ---------------------------------------------------------------- saved chats
def _chats() -> list[dict]:
    try:
        return json.loads(CHATS_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


@app.get("/api/chats")
def list_chats():
    return [{"id": c["id"], "title": c.get("title", ""), "updated": c.get("updated", 0), "count": len(c["messages"])}
            for c in sorted(_chats(), key=lambda c: -c.get("updated", 0))]


@app.get("/api/chats/{cid}")
def get_chat(cid: str):
    for c in _chats():
        if c["id"] == cid:
            return c
    raise HTTPException(404, "not found")


@app.post("/api/chats")
def save_chat(body: dict):
    chats = [c for c in _chats() if c["id"] != body["id"]]
    chats.append({"id": body["id"], "title": body.get("title", "")[:80], "updated": body.get("updated", 0),
                  "messages": body.get("messages", [])[-400:]})
    CHATS_PATH.write_text(json.dumps(sorted(chats, key=lambda c: -c["updated"])[:200]))
    return {"ok": True}


@app.delete("/api/chats/{cid}")
def delete_chat(cid: str):
    CHATS_PATH.write_text(json.dumps([c for c in _chats() if c["id"] != cid]))
    return {"ok": True}


@app.get("/api/library/plan")
def library_plan(preset: str = "starter"):
    mode = load_settings()["mode"]
    files = library.plan(preset, mode)
    for f in files:
        f["license"] = library.SOURCES[f["source"]]["license"]
    return {"preset": preset, "mode": mode, "files": files, "bytes": sum(f["size"] for f in files)}


@app.post("/api/library/build")
async def library_build(body: dict):
    t = state["library_thread"]
    if t and t.is_alive():
        return {"ok": True, "running": True}
    preset = body.get("preset", "starter")
    mode = load_settings()["mode"]
    files = library.plan(preset, mode)
    state["library_stop"].clear()

    def run():
        try:
            library.build(preset, state["library_stop"], files, mode)
            state["trainer"].mixture.refresh()
            state["trainer"].start()
        except Exception as e:
            events.emit("library", stage="error", text=f"{type(e).__name__}: {e}")

    state["library_thread"] = threading.Thread(target=run, daemon=True, name="library")
    state["library_thread"].start()
    return {"ok": True, "files": len(files)}


@app.post("/api/library/stop")
def library_stop():
    state["library_stop"].set()
    return {"ok": True}


@app.post("/api/crawl/auto")
def crawl_auto():
    state["crawler"].start_auto()
    return {"jobs": state["crawler"].status()}


@app.post("/api/crawl/site")
def crawl_site(body: dict):
    try:
        job = state["crawler"].crawl_site(body["url"], body.get("max_pages"), body.get("same_path", False))
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"job": job}


@app.post("/api/crawl/stop")
def crawl_stop(body: dict):
    state["crawler"].stop(body.get("job"))
    return {"jobs": state["crawler"].status()}


@app.post("/api/learn")
def learn(body: dict):
    doc = state["crawler"].learn_page(body["url"], body.get("title", ""), body.get("text", ""))
    return {"saved": bool(doc)}


@app.get("/api/memory/search")
def memory_search(q: str, k: int = 8):
    return memory.search(q, k)


@app.post("/api/memory/forget")
def memory_forget(body: dict):
    return {"removed": sum(memory.forget(u) for u in body.get("urls", []))}


# ---------------------------------------------------------------- account
def _acct(fn, *a):
    try:
        return fn(*a)
    except account.AuthError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # network errors
        raise HTTPException(503, f"Couldn't reach the sign-in service ({type(e).__name__}). Check your internet.")


@app.get("/api/account")
def get_account():
    return account.public(account.current())


@app.post("/api/account/signup")
def account_signup(body: dict):
    return _acct(account.sign_up, body.get("email", "").strip(), body.get("password", ""), body.get("name", "").strip())


@app.post("/api/account/signin")
def account_signin(body: dict):
    return _acct(account.sign_in, body.get("email", "").strip(), body.get("password", ""))


@app.post("/api/account/reset")
def account_reset(body: dict):
    _acct(account.reset_password, body.get("email", "").strip())
    return {"ok": True}


@app.post("/api/account/signout")
def account_signout():
    account.sign_out()
    return account.public(None)


@app.post("/api/account/google")
def account_google():
    return {"url": _acct(account.google_start, int(os.environ.get("MNEMO_PORT", "8765")))}


@app.post("/auth/callback")
async def auth_callback(request: Request):
    """The website's app-login page posts the Google sign-in result here (form POST to 127.0.0.1)."""
    from fastapi.responses import HTMLResponse
    form = await request.form()
    try:
        acc = account.google_finish(form.get("state", ""), form.get("idToken", ""), form.get("refreshToken", ""))
        events.emit("account", **acc)
        msg = f"Signed in as {acc['email']}. You can close this tab and go back to Mnemo."
    except account.AuthError as e:
        msg = f"Sign-in failed: {e}"
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>Mnemo</title><body style='font:16px system-ui;"
                        f"background:#0b0a12;color:#eee;display:grid;place-items:center;height:100vh'><p>{msg}</p>")


# ---------------------------------------------------------------- studio (local image / video / 3D)
@app.get("/api/studio")
def studio_status():
    return studio.catalog()


@app.post("/api/studio/install")
def studio_install():
    threading.Thread(target=studio.install_deps, daemon=True).start()
    return {"ok": True}


@app.post("/api/studio/download")
def studio_download(body: dict):
    if body.get("id") not in studio.BY_ID:
        raise HTTPException(400, "unknown model")
    if not studio.deps_ok():
        raise HTTPException(400, "Install the creative tools first.")
    threading.Thread(target=studio.download, args=(body["id"],), daemon=True).start()
    return {"ok": True}


@app.delete("/api/studio/model/{mid}")
def studio_remove(mid: str):
    studio.remove(mid)
    return studio.catalog()


@app.post("/api/studio/generate")
def studio_generate(body: dict):
    try:
        return {"job": studio.submit(state["trainer"], body)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/studio/creations")
def studio_creations():
    return studio.creations()


@app.delete("/api/studio/creations/{job}")
def studio_delete(job: str):
    studio.delete_creation(job)
    return {"ok": True}


@app.get("/files/creations/{name}")
def creation_file(name: str):
    from fastapi.responses import FileResponse
    path = (studio.OUT_DIR / name).resolve()
    if path.parent != studio.OUT_DIR.resolve() or not path.exists():
        raise HTTPException(404, "not found")
    return FileResponse(path)


@app.get("/api/hardware")
def hardware():
    from .trainer import list_devices
    from .config import total_ram_bytes
    return {"devices": list_devices(), "current": state["trainer"].device.type if state["trainer"].device.index is None
            else f"{state['trainer'].device.type}:{state['trainer'].device.index}", "ram_gb": round(total_ram_bytes() / 1e9),
            "cpu_threads": os.cpu_count()}


@app.get("/api/version")
def version():
    """How many commits behind GitHub this copy is (0 if unknown or offline)."""
    import subprocess
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        subprocess.run(["git", "-C", root, "fetch", "--quiet", "origin"], timeout=15, capture_output=True)
        out = subprocess.run(["git", "-C", root, "rev-list", "--count", "HEAD..@{u}"], timeout=5, capture_output=True, text=True)
        return {"behind": int(out.stdout.strip() or 0)}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"behind": 0}


@app.get("/api/plugins")
def list_plugins():
    return {"plugins": plugins.registry.loaded,
            "commands": [{"name": n, "help": h} for n, (h, _, _) in sorted(plugins.registry.commands.items())]}


@app.get("/api/memory/recent")
def memory_recent(limit: int = 40):
    return memory.recent(limit)


@app.get("/api/settings")
def get_settings():
    return load_settings()


@app.post("/api/settings")
def set_settings(body: dict):
    return save_settings(body)


@app.get("/api/history")
def history():
    return state["trainer"].history[-2000:]


# ---------------------------------------------------------------- websockets
@app.websocket("/ws/ui")
async def ws_ui(ws: WebSocket, token: str = ""):
    if TOKEN and token != TOKEN:
        await ws.close(code=4403)
        return
    await ws.accept()
    q = events.subscribe()
    send_lock = asyncio.Lock()

    async def send(msg):
        async with send_lock:
            await ws.send_text(json.dumps(msg))

    async def pump():
        try:
            while True:
                await send(await q.get())
        except (WebSocketDisconnect, RuntimeError):
            pass  # UI closed

    pump_task = asyncio.create_task(pump())
    chat_task = None
    try:
        await send({"type": "trainer", **state["trainer"].status()})
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "chat" and account.configured() and not account.current():
                await send({"type": "tool", "text": "Please sign in to use Mnemo."})
            elif msg.get("type") == "chat":
                if chat_task and not chat_task.done():
                    state["agent"].stop_flag.set()
                    await chat_task
                chat_task = asyncio.create_task(
                    state["agent"].handle(msg["text"], msg.get("history", []), send, msg.get("files")))
            elif msg.get("type") == "stop":
                state["agent"].stop_flag.set()
    except WebSocketDisconnect:
        pass
    finally:
        pump_task.cancel()
        events.unsubscribe(q)


@app.websocket("/ws/browser")
async def ws_browser(ws: WebSocket, token: str = ""):
    if TOKEN and token != TOKEN:
        await ws.close(code=4403)
        return
    await ws.accept()
    try:
        await state["browser"].attach(ws)
    except WebSocketDisconnect:
        pass


def main():
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    os.environ["MNEMO_PORT"] = str(args.port)
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
