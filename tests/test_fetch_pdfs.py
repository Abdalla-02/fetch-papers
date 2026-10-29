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
ELS_SERVED = {"n": 0, "max": 10**9}   # the fake Elsevier refuses everything (403) after this many full texts
PDF_BYTES = b"%PDF-1.4\n" + b"x" * 5000
_ELS = b'<?xml version="1.0"?><full-text-retrieval-response><coredata>' + b"x" * 2000 + b"</coredata>%s"
ELS_FULL_TEXT = _ELS % (b"<originalText><ce:sections><ce:para>Body " + b"word " * 500 +
                        b"</ce:para></ce:sections></originalText></full-text-retrieval-response>")
ELS_ABSTRACT_ONLY = _ELS % b"</full-text-retrieval-response>"
ELS_NOTICE = _ELS % (b"<originalText><ce:sections><ce:para>This article has been retracted: please see Elsevier Policy "
                     b"on Article Withdrawal. The editor no longer has confidence in the data.</ce:para></ce:sections>"
                     b"</originalText></full-text-retrieval-response>")
ELS_REMOVED = _ELS % (b"<originalText><xocs:doc><xocs:rawtext>REMOVED: A title Some Author, Some University. This article "
                      b"has been removed at the request of the editor.</xocs:rawtext></xocs:doc></originalText></full-text-retrieval-response>")
ELS_SHORT = _ELS % (b"<originalText><xocs:doc><xocs:rawtext>Journal Pre-proof A title Some Author PII: S0000 DOI: 10.1016/x "
                    b"To appear in: A Journal</xocs:rawtext></xocs:doc></originalText></full-text-retrieval-response>")


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
        if kind == "els":                       # fake Elsevier Article Retrieval API (full text as XML)
            key = self.headers.get("X-ELS-APIKey")
            if key == "good" and ("noacc" in path or ELS_SERVED["n"] >= ELS_SERVED["max"]):
                return self.send(403, b"<service-error>AUTHENTICATION_ERROR</service-error>")   # no licence
            if key == "good":
                ELS_SERVED["n"] += 1
                body = (ELS_ABSTRACT_ONLY if "abs" in path else ELS_NOTICE if "ntc" in path
                        else ELS_SHORT if "shrt" in path else ELS_FULL_TEXT)
                return self.send(200, body, [("Content-Type", "text/xml")])
            if key == "quota":
                return self.send(429, b"quota exceeded")
            return self.send(401, b"invalid api key")
        if kind == "wiley":                     # fake Wiley TDM API
            if "%25" in self.path:              # a '%' escaped twice: no such article
                return self.send(404)
            if "14651858" in path or "nolic" in path:   # Cochrane reviews / articles without a licence
                return self.send(403, b"not entitled")
            if "redir" in path and self.headers.get("Wiley-TDM-Client-Token") == "good":
                return self.send(302, headers=[("Location", f"http://127.0.0.1:{PORT}/good/w")])   # like the real API
            if self.headers.get("Wiley-TDM-Client-Token") == "good":
                return self.send(200, PDF_BYTES, [("Content-Type", "application/pdf")])
            return self.send(403, b"not entitled")
        self.send(404)


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
PORT = SERVER.server_address[1]
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
os.environ["UNPAYWALL_BASE"] = f"http://localhost:{PORT}/upw"
os.environ["ELSEVIER_BASE"] = f"http://localhost:{PORT}/els"
os.environ["WILEY_BASE"] = f"http://localhost:{PORT}/wiley"
for _k in ("ELSEVIER_API_KEY", "ELSEVIER_INSTTOKEN", "WILEY_TDM_TOKEN"):   # never use real keys in tests
    os.environ.pop(_k, None)

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


def run_fetcher(con, name, concurrency=4, **overrides):
    opts = dict(out=str(TMP / name), sources="unpaywall", email="test@example.org", verbose=False,
                retry_failed=False, retry_temporary=False, retry_not_found=False, retry_incomplete=False,
                wiley_prefixes=F.WILEY_PREFIXES, prefix=None, limit=None, concurrency=concurrency,
                progress_every=1000)
    opts.update(overrides)
    args = types.SimpleNamespace(**opts)
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


