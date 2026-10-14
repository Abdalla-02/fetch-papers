"""Offline tests for fetch_pdfs.py - no internet needed, nothing outside a temp folder is touched.

Run:  python tests/test_fetch_pdfs.py        (or: python -m pytest tests)

A small local HTTP server plays Unpaywall and some publisher sites:
  - a site behind a Cloudflare challenge (reached through a redirect from another host),
  - a site that answers "503, Retry-After: 3600",
  - an index API that answers "429, Retry-After: 3600" (quota),
  - a site that serves real PDFs.
"""
import asyncio
import http.server
import json
import os
import sys
import tempfile
import threading
import time
import types
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

# ---------------------------------------------------------------- local server (start before import)
HITS = Counter()
LEAKED = []
API_QUOTA_AFTER = {"n": 10**9}   # the fake Unpaywall answers 429 + Retry-After after this many lookups
LOOKUPS = {"n": 0}
PDF_BYTES = b"%PDF-1.4\n" + b"x" * 5000


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def send(self, code, body=b"", headers=()):
        self.send_response(code)
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        host = self.headers["Host"].split(":")[0]
        path = self.path.split("?")[0]
        kind = path.split("/")[1]
        HITS[(host, kind)] += 1
        if "X-ELS-APIKey" in self.headers and host != "localhost":
            LEAKED.append(path)
        if kind == "upw":                       # fake Unpaywall: DOI 10.9999/<kind>-<n>
            LOOKUPS["n"] += 1
            if LOOKUPS["n"] > API_QUOTA_AFTER["n"]:
                return self.send(429, b"quota", [("Retry-After", "3600")])
            doi = unquote(path[len("/upw/"):])                 # e.g. "10.9999/good-3"
            kind_, n = doi.split("/", 1)[1].split("-")
            url = {"cf": f"http://localhost:{PORT}/redir/cf",   # localhost -> 127.0.0.1 (Cloudflare)
                   "slow": f"http://127.0.0.1:{PORT}/slow/x",
                   "good": f"http://localhost:{PORT}/good/{n}"}[kind_]
            body = json.dumps({"best_oa_location": {"url_for_pdf": url}, "oa_locations": []}).encode()
            return self.send(200, body, [("Content-Type", "application/json")])
        if kind == "redir":
            return self.send(302, headers=[("Location", f"http://127.0.0.1:{PORT}/cf/x")])
        if kind == "cf":
            return self.send(403, b"<html>Just a moment...</html>", [("cf-mitigated", "challenge")])
        if kind == "slow":
            return self.send(503, b"busy", [("Retry-After", "3600")])
        if kind == "good":
            return self.send(200, PDF_BYTES, [("Content-Type", "application/pdf")])
        self.send(404)


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
PORT = SERVER.server_address[1]
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
os.environ["UNPAYWALL_BASE"] = f"http://localhost:{PORT}/upw"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import fetch_pdfs as F  # noqa: E402

F.HOST_RPS.update({"localhost": 100, "127.0.0.1": 100})   # fast tests; the logic is unchanged
TMP = Path(tempfile.mkdtemp(prefix="fetch_pdfs_test_"))


def make_db(name, dois):
    con = F.open_db(str(TMP / f"{name}.sqlite"))
    for i, doi in enumerate(dois, 1):
        con.execute("INSERT INTO papers(doi, record_ids, title, filename) VALUES (?,?,?,?)",
                    (doi, str(i), f"Title {i}", F.make_filename(str(i), f"Title {i}")))
    con.commit()
    return con


def run_fetcher(con, name, concurrency=4):
    args = types.SimpleNamespace(out=str(TMP / name), sources="unpaywall", email="test@example.org",
                                 verbose=False, retry_failed=False, retry_temporary=False,
                                 retry_not_found=False, prefix=None, limit=None,
                                 concurrency=concurrency, progress_every=1000)
    fetcher = F.Fetcher(args, con)
    t = time.time()
    asyncio.run(fetcher.run())
    return fetcher, time.time() - t


# ---------------------------------------------------------------- tests
def test_naming():
    assert F.subfolder("001454") == "001001-002000"
    assert F.subfolder("000001") == "000001-001000" and F.subfolder("001000") == "000001-001000"
    name = F.make_filename("34298;1454", "Effects of X: a study / " + "very long title " * 20)
    folder, file = name.split("/")
    assert folder == "001001-002000" and file.startswith("001454 - Effects of X a study")
    assert len(file) - len("001454 - ") <= F.MAX_TITLE_CHARS
    assert not any(c in file for c in ':/?*"<>|')


def test_classify():
    assert F.classify("not_found", None) == F.REASONS[0]
    assert F.classify("failed", "unpaywall: HTTP 403 (Cloudflare bot challenge) <u>") == F.REASONS[1]
    assert F.classify("failed", "unpaywall: ConnectTimeout:  <u>") in F.TEMPORARY_REASONS
    assert F.classify("failed", "unpaywall: HTTP 503 <u>") in F.TEMPORARY_REASONS
    assert F.classify("failed", "unpaywall: HTTP 404 <u>") not in F.TEMPORARY_REASONS


