# Retracted-papers PDF download: analysis report

*Status: 29 October 2026 (week 3). Phase A (open access) and a retry of temporary failures are complete, and every PDF has been checked. The Elsevier API key and the Wiley TDM token are in place and were tested on 29 October (section 8); the full Phase B run is next.*

## 1. Summary

- The Retraction Watch list has **63,790 unique DOIs** (72,790 rows; 5,950 rows have no usable DOI).
- **Phase A downloaded 7,005 PDFs (11.0%, 17.1 GB)** from open-access sources in 3 h 24 min, with no crashes and no API errors. A retry one week later added 172 (7,177 in total).
- **Quality check (week 2): 1,146 of these PDFs are only the retraction notice or the article's first page**, not the article. So **6,031 papers (9.5%) have a full-text PDF**; 57,759 are still missing (see section 5).
- Of the 57,759 missing papers, **35,367 (61%) have no open-access copy at all**, **19,836 (34%) have an open-access link, but the publisher's site refused the download**, mostly through Cloudflare or similar bot protection, and 1,146 (2%) have only a notice / first page as PDF.
- The biggest single group, **Hindawi (11,757 missing, 20% of all missing papers)**, is open access (CC-BY), but its download server is behind a Cloudflare bot check. Hindawi is now part of Wiley, and a test on 29 October confirmed that the Wiley TDM API delivers these papers as full PDFs.
- Most of the remaining papers can only be obtained legally through the publishers' text-and-data-mining (TDM) APIs. The API keys are requested directly from the publishers first; the university library is asked only for what they don't cover. The per-publisher list of missing papers is in `reports/missing_by_publisher.csv`.

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
| 10.1016 | Elsevier | 8,169 | Elsevier Article Retrieval API (API key, from the university network) |
| 10.1109 | IEEE | 7,797 | No public TDM PDF API → library arrangement |
| 10.1007 | Springer | 6,717 | Partly open access; the rest via Springer Nature TDM or the library |
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

Output: 7,005 PDFs, 17.1 GB (median 1.5 MB, largest 48 MB), stored as `<ID block>/<RW ID> - <title>.pdf` in 74 subfolders of 1,000 IDs each, plus `index.csv`. Files on disk and the database agree, and there are no half-finished downloads. 6,957 PDFs were found via Unpaywall and 48 via OpenAlex.

The PDFs and `index.csv` are in the shared Nextcloud folder (`Retracted_Papers`) and are uploaded by the Nextcloud desktop client. The database, logs and reports stay on the local PC, outside the synced folder. After Phase A the PDFs were moved into subfolders of 1,000 Retraction Watch IDs (currently 10–306 PDFs each, at most 1,000 when complete) so folders open quickly, and the title part of each name was cut to 150 characters. This brought the longest full path down to 243 characters, under the Windows limit of 260 (before, 241 files exceeded it).

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
| 10.1016 | Elsevier | 8,071 | 8,169 | Elsevier API key (from the university network) |
| 10.1109 | IEEE | 7,770 | 7,797 | Library arrangement |
| 10.1007 | Springer | 5,528 | 6,717 | Springer Nature TDM or library |
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

## 5. Week 2: retry and quality check

**Retry of temporary failures** (`--retry-temporary`): the 841 papers that had failed with timeouts, network or server errors were tried again one week later. 172 more PDFs were downloaded (7,177 in total). 669 still failed; 495 of them are Spandidos Publications papers, whose server did not accept connections at all (it had refused downloads in Phase A too), so no further attempts were made there.

During this run, `riviste.unimi.it` answered "503, Retry-After: 3600". The script obeyed literally and waited an hour per attempt, which stalled the end of the run. Fixed: a server asking for more than `MAX_RETRY_AFTER` (120 s) is now skipped for the rest of the run.

**Quality check of every PDF** (`verify`): the first three pages of each PDF are compared with the paper's title and DOI. Result for 7,177 PDFs:

