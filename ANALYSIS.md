# Retracted-papers PDF download: analysis report

*Status: 2 October 2026. Phase A (open access) is complete. Phase B (publisher TDM APIs) is waiting for API tokens from the library.*

## 1. Summary

- The Retraction Watch list has **63,790 unique DOIs** (72,790 rows; 5,950 rows have no usable DOI).
- **Phase A downloaded 7,005 PDFs (11.0%, 17.1 GB)** from open-access sources in 3 h 24 min, with no crashes and no API errors. 56,785 papers are still missing.
- Of the missing papers, **35,367 (62%) have no open-access copy at all**, and **19,811 (35%) have an open-access link, but the publisher's site refused the download**, mostly through Cloudflare or similar bot protection.
- The biggest single group, **Hindawi (11,749 missing, 21% of all missing papers)**, is open access (CC-BY), but its download server is behind a Cloudflare bot check. The legal way to get these papers is the Wiley TDM API; Hindawi is now part of Wiley.
- Most of the remaining papers can only be obtained legally through the publishers' text-and-data-mining (TDM) APIs. That needs tokens arranged through the university library. The per-publisher list for the library is in `reports/missing_by_publisher.csv`.

## 2. Input data

| | Count |
|---|---|
| Rows in `retraction_watch_1.10.26 - short-version.csv` | 72,790 |
| Unique DOIs | 63,790 |
| DOIs shared by several Retraction Watch entries | 2,524 |
| Rows without a usable DOI (empty or "Unavailable") | 5,950 |
| Different DOI prefixes (publishers) | 932 |

Largest publishers (by DOI prefix):

| Prefix | Publisher | DOIs | Legal route |
|---|---|---|---|
| 10.1155 | Hindawi (Wiley) | 11,801 | Open access, but download server blocks bots → Wiley TDM API |
| 10.1016 | Elsevier | 8,169 | Elsevier Article Retrieval API (API key + institutional token) |
| 10.1109 | IEEE | 7,797 | No public TDM PDF API → library arrangement |
| 10.1007 | Springer | 6,717 | Partly open access; the rest via library / Springer Nature TDM |
| 10.1002 | Wiley | 2,352 | Wiley TDM API |
| 10.3233 | IOS Press | 1,730 | Library |
| 10.1371 | PLOS | 1,682 | Open access, downloads work |
| 10.1080 | Taylor & Francis | 1,529 | Library |
| 10.1177 | SAGE | 1,368 | Library |
| 10.1111 | Wiley | 1,357 | Wiley TDM API |
| 10.1088 | IOP Publishing | 1,278 | Partly open access; IOP site returns HTML instead of PDFs |
| 10.1038 | Nature | 1,121 | Partly open access |
| 10.1186 | BMC (Springer Nature) | 1,097 | Open access, downloads work |

## 3. Test results (400 random DOIs, open-access sources only)

| Status | Count | Share |
|---|---|---|
| `done` (PDF saved) | 49 | 12% |
| `not_found` (no open-access PDF in Unpaywall/OpenAlex) | 219 | 55% |
| `failed` (PDF link exists, download refused) | 132 | 33% |

**Quality check:** for the first 13 PDFs, the title and DOI were compared with the text of each PDF. All matched. One file is a full 542-page conference supplement that contains the paper's abstract; it is the correct document, but a whole issue.

**Per publisher in the sample:**

| Prefix | Sample | Done | Not found | Failed | Comment |
|---|---|---|---|---|---|
| 10.1155 Hindawi | 70 | 0 | 1 | 69 | All blocked by Cloudflare |
| 10.1016 Elsevier | 54 | 0 | 44 | 10 | ScienceDirect refuses direct downloads |
| 10.1109 IEEE | 51 | 1 | 50 | 0 | Closed access |
| 10.1007 Springer | 35 | 7 | 27 | 1 | |
| 10.1371 PLOS | 9 | 9 | 0 | 0 | Works fully |
| 10.1051 EDP (E3S conferences) | 8 | 0 | 0 | 8 | Host returns 403 |

**Reasons for failures (132 papers):**

| Reason | Papers |
|---|---|
| Cloudflare bot challenge or host blocked for the run | 77 |
| HTTP 403 without a challenge page (some are Hindawi, from before the labelling was added) | 43 |
| HTML page instead of the PDF (iopscience, PMC, Thieme, Springer) | 11 |
| HTTP 404 | 1 |

