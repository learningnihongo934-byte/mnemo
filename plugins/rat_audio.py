"""rat.audio voices: /speak turns text into narration with Kokoro-82M, on this computer, for free.

    /speak Welcome to my channel!                    default voice (Deep Male Narrator)
    /speak rocco-spinelli Howdy, partner.            pick a voice (see /voices)
    /speak [am_puck 60, bm_fable 40, pitch -1] Hi    mix your own voice
    /speak sakura-japanese 今日はいい天気ですね。       Japanese (kanji, kana, numbers)

Audio plays right in chat and is saved to Studio → Creations as a WAV. The first use installs
kokoro-onnx and downloads the model (~340 MB) into ~/.mnemo/models/kokoro; the first Japanese text
also installs misaki[ja] + unidic-lite. Same engine as rat-audio.web.app.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import wave

import httpx

from mnemo import events
from mnemo.config import HOME
from mnemo.studio import OUT_DIR

MODEL_DIR = HOME / "models" / "kokoro"
MODEL_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
FILES = {"kokoro-v1.0.onnx": 325_532_387, "voices-v1.0.bin": 28_214_398}
SR = 24000
MAX_CHARS = 20000

# id: (name, [(kokoro voice, weight)], pace, pitch in semitones). Same presets as rat-audio.web.app.
PRESETS = {
    "deep-male-narrator": ("Deep Male Narrator", [("am_onyx", 65), ("am_michael", 35)], 0.94, -1.0),
    "crisp-female-announcer": ("Crisp Female Announcer", [("af_heart", 60), ("af_bella", 40)], 1.05, 0.0),
    "rocco-spinelli": ("Rocco Spinelli", [("am_puck", 55), ("am_fenrir", 30), ("bm_fable", 15)], 1.08, 1.0),
    "british-storyteller": ("British Storyteller", [("bm_george", 75), ("bm_fable", 25)], 0.97, 0.0),
    "calm-female-guide": ("Calm Female Guide", [("bf_emma", 100)], 0.98, 0.0),
    "sakura-japanese": ("Sakura (日本語)", [("jf_alpha", 100)], 1.0, 0.0),
    "kumo-japanese": ("Kumo (日本語)", [("jm_kumo", 100)], 1.0, 0.0),
    "storybook-japanese": ("Storybook (日本語)", [("jf_gongitsune", 100)], 0.95, 0.0),
}
JAPANESE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff66-\uff9f]")
DEFAULT = "deep-male-narrator"

_engine = None
_ja = None
_lock = threading.Lock()


# ---------------------------------------------------------------- setup (first use only)
def _pip(*packages):
    uv = shutil.which("uv")
    cmd = [uv, "pip", "install", "--python", sys.executable, *packages] if uv else [sys.executable, "-m", "pip", "install", *packages]
    events.log("plugins", f"rat.audio: installing {' '.join(packages)}…")
    if subprocess.run(cmd, capture_output=True, text=True).returncode != 0:
        raise RuntimeError(f"couldn't install {' '.join(packages)}. Try: pip install {' '.join(packages)}")
    importlib.invalidate_caches()


def _ensure_package():
    try:
        return importlib.import_module("kokoro_onnx")
    except ImportError:
        _pip("kokoro-onnx")
    return importlib.import_module("kokoro_onnx")


def ja_phonemes(text: str) -> str:
    """Japanese → Kokoro phonemes with misaki (what Kokoro's Japanese voices were trained on)."""
    global _ja
    if _ja is None:
        try:
            import fugashi, unidic_lite  # noqa: E401
            from misaki import cutlet, ja
        except ImportError:
            _pip("misaki[ja]", "unidic-lite")
            import fugashi, unidic_lite  # noqa: E401
            from misaki import cutlet, ja
        # Pin the bundled unidic-lite; misaki otherwise picks full unidic, whose dictionary isn't downloaded.
        lite = f'-d "{unidic_lite.DICDIR}" -r "{unidic_lite.DICDIR}/mecabrc"'
        cutlet.Tagger = lambda *a, **k: fugashi.Tagger(lite)
        _ja = ja.JAG2P()
    out = _ja(text)
    return (out[0] if isinstance(out, tuple) else out).strip()


def _ensure_models():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name, size in FILES.items():
        path = MODEL_DIR / name
        if path.exists() and path.stat().st_size == size:
            continue
        events.log("plugins", f"rat.audio: downloading {name} ({size / 1e6:.0f} MB)…")
        part = path.with_suffix(path.suffix + ".part")
        with httpx.stream("GET", f"{MODEL_BASE}/{name}", follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            with open(part, "wb") as f:
                for chunk in r.iter_bytes(1 << 20):
                    f.write(chunk)
        part.replace(path)


def engine():
    global _engine
    with _lock:
        if _engine is None:
            kokoro_onnx = _ensure_package()
            _ensure_models()
            _engine = kokoro_onnx.Kokoro(str(MODEL_DIR / "kokoro-v1.0.onnx"), str(MODEL_DIR / "voices-v1.0.bin"))
        return _engine


# ---------------------------------------------------------------- text → segments
_ABBR = {"mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc", "e.g", "i.e", "inc", "ltd", "no", "fig", "approx"}
_PAUSE = {"clause": 0.12, "sentence": 0.32, "paragraph": 0.65, "end": 0.0}


def _sentences(par: str) -> list[str]:
    out, start = [], 0
    for m in re.finditer(r'([.!?…。！？]+["\'”’)\]」』]*)\s+', par):
        cand = par[start:m.end()].strip()
        last = cand.rstrip('.!?…"\'”’)] ').split(" ")[-1].lower()
        if m.group(1).startswith(".") and (last in _ABBR or len(last) == 1):
            continue
        out.append(cand)
        start = m.end()
    if par[start:].strip():
        out.append(par[start:].strip())
    return out


def segments(text: str, target: int = 240, limit: int = 360) -> list[tuple[str, str]]:
    # Japanese has no spaces after 。！？、; add them for the splitter. Its phonemes run ~3x longer, so cut shorter.
    text = re.sub(r"([。！？」』])(?=[^\s」』])", r"\1 ", text)
    text = re.sub(r"([、，])(?=\S)", r"\1 ", text)
    if JAPANESE.search(text):
        target, limit = 70, 110
    text = re.sub(r"[ \t\u00a0]+", " ", text.replace("\r", "")).strip()
    paragraphs = [p.strip().replace("\n", " ") for p in re.split(r"\n\s*\n", text) if p.strip()]
    out: list[tuple[str, str]] = []
    for pi, par in enumerate(paragraphs):
        buf = ""
        for s in _sentences(par):
            while len(s) > limit:  # very long sentence: cut at a comma or space
                cut = max(s.rfind(", ", 0, limit), s.rfind("、 ", 0, limit), s.rfind(" ", 0, limit))
                cut = cut if cut > limit // 3 else limit
                if buf:
                    out.append((buf, "sentence"))
                    buf = ""
                out.append((s[:cut + 1].strip(), "clause"))
                s = s[cut + 1:].strip()
            if buf and len(buf) + len(s) + 1 > target:
                out.append((buf, "sentence"))
                buf = ""
            buf = f"{buf} {s}".strip()
        if buf:
            out.append((buf, "paragraph" if pi < len(paragraphs) - 1 else "end"))
    return out


# ---------------------------------------------------------------- synthesis
def _finish(samples, boundary: str):
    import numpy as np
    loud = np.flatnonzero(np.abs(samples) > 0.004)
    if loud.size:
        pad = int(0.02 * SR)
        samples = samples[max(loud[0] - pad, 0): loud[-1] + pad]
    fade = min(int(0.008 * SR), samples.size // 2)
    if fade:
        ramp = np.linspace(0, 1, fade, dtype=np.float32)
        samples[:fade] *= ramp
        samples[-fade:] *= ramp[::-1]
    out = np.concatenate([samples, np.zeros(int(_PAUSE[boundary] * SR), dtype=np.float32)])
    return (np.tanh(out * 1.1) / np.tanh(1.1) * 32767).astype("<i2")


def render(text: str, blend: list[tuple[str, float]], pace: float, pitch: float) -> bytes:
    import numpy as np
    k = engine()
    known = set(k.get_voices())
    bad = [v for v, _ in blend if v not in known]
    if bad:
        raise ValueError(f"unknown voice {bad[0]!r}. Voices look like am_puck, af_heart, bm_fable (see /voices)")
    total = sum(w for _, w in blend)
    style = sum(k.get_voice_style(v) * (w / total) for v, w in blend).astype(np.float32)
    lead = max(blend, key=lambda b: b[1])[0]
    ratio = 2 ** (max(-8.0, min(8.0, pitch)) / 12)
    speed = max(0.5, min(2.0, pace / ratio))
    # English voices can't read Japanese (and vice versa): swap in Kokoro's voice of the same gender.
    ja_style = style if lead[0] == "j" else k.get_voice_style("jf_alpha" if lead[1] == "f" else "jm_kumo")
    en_style = style if lead[0] != "j" else k.get_voice_style("af_heart" if lead[1] == "f" else "am_michael")
    en_lang = "en-gb" if lead.startswith("b") else "en-us"
    parts = []
    for seg, boundary in segments(text):
        if JAPANESE.search(seg):
            samples, _ = k.create(ja_phonemes(seg), voice=ja_style, speed=speed, is_phonemes=True)
        else:
            samples, _ = k.create(seg, voice=en_style, speed=speed, lang=en_lang)
        if abs(ratio - 1) > 1e-3:  # pitch shift that keeps duration
            samples = np.interp(np.arange(0, len(samples) - 1, ratio), np.arange(len(samples)), samples).astype(np.float32)
        parts.append(_finish(samples, boundary).tobytes())
    return b"".join(parts)


def save(pcm: bytes, text: str, voice_name: str, seconds_taken: float) -> dict:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    job = uuid.uuid4().hex[:8]
    stem = time.strftime("%Y%m%d-%H%M%S") + "-" + job
    with wave.open(str(OUT_DIR / f"{stem}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    meta = {"job": job, "kind": "audio", "model": "kokoro-82m", "model_name": f"rat.audio · {voice_name}",
            "license": "Apache-2.0", "commercial": True, "prompt": text[:500], "negative": "", "seed": 0,
            "voice": voice_name, "settings": {}, "files": [f"{stem}.wav"], "duration": round(len(pcm) / 2 / SR, 2),
            "seconds": round(seconds_taken, 1), "created": time.time()}
    (OUT_DIR / f"{stem}.json").write_text(json.dumps(meta, indent=2))
    events.emit("studio", stage="done", **meta)
    return meta


# ---------------------------------------------------------------- chat commands
def parse(arg: str):
    """Returns (text, blend, pace, pitch, voice_name) from '/speak [voice|[mix]] text'."""
    arg = arg.strip()
    mix = re.match(r"^\[([^\]]+)\]\s*(.*)$", arg, re.S)
    if mix:
        blend, pitch, pace = [], 0.0, 1.0
        for item in mix.group(1).split(","):
            name, _, val = item.strip().partition(" ")
            if name == "pitch":
                pitch = float(val or 0)
            elif name == "pace":
                pace = float(val or 1)
            elif name:
                blend.append((name, float(val or 50)))
        if not blend:
            raise ValueError("a mix needs at least one voice, e.g. [am_puck 60, bm_fable 40]")
        label = " + ".join(f"{v} {w:g}%" for v, w in blend)
        return mix.group(2), blend[:3], pace, pitch, label
    first, _, rest = arg.partition(" ")
    if first.lower() in PRESETS:
        name, blend, pace, pitch = PRESETS[first.lower()]
        return rest, blend, pace, pitch, name
    name, blend, pace, pitch = PRESETS[DEFAULT]
    return arg, blend, pace, pitch, name


def register(mnemo):
    @mnemo.command("/speak", "say text out loud with a rat.audio voice, e.g. /speak rocco-spinelli Howdy!")
    async def speak(arg, ctx):
        if not arg:
            return ("Usage: `/speak your text` · `/speak rocco-spinelli Howdy, partner.` · "
                    "`/speak [am_puck 60, bm_fable 40, pitch -1] Hello`. See `/voices`.")
        try:
            text, blend, pace, pitch, label = parse(arg)
        except ValueError as e:
            return f"⚠️ {e}"
        if not text.strip() or not any(c.isalnum() for c in text):
            return "⚠️ Give me some words to say, e.g. `/speak Hello there!`"
        if len(text) > MAX_CHARS:
            return f"⚠️ That's {len(text):,} characters; the limit is {MAX_CHARS:,}."
        first_run = _engine is None
        started = time.perf_counter()
        try:
            pcm = await asyncio.to_thread(render, text, blend, pace, pitch)
        except ValueError as e:
            return f"⚠️ {e}"
        except MemoryError:
            return "⚠️ Ran out of memory. Try a shorter text."
        meta = await asyncio.to_thread(save, pcm, text, label, time.perf_counter() - started)
        note = " (first run: installed the voice engine)" if first_run else ""
        return (f"🔊 **{label}** · {meta['duration']:.1f}s, made in {meta['seconds']}s{note}\n"
                f"[[audio:{meta['files'][0]}]]\n"
                f"Saved to Studio → Creations: `{OUT_DIR / meta['files'][0]}`")

    @mnemo.command("/voices", "list rat.audio voices for /speak")
    def voices(arg, ctx):
        lines = ["**rat.audio voices** (use as `/speak <voice> text`):"]
        lines += [f"`{vid}` · {name}" for vid, (name, *_rest) in PRESETS.items()]
        lines.append("Mix your own: `/speak [am_puck 60, bm_fable 40, pitch -1] text`. Base voices: af_heart, af_bella, "
                     "af_nicole, af_sarah, am_michael, am_fenrir, am_puck, am_onyx, bf_emma, bf_isabella, bm_george, bm_fable, and more. "
                     "日本語: jf_alpha, jf_gongitsune, jf_nezumi, jf_tebukuro, jm_kumo.")
        return "\n".join(lines)
