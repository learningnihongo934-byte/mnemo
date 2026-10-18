"""Learning from your files: text, Markdown, code, PDF, Word, EPUB, HTML, CSV, JSON…"""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

import trafilatura

from . import events, memory

CODE_EXT = {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".java", ".c", ".h", ".cpp", ".cc", ".hpp", ".cs", ".go",
            ".rs", ".rb", ".php", ".swift", ".kt", ".kts", ".scala", ".sh", ".bash", ".zsh", ".sql", ".lua", ".r",
            ".m", ".mm", ".css", ".scss", ".vue", ".svelte", ".dart", ".ex", ".exs", ".hs", ".jl", ".pl", ".ps1",
            ".gd", ".luau", ".zig", ".nim", ".ipynb"}
TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".jsonl", ".log", ".xml", ".yaml", ".yml",
            ".ini", ".toml", ".cfg", ".tex", ".srt", ".org", ".adoc"}
DOC_EXT = {".pdf", ".docx", ".epub", ".html", ".htm"}
SUPPORTED = CODE_EXT | TEXT_EXT | DOC_EXT
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next", ".cache", "target",
             ".idea", ".vscode", "Pods", "DerivedData"}
MAX_BYTES = 25 * 1024 * 1024
MAX_FILES = 5000


def _strip_xml(xml: str) -> str:
    xml = re.sub(r"</w:p>|<br\s*/?>|</p>|</h\d>|</li>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'"), ("&apos;", "'")):
        text = text.replace(a, b)
    return re.sub(r"\n{3,}", "\n\n", text)


def read_text(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        return "\n\n".join((p.extract_text() or "") for p in reader.pages)
    if ext == ".docx":
        with zipfile.ZipFile(path) as z:
            return _strip_xml(z.read("word/document.xml").decode("utf-8", "ignore"))
    if ext == ".epub":
        parts = []
        with zipfile.ZipFile(path) as z:
            for name in sorted(n for n in z.namelist() if n.endswith((".xhtml", ".html", ".htm"))):
                parts.append(_strip_xml(z.read(name).decode("utf-8", "ignore")))
        return "\n\n".join(parts)
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    if text.count("�") > len(text) * 0.05:
        return None  # binary
    if ext in (".html", ".htm"):
        return trafilatura.extract(text, include_tables=True) or _strip_xml(text)
    if ext == ".ipynb":
        import json
        cells = json.loads(text).get("cells", [])
        return "\n\n".join("".join(c.get("source", [])) for c in cells)
    return text


def collect(paths: list[str]) -> list[Path]:
    """Expand folders into supported files (skipping dependency/build folders)."""
    out: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
                for f in files:
                    fp = Path(root) / f
                    if fp.suffix.lower() in SUPPORTED:
                        out.append(fp)
                if len(out) >= MAX_FILES:
                    break
        elif p.is_file():
            out.append(p)
    return out[:MAX_FILES]


def learn_files(paths: list[str], mode: str) -> dict:
    files = collect(paths)
    learned, skipped, chars, urls = 0, 0, 0, []
    for i, f in enumerate(files):
        try:
            if f.stat().st_size > MAX_BYTES or f.suffix.lower() not in SUPPORTED:
                skipped += 1
                continue
            text = read_text(f)
        except Exception:
            skipped += 1
            continue
        if not text or len(text.strip()) < 40:
            skipped += 1
            continue
        is_code = f.suffix.lower() in CODE_EXT
        topic = "code" if is_code else mode
        body = f"# {f.name}\n{text}" if is_code else text
        url = f.resolve().as_uri()
        doc = memory.add_doc(url, f.name, body, "upload", topic=topic)
        if doc is None:  # same file again, or too short for memory
            skipped += 1
        else:
            learned += 1
            chars += len(body)
            urls.append(url)
        if i % 25 == 0 or i == len(files) - 1:
            events.emit("upload", done=i + 1, total=len(files), learned=learned, file=f.name)
    events.emit("upload", done=len(files), total=len(files), learned=learned, skipped=skipped, finished=True,
                chars=chars)
    return {"files": len(files), "learned": learned, "skipped": skipped, "chars": chars, "urls": urls}
