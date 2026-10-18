"""Topic search for /learn: finds good pages about a topic using official, bot-friendly
search APIs (no scraping of search engines that ask bots to stay away)."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import httpx

from . import modes
from .config import load_settings

# Extra words that point a topic at a mode, beyond each mode's own keywords.
SYNONYMS = {
    "code": "code coding programming program software developer python javascript typescript java rust golang c++ "
            "c# html css sql react node algorithm algorithms data structures api web development linux git".split(),
    "math": "math maths mathematics algebra calculus geometry trigonometry statistics probability arithmetic "
            "number theory linear algebra proofs".split(),
    "science": "science physics chemistry biology astronomy space quantum genetics evolution climate geology "
               "neuroscience medicine ecology".split(),
    "literature": "literature poetry poems novel novels books fiction shakespeare writing stories poets authors "
                  "drama".split(),
    "news": "news current events politics world economy headlines".split(),
    "conversation": "conversation chatting small talk dialogue manners".split(),
}


def guess_mode(topic: str, current: str) -> str:
    words = set(re.findall(r"[a-z0-9+#]+", topic.lower()))
    low = topic.lower()
    best, score = current, 0
    for mode, syn in SYNONYMS.items():
        s = sum(1 for w in syn if (w in words if " " not in w else w in low))
        if s > score:
            best, score = mode, s
    for key, m in modes.all_modes().items():  # custom modes match on their own keywords/name
        if key in SYNONYMS:
            continue
        s = sum(1 for w in m.get("keywords", []) + [m["name"].lower()] if w and w.lower() in low)
        if s > score:
            best, score = key, s
    return best


def _client():
    return httpx.Client(headers={"User-Agent": load_settings()["user_agent"]}, timeout=12, follow_redirects=True)


def _wikipedia(c, q, host="en.wikipedia.org", n=8):
    r = c.get(f"https://{host}/w/rest.php/v1/search/page", params={"q": q, "limit": n})
    return [f"https://{host}/wiki/{p['key']}" for p in r.json().get("pages", [])]


def _stackexchange(c, q, site, n=8):
    r = c.get("https://api.stackexchange.com/2.3/search/advanced",
              params={"q": q, "site": site, "sort": "votes", "pagesize": n, "accepted": "True"})
    return [i["link"] for i in r.json().get("items", [])]


def _hn(c, q, n=8):
    r = c.get("https://hn.algolia.com/api/v1/search", params={"query": q, "tags": "story", "hitsPerPage": n})
    return [h["url"] for h in r.json().get("hits", []) if h.get("url") and not h["url"].endswith(".pdf")]


def _arxiv(c, q, n=6):
    r = c.get("https://export.arxiv.org/api/query", params={"search_query": f"all:{q}", "max_results": n})
    return [u.replace("http://", "https://") for u in re.findall(r"<id>(http://arxiv\.org/abs/[^<]+)</id>", r.text)]


def _gutenberg(c, q, n=5):
    r = c.get("https://gutendex.com/books/", params={"search": q}, timeout=8)
    out = []
    for b in r.json().get("results", [])[:n]:
        f = b.get("formats", {})
        url = next((v for k, v in f.items() if k.startswith("text/html")), None)
        if url:
            out.append(url)
    return out


def _marginalia(c, q, n=10):
    r = c.get(f"https://api.marginalia.nu/public/search/{q}", params={"count": n}, timeout=8)
    return [x["url"] for x in r.json().get("results", [])]


def find_pages(topic: str, mode: str) -> list[str]:
    """Search several sources in parallel; return de-duplicated result URLs, best first."""
    # A short, vague topic ("coding") gets the mode's subject added for general sources.
    hint = {"code": "programming", "math": "mathematics", "science": "science", "literature": "literature"}.get(mode)
    broad = f"{topic} {hint}" if hint and len(topic.split()) <= 2 and hint not in topic.lower() else topic
    jobs = [("wiki", _wikipedia, (broad,)), ("web", _marginalia, (broad,)), ("hn", _hn, (broad,))]
    if mode == "code":
        jobs += [("so", _stackexchange, (topic, "stackoverflow")), ("books", _wikipedia, (topic, "en.wikibooks.org", 5))]
    elif mode == "math":
        jobs += [("mse", _stackexchange, (topic, "math"))]
    elif mode == "science":
        jobs += [("arxiv", _arxiv, (topic,))]
    elif mode == "literature":
        jobs += [("gutenberg", _gutenberg, (topic,)), ("source", _wikipedia, (topic, "en.wikisource.org", 5))]
    elif mode == "conversation":
        jobs += [("ell", _stackexchange, (topic, "english"))]
    else:
        jobs += [("books", _wikipedia, (topic, "en.wikibooks.org", 4))]

    def run(job):
        _, fn, args = job
        try:
            with _client() as c:
                return fn(c, *args)
        except (httpx.HTTPError, ValueError, KeyError):
            return []

    with ThreadPoolExecutor(len(jobs)) as ex:
        results = list(ex.map(run, jobs))
    # Interleave sources so one doesn't dominate.
    out, seen = [], set()
    for i in range(max((len(r) for r in results), default=0)):
        for r in results:
            if i < len(r) and r[i] not in seen:
                seen.add(r[i])
                out.append(r[i])
    return out
