"""Studio: run open image, video and 3D generators locally.

Models come from Hugging Face through the `diffusers` library. They are installed
on demand (Studio → Install creative tools), downloaded into ~/.mnemo/models, and
run on the same device as training. Training pauses while a creation renders so
both don't fight over memory.

Every catalog entry lists its license. Some are research/non-commercial only;
the app shows that before download.
"""

from __future__ import annotations

import importlib
import json
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

from . import events
from .config import HOME, load_settings, total_ram_bytes

MODELS_DIR = HOME / "models"
OUT_DIR = HOME / "creations"
DEPS = ["diffusers>=0.32", "transformers", "accelerate", "safetensors", "sentencepiece", "imageio", "imageio-ffmpeg",
        "trimesh", "ftfy"]

# kind, name, repo, pipeline, fp16 variant?, download GB (approx), RAM GB needed, license, commercial use?, defaults
CATALOG = [
    {"id": "bk-sdm-small", "kind": "image", "name": "BK-SDM Small", "repo": "nota-ai/bk-sdm-small",
     "pipeline": "StableDiffusionPipeline", "variant": None, "gb": 2.0, "ram": 6, "license": "CreativeML OpenRAIL-M",
     "commercial": True, "about": "Small, fast Stable Diffusion. Good for CPUs and 8 GB machines.",
     "defaults": {"steps": 25, "guidance": 7.5, "width": 512, "height": 512}},
    {"id": "dreamshaper-8", "kind": "image", "name": "DreamShaper 8", "repo": "Lykon/dreamshaper-8",
     "pipeline": "StableDiffusionPipeline", "variant": "fp16", "gb": 2.2, "ram": 8, "license": "CreativeML OpenRAIL-M",
     "commercial": True, "about": "Popular all-rounder: art, portraits, landscapes. 512–768 px.",
     "defaults": {"steps": 25, "guidance": 7.0, "width": 512, "height": 512}},
    {"id": "sd-1.5", "kind": "image", "name": "Stable Diffusion 1.5", "repo": "stable-diffusion-v1-5/stable-diffusion-v1-5",
     "pipeline": "StableDiffusionPipeline", "variant": "fp16", "gb": 2.2, "ram": 8, "license": "CreativeML OpenRAIL-M",
     "commercial": True, "about": "The classic. Huge ecosystem of styles and know-how.",
     "defaults": {"steps": 30, "guidance": 7.5, "width": 512, "height": 512}},
    {"id": "ssd-1b", "kind": "image", "name": "Segmind SSD-1B", "repo": "segmind/SSD-1B",
     "pipeline": "StableDiffusionXLPipeline", "variant": "fp16", "gb": 4.6, "ram": 12, "license": "Apache-2.0",
     "commercial": True, "about": "SDXL quality at 1024 px, 60% faster. Best quality here for business use.",
     "defaults": {"steps": 25, "guidance": 7.0, "width": 1024, "height": 1024}},
    {"id": "sdxl-turbo", "kind": "image", "name": "SDXL Turbo", "repo": "stabilityai/sdxl-turbo",
     "pipeline": "AutoPipelineForText2Image", "variant": "fp16", "gb": 7.0, "ram": 12,
     "license": "Stability AI Non-Commercial Research", "commercial": False,
     "about": "Images in 1–4 steps, near real-time on a good GPU. Non-commercial only.",
     "defaults": {"steps": 2, "guidance": 0.0, "width": 512, "height": 512}},
    {"id": "text2video-ms", "kind": "video", "name": "ModelScope Text-to-Video", "repo": "ali-vilab/text-to-video-ms-1.7b",
     "pipeline": "DiffusionPipeline", "variant": "fp16", "gb": 3.5, "ram": 10, "license": "CC BY-NC 4.0",
     "commercial": False, "about": "Short 2-second clips. Runs on 8–12 GB GPUs. Non-commercial only.",
     "defaults": {"steps": 25, "guidance": 9.0, "frames": 16, "width": 256, "height": 256}},
    {"id": "wan2.1-1.3b", "kind": "video", "name": "Wan 2.1 (1.3B)", "repo": "Wan-AI/Wan2.1-T2V-1.3B-Diffusers",
     "pipeline": "WanPipeline", "variant": None, "gb": 17.0, "ram": 24, "license": "Apache-2.0", "commercial": True,
     "about": "Modern, high-quality 480p video. Best with an NVIDIA GPU (12 GB+).",
     "defaults": {"steps": 30, "guidance": 5.0, "frames": 33, "width": 832, "height": 480}},
    {"id": "cogvideox-2b", "kind": "video", "name": "CogVideoX 2B", "repo": "zai-org/CogVideoX-2b",
     "pipeline": "CogVideoXPipeline", "variant": None, "gb": 13.0, "ram": 24, "license": "Apache-2.0", "commercial": True,
     "about": "6-second 720×480 clips with good motion. NVIDIA GPU recommended.",
     "defaults": {"steps": 40, "guidance": 6.0, "frames": 25, "width": 720, "height": 480}},
    {"id": "shap-e", "kind": "3d", "name": "Shap-E (text → 3D)", "repo": "openai/shap-e",
     "pipeline": "ShapEPipeline", "variant": None, "gb": 2.6, "ram": 8, "license": "MIT", "commercial": True,
     "about": "Type a description, get a 3D mesh (.glb / .obj / .ply) you can open in Blender or a game engine.",
     "defaults": {"steps": 64, "guidance": 15.0, "frame_size": 256}},
]
BY_ID = {m["id"]: m for m in CATALOG}

