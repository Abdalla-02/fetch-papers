#!/usr/bin/env python3
"""
fetch_pdfs.py - bulk-download PDFs of retracted papers by DOI, legally and resumably.

Sources (tried in this order, each one optional):
  1. unpaywall  - free open-access PDF links            (needs: your e-mail)
  2. openalex   - second open-access index              (needs: your e-mail)
  3. elsevier   - Elsevier TDM API, 10.1016/* only      (needs: ELSEVIER_API_KEY [+ ELSEVIER_INSTTOKEN])
  4. wiley      - Wiley TDM API, 10.1002/* and 10.1111/* (needs: WILEY_TDM_TOKEN)
  5. crossref   - publisher full-text links registered in Crossref for text mining
                  (works for subscribed content only when run from the university network/VPN)

State lives in a SQLite file, so you can stop (Ctrl+C) and restart at any time.

Usage:
  python fetch_pdfs.py import  retraction_watch.csv
  python fetch_pdfs.py run     --email you@uni.de --out /data/retracted_pdfs
  python fetch_pdfs.py report  [--export status.csv]
  python fetch_pdfs.py index   --out /data/retracted_pdfs        (writes index.csv)
  python fetch_pdfs.py rename  --out /data/retracted_pdfs [--dry-run]

PDFs are saved as '<ID block>/<RW ID> - <title>.pdf' (title cut to 150 characters),
e.g. '001001-002000/001454 - Circulatory Responses ....pdf'.

Requires: Python 3.9+, `pip install httpx`
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import random
import re
import sqlite3
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, urlparse

import httpx

# ----------------------------------------------------------------------------- config
# API base URLs (overridable via env vars, mainly for testing)
UNPAYWALL = os.environ.get("UNPAYWALL_BASE", "https://api.unpaywall.org/v2")
OPENALEX = os.environ.get("OPENALEX_BASE", "https://api.openalex.org")
ELSEVIER = os.environ.get("ELSEVIER_BASE", "https://api.elsevier.com")
WILEY = os.environ.get("WILEY_BASE", "https://api.wiley.com")
CROSSREF = os.environ.get("CROSSREF_BASE", "https://api.crossref.org")

ALL_SOURCES = ["unpaywall", "openalex", "elsevier", "wiley", "crossref"]

# Requests per second allowed per host. Anything not listed uses DEFAULT_RPS.
# Keep publisher sites slow: this is what keeps you from being blocked.
HOST_RPS = {
    "api.unpaywall.org": 8,   # no per-second limit published; 100,000 calls/day
    "api.openalex.org": 8,    # keyless budget; DOI lookups cost $0 (checked 2026-10)
    "api.crossref.org": 3,    # polite pool: 10 req/s but max 3 concurrent requests
    "api.elsevier.com": 2,    # Article Retrieval: 10 req/s, 50,000/week
    "api.wiley.com": 0.1,     # Wiley TDM: max 3/s AND max 60 per 10 min -> 1 every 10 s
}
DEFAULT_RPS = 0.5  # = one request every 2 s per publisher/repository host

# A host that refuses this many downloads in a row (403/429, bot-challenge or HTML
# page instead of a PDF) without a single success is skipped for the rest of the run.
# Its papers end up as 'failed' and can be retried later with --retry-failed.
BLOCK_AFTER = 8

MAX_PDF_BYTES = 300 * 1024 * 1024
TIMEOUT = httpx.Timeout(60.0, connect=20.0)
MAX_TITLE_CHARS = 150     # title part of a file name; keeps full Windows paths under 260 characters
MAX_FILENAME_BYTES = 200  # extra cap for non-Latin titles (ext4 allows 255 bytes per name)
FOLDER_SIZE = 1000        # PDFs are grouped in subfolders of 1,000 Retraction Watch IDs each

# ----------------------------------------------------------------------------- helpers
DOI_RE = re.compile(r"10\.\d{4,9}/\S+", re.I)


def clean_doi(raw: str | None) -> str | None:
    if not raw:
        return None
    m = DOI_RE.search(raw.strip())
    if not m:
        return None
    return m.group(0).rstrip(".,;").lower()


def safe_filename(title: str) -> str:
    """Turn a paper title into a file-system-safe name (without extension)."""
    t = unicodedata.normalize("NFC", title or "untitled")
    t = re.sub(r"<[^>]+>", "", t)                     # stray HTML tags
    t = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', " ", t)   # forbidden on Windows/Linux
    t = re.sub(r"\s+", " ", t).strip(" .")
    if not t:
        t = "untitled"
    if len(t) > MAX_TITLE_CHARS:
        cut = t[:MAX_TITLE_CHARS]
        space = cut.rfind(" ")
        if space >= MAX_TITLE_CHARS - 30:  # end at a word boundary if one is close
            cut = cut[:space]
        t = cut.rstrip(" .,;-")
    b = t.encode("utf-8")
    if len(b) > MAX_FILENAME_BYTES:
        t = b[:MAX_FILENAME_BYTES].decode("utf-8", "ignore").rstrip(" .")
    return t


def first_id(record_ids: str) -> str:
    """Smallest Retraction Watch ID of a paper, zero-padded to 6 digits so files sort by ID."""
    ids = [i.strip() for i in (record_ids or "").split(";") if i.strip()]
    nums = sorted(int(i) for i in ids if i.isdigit())
    return f"{nums[0]:06d}" if nums else (ids[0] if ids else "000000")


def subfolder(rw_id: str) -> str:
    """Folder for a paper: blocks of FOLDER_SIZE IDs, e.g. ID 001454 -> '001001-002000'."""
    if not rw_id.isdigit():
        return "other"
    lo = (int(rw_id) - 1) // FOLDER_SIZE * FOLDER_SIZE + 1
    return f"{lo:06d}-{lo + FOLDER_SIZE - 1:06d}"


def make_filename(record_ids: str, title: str) -> str:
    """Path of the PDF relative to the output folder, without extension:
    '<ID block>/<RW ID> - <title>', e.g. '001001-002000/001454 - Circulatory Responses ...'."""
    rid = first_id(record_ids)
    return f"{subfolder(rid)}/{rid} - {safe_filename(title)}"


def looks_like_pdf(first_bytes: bytes) -> bool:
    return b"%PDF" in first_bytes[:1024]


# ----------------------------------------------------------------------------- database
SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    doi        TEXT PRIMARY KEY,
    record_ids TEXT,              -- Retraction Watch IDs sharing this DOI
    title      TEXT,
    filename   TEXT UNIQUE,
    status     TEXT DEFAULT 'pending',   -- pending | done | not_found | failed
    source     TEXT,
    pdf_url    TEXT,
    error      TEXT,
    attempts   INTEGER DEFAULT 0,
    updated    REAL
);
CREATE INDEX IF NOT EXISTS idx_status ON papers(status);
CREATE TABLE IF NOT EXISTS no_doi (record_id TEXT PRIMARY KEY, title TEXT, raw_doi TEXT);
"""


