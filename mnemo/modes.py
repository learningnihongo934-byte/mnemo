"""Learning modes. Each mode steers what Mnemo reads and how it answers:

  * where the explorer crawls (seed sites, favoured domains, keywords)
  * which pages it keeps (e.g. Code mode keeps only pages with code)
  * which library datasets it downloads
  * how strongly matching data is weighted in training
  * the reply style (a mode tag in the context + temperature)

Every document is stored with a topic, and in training it is prefixed with
"<|system|>mode: <topic><|end|>". Chatting in a mode puts the same tag in
front of the conversation, so the model learns to answer in that domain.
"""

from __future__ import annotations

import re
import time

from .config import load_settings

MODES: dict[str, dict] = {
    "general": {
        "name": "General", "icon": "🌐", "temperature": 0.8, "min_letters": 0.55,
        "blurb": "A bit of everything: encyclopedias, books, how-tos and discussions.",
        "seeds": [
            "https://en.wikipedia.org/wiki/Main_Page",
            "https://en.wikipedia.org/wiki/Wikipedia:Featured_articles",
            "https://simple.wikipedia.org/wiki/Main_Page",
            "https://en.wikibooks.org/wiki/Main_Page",
            "https://plato.stanford.edu/contents.html",
            "https://www.gutenberg.org/browse/scores/top",
            "https://news.ycombinator.com/",
        ],
        "domains": [], "keywords": [],
        "library": {"starter": {"wikipedia": 2, "smoltalk": 1},
                    "standard": {"wikipedia": 4, "fineweb-edu": 1, "smoltalk": 2},
                    "large": {"wikipedia": 12, "fineweb-edu": 4, "smoltalk": 4}},
    },
    "code": {
        "name": "Code", "icon": "💻", "temperature": 0.4, "min_letters": 0.3, "needs_code": True,
        "blurb": "Programming: docs, tutorials, references and real source code.",
        "seeds": [
            "https://docs.python.org/3/tutorial/index.html",
            "https://developer.mozilla.org/en-US/docs/Web/JavaScript/Guide",
            "https://doc.rust-lang.org/book/",
            "https://go.dev/doc/effective_go",
            "https://en.cppreference.com/w/",
            "https://learn.microsoft.com/en-us/dotnet/csharp/",
            "https://realpython.com/",
            "https://rosettacode.org/wiki/Category:Programming_Tasks",
            "https://www.typescriptlang.org/docs/handbook/intro.html",
        ],
        "domains": ["docs.python.org", "developer.mozilla.org", "rust-lang.org", "go.dev", "cppreference.com",
                    "learn.microsoft.com", "realpython.com", "rosettacode.org", "typescriptlang.org",
                    "geeksforgeeks.org", "stackoverflow.com", "github.com", "readthedocs.io", "kotlinlang.org",
                    "docs.oracle.com", "nodejs.org", "react.dev", "pytorch.org", "numpy.org"],
        "keywords": ["docs", "tutorial", "reference", "api", "guide", "example", "howto", "library", "language",
                     "function", "class", "module", "learn"],
        "library": {"starter": {"wikipedia": 1, "smoltalk": 1, "code": 2, "code-instruct": 1},
                    "standard": {"wikipedia": 2, "smoltalk": 1, "code": 8, "code-instruct": 1},
                    "large": {"wikipedia": 4, "fineweb-edu": 1, "smoltalk": 2, "code": 30, "code-instruct": 1}},
    },
    "literature": {
        "name": "Literature", "icon": "📚", "temperature": 0.95, "min_letters": 0.6,
        "blurb": "Novels, short stories, poetry, plays and writing about them.",
        "seeds": [
            "https://www.gutenberg.org/browse/scores/top",
            "https://standardebooks.org/ebooks",
            "https://en.wikisource.org/wiki/Main_Page",
            "https://poets.org/poems",
            "https://en.wikipedia.org/wiki/Portal:Literature",
            "https://americanliterature.com/short-stories",
        ],
        "domains": ["gutenberg.org", "standardebooks.org", "wikisource.org", "poets.org", "poetryfoundation.org",
                    "americanliterature.com", "bartleby.com", "sparknotes.com"],
        "keywords": ["poem", "poetry", "novel", "story", "stories", "chapter", "fiction", "author", "literature",
                     "ebook", "book", "play"],
        "library": {"starter": {"wikipedia": 1, "smoltalk": 1, "gutenberg": 2},
                    "standard": {"wikipedia": 2, "smoltalk": 1, "gutenberg": 8},
                    "large": {"wikipedia": 4, "smoltalk": 2, "gutenberg": 24}},
    },
    "science": {
        "name": "Science", "icon": "🔬", "temperature": 0.6, "min_letters": 0.5,
        "blurb": "Physics, biology, chemistry, space and research papers.",
        "seeds": [
            "https://en.wikipedia.org/wiki/Portal:Science",
            "https://www.nasa.gov/",
            "https://phys.org/",
            "https://www.sciencedaily.com/",
            "https://plos.org/",
            "https://www.britannica.com/browse/Science",
            "https://www.khanacademy.org/science",
        ],
        "domains": ["nasa.gov", "phys.org", "sciencedaily.com", "plos.org", "britannica.com", "khanacademy.org",
                    "nature.com", "scientificamerican.com", "arxiv.org", "nih.gov", "noaa.gov", "esa.int"],
        "keywords": ["science", "physics", "biology", "chemistry", "space", "research", "study", "cell", "energy",
                     "planet", "species", "quantum", "climate"],
        "library": {"starter": {"wikipedia": 1, "smoltalk": 1, "arxiv": 2, "sciq": 1},
                    "standard": {"wikipedia": 2, "fineweb-edu": 1, "smoltalk": 1, "arxiv": 6, "sciq": 1},
                    "large": {"wikipedia": 4, "fineweb-edu": 2, "smoltalk": 2, "arxiv": 15, "sciq": 1}},
    },
    "math": {
        "name": "Math", "icon": "➗", "temperature": 0.3, "min_letters": 0.35,
        "blurb": "Arithmetic to proofs: explanations, worked problems and theorems.",
        "seeds": [
            "https://en.wikipedia.org/wiki/Portal:Mathematics",
            "https://mathworld.wolfram.com/",
            "https://proofwiki.org/wiki/Main_Page",
            "https://brilliant.org/wiki/",
            "https://www.mathsisfun.com/",
            "https://betterexplained.com/",
            "https://math.stackexchange.com/questions?tab=Votes",
        ],
        "domains": ["mathworld.wolfram.com", "proofwiki.org", "brilliant.org", "mathsisfun.com", "betterexplained.com",
                    "math.stackexchange.com", "khanacademy.org", "mathsisfun.com", "artofproblemsolving.com",
                    "cut-the-knot.org"],
        "keywords": ["math", "theorem", "proof", "equation", "algebra", "geometry", "calculus", "number",
                     "probability", "statistics", "matrix", "function"],
        "library": {"starter": {"wikipedia": 1, "smoltalk": 1, "finemath": 2, "gsm8k": 1},
                    "standard": {"wikipedia": 2, "smoltalk": 1, "finemath": 8, "gsm8k": 1},
                    "large": {"wikipedia": 4, "smoltalk": 2, "finemath": 24, "gsm8k": 1}},
    },
    "news": {
        "name": "News", "icon": "📰", "temperature": 0.7, "min_letters": 0.55,
        "blurb": "Current events and journalism, kept up to date as it explores.",
        "seeds": [
            "https://apnews.com/",
            "https://www.bbc.com/news",
            "https://www.npr.org/sections/news/",
            "https://www.theguardian.com/international",
            "https://www.aljazeera.com/",
            "https://en.wikipedia.org/wiki/Portal:Current_events",
        ],
        "domains": ["apnews.com", "bbc.com", "bbc.co.uk", "npr.org", "theguardian.com", "aljazeera.com",
                    "reuters.com", "pbs.org", "abc.net.au", "cbc.ca", "dw.com"],
        "keywords": ["news", "article", "world", "politics", "business", "technology", "health", "sport", "2025",
                     "2026"],
        "library": {"starter": {"wikipedia": 1, "smoltalk": 1, "cc-news": 2},
                    "standard": {"wikipedia": 2, "smoltalk": 1, "cc-news": 5},
                    "large": {"wikipedia": 6, "fineweb-edu": 1, "smoltalk": 2, "cc-news": 5}},
    },
    "conversation": {
        "name": "Conversation", "icon": "💬", "temperature": 0.85, "min_letters": 0.55,
        "blurb": "Talking naturally: questions, answers and back-and-forth discussion.",
        "seeds": [
            "https://english.stackexchange.com/questions?tab=Votes",
            "https://cooking.stackexchange.com/questions?tab=Votes",
            "https://travel.stackexchange.com/questions?tab=Votes",
            "https://diy.stackexchange.com/questions?tab=Votes",
            "https://workplace.stackexchange.com/questions?tab=Votes",
            "https://simple.wikipedia.org/wiki/Main_Page",
        ],
        "domains": ["stackexchange.com", "simple.wikipedia.org"],
        "keywords": ["questions", "answer", "how", "why", "what"],
        "library": {"starter": {"wikipedia": 1, "smoltalk": 2},
                    "standard": {"wikipedia": 2, "smoltalk": 4},
                    "large": {"wikipedia": 4, "fineweb-edu": 1, "smoltalk": 4}},
    },
}