_lock = threading.Lock()
_loaded: tuple[str, object] | None = None
state = {"installing": False, "downloads": {}, "job": None, "queue": []}


# --- setup -------------------------------------------------------------------
def deps_ok() -> bool:
    try:
        for mod in ("diffusers", "transformers", "accelerate", "imageio"):
            importlib.import_module(mod)
        return True
    except ImportError:
        return False


def install_deps():
    if state["installing"]:
        return
    state["installing"] = True
    try:
        uv = shutil.which("uv")
        cmd = [uv, "pip", "install", "--python", sys.executable, *DEPS] if uv else [sys.executable, "-m", "pip", "install", *DEPS]
        events.emit("studio", stage="install", text="Installing creative tools (about 1 minute)…")
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in p.stdout:
            events.emit("studio", stage="install", text=line.strip()[:160])
        ok = p.wait() == 0
        importlib.invalidate_caches()
        events.emit("studio", stage="install-done", ok=ok and deps_ok(),
                    text="Creative tools installed." if ok else "Install failed; see the log above.")
    finally:
        state["installing"] = False


def model_dir(mid: str) -> Path:
    return MODELS_DIR / mid


def installed(mid: str) -> bool:
    return (model_dir(mid) / ".ready").exists()


def _dir_size(p: Path) -> int:
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) if p.exists() else 0


def catalog() -> dict:
    ram = total_ram_bytes() / 1e9
    return {"deps": deps_ok(), "installing": state["installing"], "ram_gb": round(ram),
            "models": [{**m, "installed": installed(m["id"]), "fits": m["ram"] <= ram + 1,
                        "downloading": m["id"] in state["downloads"]} for m in CATALOG],
            "job": state["job"], "queue": len(state["queue"])}


def download(mid: str):
    m = BY_ID[mid]
    if mid in state["downloads"] or installed(mid):
        return
    state["downloads"][mid] = True
    stop = threading.Event()

    def progress():
        while not stop.wait(2):
            events.emit("studio", stage="download", id=mid, done=_dir_size(model_dir(mid)), total=m["gb"] * 1e9)

    threading.Thread(target=progress, daemon=True).start()
    try:
        from diffusers import DiffusionPipeline
        kwargs = {"cache_dir": str(model_dir(mid))}
        if m["variant"]:
            kwargs["variant"] = m["variant"]
        DiffusionPipeline.download(m["repo"], **kwargs)
        (model_dir(mid) / ".ready").write_text(json.dumps({"repo": m["repo"], "at": time.time()}))
        events.emit("studio", stage="downloaded", id=mid, text=f"{m['name']} is ready.")
    except Exception as e:
        events.emit("studio", stage="error", id=mid, text=f"Download failed: {type(e).__name__}: {e}"[:300])
    finally:
        stop.set()
        state["downloads"].pop(mid, None)


def remove(mid: str):
    global _loaded
    with _lock:
        if _loaded and _loaded[0] == mid:
            _loaded = None
    shutil.rmtree(model_dir(mid), ignore_errors=True)


# --- generation --------------------------------------------------------------
def _device():
    import torch
    want = load_settings().get("device", "auto")
    if want and want != "auto":
        return torch.device(want)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _pipeline(m: dict):
    global _loaded
    if _loaded and _loaded[0] == m["id"]:
        return _loaded[1]
    _loaded = None
    import diffusers
    import torch
    dev = _device()
    dtype = torch.float32 if dev.type == "cpu" else torch.float16
    cls = getattr(diffusers, m["pipeline"])
    kwargs = {"cache_dir": str(model_dir(m["id"])), "torch_dtype": dtype, "local_files_only": True}
    if m["variant"] and dev.type != "cpu":
        kwargs["variant"] = m["variant"]
    pipe = cls.from_pretrained(m["repo"], **kwargs)
    if dev.type == "cuda" and m["ram"] >= 16:
        pipe.enable_model_cpu_offload()  # big video models: keep only the active part on the GPU
    else:
        pipe = pipe.to(dev)
    if hasattr(pipe, "enable_attention_slicing") and dev.type != "cuda":
        pipe.enable_attention_slicing()
    _loaded = (m["id"], pipe)
    return pipe