def open_db(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    con.executescript(SCHEMA)
    return con


def cmd_import(args):
    con = open_db(args.db)
    with open(args.csv, newline="", encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.DictReader(f))
    cols = rows[0].keys() if rows else []
    doi_col = args.doi_col or next(c for c in cols if "doi" in c.lower())
    title_col = args.title_col or next(c for c in cols if c.lower() == "title")
    id_col = args.id_col or next((c for c in cols if c.lower() in ("id", "record id", "record_id")), None)

    by_doi: dict[str, dict] = {}
    no_doi = []
    for i, r in enumerate(rows):
        rid = (r.get(id_col) if id_col else None) or str(i + 1)
        doi = clean_doi(r.get(doi_col))
        if not doi:
            no_doi.append((rid, r.get(title_col, ""), r.get(doi_col, "")))
            continue
        e = by_doi.setdefault(doi, {"ids": [], "title": r.get(title_col, "")})
        e["ids"].append(rid)

    # file names start with the paper's (smallest) Retraction Watch ID, so they are unique
    used = {fn.lower() for (fn,) in con.execute("SELECT filename FROM papers")}
    known = {d for (d,) in con.execute("SELECT doi FROM papers")}
    new = 0
    for doi, e in by_doi.items():
        if doi in known:
            continue
        base = make_filename(";".join(e["ids"]), e["title"])
        fn, n = base, 2
        while fn.lower() in used:  # only possible with a malformed ID column
            fn, n = f"{base} ({n})", n + 1
        used.add(fn.lower())
        con.execute(
            "INSERT INTO papers(doi, record_ids, title, filename, updated) VALUES (?,?,?,?,?)",
            (doi, ";".join(e["ids"]), e["title"], fn, time.time()),
        )
        new += 1
    con.executemany("INSERT OR IGNORE INTO no_doi VALUES (?,?,?)", no_doi)
    con.commit()
    print(f"rows in CSV:        {len(rows)}")
    print(f"unique DOIs:        {len(by_doi)}  (new in DB: {new})")
    print(f"rows without DOI:   {len(no_doi)}  (stored in table 'no_doi')")


# ----------------------------------------------------------------------------- rate limiting
class HostLimiter:
    """Simple per-host spacing: at most `rps` request starts per second per host."""

    def __init__(self):
        self.locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.next_ok: dict[str, float] = defaultdict(float)
        self.penalty: dict[str, float] = defaultdict(float)
        self.refusals: dict[str, int] = defaultdict(int)   # consecutive refusals
        self.blocked: dict[str, str] = {}                   # host -> last refusal reason
        self.warned: set[str] = set()

    def is_blocked(self, url: str) -> bool:
        return (urlparse(url).hostname or "") in self.blocked

    def refused(self, url: str, reason: str):
        """Download refused (403/429/bot check/HTML instead of PDF). Block host after BLOCK_AFTER in a row."""
        host = urlparse(url).hostname or ""
        self.refusals[host] += 1
        if self.refusals[host] >= BLOCK_AFTER and host not in self.blocked:
            self.blocked[host] = reason
            print(f"! host {host} refused {BLOCK_AFTER} downloads in a row ({reason}) "
                  f"- skipping it for the rest of this run", file=sys.stderr, flush=True)

    async def wait(self, url: str):
        host = urlparse(url).hostname or ""
        interval = 1.0 / HOST_RPS.get(host, DEFAULT_RPS) + self.penalty[host]
        async with self.locks[host]:
            now = time.monotonic()
            delay = self.next_ok[host] - now
            if delay > 0:
                await asyncio.sleep(delay)
            self.next_ok[host] = max(now, self.next_ok[host]) + interval

    def slow_down(self, url: str, seconds: float):
        """Host pushed back (429/403/5xx): pause it and widen its spacing."""
        host = urlparse(url).hostname or ""
        self.penalty[host] = min(self.penalty[host] * 2 + 0.5, 10)
        self.next_ok[host] = max(self.next_ok[host], time.monotonic() + seconds)
        if self.penalty[host] >= 10 and host not in self.warned:
            self.warned.add(host)
            print(f"! host {host} keeps pushing back (429/403/5xx) - slowed to 1 request "
                  f"every {1.0 / HOST_RPS.get(host, DEFAULT_RPS) + 10:.0f} s", file=sys.stderr, flush=True)

    def ok(self, url: str):
        """Successful response: let the extra spacing decay again."""
        host = urlparse(url).hostname or ""
        if self.penalty[host]:
            self.penalty[host] = self.penalty[host] * 0.7 if self.penalty[host] > 0.05 else 0.0


# ----------------------------------------------------------------------------- downloader
class HostBlocked(Exception):
    """The host was skipped because it kept refusing downloads (see BLOCK_AFTER)."""


class Fetcher:
    def __init__(self, args, con):
        self.a = args
        self.con = con
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.limiter = HostLimiter()
        self.sources = [s.strip() for s in args.sources.split(",") if s.strip()]
        self.els_key = os.environ.get("ELSEVIER_API_KEY")
        self.els_inst = os.environ.get("ELSEVIER_INSTTOKEN")
        self.wiley_tok = os.environ.get("WILEY_TDM_TOKEN")
        self.ua = f"RetractedPapersResearch/1.0 (mailto:{args.email})"
        self.stats = defaultdict(int)
        self.t0 = time.time()

    # -- HTTP with retries -------------------------------------------------
    async def send(self, client, url, headers, stream, max_hops=10):
        """GET that follows redirects itself, so every hop goes through the per-host
        rate limiter (a doi.org/repository link often redirects to a publisher host).
        Extra headers (API keys) are only sent to the host they were meant for."""
        first_host = urlparse(url).hostname
        for _ in range(max_hops):
            if self.limiter.is_blocked(url):
                raise HostBlocked(urlparse(url).hostname)
            await self.limiter.wait(url)
            h = headers if urlparse(url).hostname == first_host else \
                {k: v for k, v in (headers or {}).items() if k.lower() == "accept"}
            resp = await client.send(client.build_request("GET", url, headers=h), stream=stream)
            if resp.is_redirect and resp.headers.get("location"):
                url = str(resp.url.join(resp.headers["location"]))
                await resp.aclose()
                continue
            return resp
        raise httpx.TooManyRedirects(f"more than {max_hops} redirects", request=resp.request)

    async def request(self, client, url, *, headers=None, stream=False, tries=3):
        for attempt in range(tries):
            try:
                resp = await self.send(client, url, headers, stream)
            except (httpx.TransportError, httpx.TimeoutException) as e:
                if attempt == tries - 1:
                    raise
                await asyncio.sleep(2 ** attempt + random.random())
                continue
            final = str(resp.url)  # penalise/reward the host that actually answered
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < tries - 1:
                ra = resp.headers.get("Retry-After", "")
                wait = float(ra) if ra.isdigit() else 5 * (attempt + 1)
                self.limiter.slow_down(final, wait)
                await resp.aclose()
                continue  # the limiter now holds this host back for `wait` seconds
            if resp.status_code < 400:
                self.limiter.ok(final)
            return resp
        return resp

    async def get_json(self, client, url, headers=None):
        r = await self.request(client, url, headers=headers)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    # -- candidate URL discovery -------------------------------------------
    async def candidates(self, client, doi, lookup_errors: list):
        """Yield (source, url, extra_headers) in priority order.
        Failed index lookups are appended to `lookup_errors`."""
        q = quote(doi, safe="")
        for src in self.sources:
            try:
                if src == "unpaywall":
                    j = await self.get_json(client, f"{UNPAYWALL}/{q}?email={quote(self.a.email)}")
                    if j:
                        locs = [j.get("best_oa_location")] + (j.get("oa_locations") or [])
                        seen = set()
                        for loc in filter(None, locs):
                            for key in ("url_for_pdf",):
                                u = loc.get(key)
                                if u and u not in seen:
                                    seen.add(u)
                                    yield "unpaywall", u, None
                elif src == "openalex":
                    j = await self.get_json(client, f"{OPENALEX}/works/doi:{doi}?mailto={quote(self.a.email)}")
                    if j:
                        locs = [j.get("best_oa_location")] + (j.get("locations") or [])
                        seen = set()
                        for loc in filter(None, locs):
                            u = loc.get("pdf_url")
                            if u and u not in seen:
                                seen.add(u)
                                yield "openalex", u, None
                elif src == "elsevier" and self.els_key and doi.startswith("10.1016/"):
                    h = {"X-ELS-APIKey": self.els_key, "Accept": "application/pdf"}
                    if self.els_inst:
                        h["X-ELS-Insttoken"] = self.els_inst
                    yield "elsevier", f"{ELSEVIER}/content/article/doi/{doi}?httpAccept=application/pdf", h
                elif src == "wiley" and self.wiley_tok and doi.startswith(("10.1002/", "10.1111/")):
                    yield "wiley", f"{WILEY}/onlinelibrary/tdm/v1/articles/{q}", {"Wiley-TDM-Client-Token": self.wiley_tok}
                elif src == "crossref":
                    j = await self.get_json(client, f"{CROSSREF}/works/{q}?mailto={quote(self.a.email)}")
                    for link in ((j or {}).get("message", {}).get("link") or []):
                        if "pdf" in (link.get("content-type") or "") and link.get("URL"):
                            yield "crossref", link["URL"], None
            except Exception as e:  # a broken index lookup must not kill the paper
                self.stats[f"lookup_error_{src}"] += 1
                lookup_errors.append(f"{src}: lookup failed: {type(e).__name__}: {e}"[:300])
                if self.a.verbose:
                    print(f"  ! {src} lookup failed for {doi}: {e}", file=sys.stderr)

    # -- download one PDF ---------------------------------------------------
    async def download(self, client, url, headers, dest: Path):
        tmp = dest.with_suffix(".pdf.part")
        h = {"Accept": "application/pdf,*/*;q=0.8"}
        h.update(headers or {})
        try:
            r = await self.request(client, url, headers=h, stream=True)
        except HostBlocked as e:
            return f"skipped: {e} blocked for this run ({self.limiter.blocked.get(str(e))})"
        final = str(r.url)
        via = "" if urlparse(final).hostname == urlparse(url).hostname else f" via {urlparse(final).hostname}"
        try:
            if r.status_code != 200:
                if r.status_code in (403, 429):
                    self.limiter.slow_down(final, 10)
                if r.headers.get("cf-mitigated") == "challenge":
                    err = f"HTTP {r.status_code} (Cloudflare bot challenge)"
                else:
                    err = f"HTTP {r.status_code}"
                if r.status_code in (401, 403, 429):
                    self.limiter.refused(final, err)
                return err + via
            size, first = 0, b""
            dest.parent.mkdir(parents=True, exist_ok=True)  # ID-block subfolder
            with open(tmp, "wb") as f:
                async for chunk in r.aiter_bytes(65536):
                    if not first:
                        first = chunk
                        if not looks_like_pdf(first):
                            self.limiter.refused(final, "HTML page instead of PDF")
                            return "not a PDF (got HTML/login page?)" + via
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        return "too large"
                    f.write(chunk)
            if size < 1000:
                return "file too small"
            os.replace(tmp, dest)
            self.limiter.refusals[urlparse(final).hostname or ""] = 0
            return None
        finally:
            await r.aclose()
            if tmp.exists():
                tmp.unlink()

    async def process(self, client, doi, filename):
        dest = self.out / f"{filename}.pdf"
        if dest.exists() and dest.stat().st_size > 1000:
            self.save(doi, "done", "already_on_disk", None, None)
            return
        errors, tried, lookup_errors = [], set(), []
        async for src, url, headers in self.candidates(client, doi, lookup_errors):
            if url in tried:
                continue
            tried.add(url)
            try:
                err = await self.download(client, url, headers, dest)
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
            if err is None:
                self.save(doi, "done", src, url, None)
                self.stats[f"done_{src}"] += 1
                return
            errors.append(f"{src}: {err} <{url[:120]}>")
        errors += lookup_errors
        if not tried and not lookup_errors:
            self.save(doi, "not_found", None, None, "no PDF link found in any source")
            self.stats["not_found"] += 1
        else:
            # a failed index lookup means "unknown", not "not found" -> keep it retryable
            self.save(doi, "failed", None, None, " | ".join(errors)[:2000])
            self.stats["failed"] += 1

    def save(self, doi, status, source, url, error):
        self.con.execute(
            "UPDATE papers SET status=?, source=?, pdf_url=?, error=?, attempts=attempts+1, updated=? WHERE doi=?",
            (status, source, url, error, time.time(), doi),
        )
        self.con.commit()

    def progress(self, n_done, n_total):
        el = time.time() - self.t0
        rate = n_done / el if el else 0
        eta = (n_total - n_done) / rate / 3600 if rate else 0
        ok = sum(v for k, v in self.stats.items() if k.startswith("done_"))
        print(f"[{n_done}/{n_total}] ok={ok} not_found={self.stats['not_found']} "
              f"failed={self.stats['failed']}  {rate*60:.0f}/min  ETA {eta:.1f} h", flush=True)

    async def run(self):
        statuses = ["pending"] + (["failed"] if self.a.retry_failed else []) \
                   + (["not_found"] if self.a.retry_not_found else [])
        sql = f"SELECT doi, filename FROM papers WHERE status IN ({','.join('?'*len(statuses))})"
        params = list(statuses)
        if self.a.prefix:
            sql += " AND doi LIKE ?"
            params.append(self.a.prefix.lower() + "%")
        todo = self.con.execute(sql + " ORDER BY doi", params).fetchall()
        if self.a.limit:
            random.seed(0)
            random.shuffle(todo)
            todo = todo[: self.a.limit]
        # interleave publishers so per-host rate limits don't serialize the queue
        groups = defaultdict(list)
        for d, fn in todo:
            groups[d.split("/")[0]].append((d, fn))
        queue: asyncio.Queue = asyncio.Queue()
        while any(groups.values()):
            for k in list(groups):
                if groups[k]:
                    queue.put_nowait(groups[k].pop())
        total = queue.qsize()
        print(f"{total} DOIs to process with sources: {', '.join(self.sources)}")
        done = 0

        limits = httpx.Limits(max_connections=self.a.concurrency * 2, max_keepalive_connections=self.a.concurrency)
        async with httpx.AsyncClient(timeout=TIMEOUT, limits=limits,
                                     headers={"User-Agent": self.ua}) as client:
            async def worker():
                nonlocal done
                while True:
                    try:
                        doi, fn = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    await self.process(client, doi, fn)
                    done += 1
                    if done % self.a.progress_every == 0 or done == total:
                        self.progress(done, total)

            await asyncio.gather(*(worker() for _ in range(self.a.concurrency)))
        print("finished:", dict(self.stats))
        for host, reason in self.limiter.blocked.items():
            print(f"blocked host (skipped after {BLOCK_AFTER} refusals in a row): {host} - {reason}")


def cmd_run(args):
    if "@" not in args.email:
        sys.exit("--email is required (Unpaywall/OpenAlex/Crossref ask for it)")
    con = open_db(args.db)
    if not con.execute("SELECT COUNT(*) FROM papers").fetchone()[0]:
        # a wrong --db path would otherwise create an empty DB and overwrite index.csv with nothing
        sys.exit(f"{os.path.abspath(args.db)} contains no papers - run 'import' first or check --db")
    try:
        asyncio.run(Fetcher(args, con).run())
    except KeyboardInterrupt:
        print("\nstopped - progress is saved, just run the same command again to resume")
    write_index(con, Path(args.out))


# ----------------------------------------------------------------------------- index / rename
INDEX_COLUMNS = ["rw_id", "all_rw_ids", "doi", "doi_prefix", "title", "folder", "filename",
                 "status", "source", "pdf_url", "error"]


def write_index(con, out: Path):
    """Write <out>/index.csv: one row per paper (incl. rows without DOI), sorted by RW ID.
    'folder' and 'filename' are only filled for downloaded papers.
    UTF-8 with BOM so Excel shows non-ASCII titles correctly."""
    rows = []
    for doi, ids, title, fn, status, source, url, err in con.execute(
            "SELECT doi, record_ids, title, filename, status, source, pdf_url, error FROM papers"):
        folder, _, name = fn.rpartition("/")
        done = status == "done"
        rows.append([first_id(ids), ids, doi, doi.split("/")[0], title, folder if done else "",
                     f"{name}.pdf" if done else "", status, source, url, (err or "")[:300]])
    for rid, title, raw in con.execute("SELECT record_id, title, raw_doi FROM no_doi"):
        rows.append([first_id(rid), rid, raw, "", title, "", "", "no_doi", "", "", "no usable DOI in the CSV"])
    rows.sort(key=lambda r: r[0])
    out.mkdir(parents=True, exist_ok=True)
    tmp = out / "index.csv.part"
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(INDEX_COLUMNS)
        w.writerows(rows)
    os.replace(tmp, out / "index.csv")
    print(f"index written: {out / 'index.csv'} ({len(rows)} rows)")


def cmd_index(args):
    con = open_db(args.db)
    if not con.execute("SELECT COUNT(*) FROM papers").fetchone()[0]:
        sys.exit(f"{os.path.abspath(args.db)} contains no papers - check --db (index.csv not touched)")
    write_index(con, Path(args.out))


# ----------------------------------------------------------------------------- summary for the library
# How the still-missing papers of the big publishers can be obtained legally.
ROUTES = {
    "10.1155": "Wiley TDM API (Hindawi is part of Wiley) - open access, download site blocks bots",
    "10.1002": "Wiley TDM API (token)", "10.1111": "Wiley TDM API (token)",
    "10.1016": "Elsevier Article Retrieval API (API key + institutional token)",
    "10.1109": "IEEE - no public TDM PDF API; library arrangement",
    "10.1007": "Springer Nature TDM - library", "10.1186": "Springer Nature TDM - library",
    "10.1038": "Springer Nature TDM - library",
}
REASONS = ["closed access (no open-access copy)", "blocked by bot protection (Cloudflare)",
           "refused by site (HTTP 401/403/429)", "HTML page instead of PDF",
           "network error / timeout (worth retrying)", "TLS certificate error on site",
           "broken link (HTTP 404/410)", "index lookup error (worth retrying)", "other"]


def classify(status: str, error: str | None) -> str:
    """One main reason per missing paper (most informative first)."""
    if status == "not_found":
        return REASONS[0]
    e = error or ""
    if "Cloudflare" in e:
        return REASONS[1]
    if re.search(r"HTTP (401|403|429)", e):
        return REASONS[2]
    if "HTML page instead of PDF" in e or "not a PDF" in e:
        return REASONS[3]
    if re.search(r"Timeout|ReadError|getaddrinfo|All connection attempts|RemoteProtocolError|ConnectError: +<", e):
        return REASONS[4]
    if "CERTIFICATE" in e or "SSL" in e or "TLS" in e:
        return REASONS[5]
    if re.search(r"HTTP (404|410)", e):
        return REASONS[6]
    if "lookup failed" in e:
        return REASONS[7]
    return REASONS[8]


def publisher_names(con, prefixes, email):
    """Publisher name per DOI prefix from Crossref (/prefixes/<p>), cached in the DB."""
    con.execute("CREATE TABLE IF NOT EXISTS publishers (prefix TEXT PRIMARY KEY, name TEXT)")
    names = dict(con.execute("SELECT prefix, name FROM publishers"))
    todo = [p for p in prefixes if p not in names]
    if todo:
        print(f"looking up {len(todo)} publisher names at Crossref ...")
    with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": f"RetractedPapersResearch/1.0 (mailto:{email})"}) as c:
        for i, p in enumerate(todo):
            time.sleep(1.0 / HOST_RPS["api.crossref.org"])
            try:
                r = c.get(f"{CROSSREF}/prefixes/{p}", params={"mailto": email})
                name = r.json()["message"]["name"] if r.status_code == 200 else ""
            except Exception:
                continue  # not cached -> tried again next time
            names[p] = name
            con.execute("INSERT OR REPLACE INTO publishers VALUES (?,?)", (p, name))
            if i % 50 == 49:
                con.commit()
    con.commit()
    return names


def cmd_summary(args):
    con = open_db(args.db)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rows = con.execute("SELECT doi, record_ids, title, status, error FROM papers").fetchall()
    per = defaultdict(lambda: defaultdict(int))
    missing = []
    for doi, ids, title, status, err in rows:
        p = doi.split("/")[0]
        per[p]["total"] += 1
        if status == "done":
            per[p]["done"] += 1
            continue
        reason = classify(status, err) if status != "pending" else "not processed yet"
        per[p][reason] += 1
        missing.append((p, doi, first_id(ids), ids, title, status, reason))
    names = {} if args.no_names else publisher_names(con, sorted(per), args.email)
    order = sorted(per, key=lambda p: -(per[p]["total"] - per[p]["done"]))
    rank = {p: i for i, p in enumerate(order)}

    with open(out / "publisher_summary.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["doi_prefix", "publisher", "papers", "downloaded", "missing", "missing_%",
                    "suggested_route"] + REASONS)
        for p in order:
            d = per[p]
            miss = d["total"] - d["done"]
            w.writerow([p, names.get(p, ""), d["total"], d["done"], miss, f"{100 * miss / d['total']:.0f}",
                        ROUTES.get(p, "")] + [d[r] for r in REASONS])

    missing.sort(key=lambda m: (rank[m[0]], m[1]))
    with open(out / "missing_by_publisher.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["publisher", "doi_prefix", "doi", "rw_id", "all_rw_ids", "title", "status", "reason"])
        for p, doi, rid, ids, title, status, reason in missing:
            w.writerow([names.get(p, ""), p, doi, rid, ids, title, status, reason])

    # console summary
    total, done = len(rows), sum(per[p]["done"] for p in per)
    print(f"\npapers with DOI: {total}   downloaded: {done} ({100 * done / total:.1f}%)   missing: {total - done}")
    print("\nmain reasons for missing PDFs:")
    reasons = defaultdict(int)
    for m in missing:
        reasons[m[6]] += 1
    for r, n in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {n:6}  {r}")
    print(f"\nmissing by publisher (top {args.top}):")
    for p in order[:args.top]:
        d = per[p]
        print(f"  {p:<9} {names.get(p, '')[:38]:<38} {d['total'] - d['done']:6} of {d['total']:6} missing")
    print(f"\nwritten: {out / 'publisher_summary.csv'}\n         {out / 'missing_by_publisher.csv'} ({len(missing)} rows)")


def cmd_rename(args):
    """Switch every paper to the current naming scheme ('<ID block>/<RW ID> - <title>') and
    rename/move PDFs already downloaded. Never deletes anything; --dry-run only prints the plan."""
    con = open_db(args.db)
    out = Path(args.out)
    plan = [(doi, old, make_filename(ids, title), status)
            for doi, ids, title, old, status in
            con.execute("SELECT doi, record_ids, title, filename, status FROM papers")]
    changes = [p for p in plan if p[1] != p[2]]
    new_names = [p[2].lower() for p in plan]
    if len(set(new_names)) != len(new_names):
        sys.exit("new file names are not unique - aborting, nothing changed")
    files = [(doi, old, new) for doi, old, new, st in changes if (out / f"{old}.pdf").exists()]
    print(f"{len(changes)} of {len(plan)} names change; {len(files)} PDFs on disk to rename")
    for _, old, new in files[:10]:
        print(f"  {old[:60]}.pdf\n   -> {new[:70]}.pdf")
    clash = [new for _, _, new in files if (out / f"{new}.pdf").exists()]
    if clash:
        sys.exit(f"{len(clash)} target files already exist (e.g. {clash[0]}.pdf) - aborting, nothing changed")
    if args.dry_run:
        print("dry run - nothing changed")
        return
    done = []
    try:
        for _, old, new in files:
            (out / f"{new}.pdf").parent.mkdir(parents=True, exist_ok=True)
            os.rename(out / f"{old}.pdf", out / f"{new}.pdf")
            done.append((old, new))
    except OSError as e:  # undo, so files and database stay consistent
        for old, new in reversed(done):
            os.rename(out / f"{new}.pdf", out / f"{old}.pdf")
        sys.exit(f"rename failed ({e}) - undone, nothing changed")
    for _, old, _ in files:  # remove folders that the move left empty (never non-empty ones)
        parent = (out / f"{old}.pdf").parent
        if parent != out and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
    with con:  # one transaction; temporary names avoid UNIQUE clashes while swapping
        con.executemany("UPDATE papers SET filename='~tmp~'||doi WHERE doi=?", [(d,) for d, *_ in changes])
        con.executemany("UPDATE papers SET filename=? WHERE doi=?", [(new, d) for d, _, new, _ in changes])
    print(f"updated {len(changes)} names in the database, renamed {len(done)} PDFs")
    write_index(con, out)


def cmd_report(args):
    con = open_db(args.db)
    print("status:")
    for s, n in con.execute("SELECT status, COUNT(*) FROM papers GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {s:<10} {n}")
    print("downloaded via:")
    for s, n in con.execute("SELECT source, COUNT(*) FROM papers WHERE status='done' GROUP BY 1 ORDER BY 2 DESC"):
        print(f"  {s or '-':<16} {n}")
    print("missing PDFs by DOI prefix (publisher), top 15:")
    q = """SELECT substr(doi,1,instr(doi,'/')-1) p, COUNT(*) FROM papers
           WHERE status!='done' GROUP BY p ORDER BY 2 DESC LIMIT 15"""
    for p, n in con.execute(q):
        print(f"  {p:<12} {n}")
    print("rows without a DOI:", con.execute("SELECT COUNT(*) FROM no_doi").fetchone()[0])
    if args.export:
        with open(args.export, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["doi", "record_ids", "title", "filename", "status", "source", "pdf_url", "error"])
            w.writerows(con.execute("SELECT doi, record_ids, title, filename||'.pdf', status, source, pdf_url, error FROM papers"))
        print("exported to", args.export)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default="papers.sqlite", help="state database (default: papers.sqlite)")
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("import", help="load the Retraction Watch CSV into the state DB")
    i.add_argument("csv")
    i.add_argument("--doi-col"); i.add_argument("--title-col"); i.add_argument("--id-col")
    i.set_defaults(func=cmd_import)

    r = sub.add_parser("run", help="download PDFs (resumable)")
    r.add_argument("--email", required=True, help="your e-mail, sent to the APIs as contact")
    r.add_argument("--out", required=True, help="folder for the PDFs (e.g. an rclone-mounted cloud folder)")
    r.add_argument("--sources", default="unpaywall,openalex,elsevier,wiley",
                   help=f"comma list, order = priority. Available: {','.join(ALL_SOURCES)}")
    r.add_argument("--concurrency", type=int, default=16)
    r.add_argument("--limit", type=int, help="only process N random DOIs (for a test run)")
    r.add_argument("--prefix", help="only DOIs starting with this, e.g. 10.1155")
    r.add_argument("--retry-failed", action="store_true")
    r.add_argument("--retry-not-found", action="store_true")
    r.add_argument("--progress-every", type=int, default=50)
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("report", help="show progress / export status CSV")
    s.add_argument("--export", help="write per-paper status to this CSV")
    s.set_defaults(func=cmd_report)

    x = sub.add_parser("index", help="write index.csv (all papers, sorted by RW ID) into the PDF folder")
    x.add_argument("--out", required=True, help="the PDF folder")
    x.set_defaults(func=cmd_index)

    m = sub.add_parser("summary", help="per-publisher summary + CSV of missing DOIs (for the library)")
    m.add_argument("--out-dir", default="reports", help="folder for the CSV files (default: reports)")
    m.add_argument("--email", default="", help="contact e-mail for the Crossref publisher-name lookup")
    m.add_argument("--no-names", action="store_true", help="skip looking up publisher names at Crossref")
    m.add_argument("--top", type=int, default=20)
    m.set_defaults(func=cmd_summary)

    n = sub.add_parser("rename", help="rename/move existing PDFs to the current naming scheme (never deletes)")
    n.add_argument("--out", required=True, help="the PDF folder")
    n.add_argument("--dry-run", action="store_true", help="only show what would change")
    n.set_defaults(func=cmd_rename)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