class env:
    """Temporarily set environment variables (API keys) for one test."""
    def __init__(self, **kv):
        self.kv = kv
    def __enter__(self):
        self.old = {k: os.environ.get(k) for k in self.kv}
        os.environ.update(self.kv)
    def __exit__(self, *exc):
        for k, v in self.old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def test_load_env_file():
    p = TMP / "test.env"
    p.write_text('# comment\nexport ELSEVIER_API_KEY="abc123"\nWILEY_TDM_TOKEN = \'tok\'\nEMPTY=\nPRESET=from_file\n',
                 encoding="utf-8")
    with env(PRESET="from_shell"):
        try:
            names = F.load_env(str(p))
            assert set(names) == {"ELSEVIER_API_KEY", "WILEY_TDM_TOKEN"}, names
            assert os.environ["ELSEVIER_API_KEY"] == "abc123" and os.environ["WILEY_TDM_TOKEN"] == "tok"
            assert os.environ["PRESET"] == "from_shell"                  # existing variables win
        finally:
            os.environ.pop("ELSEVIER_API_KEY", None)
            os.environ.pop("WILEY_TDM_TOKEN", None)


def test_wiley_prefixes_and_elsevier_xml():
    HITS.clear()
    sici = "10.1002/(sici)1-2(1996)3:4%3c5::aid-x6%3e7.0.co;2-l"            # stored with '<' '>' escaped
    dois = ["10.1016/els-1", "10.1016/abs-2", "10.1155/hin-1", "10.1002/wil-1", "10.1002/14651858.cd000001", sici]
    with env(ELSEVIER_API_KEY="good", WILEY_TDM_TOKEN="good"):
        con = make_db("tdm_default", dois)
        run_fetcher(con, "tdm_default", sources="elsevier,wiley")
        st = dict(con.execute("SELECT doi, status FROM papers"))
        assert st == {"10.1016/els-1": "done", "10.1016/abs-2": "failed", "10.1155/hin-1": "done",
                      "10.1002/wil-1": "done", "10.1002/14651858.cd000001": "pending", sici: "done"}, st
        assert HITS[("localhost", "wiley")] == 3, HITS                    # Cochrane is never sent to Wiley
        fn1, src1 = con.execute("SELECT filename, source FROM papers WHERE doi='10.1016/els-1'").fetchone()
        assert src1 == "elsevier" and (TMP / "tdm_default" / f"{fn1}.xml").exists()      # Elsevier: XML, no PDF
        assert not (TMP / "tdm_default" / f"{fn1}.pdf").exists()
        err = con.execute("SELECT error FROM papers WHERE doi='10.1016/abs-2'").fetchone()[0]
        assert "only the abstract" in err, err
        fn2 = con.execute("SELECT filename FROM papers WHERE doi='10.1016/abs-2'").fetchone()[0]
        assert not list((TMP / "tdm_default").rglob(f"{fn2.split('/')[1]}*")), "abstract-only XML was kept"
        F.write_index(con, TMP / "tdm_default")
        assert "000001 - Title 1.xml" in (TMP / "tdm_default" / "index.csv").read_text(encoding="utf-8-sig")
        con = make_db("tdm_no_hindawi", dois[:4])                          # Hindawi can be switched off
        run_fetcher(con, "tdm_no_hindawi", sources="elsevier,wiley", wiley_prefixes="10.1002,10.1111")
        st = dict(con.execute("SELECT doi, status FROM papers"))
        assert st["10.1155/hin-1"] == "pending", st


def test_tdm_api_not_skipped_for_articles_without_licence():
    HITS.clear()
    dois = ["10.1016/a-good-1"] + [f"10.1016/b-noacc-{n:02}" for n in range(12)] + ["10.1016/c-good-2"]
    with env(ELSEVIER_API_KEY="good"):
        # 12 articles without a licence in a row, but access as such works: Elsevier is not skipped
        con = make_db("els_noacc", dois)
        run_fetcher(con, "els_noacc", sources="elsevier", concurrency=1)
        st = Counter(s for (s,) in con.execute("SELECT status FROM papers"))
        assert st == {"done": 2, "failed": 12}, st
        errs = {e for (e,) in con.execute("SELECT error FROM papers WHERE status='failed'")}
        assert all("HTTP 403" in e and "skipped" not in e for e in errs), errs
        assert HITS[("localhost", "els")] == 1 + 12 + 1 + 1, HITS       # one extra request: the access check
        # access is gone after the first paper (e.g. VPN off): the check fails and Elsevier is skipped
        HITS.clear()
        ELS_SERVED.update(n=0, max=1)
        try:
            con = make_db("els_gone", dois)
            run_fetcher(con, "els_gone", sources="elsevier", concurrency=1)
        finally:
            ELS_SERVED["max"] = 10**9
        st = Counter(s for (s,) in con.execute("SELECT status FROM papers"))
        assert st == {"done": 1, "failed": 13}, st
        assert HITS[("localhost", "els")] == 1 + F.BLOCK_AFTER + 1, HITS
        err = con.execute("SELECT error FROM papers WHERE doi='10.1016/a-good-1'").fetchone()[0]   # last (DOI order is descending)
        assert "skipped" in err, err