| Result | PDFs | Meaning |
|---|---|---|
| ok | 5,936 | Title or DOI found: the expected paper |
| notice | 948 | 1–2 pages that read like a retraction notice: the link gave the notice, not the article |
| short | 198 | 1–2 pages, not a notice: mostly only the first page of the article with a "RETRACTED ARTICLE" stamp |
| mismatch | 54 | Neither title nor DOI found: often a different document, sometimes a paper in another language |
| no_text | 28 | Scanned PDF without a text layer |
| check | 13 | Title only partly found |
| unreadable | 0 | (encrypted PDFs are read with the `cryptography` package) |

So **1,146 PDFs (16%) are not the full article**. Some publishers replace retracted articles with the notice or a stamped first page, and the open-access indexes link to that file; Springer (852 of its 1,189 PDFs) is by far the largest source. A spot check of randomly chosen files confirmed this: of 23 files marked `notice` or `short`, at least 19 were clearly not the full article; of 8 `mismatch` files, about half were clearly a different document. With these counted as missing, **6,031 papers (9.5%) have a full-text PDF**.

The verdicts are stored in the database (table `checks`), shown in `index.csv` (column `pdf_check`) and listed in `reports/verify.csv`. `summary` counts the notice/first-page PDFs as missing, so the library list includes them.

