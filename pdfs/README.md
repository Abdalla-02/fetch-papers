# The PDFs are not in this repository

This repository holds only the code and the documentation. The downloaded PDFs are copyrighted publisher content, so they are not uploaded here (they are excluded in `.gitignore`), and neither is the database `papers.sqlite`.

The PDF collection is kept in the project's folder on the OVGU cloud (Nextcloud):

**https://cloud.ovgu.de/f/221439039** → folder `Abdalla - shared folder`

| Subfolder | Contents |
|---|---|
| `Retracted_Papers/` | The PDFs, in subfolders of 1,000 Retraction Watch IDs (`<ID block>/<RW ID> - <title>.pdf`), and `index.csv` with one row per paper (DOI, title, file name, status) |
| `Retracted_Papers_Reports/` | Weekly reports, the PDF quality check (`verify.csv`) and the lists of missing papers by publisher |

The link only works for people the folder has been shared with (OVGU login). If you need access, contact Abdalla Ahmed.

How the files are named and what the statuses mean: see the [main README](../README.md); current numbers: [ANALYSIS.md](../ANALYSIS.md).