def test_elsevier_notice_xml_is_kept_as_notice():
    out = TMP / "els_notice"
    con = make_db("els_notice", ["10.1016/ntc-1", "10.1016/ntc-2", "10.1016/els-3"])
    fn2 = con.execute("SELECT filename FROM papers WHERE doi='10.1016/ntc-2'").fetchone()[0]
    (out / fn2).parent.mkdir(parents=True, exist_ok=True)                 # paper 2 already has a notice PDF
    (out / f"{F.marked_name(fn2, 'notice')}.pdf").write_bytes(PDF_BYTES)
    con.execute("UPDATE papers SET status='incomplete', source='unpaywall' WHERE doi='10.1016/ntc-2'")
    con.execute("INSERT INTO checks VALUES ('10.1016/ntc-2','notice','',1,0)")
    con.commit()
    with env(ELSEVIER_API_KEY="good"):
        run_fetcher(con, "els_notice", sources="elsevier", retry_incomplete=True)
    st = dict(con.execute("SELECT doi, status FROM papers"))
    assert st == {"10.1016/ntc-1": "incomplete", "10.1016/ntc-2": "incomplete", "10.1016/els-3": "done"}, st
    fn1 = con.execute("SELECT filename FROM papers WHERE doi='10.1016/ntc-1'").fetchone()[0]
    assert (out / f"{F.marked_name(fn1, 'notice')}.xml").exists() and not (out / f"{fn1}.xml").exists()
    assert con.execute("SELECT verdict FROM checks WHERE doi='10.1016/ntc-1'").fetchone()[0] == "notice"
    # paper 2 keeps its notice PDF and its source; the second notice (XML) is not kept
    assert con.execute("SELECT source FROM papers WHERE doi='10.1016/ntc-2'").fetchone()[0] == "unpaywall"
    assert not list(out.rglob("000002*.xml")) and (out / f"{F.marked_name(fn2, 'notice')}.pdf").exists()
    F.write_index(con, out)
    index = (out / "index.csv").read_text(encoding="utf-8-sig")
    assert "000001 [notice] - Title 1.xml" in index and "000002 [notice] - Title 2.pdf" in index
    assert F.xml_verdict(ELS_FULL_TEXT)[0] == "ok"
    assert F.xml_verdict(ELS_NOTICE)[0] == "notice" and F.xml_verdict(ELS_REMOVED)[0] == "notice"
    assert F.xml_verdict(ELS_SHORT)[0] == "short_text"
    squashed = ELS_SHORT.replace(b"To appear in: A Journal", b"Thewholearticlewithoutspaces" * 100)   # few words, much text
    assert F.xml_verdict(squashed)[0] == "ok"


def test_short_xml_is_kept_as_short_and_old_xml_can_be_verified():
    out = TMP / "short_xml"
    with env(ELSEVIER_API_KEY="good"):
        con = make_db("short_xml", ["10.1016/shrt-1", "10.1016/els-2"])
        run_fetcher(con, "short_xml", sources="elsevier")
    st = dict(con.execute("SELECT doi, status FROM papers"))
    assert st == {"10.1016/shrt-1": "incomplete", "10.1016/els-2": "done"}, st
    fn1 = con.execute("SELECT filename FROM papers WHERE doi='10.1016/shrt-1'").fetchone()[0]
    assert F.marked_name(fn1, "short_text").endswith("000001 [short] - Title 1")
    assert (out / f"{F.marked_name(fn1, 'short_text')}.xml").exists() and not (out / f"{fn1}.xml").exists()
    assert con.execute("SELECT verdict FROM checks WHERE doi='10.1016/shrt-1'").fetchone()[0] == "short_text"
    # an XML saved by an older version: 'verify' finds it, 'mark-incomplete' keeps it as '[short]'
    fn2 = con.execute("SELECT filename FROM papers WHERE doi='10.1016/els-2'").fetchone()[0]
    (out / f"{fn2}.xml").write_bytes(ELS_SHORT)
    assert [d for d, *_ in F.xml_to_verify(con)] == ["10.1016/els-2"]
    r = F.verify_xml(out / f"{fn2}.xml")
    assert r["verdict"] == "short_text" and "words" in r["note"], r
    con.execute("INSERT INTO checks VALUES ('10.1016/els-2', 'short_text', ?, 0, 0)", (r["note"],))
    con.commit()
    args = types.SimpleNamespace(db=str(TMP / "short_xml.sqlite"), out=str(out), dry_run=False, skip_folder_check=True)
    F.cmd_mark_incomplete(args)
    assert con.execute("SELECT status FROM papers WHERE doi='10.1016/els-2'").fetchone()[0] == "incomplete"
    assert (out / f"{F.marked_name(fn2, 'short_text')}.xml").exists() and not (out / f"{fn2}.xml").exists()