Hosts that refused systematically: `downloads.hindawi.com`, `onlinelibrary.wiley.com`, `www.e3s-conferences.org`. Other hosts refused occasionally: OUP, Taylor & Francis, Cell, RSC, MDPI, ScienceDirect, BMJ, ACS.

**Where the 49 PDFs came from:** PLOS, Springer/BMC, Frontiers, Nature, Spandidos, Cureus, SciELO and others. All of them were found via Unpaywall. OpenAlex never found a PDF that Unpaywall did not already list, but it is kept as a fallback.

**Not-found papers:** 39 of the first 51 checked were closed access. 11 were open access, but only as a web page without a direct PDF link (getting those would mean scraping publisher pages, which we do not do).

**Alternatives checked for blocked papers:**

- Europe PMC's PDF endpoint is also behind Cloudflare, and NCBI's old OA service has been retired.
- NCBI's official PMC bulk copy on AWS S3 has no PDF for most retracted papers (1 of 20 checked).

## 4. Phase A results (full run, 2 October 2026)

Run: 01:31–04:54 (3 h 24 min), average 311 DOIs/min, sources Unpaywall and OpenAlex, 16 parallel workers, polite per-host rate limits.

| Status | Papers | Share |
|---|---|---|
| Downloaded | 7,005 | 11.0% |
| Not found (no open-access copy) | 35,367 | 55.4% |
| Failed (open-access link exists, download refused) | 21,418 | 33.6% |

Output: 7,005 PDFs, 17.1 GB (median 1.5 MB, largest 48 MB), named `<RW ID> - <title>.pdf`, plus `index.csv`. Files on disk and the database agree, and there are no half-finished downloads. 6,957 PDFs were found via Unpaywall and 48 via OpenAlex.

**Main reasons for the 56,785 missing PDFs:**

| Reason | Papers | What can be done |
|---|---|---|
| Closed access (no open-access copy) | 35,367 | Publisher TDM APIs / library |
| Blocked by bot protection (Cloudflare) | 15,930 | TDM APIs (Wiley incl. Hindawi, Elsevier); never bypassed |
| HTML page instead of PDF (other bot checks, e.g. Radware on IOP) | 2,040 | TDM APIs / library |
| Refused by site (HTTP 401/403/429) | 1,841 | TDM APIs / library |
| Network error / timeout | 726 | Retry later with `--retry-failed` |
| Broken link (HTTP 404/410) | 659 | Mostly lost unless the publisher provides it |
| Other (e.g. HTTP 5xx, file too small) | 115 | Retry later |
| TLS certificate error on the site | 107 | Not bypassed (certificate checks stay on) |

**Sites that refused the most papers** (58 sites were skipped after 8 refusals in a row):

| Site | Papers | Notes |
|---|---|---|
| downloads.hindawi.com | 10,875 | Cloudflare challenge |
| onlinelibrary.wiley.com | 2,100 | Cloudflare challenge |
| validate.perfdrive.com | 1,172 | Radware bot check in front of IOP Publishing |
| www.spandidos-publications.com | 633 | Worked at first, then refused |
| www.e3s-conferences.org | 585 | HTTP 403 |
| www.dovepress.com | 545 | |
| www.sciencedirect.com, linkinghub.elsevier.com, www.cell.com | 1,043 | Elsevier, covered by the Elsevier API |
| www.mdpi.com | 476 | Fully open access, but blocks automated downloads |
| www.tandfonline.com | 411 | Cloudflare challenge |
| academic.oup.com | 328 | Cloudflare challenge |

**Missing PDFs by publisher (top 15).** The full table, with reasons per publisher, is in `reports/publisher_summary.csv`:

| Prefix | Publisher | Missing | of | Legal route |
|---|---|---|---|---|
| 10.1155 | Hindawi | 11,749 | 11,801 | Wiley TDM API |
| 10.1016 | Elsevier | 8,071 | 8,169 | Elsevier API (key + institutional token) |
| 10.1109 | IEEE | 7,770 | 7,797 | Library arrangement |
| 10.1007 | Springer | 5,528 | 6,717 | Springer Nature TDM via library |
| 10.1002 | Wiley | 2,327 | 2,352 | Wiley TDM API |
| 10.3233 | IOS Press | 1,725 | 1,730 | Library |
| 10.1080 | Taylor & Francis (Informa) | 1,523 | 1,529 | Library |
| 10.1177 | SAGE | 1,362 | 1,368 | Library |
| 10.1111 | Wiley | 1,350 | 1,357 | Wiley TDM API |
| 10.1088 | IOP Publishing | 1,268 | 1,278 | Library |
| 10.1051 | EDP Sciences | 769 | 772 | Library |
| 10.3892 | Spandidos | 668 | 981 | Library / retry later |
| 10.2147 | Dove Medical Press (Informa) | 569 | 581 | Library |
| 10.1093 | Oxford University Press | 539 | 557 | Library |
| 10.3390 | MDPI | 512 | 519 | Open access; ask MDPI or library |