## 6. Changes made to `fetch_pdfs.py`

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
| New file names: `<ID block>/<RW ID> - <title>.pdf` (ID zero-padded to 6 digits, title cut to 150 characters, subfolders of 1,000 IDs) | Everything sorts by Retraction Watch ID, every name is unique, the title is still readable, folders stay small enough to open quickly, and paths stay under Windows' 260-character limit |
| New `index.csv` in the PDF folder, and `index` and `rename` commands | One table of all 69,740 entries (sorted by ID) with DOI, publisher, file name and status. It opens in Excel |
| New `verify` command (week 2): checks every PDF against its title and DOI; verdicts stored in table `checks`, column `pdf_check` in `index.csv` and `reports/verify.csv` | Found 1,146 PDFs that are only a retraction notice or first page, and 54 that are probably a different document |
| `summary` counts notice / first-page-only PDFs as missing (status `pdf_incomplete`); column `downloaded` renamed to `full_text_pdfs` | The library list must include papers whose full text is still missing |
| New option `run --retry-temporary` (week 2) | Retries only timeouts, network and server errors, without contacting the sites that blocked us again |
| A site asking for a pause (`Retry-After`) longer than 120 s is skipped for the rest of the run; if one of the APIs asks for it (e.g. a quota), the run stops cleanly and leaves the remaining papers untouched (week 2) | A server answering "503, Retry-After: 3600" stalled the retry run for hours; skipping an API instead would have marked every remaining paper as failed |
| Phase B preparation (week 3): API keys from a `.env` file (`.env.example` in the repo), `--wiley-prefixes` (Hindawi `10.1155` included since the test on 29 October), status `incomplete` with `mark-incomplete` and `--retry-incomplete`, Windows template `windows/run_phase_b.cmd` | Phase B can start as soon as the keys arrive; notice-only papers get a second chance through the APIs while the notice files are kept |
| A rejected API key (HTTP 401) or an API still answering 429 after retries stops the run; papers that no selected source can handle are not touched (week 3) | A wrong key or a used-up quota must not turn thousands of papers into 'failed', and a Phase B run must not overwrite the Phase A reasons of papers it cannot handle |
| After the Phase B test (week 3): Elsevier full texts saved as XML (an abstract-only answer is not kept); Cochrane reviews never sent to the Wiley API; old SICI DOIs stored with `%3c`/`%3e` no longer escaped twice; `verify` leaves out PDFs decided by hand (check note `manual check …`) and XML files | Elsevier sends the PDF only as its first page, but the full text as XML; 4 of the 6 Wiley failures in the test were Cochrane reviews (403), and 8 refusals in a row would get the whole Wiley API skipped; running `verify` after Phase B would have reset the 21 manually confirmed papers to `mismatch` |
| Elsevier XML that is only the retraction notice (< 1,000 words, notice wording at the start) is kept as `<ID> [notice] - <title>.xml` with status `incomplete` (week 3, PR #8) | In the Elsevier test, 4 of 19 XML answers were only the notice and had been counted as full texts |
| Before Elsevier or Wiley is skipped after 8 refusals in a row, the paper that worked last in the run is requested once more; if it still works, the run goes on. `run_phase_b.cmd elsevier` / `wiley` runs one API with its own log (week 3, PR #9) | In the full run, Elsevier was skipped after 41 papers because 8 articles in a row were from journals without a licence (403); the key still worked |
| XML check extended: "REMOVED:" / "has been removed" / "RETRAIT :" also count as a notice; an XML with less than 2,000 characters of text is kept as `[short]` (status `incomplete`); `verify` checks XML files too and `mark-incomplete` marks them. A success redirected to another host (Wiley sends every PDF from a second host) now also resets the API's refusal counter and slow-down (week 3, PR #10) | After the Elsevier run, 161 of 5,317 XML "full texts" were removed-article notices, pre-proof cover pages, corrections or single first pages. The Wiley run was skipped after 8 scattered 403s over two hours, because the successes were counted for the redirect host only |
| A file error for one paper (e.g. the Nextcloud folder timing out) leaves that paper as it was and the run goes on; 20 in a row stop the run. If nothing has worked yet in a run, the access check before skipping Elsevier/Wiley uses a paper the API delivered in an earlier run. `--retry-incomplete` no longer sends a paper to the Elsevier/Wiley API that itself sent the notice (week 3, PR #11) | On 30 October one Nextcloud timeout (`WinError 426`) ended the Wiley run after 3,000 of 13,000 papers. The restart retried the old 403 failures first, so its first 8 papers were all refused before any had worked; with no paper to check access with, Wiley was skipped and the remaining 10,400 papers were marked failed. The night before, the restart had also asked Wiley again for the 37 notices it had sent the day before, and saved each one a second time as if it were the article |
| `verify` warns about files renamed to a Windows short name like `049929~1.PDF` (week 3) | The Nextcloud client renamed one PDF this way |
| PDF folder check before `run`, `verify`, `mark-incomplete`, `rename` (stop if < 90% of the expected PDFs are on disk; `--skip-folder-check` overrides) (week 3) | On 2026-10-16 the Nextcloud folder looked empty while the client (virtual files) was closed; a run would then have downloaded everything again and `rename` would have updated the database for files it could not see |
| Offline test suite `tests/test_fetch_pdfs.py` (week 2) | The checks done so far by hand (blocking, no key leak, Retry-After, subfolders, verify) can be rerun after every change |
| New `summary` command: `publisher_summary.csv` and `missing_by_publisher.csv` | Missing papers grouped by publisher (names from Crossref), with one main reason per paper, for the library request |

All changes were tested: the bug fixes, blocked-host and Retry-After handling against a local mock server and the real APIs; the renaming, the `checks` table and `summary` on a copy of the data first; the `verify` verdicts by reading samples of the flagged PDFs. A fresh import produces exactly the same file names as the rename.

Things that were deliberately **not** done: no browser automation (e.g. Puppeteer), no getting past Cloudflare or CAPTCHAs, no logging in with the university account. Publisher licences forbid this, and it could get the university's IP range blocked.

## 7. Next steps

| Phase | Source | Result / expected | Needs |
|---|---|---|---|
| A | Unpaywall + OpenAlex (open access) | **done: 7,005 PDFs (11%)** | – |
| A (retry) | same, `--retry-temporary` | **done: 172 more PDFs** (7,177 in total; 1,146 of them only a notice / first page) | – |
| B | Wiley TDM (incl. Hindawi) | **tested: 14 of 20 Wiley + 2 of 2 Hindawi as full PDFs**; up to ~14,900 (Cochrane excluded) | Wiley TDM token (in place) |
| B | Elsevier API | **tested: full text as XML (the PDF is only the first page)**; up to ~8,100 | Elsevier API key (in place), university network or full-tunnel VPN |
| C | Crossref full-text links | depends on licences | library approval, university network |
| – | IEEE, Springer Nature, T&F, SAGE, IOS Press … | – | publisher APIs where available, otherwise library |
| end | Papers that still failed | – | manual download |

With the Wiley and Elsevier keys, roughly half of the list looks reachable.

**Storage:** so far 17.1 GB for 7,177 PDFs (median 1.5 MB). The whole list would be about 150 GB. As much as possible stays in the cloud (about 100 GB available on cloud.ovgu.de); the rest goes on an external drive. Zipping the PDFs saves only about 13% (they are already compressed internally) and would make single files impossible to browse in the cloud, so the PDFs are uploaded as they are.

**Open items:**

1. **Phase B full run** (Wiley incl. Hindawi, Elsevier as XML), then check the results. At 1 Wiley request every 10 s this takes about 43 hours.
2. **Library** (ub.it-anwendungen@ovgu.de, supervisor in cc): only after trying the publishers directly, for the publishers whose APIs are not available to us. Attach the list of missing papers by publisher.
3. **Notice-only papers (1,146, of which 852 from Springer):** the retracted article itself often still exists. On Springer's article pages it is usually attached under "Electronic supplementary material" (example: `10.1007/s10854-016-4998-z`). Get the real article for each of these papers; if it is not available anywhere, mark the paper as "article not found" so it is clear the article itself is missing. The notice files are kept (`<ID> [notice] - <title>.pdf`). How these attachments can be fetched within the rules (official API, or manually) is still being clarified.
4. **Failed downloads:** keep track of every paper that failed (status `failed`, with the reason, in the database and in `index.csv`) and prepare a list so they can be downloaded manually at the end.
5. Look up DOIs for the 5,950 entries without one (Crossref title search with strict matching).

## 8. Week 3: mismatch review and Phase B test (29 October 2026)

**Mismatch review.** The 54 PDFs whose first pages contained neither the title nor the DOI were checked by hand, and the decisions were cross-checked by searching each PDF's full text for the title and DOI:

| Decision | PDFs | What happened |
|---|---|---|
| Correct paper | 4 | kept (one of them is a 563-page conference supplement that contains the retracted abstract) |
| Correct paper, other language | 17 | kept (mostly Russian) |
| Only the retraction notice | 1 | kept as `[notice]`, status `incomplete` |
| Wrong document | 32 | moved (not deleted) to `_wrong_documents`, status back to `failed`, on the manual-download list |

So 32 of the 54 suspicious files (59%) were a different document: an open-access index linked the DOI to an unrelated file (other papers, reports, drug labels, theses).

**Phase B test.** The VPN has to run in full-tunnel mode: with a split tunnel the publishers see the home connection and refuse the full texts.

| API | Test | Result |
|---|---|---|
| Wiley (10.1002) | 20 random missing papers | 14 full PDFs (6–22 pages, all checked OK); 4 Cochrane reviews refused (403); 2 not found (404), one of them because of a DOI escaping bug, now fixed |
| Wiley for Hindawi (10.1155) | 2 random missing papers | 2 full PDFs |
| Elsevier (10.1016) | 2 articles | full text as XML (body included); as a PDF only the first page |
| Elsevier (10.1016), through the tool | 20 random missing papers | 15 complete articles (3,300–17,300 words, titles checked); 4 only the retraction notice (44–365 words), now kept as `[notice]` with status `incomplete`; 1 abstract only (not entitled) |

Elsevier full texts are therefore saved as XML (structured full text, figures only referenced). For about one in five retracted Elsevier papers, Elsevier itself only provides the retraction notice, so these count as missing ("article not found" candidates). With these results, about 14,900 Wiley/Hindawi papers and 8,100 Elsevier papers are reachable through the official APIs, about 36% of the list.