def test_wiley_redirects_count_as_success_for_the_api():
    # the real Wiley API answers every PDF with a redirect to another host; single 403s (articles without a
    # licence) in between must not add up to "8 in a row", and a run of them is checked with a paper that worked
    HITS.clear()
    alternating = [f"10.1002/x{n:02}a-nolic" for n in range(10)] + [f"10.1002/x{n:02}b-redir" for n in range(10)]
    run_of_refusals = ["10.1002/y-redir-1"] + [f"10.1002/w-nolic-{n:02}" for n in range(10)] + ["10.1002/a-redir-2"]
    with env(WILEY_TDM_TOKEN="good"):
        for name, dois in (("wiley_alt", alternating), ("wiley_run", run_of_refusals)):
            con = make_db(name, dois)
            run_fetcher(con, name, sources="wiley", concurrency=1)
            st = Counter(s for (s,) in con.execute("SELECT status FROM papers"))
            assert st == {"failed": 10, "done": len(dois) - 10}, (name, st)
            errs = [e for (e,) in con.execute("SELECT error FROM papers WHERE status='failed'")]
            assert all("HTTP 403" in e and "skipped" not in e for e in errs), (name, errs)


def test_verify_skips_manual_decisions_and_xml():
    con = make_db("verify_select", ["10.9999/a-1", "10.9999/b-2", "10.1016/c-3", "10.9999/d-4"])
    con.execute("UPDATE papers SET status='done', source='unpaywall'")
    con.execute("UPDATE papers SET source='elsevier' WHERE doi='10.1016/c-3'")
    con.execute("INSERT INTO checks VALUES ('10.9999/b-2','ok','manual check 29 Oct 2026: correct paper',5,0)")
    con.execute("INSERT INTO checks VALUES ('10.9999/d-4','mismatch','',5,0)")    # automatic result: checked again
    con.commit()
    assert sorted(d for d, *_ in F.papers_to_verify(con)) == ["10.9999/a-1", "10.9999/d-4"]


def test_papers_no_source_can_handle_are_untouched():
    con = make_db("untouched", ["10.1016/els-1", "10.1002/wil-1", "10.9999/x-1"])
    con.execute("UPDATE papers SET status='failed', error='unpaywall: HTTP 403 (Cloudflare bot challenge) <u>'")
    con.commit()
    with env(WILEY_TDM_TOKEN="good"):                                   # no Elsevier key
        run_fetcher(con, "untouched", sources="elsevier,wiley", retry_failed=True)
    rows = {d: (s, e) for d, s, e in con.execute("SELECT doi, status, error FROM papers")}
    assert rows["10.1002/wil-1"][0] == "done", rows
    for doi in ("10.1016/els-1", "10.9999/x-1"):                         # kept exactly as they were
        assert rows[doi] == ("failed", "unpaywall: HTTP 403 (Cloudflare bot challenge) <u>"), rows[doi]


def test_rejected_key_or_quota_stops_the_run():
    for key, expected in (("bad", "API key was rejected"), ("quota", "rate limit or quota")):
        with env(ELSEVIER_API_KEY=key):
            con = make_db(f"els_{key}", [f"10.1016/els-{n}" for n in range(10)])
            fetcher, secs = run_fetcher(con, f"els_{key}", concurrency=1, sources="elsevier")
        assert expected in fetcher.stop_reason, fetcher.stop_reason
        st = Counter(s for (s,) in con.execute("SELECT status FROM papers"))
        assert st == {"pending": 10}, st                                   # nothing marked as failed


