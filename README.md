# Retracted-papers PDF downloader

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

**Phase B: publisher TDM APIs** (once you have the keys, see section 3):

```bash
export ELSEVIER_API_KEY=...        # https://dev.elsevier.com
export ELSEVIER_INSTTOKEN=...      # from your library, or run from the uni network
export WILEY_TDM_TOKEN=...         # https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining
python fetch_pdfs.py run --email you@uni.de --out /data/retracted_pdfs \
    --sources elsevier,wiley --retry-not-found --retry-failed
```

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
| `rename --out <folder> [--dry-run]` | Rename existing PDFs after a change of the naming scheme |

## 3. Getting access to the paywalled papers

Ask your library for TDM access. Here is a short email you can adapt:

> For a research project on retracted literature I need the full texts of ~64,000 retracted articles (list attached, DOIs). I'd like to obtain them via the publishers' TDM APIs (Elsevier, Wiley, Springer Nature, IEEE) under §60d UrhG rather than by manual downloading. Can you provide an Elsevier institutional token / confirm our TDM entitlements, and advise for IEEE and Springer Nature?

Attach the files made by

```bash
python fetch_pdfs.py summary --out-dir reports --email you@uni.de
```

`reports/missing_by_publisher.csv` lists every missing DOI grouped by publisher (names looked up at Crossref) with the main reason it is missing. `reports/publisher_summary.csv` gives one row per publisher with counts per reason and the suggested legal route. If `verify` has been run, PDFs it found to be only a retraction notice or a first page count as missing (reason `PDF is only a retraction notice or first page`, status `pdf_incomplete`), because the full article still has to be obtained.

Still missing after Phase A (largest publishers):

| DOI prefix | Publisher | Missing | Route |
|---|---|---|---|
| 10.1155 | Hindawi | 11,749 | Open access, but the download site blocks bots → Wiley TDM API |
| 10.1016 | Elsevier | 8,071 | Elsevier API (key + institutional token) |
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
- **Blocked hosts:** if a host refuses `BLOCK_AFTER` (8) downloads in a row (403/429, a Cloudflare "Just a moment…" challenge, or an HTML page instead of a PDF), it is skipped for the rest of the run and the log shows `! host … skipping it for the rest of this run`. Its papers are marked `failed` with `skipped: … blocked for this run`, so `--retry-failed` (or Phase B) can pick them up later. The script never tries to get past such a block. In Phase A, 58 hosts were skipped this way, among them `downloads.hindawi.com`, `onlinelibrary.wiley.com` and `www.sciencedirect.com`.
- **Long pauses requested by a server:** a 429/5xx answer with `Retry-After` up to `MAX_RETRY_AFTER` (120 s) is respected by pausing that host. If a server asks for a longer pause (for example "503, Retry-After: 3600"), the host is skipped for the rest of the run instead, so its papers don't hold up the whole run; they stay `failed` and can be retried later.
- **Statuses:**
  - `done`: the PDF was saved
  - `not_found`: no source had a PDF link
  - `failed`: a link existed but the download failed, or an index lookup failed (the reason is in the `error` column)
