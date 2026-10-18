"""Web crawler: how Mnemo reads the internet.

Two kinds of jobs:
  * "auto:<mode>" – endless exploration from the mode's seed pages, favouring
                    on-topic links (modes.py) and new sites.
  * "site:<host>" – read one specific website (stays on that domain, up to N pages).

Every page's main text is extracted, deduplicated and stored in memory; the
trainer then learns from it. The crawler respects robots.txt, waits between
requests to the same site, skips logins/carts/forms, and never touches
private/local network addresses.
"""

from __future__ import annotations

import ipaddress
import re
import threading
import time
import urllib.robotparser
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
import lxml.html
import trafilatura

from . import events, memory, modes
from .config import load_settings

SKIP_EXT = re.compile(r"\.(png|jpe?g|gif|svg|webp|ico|pdf|zip|gz|tar|mp[34]|avi|mov|wav|ogg|exe|dmg|iso|css|js|json|xml|woff2?)$", re.I)
SKIP_PATH = re.compile(r"(login|signin|sign-in|signup|register|logout|cart|checkout|account|password|"
                       r"action=edit|Special:(?!Random)|oldid=|diff=|printable=|/edit/|share=)", re.I)


def is_public_http(url: str) -> bool:
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        return False
    host = p.hostname
    if host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_global
    except ValueError:
        return True


def normalize(url: str) -> str:
    url, _ = urldefrag(url)
    return url.rstrip("/") if url.count("/") > 3 else url


class Robots:
    def __init__(self, user_agent: str):
        self.ua = user_agent
        self.cache: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.lock = threading.Lock()

    def allowed(self, client: httpx.Client, url: str) -> bool:
        p = urlparse(url)
        root = f"{p.scheme}://{p.netloc}"
        with self.lock:
            rp = self.cache.get(root, "missing")
        if rp == "missing":
            rp = urllib.robotparser.RobotFileParser()
            try:
                r = client.get(root + "/robots.txt", timeout=10)
                if r.status_code in (401, 403):
                    rp = None  # robots says "keep out"
                elif r.status_code >= 400:
                    rp.parse([])
                else:
                    rp.parse(r.text.splitlines())
            except httpx.HTTPError:
                rp.parse([])
            with self.lock:
                self.cache[root] = rp
        return rp is not None and rp.can_fetch("MnemoBot", url)


def extract(html: str, url: str, markdown: bool = False) -> tuple[str, str, list[str]]:
    """Main text, title and links. markdown=True keeps code blocks and formatting (Code mode)."""
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True, favor_precision=not markdown,
                               output_format="markdown" if markdown else "txt", include_formatting=markdown) or ""
    title = ""
    links: list[str] = []
    try:
        doc = lxml.html.fromstring(html)
        t = doc.find(".//title")
        title = (t.text or "").strip() if t is not None else ""
        doc.make_links_absolute(url)
        for el, attr, link, _ in doc.iterlinks():
            if el.tag == "a" and attr == "href":
                links.append(normalize(link))
    except (ValueError, lxml.etree.ParserError):
        pass
    return title[:300], text, links