def submit(trainer, req: dict) -> str:
    m = BY_ID.get(req.get("id", ""))
    if not m:
        raise ValueError("Unknown model")
    if not installed(m["id"]):
        raise ValueError(f"Download {m['name']} first (Studio).")
    if not (req.get("prompt") or "").strip():
        raise ValueError("Describe what to make.")
    job = {"job": uuid.uuid4().hex[:10], **req, "model": m["id"], "kind": m["kind"], "queued": time.time()}
    state["queue"].append(job)
    events.emit("studio", stage="queued", job=job["job"], position=len(state["queue"]))
    if not state["job"]:
        threading.Thread(target=_worker, args=(trainer,), daemon=True).start()
    return job["job"]


def _worker(trainer):
    global _loaded
    was_training = trainer.running.is_set()
    if was_training:
        trainer.pause()  # free the GPU for rendering; training resumes afterwards
    try:
        while state["queue"]:
            job = state["queue"].pop(0)
            state["job"] = {"job": job["job"], "model": job["model"], "prompt": job["prompt"], "step": 0}
            try:
                with _lock:
                    _run(job)
            except Exception as e:
                events.emit("studio", stage="error", job=job["job"], text=f"{type(e).__name__}: {e}"[:400])
    finally:
        state["job"] = None
        if not load_settings().get("studio_keep_loaded"):
            _loaded = None
            _free()
        if was_training:
            trainer.start()


def _free():
    import gc
    import torch
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    elif torch.backends.mps.is_available():
        torch.mps.empty_cache()


def _run(job: dict):
    import torch
    m = BY_ID[job["model"]]
    d = {**m["defaults"], **{k: v for k, v in job.items() if k in m["defaults"] and v not in (None, "")}}
    events.emit("studio", stage="loading", job=job["job"], text=f"Loading {m['name']}…")
    pipe = _pipeline(m)
    seed = int(job.get("seed") or torch.randint(0, 2**31 - 1, (1,)).item())
    gen = torch.Generator("cpu").manual_seed(seed)
    total = int(d.get("steps", 25))

    def on_step(p, i, t, kw):
        state["job"]["step"] = i + 1
        events.emit("studio", stage="step", job=job["job"], step=i + 1, total=total)
        return kw

    common = {"prompt": job["prompt"], "num_inference_steps": total, "guidance_scale": float(d.get("guidance", 7)),
              "generator": gen}
    if job.get("negative") and m["kind"] != "3d":
        common["negative_prompt"] = job["negative"]
    if m["kind"] != "3d":
        common["callback_on_step_end"] = on_step
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stem = time.strftime("%Y%m%d-%H%M%S") + "-" + job["job"]
    started = time.time()

    if m["kind"] == "image":
        img = pipe(**common, width=int(d["width"]), height=int(d["height"])).images[0]
        files = [f"{stem}.png"]
        img.save(OUT_DIR / files[0])
    elif m["kind"] == "video":
        from diffusers.utils import export_to_video
        frames = pipe(**common, num_frames=int(d["frames"]), width=int(d["width"]), height=int(d["height"])).frames[0]
        files = [f"{stem}.mp4"]
        export_to_video(frames, str(OUT_DIR / files[0]), fps=8 if m["id"] == "text2video-ms" else 16)
    else:
        from diffusers.utils import export_to_obj, export_to_ply
        mesh = pipe(**common, frame_size=int(d.get("frame_size", 256)), output_type="mesh").images[0]
        files = [f"{stem}.ply", f"{stem}.obj"]
        export_to_ply(mesh, str(OUT_DIR / files[0]))
        export_to_obj(mesh, str(OUT_DIR / files[1]))
        try:
            import trimesh
            tm = trimesh.load(str(OUT_DIR / files[0]))
            tm.apply_transform(trimesh.transformations.rotation_matrix(-1.5708, [1, 0, 0]))  # Shap-E is z-up
            tm.export(str(OUT_DIR / f"{stem}.glb"))
            files.insert(0, f"{stem}.glb")
        except Exception:
            pass

    meta = {"job": job["job"], "kind": m["kind"], "model": m["id"], "model_name": m["name"], "license": m["license"],
            "commercial": m["commercial"], "prompt": job["prompt"], "negative": job.get("negative", ""), "seed": seed,
            "settings": d, "files": files, "seconds": round(time.time() - started, 1), "created": time.time()}
    (OUT_DIR / f"{stem}.json").write_text(json.dumps(meta, indent=2))
    events.emit("studio", stage="done", **meta)


def creations(limit: int = 200) -> list[dict]:
    out = []
    for f in sorted(OUT_DIR.glob("*.json"), reverse=True)[:limit]:
        try:
            out.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            pass
    return out


def delete_creation(job: str):
    for f in OUT_DIR.glob(f"*-{job}.*"):
        f.unlink()
