# Retracted-papers PDF downloader

Research project at Otto von Guericke University Magdeburg (OVGU): collecting the full texts of the ~64,000 retracted papers listed by [Retraction Watch](https://retractionwatch.com), for later analysis. Maintained by Abdalla Ahmed (student research assistant).

**Current state (week 3):** 7,177 PDFs downloaded from open-access sources, of which 6,031 are full articles and 1,146 only the retraction notice or the article's first page. The Elsevier key and the Wiley token are in place and tested: Wiley (including Hindawi) delivers full PDFs, Elsevier full texts as XML. Next: the full Phase B run. Details, numbers and open items: [ANALYSIS.md](ANALYSIS.md).

`fetch_pdfs.py` downloads the PDFs for the DOIs in the Retraction Watch CSV and saves each one as `<ID block>/<RW ID> - <title>.pdf`, e.g. `001001-002000/001454 - Circulatory Responses ….pdf`. It uses only legal channels: open-access indexes and the publishers' official text-and-data-mining (TDM) APIs. It never logs in to your university account and never tries to get past bot protection.

**About the CSV:** `retraction_watch_1.10.26 - short-version.csv` (columns `ID`, `Title`, `OriginalPaperDOI`) has 72,790 rows, which become 63,790 unique DOIs after cleaning. 5,950 rows have no usable DOI; they're kept in the database (table `no_doi`) so you can handle them by hand.

Results and analysis of the runs so far: see [ANALYSIS.md](ANALYSIS.md).

## 1. Setup

Python 3.9 or newer.

**Linux / macOS:**

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python fetch_pdfs.py import "retraction_watch_1.10.26 - short-version.csv"
```

**Windows (PowerShell):**

```powershell
py -3 -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
venv\Scripts\python fetch_pdfs.py --db C:\path\to\retracted_pdfs\papers.sqlite import "retraction_watch_1.10.26 - short-version.csv"
```

This creates `papers.sqlite`, which stores the status and file name of every paper. Use `--db` to keep it in a data folder. **Don't put the database in a OneDrive or Nextcloud folder**: sync programs can lock or corrupt a database that changes constantly. The PDFs themselves can go into a synced folder (see section 4).

## 2. Run in phases

You can stop a run at any time (Ctrl+C, closing the window, a reboot). Running the same command again resumes where it stopped.

- **Linux:** run it inside `tmux` or with `nohup` so it keeps going after you log out.
- **Windows:** copy [`windows/run_phase_a.cmd`](windows/run_phase_a.cmd) next to your data, fill in the four settings at the top, and double-click it. It writes everything to `logs\phaseA.log` and uses [`windows/keep_awake_run.py`](windows/keep_awake_run.py) so the PC doesn't fall asleep during the run (closing the lid still does).

**Quick test first:**

```bash
python fetch_pdfs.py run --email you@uni.de --out /data/retracted_pdfs --limit 100 --sources unpaywall,openalex
python fetch_pdfs.py report
```

**Phase A: open access (works anywhere, no keys needed).**

```bash
python fetch_pdfs.py run --email you@uni.de --out /data/retracted_pdfs --sources unpaywall,openalex
```

The full run took 3.5 hours on a home connection (about 310 DOIs per minute) and produced 7,005 PDFs (17 GB).

**Retry temporary errors** (timeouts, network errors, HTTP 5xx) a few days later. `--retry-temporary` skips papers whose site blocked us, so the blocked sites are not contacted again for nothing; `--retry-failed` retries every failed paper:

```bash
python fetch_pdfs.py run --email you@uni.de --out /data/retracted_pdfs --sources unpaywall,openalex --retry-temporary
```

**Check the downloaded PDFs** (needs `pip install pypdf cryptography`; works offline):

```bash
python fetch_pdfs.py verify --out /data/retracted_pdfs --out-dir reports
```

This reads the first pages of every PDF and writes `reports/verify.csv` with one verdict per file:

| Verdict | Meaning |
|---|---|
| `ok` | Title or DOI found on the first pages |
| `notice` | 1–2 pages that read like a retraction notice: the publisher's link gave the notice, not the article |
| `short` | 1–2 pages, not a notice: a short item, or only the first page of the article (often with a "RETRACTED ARTICLE" stamp) |
| `mismatch` | Neither title nor DOI found: probably a different document, or a paper in another language than its title. Check by hand |
| `check` | Title only partly found |
| `no_text` | No text layer (scanned PDF), can't be checked automatically |
| `unreadable` | The PDF can't be opened |

The note column also flags PDFs with more than 60 pages (probably a whole issue or supplement).

**Phase B: publisher TDM APIs** (once you have the keys, see section 3).

1. **Keys in `.env`.** Copy [`.env.example`](.env.example) to `.env` in the folder you run the script from (or next to `fetch_pdfs.py`) and fill in the keys. The script reads them at start and only prints whether each key is set, never the key itself. `.env` is in `.gitignore`: never commit it, never share it. Real environment variables take precedence over `.env`.
2. **Mark the notice-only PDFs** (once, after `verify`), so Phase B fetches the real articles for them:
   ```bash
   python fetch_pdfs.py mark-incomplete --out /data/retracted_pdfs --dry-run   # shows what would change
   python fetch_pdfs.py mark-incomplete --out /data/retracted_pdfs
   ```
   Each such PDF is kept, renamed with its status right after the ID (e.g. `001454 [notice] - Title.pdf` or `001454 [first page] - Title.pdf`, so it still sorts by ID), and its paper gets status `incomplete`. Nothing is deleted.
3. **Small test first** (20 papers per publisher), then look at the log and the new PDFs:
   ```bash
   python fetch_pdfs.py run --email you@uni.de --out /data/retracted_pdfs --sources elsevier,wiley \
       --retry-not-found --retry-failed --retry-incomplete --prefix 10.1016 --limit 20
   # the same again with --prefix 10.1002, then:
   python fetch_pdfs.py verify --out /data/retracted_pdfs
   ```
   Elsevier full texts are saved as XML (`<ID> - <title>.xml`): as a PDF, the API only sends the first page. An XML that contains only the abstract (no entitlement) is not kept; the paper is marked `failed` with `XML has no full text, only the abstract`. An XML that is only the retraction notice (under 1,000 words, starting like a notice) is kept like a notice PDF, as `<ID> [notice] - <title>.xml`, and the paper gets status `incomplete`; if the paper already has a notice, the new one is not kept.
4. **Full run:** the same command without `--prefix` and `--limit`. On Windows, use [`windows/run_phase_b.cmd`](windows/run_phase_b.cmd) (`TEST=1` for step 3, `TEST=0` for the full run). `run_phase_b.cmd elsevier` and `run_phase_b.cmd wiley` run one API each, so both can run at the same time in two windows (their papers don't overlap); each logs to its own file (`logs\phaseB_elsevier.log`, `logs\phaseB_wiley.log`).

Good to know:

- Only papers that the configured APIs can handle are touched (Elsevier: DOIs `10.1016/…`; Wiley: the prefixes in `--wiley-prefixes`, default `10.1002,10.1111,10.1155`, the last one being Hindawi). All other papers keep their status and the reason from earlier runs.
- **Cochrane reviews** (`10.1002/14651858.…`) are never sent to the Wiley API: they are licensed separately and refused (403), and a run of them in a row would get the whole API skipped for the run.
- **Network:** run Phase B from the university network, or with the VPN in **full-tunnel** mode. With a split tunnel, the publishers see the home connection: Elsevier then answers `403 … Requestor configuration settings insufficient`.
- If an API rejects the key (HTTP 401) or keeps answering 429 (rate limit or quota used up), the run stops with `STOPPED EARLY` and exit code 3, without marking any paper as failed. Fix the key or wait, then run the same command again.
- Papers with status `incomplete` keep it (and their notice file) if the APIs find nothing; if the real article is downloaded, it is saved under the normal name next to the notice file.

**Phase C: Crossref full-text links.** Only run this if your library agrees, and only from a computer on the university network or VPN, so the publisher recognises your subscription:

```bash
python fetch_pdfs.py run --email you@uni.de --out /data/retracted_pdfs \
    --sources crossref --retry-not-found --retry-failed
```

**Watching progress:**

```bash
tail -f logs/phaseA.log                                 # Linux
Get-Content logs\phaseA.log -Tail 20 -Wait              # Windows PowerShell
python fetch_pdfs.py report                             # counts per status and publisher
```

**Useful options:**

- `--prefix 10.1155` processes one publisher only. Here, 10.1155 is Hindawi.
- `--concurrency 16` sets how many papers are processed in parallel. More doesn't help: the speed is capped by the polite rate limits of the open-access indexes.
- `-v` shows detailed lookup errors.

**All commands:**

| Command | What it does |
|---|---|
| `import <csv>` | Load the Retraction Watch CSV into the database |
| `run --email … --out <folder>` | Download PDFs (resumable) and rewrite `index.csv` |
| `report [--export status.csv]` | Counts per status, per source and per publisher; optional per-paper CSV |
| `summary --out-dir reports --email …` | Per-publisher summary and the list of missing DOIs for the library |
| `index --out <folder>` | Rewrite `index.csv` in the PDF folder |
| `verify --out <folder> [--out-dir reports]` | Check every downloaded PDF against its title and DOI (`verify.csv`) |
| `mark-incomplete --out <folder> [--dry-run]` | Keep notice / first-page-only PDFs as `<ID> [notice] - <title>.pdf` and mark their papers `incomplete` for Phase B |
| `rename --out <folder> [--dry-run]` | Rename existing PDFs after a change of the naming scheme |

## 3. Getting access to the paywalled papers

**First, request API keys from the publishers directly:**

- **Elsevier:** create an API key on the [Elsevier Developer Portal](https://dev.elsevier.com) and put it in `.env` as `ELSEVIER_API_KEY`. Elsevier recognises the university's subscriptions by its network, so run Phase B from the university network or a full-tunnel VPN. An institutional token (`ELSEVIER_INSTTOKEN`) is only needed to work from outside it.
- **Wiley:** request a text-and-data-mining token with your Wiley Online Library account and put it in `.env` as `WILEY_TDM_TOKEN`.

**Then ask the library** for whatever the publishers' own APIs don't cover (IEEE, Springer Nature, Taylor & Francis, SAGE, …). Here is a short email you can adapt:

> For a research project on retracted literature I need the full texts of retracted articles (list attached, DOIs). I'd like to obtain them via the publishers' TDM interfaces under §60d UrhG rather than by manual downloading. Can you confirm our TDM entitlements and advise how to get access for the publishers on the list?

Attach the files made by

```bash
python fetch_pdfs.py summary --out-dir reports --email you@uni.de
```

`reports/missing_by_publisher.csv` lists every missing DOI grouped by publisher (names looked up at Crossref) with the main reason it is missing. `reports/publisher_summary.csv` gives one row per publisher with counts per reason and the suggested legal route. If `verify` has been run, PDFs it found to be only a retraction notice or a first page count as missing (reason `PDF is only a retraction notice or first page`, status `pdf_incomplete`), because the full article still has to be obtained.

Still missing right after Phase A (largest publishers; current numbers in [ANALYSIS.md](ANALYSIS.md)):

| DOI prefix | Publisher | Missing | Route |
|---|---|---|---|
| 10.1155 | Hindawi | 11,749 | Open access, but the download site blocks bots → Wiley TDM API |
| 10.1016 | Elsevier | 8,071 | Elsevier API key (from the university network) |
| 10.1109 | IEEE | 7,770 | Library arrangement; no public TDM PDF API |
| 10.1007 | Springer | 5,528 | Springer Nature TDM via the library |
| 10.1002 / 10.1111 | Wiley | 3,677 | Wiley TDM token |

## 4. Saving to cloud storage

**Nextcloud (what we use):** install the [Nextcloud desktop client](https://nextcloud.com/install/), log in (the university login opens in your browser), and pass a folder inside the Nextcloud sync folder as `--out`. Every new PDF and `index.csv` is uploaded automatically, and interrupted uploads resume. Keep `papers.sqlite`, `logs/` and `reports/` outside the synced folder.

Two things to know:

- Deleting a PDF in the synced folder also deletes it in the cloud.
- PDFs are grouped in subfolders of 1,000 Retraction Watch IDs, so no folder gets too large to open quickly, and titles are cut to 150 characters so full paths stay under Windows' 260-character limit. Moving files into the subfolders with `rename` is synced as a move, not a new upload.

Zipping the PDFs first is not worth it: they are already compressed, so a zip saves only about 13%, and single papers could no longer be opened in the cloud.

**Other clouds:** [rclone](https://rclone.org) supports Google Drive, Nextcloud/WebDAV, OneDrive, S3 and others:

```bash
rclone config                                   # one-time: add a remote called "cloud"
rclone copy /data/retracted_pdfs cloud:RetractedPapers --progress   # repeat after each run
```

## 5. How it works

- **Folders and file names:** `<ID block>/<RW ID> - <title>.pdf`, e.g. `001001-002000/001454 - Circulatory Responses to Laryngeal Mask Airway Insertion ….pdf`. Each subfolder holds one block of 1,000 Retraction Watch IDs (`FOLDER_SIZE`), so a folder never holds more than 1,000 PDFs and you can find a paper from its ID alone. The ID is zero-padded to 6 digits so everything sorts by ID, and it makes every name unique. If several Retraction Watch entries share one DOI, the smallest ID is used (all IDs are listed in `index.csv`). The title has characters like `/ : ? *` removed and is cut to 150 characters (`MAX_TITLE_CHARS`), at a word boundary where possible; the full title is in `index.csv`.
- **`index.csv`:** written into the PDF folder after every `run` (or with `index`). One row per Retraction Watch entry, sorted by ID: `rw_id, all_rw_ids, doi, doi_prefix, title, folder, filename, status, pdf_check, source, pdf_url, error`. `folder`, `filename` and `pdf_check` (the `verify` result, e.g. `ok` or `notice`) are filled for downloaded papers. It includes the papers that are still missing and the rows without a DOI (`status = no_doi`), so you can filter it in Excel. It is saved as UTF-8 with BOM so Excel shows special characters correctly.
- **Renaming after a naming change:** `rename --out <folder> --dry-run` shows what would change; without `--dry-run` it renames the PDFs and updates the database. It never deletes anything, and if a rename fails it undoes the renames it already made.
- **No fake PDFs:** a file is saved only if its first kilobyte contains `%PDF`. HTML login and bot-check pages are rejected and logged as `not a PDF`.
- **Polite rate limits:** each server gets its own speed limit (`HOST_RPS` and `DEFAULT_RPS` at the top of the script). Publisher sites get one request every 2 seconds; the Wiley TDM API one every 10 seconds (its limit is 60 per 10 minutes). Redirects are followed one hop at a time, so the limit applies to the server that actually answers, and API keys are never forwarded to another host. When a site answers 429 or 403, the script slows down for that site and speeds up again once requests succeed; a line starting with `! host … keeps pushing back` appears in the log.
- **Blocked hosts:** if a host refuses `BLOCK_AFTER` (8) downloads in a row (403/429, a Cloudflare "Just a moment…" challenge, or an HTML page instead of a PDF), it is skipped for the rest of the run and the log shows `! host … skipping it for the rest of this run`. Its papers are marked `failed` with `skipped: … blocked for this run`, so `--retry-failed` (or Phase B) can pick them up later. The script never tries to get past such a block. Exception for the TDM APIs (Elsevier, Wiley): there a 403 usually means "no licence for this one article" (e.g. a journal the university doesn't subscribe to), and since papers are processed in DOI order, such articles come in runs. Before skipping the API, the script requests one paper that worked earlier in the run: if it still works, the refusals stay single failed papers and the run goes on (log: `… refused 8 papers in a row, but a paper that worked before still works`); if not (VPN off, key revoked), the API is skipped as before. The 403s still slow the API down. In Phase A, 58 hosts were skipped this way, among them `downloads.hindawi.com`, `onlinelibrary.wiley.com` and `www.sciencedirect.com`.
- **PDF folder check:** `run`, `verify`, `mark-incomplete` and `rename` first count how many of the PDFs the database expects are really in `--out`. If fewer than 90% are there (once at least 20 are expected), they stop with `STOPPED: only N of M PDFs …` and change nothing. This protects against a wrong `--out` path and against a Nextcloud/OneDrive folder with *virtual files* that looks empty while its sync client is not running (this happened once). If the folder really is meant to be new or empty, add `--skip-folder-check`.
- **Long pauses requested by a server:** a 429/5xx answer with `Retry-After` up to `MAX_RETRY_AFTER` (120 s) is respected by pausing that host. If a publisher or repository site asks for a longer pause (for example "503, Retry-After: 3600"), it is skipped for the rest of the run instead, so its papers don't hold up the whole run; they stay `failed` and can be retried later. If one of the APIs themselves (Unpaywall, OpenAlex, Crossref, Elsevier, Wiley) asks for a longer pause, which usually means a quota is used up, the run **stops cleanly** with a `STOPPED EARLY` message and exit code 3; the papers not reached yet keep their status, so running the same command later simply continues.
- **Statuses:**
  - `done`: the PDF was saved
  - `not_found`: no source had a PDF link
  - `failed`: a link existed but the download failed, or an index lookup failed (the reason is in the `error` column)
  - `incomplete`: the only PDF we have is a retraction notice or the first page (kept as `<ID> [notice] - <title>.pdf` / `<ID> [first page] - <title>.pdf`, see `mark-incomplete`)

## 6. Tests

```bash
python tests/test_fetch_pdfs.py
```

The tests run offline against a small local web server that plays Unpaywall and some publisher sites. They check the file naming, the classification of failures, that a Cloudflare-blocked site gets exactly 8 requests and is then skipped, that API keys are not forwarded across redirects, that PDFs land in their ID-block folder, both kinds of long `Retry-After` (site skipped / run stopped), reading `.env`, Elsevier (XML, abstract-only answers rejected, notice-only answers kept as `[notice]`) and Wiley downloads through fake APIs (Hindawi included, Cochrane never sent, SICI DOIs with `%3c` not escaped twice), that `verify` leaves out manual decisions and XML files, that a rejected key or a used-up quota stops the run without marking papers as failed, that papers no source can handle stay untouched, that the commands stop when most PDFs are missing from the folder, `mark-incomplete` with a later `--retry-incomplete`, and the `verify` verdicts on small generated PDFs. Run them after every change to the script.