class Crawler:
    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()
        self.last_hit: dict[str, float] = defaultdict(float)
        self.site_counts: dict[str, int] = defaultdict(int)
        self.thread: threading.Thread | None = None
        self.stop_all = threading.Event()
        self.settings = load_settings()
        self.robots = Robots(self.settings["user_agent"])
        self.client = httpx.Client(headers={"User-Agent": self.settings["user_agent"]},
                                   follow_redirects=True, timeout=15)

    # --- public API ---------------------------------------------------------
    def start_auto(self, mode: str | None = None):
        mode = mode or load_settings()["mode"]
        self.stop("auto")  # one explorer at a time, in the current mode
        self._add_job(f"auto:{mode}", {"kind": "auto", "mode": mode, "pages": 0})

    def crawl_site(self, url: str, max_pages: int | None = None, same_path: bool = False) -> str:
        url = normalize(url if "://" in url else "https://" + url)
        if not is_public_http(url):
            raise ValueError("Only public http(s) websites can be crawled")
        p = urlparse(url)
        job = f"site:{p.netloc}"
        prefix = url.rsplit("/", 1)[0] if same_path else f"{p.scheme}://{p.netloc}"
        memory.clear_job(job)
        memory.enqueue([url], job, depth=0, priority=1.0)
        self._add_job(job, {"kind": "site", "mode": load_settings()["mode"], "netloc": p.netloc, "prefix": prefix, "pages": 0,
                            "max": max_pages or self.settings["crawl_max_pages"], "start": url})
        return job

    def crawl_topic(self, topic: str, urls: list[str], mode: str, max_pages: int) -> str:
        """Read pages found by a /learn search, then follow links that stay on the topic."""
        job = "learn:" + modes.slug(topic)
        memory.clear_job(job)
        memory.enqueue([normalize(u) for u in urls if is_public_http(u)], job, depth=0, priority=1.0)
        words = [w for w in re.findall(r"[a-z0-9+#]+", topic.lower()) if len(w) > 2]
        self._add_job(job, {"kind": "topic", "mode": mode, "topic": topic, "words": words, "pages": 0,
                            "max": max_pages, "start": topic})
        return job

    def stop(self, job: str | None = None):
        with self.lock:
            if job is None:
                self.jobs.clear()
            elif job == "auto":
                for k in [k for k in self.jobs if k.startswith("auto")]:
                    self.jobs.pop(k)
            else:
                self.jobs.pop(job, None)
        events.emit("crawl", stage="jobs", jobs=self.status())

    def status(self) -> list[dict]:
        with self.lock:
            return [{"id": k, **{x: v for x, v in j.items() if x in ("kind", "mode", "pages", "max", "start", "topic")}}
                    for k, j in self.jobs.items()]

    def learn_page(self, url: str, title: str, text: str, source: str = "browser") -> int | None:
        """Store text from a page the user (or Mnemo) viewed in the built-in browser."""
        doc = memory.add_doc(url, title, text, source, topic=load_settings()["mode"])
        if doc:
            events.emit("crawl", stage="learned", url=url, title=title, chars=len(text), source=source)
        return doc

    # --- internals ----------------------------------------------------------
    def _add_job(self, job: str, info: dict):
        self.settings = load_settings()
        with self.lock:
            self.jobs[job] = info
        events.emit("crawl", stage="jobs", jobs=self.status())
        if not self.thread or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True, name="crawler")
            self.thread.start()

    def _run(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            while not self.stop_all.is_set():
                with self.lock:
                    jobs = list(self.jobs.items())
                if not jobs:
                    break
                futures = []
                for job, info in jobs:
                    for row in self._pick(job, info):
                        futures.append(pool.submit(self._visit, job, info, row["url"], row["depth"]))
                if not futures:
                    time.sleep(1)
                for f in futures:
                    f.result()

    def _pick(self, job: str, info: dict) -> list:
        rows = memory.next_urls(job, 30)
        if info["kind"] == "auto" and len(rows) < 3:
            # Seed (or re-seed) from hub pages; they change daily, so revisiting finds new links.
            seeds = [normalize(s) for s in modes.get(info["mode"])["seeds"] + list(self.settings["crawl_seeds"])]
            memory.enqueue(seeds, job, depth=0, priority=0.5)
            memory.requeue(seeds)
            rows = memory.next_urls(job, 30)
        if info["kind"] in ("site", "topic") and not rows and info.get("visited", 0) > 0:
            events.emit("crawl", stage="finished", job=job, pages=info["pages"])
            self.stop(job)
            return []
        # One URL per site per round, and only sites whose politeness delay has passed.
        picked, sites, now = [], set(), time.time()
        delay = float(self.settings["crawl_delay_sec"])
        for r in rows:
            if r["site"] in sites or now - self.last_hit[r["site"]] < delay:
                continue
            sites.add(r["site"])
            self.last_hit[r["site"]] = now
            picked.append(r)
            if len(picked) >= 6:
                break
        return picked

    def _visit(self, job: str, info: dict, url: str, depth: int):
        info["visited"] = info.get("visited", 0) + 1
        try:
            self.__visit(job, info, url, depth)
        except Exception as e:  # never let one bad page kill the crawler
            memory.mark_url(url, 2)
            events.log("crawler", f"skip {url}: {type(e).__name__}")

    def __visit(self, job: str, info: dict, url: str, depth: int):
        blocked = any(b and b in url for b in self.settings.get("crawl_blocklist", []))
        if blocked or not is_public_http(url) or not self.robots.allowed(self.client, url):
            memory.mark_url(url, 2)
            return
        r = self.client.get(url)
        ctype = r.headers.get("content-type", "")
        if r.status_code != 200 or "html" not in ctype or len(r.content) > 4_000_000:
            memory.mark_url(url, 2)
            return
        final = normalize(str(r.url))
        memory.mark_url(url, 1)
        code = modes.get(info["mode"]).get("needs_code")
        title, text, links = extract(r.text, final, markdown=code)
        if modes.page_ok(info["mode"], r.text, text, strict=info["kind"] == "auto") and not memory.known_url(final):
            doc = memory.add_doc(final, title, text, "web" if info["kind"] == "auto" else "site", topic=info["mode"])
            if doc:
                info["pages"] += 1
                self.site_counts[urlparse(final).netloc] += 1
                events.emit("crawl", stage="learned", job=job, url=final, title=title, chars=len(text),
                            pages=info["pages"], topic=info["mode"])
        if info["kind"] in ("site", "topic") and info["pages"] >= info["max"]:
            events.emit("crawl", stage="finished", job=job, pages=info["pages"])
            self.stop(job)
            return
        self._enqueue_links(job, info, final, links, depth)

    def _enqueue_links(self, job, info, base, links, depth):
        out = []
        for link in links:
            if not is_public_http(link) or SKIP_EXT.search(urlparse(link).path) or SKIP_PATH.search(link):
                continue
            if len(link) > 300 or link.count("?") and link.count("&") > 2:
                continue
            out.append(link)
        if info["kind"] == "site":
            out = [l for l in out if l.startswith(info["prefix"])]
            if depth < 6:
                memory.enqueue(out[:200], job, depth + 1, priority=1.0 / (depth + 2))
        elif info["kind"] == "topic":
            if depth >= 2:
                return
            # Follow only links that mention the topic (or point at the mode's favourite sites).
            site = urlparse(base).netloc
            keep = [l for l in set(out) if any(w in l.lower() for w in info["words"])
                    or modes.link_score(info["mode"], l, urlparse(l).netloc) >= 3]
            if depth == 0:  # pages next to a search result are usually on the same subject
                keep += [l for l in out if urlparse(l).netloc == site][:10]
            memory.enqueue(keep[:40], job, depth + 1, priority=0.5 / (depth + 1))
        else:
            if depth >= 6:
                return
            base_site = urlparse(base).netloc
            ranked = []
            for l in set(out):
                site = urlparse(l).netloc
                if self.site_counts[site] > 300:
                    continue
                # Prefer links that lead to new websites: broader knowledge.
                pr = (1.0 if site != base_site else 0.3) / (1 + self.site_counts[site]) / (depth + 1)
                pr *= modes.link_score(info["mode"], l, site)
                ranked.append((pr, l))
            ranked.sort(reverse=True)
            for pr, l in ranked[:25]:
                memory.enqueue([l], job, depth + 1, priority=pr)