Wiley (incl. Hindawi) and Elsevier together account for **23,497 missing papers (41%)**, and both have official TDM APIs. IEEE, Springer Nature, T&F, SAGE and IOS Press need a library arrangement.

## 5. Changes made to `fetch_pdfs.py`

| Change | Why |
|---|---|
| A failed index lookup is now `failed` (with the reason), not `not_found` | Before, papers hit by a temporary API error were silently treated as "no PDF exists" and not retried |
| Wiley TDM rate limit: 1/s → 1 per 10 s | Wiley allows at most 60 requests per 10 minutes; the old setting broke that rule |
| Crossref rate limit: 5/s → 3/s | Crossref allows at most 3 requests at the same time |
| Redirects are followed one hop at a time through the rate limiter | Links via doi.org or repositories redirected to publisher hosts without that host's rate limit |
| API keys are not forwarded when a redirect leads to another host | Prevents leaking the Elsevier/Wiley keys |
| Hosts that refuse 8 downloads in a row are skipped for the rest of the run, with a warning in the log | Without this, the Hindawi refusals slowed the whole run from ~370 to ~50 papers/min. Skipping also sends fewer requests to hosts that do not want them |
| Warning in the log when a host keeps pushing back | So that repeated 403/429 errors are visible |
| Cloudflare blocks are labelled in the error column | To group failures by cause |
| New file names: `<RW ID> - <title>.pdf` (ID zero-padded to 6 digits) | The folder sorts by Retraction Watch ID, every name is unique, and the title is still readable |
| New `index.csv` in the PDF folder, and `index` and `rename` commands | One table of all 69,740 entries (sorted by ID) with DOI, publisher, file name and status. It opens in Excel |
| New `summary` command: `publisher_summary.csv` and `missing_by_publisher.csv` | Missing papers grouped by publisher (names from Crossref), with one main reason per paper, for the library request |

All changes were tested: the bug fixes and blocked-host handling against a local mock server and the real APIs, and the renaming on a copy of the data first. A fresh import produces exactly the same file names as the rename.

Things that were deliberately **not** done: no browser automation (e.g. Puppeteer), no getting past Cloudflare or CAPTCHAs, no logging in with the university account. Publisher licences forbid this, and it could get the university's IP range blocked.

## 6. Next steps

| Phase | Source | Result / expected | Needs |
|---|---|---|---|
| A | Unpaywall + OpenAlex (open access) | **done: 7,005 PDFs (11%)** | – |
| A (retry) | same, `--retry-failed` in a few days | up to ~800 (timeouts, other errors) | nothing |
| B | Wiley TDM (incl. Hindawi, if Wiley serves 10.1155) | up to ~15,400 | Wiley TDM token |
| B | Elsevier API | up to ~8,000 | Elsevier API key + institutional token |
| C | Crossref full-text links | depends on licences | library approval, university network |
| – | IEEE, Springer Nature, T&F, SAGE, IOS Press … | – | library arrangement |

With the Wiley and Elsevier tokens, roughly half of the list looks reachable.

**Storage:** Phase A produced 17.1 GB (median PDF 1.5 MB). The whole list would be about 140 GB, so check the quota on cloud.ovgu.de. Zipping the PDFs saves only about 13% (they are already compressed internally) and would make single files impossible to browse in the cloud, so the PDFs are uploaded as they are.

**Open items:**

1. Send `reports/missing_by_publisher.csv` and `reports/publisher_summary.csv` to the university library with the TDM request (Elsevier, Wiley/Hindawi, Springer Nature, IEEE).
2. Test whether the Wiley TDM API serves Hindawi DOIs (10.1155) as soon as a token is available.
3. Upload the PDFs to cloud.ovgu.de (Nextcloud desktop client recommended).
