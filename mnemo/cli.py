"""Cross-platform helpers behind the `mnemo` command: `python -m mnemo.cli config|doctor ...`."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys

from .config import HOME, load_settings, save_settings, total_ram_bytes


def config(args: list[str]):
    if not args:
        print(json.dumps(load_settings(), indent=2))
        return
    out = {}
    for kv in args:
        k, _, v = kv.partition("=")
        try:
            out[k] = json.loads(v)
        except json.JSONDecodeError:
            out[k] = v
    s = save_settings(out)
    saved = [f"{k}={s[k]}" for k in out if k in s]
    print("Saved:", ", ".join(saved) if saved else "nothing (unknown keys)")


def doctor():
    import torch
    gpu = ("Apple Metal" if torch.backends.mps.is_available() else
           f"CUDA ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else "none (CPU only, slow)")
    node = shutil.which("node")
    nv = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip() if node else "not found"
    free = shutil.disk_usage(HOME.parent).free / 1e9
    print(f"System   {platform.system()} {platform.machine()} · RAM {total_ram_bytes() / 1e9:.0f} GB · free disk {free:.0f} GB")
    print(f"Python   {sys.version.split()[0]} · torch {torch.__version__} · GPU: {gpu}")
    print(f"Node     {nv}")
    print(f"Data     {HOME}")
    if gpu.startswith("none") and shutil.which("nvidia-smi"):
        print("Tip: you have an NVIDIA GPU but PyTorch can't see it. Reinstall torch with CUDA:\n"
              "  uv pip install --python .venv torch --index-url https://download.pytorch.org/whl/cu124")


if __name__ == "__main__":
    cmd, rest = (sys.argv[1] if len(sys.argv) > 1 else "doctor"), sys.argv[2:]
    {"config": lambda: config(rest), "doctor": doctor}.get(cmd, doctor)()
