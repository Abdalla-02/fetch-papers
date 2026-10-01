# Retracted-papers PDF download: analysis report

*Status: 2 October 2026. Steps 1–3 done (setup, smoke test, tuning). The full Phase A run has not started yet.*

## 1. Summary

- The Retraction Watch list has **63,790 unique DOIs** (72,790 rows; 5,950 rows have no usable DOI).
- The downloader was tested against the real APIs on a random sample of **400 DOIs**. Result: **49 PDFs (12%)** downloaded, 219 (55%) have no open-access PDF, and 132 (33%) have a PDF link but the publisher's site refused the download.
- **Open access alone will give roughly 7,000–8,000 PDFs** (about 12%). Most of the remaining papers can only be obtained legally through the publishers' text-and-data-mining (TDM) APIs. That needs tokens arranged through the university library.
- The biggest single group, **Hindawi (11,801 DOIs, 18% of the list)**, is open access (CC-BY), but its download server is behind a Cloudflare bot check. The legal way to get these papers is the Wiley TDM API; Hindawi is now part of Wiley.

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

## 4. Changes made to `fetch_pdfs.py`

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

All changes were tested: the bug fixes and blocked-host handling against a local mock server and the real APIs, and the renaming on a copy of the data first. A fresh import produces exactly the same file names as the rename.

Things that were deliberately **not** done: no browser automation (e.g. Puppeteer), no getting past Cloudflare or CAPTCHAs, no logging in with the university account. Publisher licences forbid this, and it could get the university's IP range blocked.

## 5. Expectations and next steps

| Phase | Source | Expected PDFs | Needs |
|---|---|---|---|
| A | Unpaywall + OpenAlex (open access) | ~7,000–8,000 (≈12%), about 3–5 hours | nothing |
| B | Wiley TDM (incl. Hindawi, if Wiley serves 10.1155) | up to ~15,000 | Wiley TDM token |
| B | Elsevier API | up to ~8,000 | Elsevier API key + institutional token |
| C | Crossref full-text links | depends on licences | library approval, university network |
| — | IEEE, T&F, SAGE, IOS Press … | — | library arrangement |

With the TDM tokens, roughly half of the list looks reachable. IEEE (7,797) has no public TDM PDF API and needs a library arrangement.

**Storage:** the PDFs average about 2.2 MB, so Phase A needs about 17 GB and the whole list about 140 GB. Check the quota on cloud.ovgu.de before the full run, and keep the output folder outside OneDrive.

**Open items:**

1. Decide where the full Phase A run happens (this PC or a server).
2. Request TDM access from the library (Elsevier, Wiley/Hindawi, Springer Nature, IEEE). After Phase A, the missing DOIs will be exported grouped by publisher.
3. Test whether the Wiley TDM API serves Hindawi DOIs (10.1155) as soon as a token is available.