# Data from the active mode's topic is weighted this many times higher in training.
FOCUS_BOOST = 5.0


_cache: tuple[float, dict] = (0.0, {})


def _custom(spec: dict) -> dict:
    """A user-made mode (Settings → Custom modes). It uses the General library."""
    lines = lambda v: [x.strip() for x in (v.splitlines() if isinstance(v, str) else v or []) if x.strip()]
    seeds = [s if "://" in s else "https://" + s for s in lines(spec.get("seeds"))]
    return {
        "name": spec.get("name") or "Custom", "icon": spec.get("icon") or "✨", "custom": True,
        "blurb": spec.get("blurb") or "Your own mode.",
        "temperature": float(spec.get("temperature") or 0.7), "min_letters": 0.45,
        "seeds": seeds or MODES["general"]["seeds"],
        "domains": [d.replace("https://", "").replace("http://", "").strip("/") for d in lines(spec.get("domains"))],
        "keywords": [k.lower() for k in lines(spec.get("keywords"))],
        "library": MODES["general"]["library"],
    }


def all_modes() -> dict[str, dict]:
    """Built-in modes plus custom ones from settings (cached for a few seconds)."""
    global _cache
    if time.time() - _cache[0] > 3:
        merged = dict(MODES)
        for key, spec in (load_settings().get("custom_modes") or {}).items():
            if key not in MODES:
                merged[key] = _custom(spec)
        _cache = (time.time(), merged)
    return _cache[1]