def test_blocked_host_subfolders_and_no_key_leak():
    HITS.clear()
    dois = [f"10.9999/cf-{n}" for n in range(12)] + [f"10.9999/good-{n}" for n in range(4)]
    con = make_db("blocking", dois)
    fetcher, secs = run_fetcher(con, "blocking", concurrency=1)
    assert HITS[("127.0.0.1", "cf")] == F.BLOCK_AFTER, HITS            # exactly 8 requests, then skipped
    st = Counter(s for (s,) in con.execute("SELECT status FROM papers"))
    assert st == {"failed": 12, "done": 4}, st
    for (fn,) in con.execute("SELECT filename FROM papers WHERE status='done'"):
        assert (TMP / "blocking" / f"{fn}.pdf").exists()                 # saved inside its ID-block folder
        assert "/" in fn
    # an API key must not follow a redirect to another host
    async def leak():
        import httpx
        async with httpx.AsyncClient() as c:
            await F.Fetcher(fetcher.a, con).request(
                c, f"http://localhost:{PORT}/redir/x", headers={"X-ELS-APIKey": "SECRET"})
    asyncio.run(leak())
    assert LEAKED == [], LEAKED


def test_long_retry_after_on_a_site_skips_that_site():
    HITS.clear()
    con = make_db("slow", [f"10.9999/slow-{n}" for n in range(6)] + [f"10.9999/good-{n}" for n in range(3)])
    # realistic spacing for the site (real default: 1 request / 2 s), so the "wait 3600 s" answer
    # arrives before the next request is due; at 100 req/s two parallel requests could race
    F.HOST_RPS["127.0.0.1"] = 4
    try:
        fetcher, secs = run_fetcher(con, "slow")
    finally:
        F.HOST_RPS["127.0.0.1"] = 100
    assert secs < 30, f"run took {secs:.0f} s - it waited for Retry-After"
    assert HITS[("127.0.0.1", "slow")] == 1, HITS                       # asked once, then left alone
    assert not fetcher.stop_reason
    st = Counter(s for (s,) in con.execute("SELECT status FROM papers"))
    assert st == {"failed": 6, "done": 3}, st


def test_long_retry_after_on_an_api_stops_the_run():
    HITS.clear()
    LOOKUPS["n"], API_QUOTA_AFTER["n"] = 0, 3
    try:
        con = make_db("quota", [f"10.9999/good-{n}" for n in range(20)])
        fetcher, secs = run_fetcher(con, "quota", concurrency=1)
    finally:
        API_QUOTA_AFTER["n"] = 10**9
    assert secs < 30, f"run took {secs:.0f} s"
    assert "asked to wait 3600" in fetcher.stop_reason
    st = Counter(s for (s,) in con.execute("SELECT status FROM papers"))
    assert st == {"done": 3, "pending": 17}, st                          # rest untouched, not 'failed'


def _pdf(page_texts):
    """Minimal valid PDF with one text line per entry of each page."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for lines in page_texts:
        ops = "BT /F1 11 Tf 14 TL 50 780 Td " + " ".join(
            "(" + l.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for l in lines) + " ET"
        objs.append(f"<< /Length {len(ops)} >>\nstream\n{ops}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                    f"/Resources << /Font << /F1 3 0 R >> >> /Contents {len(objs)} 0 R >>")
        kids.append(f"{len(objs)} 0 R")
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def test_verify_verdicts():
    import importlib.util
    if importlib.util.find_spec("pypdf") is None:
        print("  (skipped: pypdf not installed)")
        return
    title, doi = "Regulation of Wnt beta-catenin pathway by cPLA2alpha", "10.1002/jcb.21852"
    filler = ["Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor."] * 12
    cases = {
        "ok": [[title, f"doi {doi}"] + filler, filler, filler],
        "notice": [[f"Retraction: {title}", "This article has been retracted by the editor."] + filler],
        "short": [[f"RETRACTED ARTICLE: {title}"] + filler],
        "mismatch": [["Highlights of prescribing information for a drug"] + filler] * 4,
    }
    for expected, pages in cases.items():
        path = TMP / f"{expected}.pdf"
        path.write_bytes(_pdf(pages))
        got = F.verify_pdf(str(path), title, doi)["verdict"]
        assert got == expected, (expected, got)
    broken = TMP / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4 this is not really a pdf")
    assert F.verify_pdf(str(broken), title, doi)["verdict"] in ("unreadable", "no_text")


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as e:
                failed += 1
                print(f"FAIL {name}: {type(e).__name__}: {e}")
    SERVER.shutdown()
    print("all tests passed" if not failed else f"{failed} test(s) failed")
    sys.exit(1 if failed else 0)
