# Retracted-papers PDF downloader

`fetch_pdfs.py` downloads the PDFs for the DOIs in the Retraction Watch CSV and names each file after the paper's title. It uses only legal channels: open-access indexes and the publishers' official text-and-data-mining (TDM) APIs. It never logs in to your university account.

**About your CSV:** it has 72,790 rows, which become 63,790 unique DOIs after cleaning. 5,950 rows have no usable DOI; they're kept in the database (table `no_doi`) so you can handle them by hand.

## 1. Setup (on the cloud server)

```bash
python3 -m venv venv && source venv/bin/activate
pip install httpx
python fetch_pdfs.py import "retraction_watch_1.10.26 - short-version.csv"
```

This creates `papers.sqlite`, which stores the status of every paper. Keep it next to the script.

## 2. Run in phases

Run it inside `tmux` or with `nohup` so it keeps going after you log out. You can press Ctrl+C at any time, and running the same command again resumes where it stopped.

**Quick test first:**

```bash
python fetch_pdfs.py run --email you@uni.de --out /data/retracted_pdfs --limit 100
python fetch_pdfs.py report
```

**Phase A: open access (works anywhere, no keys needed).**

```bash
python fetch_pdfs.py run --email you@uni.de --out /data/retracted_pdfs --sources unpaywall,openalex
```

**Phase B: publisher TDM APIs** (once you have the keys, see section 3):

```bash
export ELSEVIER_API_KEY=...        # https://dev.elsevier.com
export ELSEVIER_INSTTOKEN=...      # from your library, or run from the uni network
export WILEY_TDM_TOKEN=...         # https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining
python fetch_pdfs.py run --email you@uni.de --out /data/retracted_pdfs \
    --sources elsevier,wiley --retry-not-found --retry-failed
```

**Phase C: Crossref full-text links.** Only run this if your library agrees, and only from a server on the university network or VPN, so the publisher recognises your subscription:

```bash
python fetch_pdfs.py run --email you@uni.de --out /data/retracted_pdfs \
    --sources crossref --retry-not-found --retry-failed
```

**Useful options:**

- `--prefix 10.1155` processes one publisher only. Here, 10.1155 is Hindawi.
- `--concurrency 16` sets how many papers are processed in parallel.
- `-v` shows detailed lookup errors.

## 3. Getting access to the paywalled papers

Ask your library for TDM access. Here is a short email you can adapt:

> For a research project on retracted literature I need the full texts of ~64,000 retracted articles (list attached, DOIs). I'd like to obtain them via the publishers' TDM APIs (Elsevier, Wiley, Springer Nature, IEEE) under §60d UrhG rather than by manual downloading. Can you provide an Elsevier institutional token / confirm our TDM entitlements, and advise for IEEE and Springer Nature?

Attach the files made by

```bash
python fetch_pdfs.py summary --out-dir reports --email you@uni.de
```

`reports/missing_by_publisher.csv` lists every missing DOI grouped by publisher (names looked up at Crossref) with the main reason it is missing. `reports/publisher_summary.csv` gives one row per publisher with counts per reason and the suggested legal route. The table shows which DOIs belong to which publisher and how many are still missing, measured before Phase A:

| DOI prefix | Publisher | Missing before Phase A | Route |
|---|---|---|---|
| 10.1155 | Hindawi | 11,778 | Open access, handled in Phase A |
| 10.1016 | Elsevier | 8,157 | Elsevier API (key + insttoken) |
| 10.1109 | IEEE | 7,785 | Library arrangement; no public TDM PDF API |
| 10.1007 / 10.1186 | Springer Nature | ~7,800 | BMC is open access; the rest via the library or Crossref links |
| 10.1002 / 10.1111 | Wiley | ~3,700 | Wiley TDM token |

## 4. Saving to cloud storage

Point `--out` at a folder that syncs to your cloud. The easiest way is [rclone](https://rclone.org), which supports Google Drive, Nextcloud/WebDAV, OneDrive, S3 and others:

```bash
rclone config                                   # one-time: add a remote called "cloud"
# Option 1: download locally, then sync from time to time (most robust)
rclone copy /data/retracted_pdfs cloud:RetractedPapers --progress
# Option 2: mount the cloud folder and write into it directly
rclone mount cloud:RetractedPapers /mnt/cloud --vfs-cache-mode writes &
python fetch_pdfs.py run ... --out /mnt/cloud
```

Option 1 is better for 64,000 files.

## 5. How it works

- **File names:** `<RW ID> - <title>.pdf`, e.g. `001454 - Circulatory Responses to Laryngeal Mask Airway Insertion ….pdf`. The Retraction Watch ID is zero-padded to 6 digits so the folder sorts by ID, and it makes every name unique. If several Retraction Watch entries share one DOI, the smallest ID is used (all IDs are listed in `index.csv`). The title has characters like `/ : ? *` removed and is cut to a maximum of 200 bytes.
- **`index.csv`:** written into the PDF folder after every `run` (or with `python fetch_pdfs.py index --out <folder>`). One row per Retraction Watch entry, sorted by ID: `rw_id, all_rw_ids, doi, doi_prefix, title, filename, status, source, pdf_url, error`. It includes the papers that are still missing and the rows without a DOI (`status = no_doi`), so you can filter it in Excel. It is saved as UTF-8 with BOM so Excel shows special characters correctly.
- **Renaming after a naming change:** `python fetch_pdfs.py rename --out <folder> --dry-run` shows what would change; without `--dry-run` it renames the PDFs and updates the database. It never deletes anything, and if a rename fails it undoes the renames it already made.
- **No fake PDFs:** a file is saved only if its content really starts with `%PDF`. HTML login pages are rejected and logged as `not a PDF`.
- **Polite rate limits:** each server gets its own speed limit (`HOST_RPS` and `DEFAULT_RPS` at the top of the script). Publisher sites get one request every 2 seconds; the Wiley TDM API one every 10 seconds (its limit is 60 per 10 minutes). Redirects are followed one hop at a time, so the limit applies to the server that actually answers, and API keys are never forwarded to another host. When a site answers 429 or 403, the script slows down for that site and speeds up again once requests succeed; a line starting with `! host … keeps pushing back` appears in the log.
- **Blocked hosts:** if a host refuses `BLOCK_AFTER` (8) downloads in a row (403/429, a Cloudflare "Just a moment…" challenge, or an HTML page instead of a PDF), it is skipped for the rest of the run and the log shows `! host … skipping it for the rest of this run`. Its papers are marked `failed` with `skipped: … blocked for this run`, so `--retry-failed` (or Phase B) can pick them up later. The script never tries to get past such a block. In testing, `downloads.hindawi.com`, `onlinelibrary.wiley.com` and `www.e3s-conferences.org` were blocked this way.
- **Statuses:**
  - `done`: the PDF was saved
  - `not_found`: no source had a PDF link
  - `failed`: links existed but the download failed (the reason is in the `error` column)
- **Speed:** looking up all DOIs in the open-access indexes takes a few hours. Downloads are spread over many different servers in parallel, so they run alongside the lookups. Expect Phase A to finish within roughly a day.