def test_mark_incomplete_and_retry():
    out = TMP / "incomplete"
    con = make_db("incomplete", ["10.1016/els-1", "10.9999/x-2", "10.9999/x-3"])
    verdicts = {"10.1016/els-1": "notice", "10.9999/x-2": "short", "10.9999/x-3": "ok"}
    for doi, fn in con.execute("SELECT doi, filename FROM papers").fetchall():
        (out / fn).parent.mkdir(parents=True, exist_ok=True)
        (out / f"{fn}.pdf").write_bytes(PDF_BYTES)
        con.execute("UPDATE papers SET status='done', source='unpaywall' WHERE doi=?", (doi,))
        con.execute("INSERT INTO checks VALUES (?,?,?,?,?)", (doi, verdicts[doi], "", 1, 0))
    con.commit()
    args = types.SimpleNamespace(db=str(TMP / "incomplete.sqlite"), out=str(out), dry_run=True)
    F.cmd_mark_incomplete(args)                                            # dry run: nothing changes
    assert Counter(s for (s,) in con.execute("SELECT status FROM papers")) == {"done": 3}
    args.dry_run = False
    F.cmd_mark_incomplete(args)
    st = dict(con.execute("SELECT doi, status FROM papers"))
    assert st == {"10.1016/els-1": "incomplete", "10.9999/x-2": "incomplete", "10.9999/x-3": "done"}, st
    fn1 = con.execute("SELECT filename FROM papers WHERE doi='10.1016/els-1'").fetchone()[0]
    marked1 = F.marked_name(fn1, "notice")
    assert marked1.endswith("000001 [notice] - Title 1"), marked1          # status right after the ID
    assert (out / f"{marked1}.pdf").exists() and not (out / f"{fn1}.pdf").exists()
    index = (out / "index.csv").read_text(encoding="utf-8-sig")
    assert "000001 [notice] - Title 1.pdf" in index and "000002 [first page] - Title 2.pdf" in index
    # a later Phase B run fetches the real article for the Elsevier paper; the other stays 'incomplete'
    with env(ELSEVIER_API_KEY="good"):
        run_fetcher(con, "incomplete", sources="elsevier", retry_incomplete=True)
    st = dict(con.execute("SELECT doi, status FROM papers"))
    assert st == {"10.1016/els-1": "done", "10.9999/x-2": "incomplete", "10.9999/x-3": "done"}, st
    assert (out / f"{fn1}.xml").exists() and (out / f"{marked1}.pdf").exists()   # notice is kept
    assert con.execute("SELECT source FROM papers WHERE doi='10.9999/x-2'").fetchone()[0] == "unpaywall"
    assert con.execute("SELECT COUNT(*) FROM checks WHERE doi='10.1016/els-1'").fetchone()[0] == 0  # re-check


def test_folder_guard_stops_on_missing_pdfs():
    """A sync folder that looks empty (e.g. Nextcloud virtual files without the client) must stop the commands."""
    out = TMP / "guard"
    con = make_db("guard", [f"10.9999/g-{n}" for n in range(30)])
    fns = [fn for (fn,) in con.execute("SELECT filename FROM papers ORDER BY doi")]
    for fn in fns:
        (out / fn).parent.mkdir(parents=True, exist_ok=True)
        (out / f"{fn}.pdf").write_bytes(PDF_BYTES)
    con.execute("UPDATE papers SET status='done'")
    # one paper is 'incomplete': its file is the marked notice - it must count as present
    marked = F.marked_name(fns[0], "notice")
    (out / f"{fns[0]}.pdf").rename(out / f"{marked}.pdf")
    con.execute("UPDATE papers SET status='incomplete' WHERE filename=?", (fns[0],))
    con.execute("INSERT INTO checks VALUES ((SELECT doi FROM papers WHERE filename=?),'notice','',1,0)", (fns[0],))
    con.commit()
    args = types.SimpleNamespace(db=str(TMP / "guard.sqlite"), out=str(out), dry_run=True, skip_folder_check=False)
    F.check_pdf_folder(con, out, args)                                    # all 30 present: no complaint
    for fn in fns[1:5]:                                                   # 26 of 30 left = 87% < 90%
        (out / f"{fn}.pdf").unlink()
    before = list(con.execute("SELECT doi, status, filename FROM papers ORDER BY doi"))
    for cmd in (F.cmd_rename, F.cmd_mark_incomplete):
        try:
            cmd(args)
            raise AssertionError(f"{cmd.__name__} did not stop")
        except SystemExit as e:
            assert "STOPPED: only 26 of 30" in str(e), e
    assert list(con.execute("SELECT doi, status, filename FROM papers ORDER BY doi")) == before   # nothing changed
    args.skip_folder_check = True                                         # explicit override works
    F.check_pdf_folder(con, out, args)


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