def invalidate():
    global _cache
    _cache = (0.0, {})


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "custom"


def get(mode: str) -> dict:
    return all_modes().get(mode, MODES["general"])


def public_list() -> list[dict]:
    return [{"id": k, "name": v["name"], "icon": v["icon"], "blurb": v["blurb"], "custom": v.get("custom", False),
             "seeds": v["seeds"], "domains": v["domains"], "keywords": v["keywords"], "temperature": v["temperature"]}
            for k, v in all_modes().items()]


def tag(topic: str) -> str:
    return f"mode: {topic}"


def link_score(mode: str, url: str, site: str) -> float:
    """How on-topic a link looks for this mode (1.0 = neutral)."""
    m = get(mode)
    if not m["domains"] and not m["keywords"]:
        return 1.0
    score = 0.25
    if any(site == d or site.endswith("." + d) for d in m["domains"]):
        score = 3.0
    low = url.lower()
    if any(k in low for k in m["keywords"]):
        score *= 1.6
    return score


def page_ok(mode: str, html: str, text: str, strict: bool = True) -> bool:
    m = get(mode)
    if len(text) < 400:
        return False
    letters = sum(c.isalpha() for c in text) / max(1, len(text))
    if letters < min(m["min_letters"], 0.3 if m.get("needs_code") else 1):
        return False
    if strict and m.get("needs_code"):
        return html.count("<pre") + html.count("<code") >= 2
    return True
