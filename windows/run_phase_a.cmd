@echo off
rem Run a download phase in the background-friendly way used for Phase A.
rem Copy this file next to your data, fill in the four settings below, then double-click it
rem (or start it hidden:  powershell Start-Process cmd -ArgumentList '/c','run_phase_a.cmd' -WindowStyle Hidden).
rem It is safe to run again: the script resumes where it stopped.

rem ---- settings ---------------------------------------------------------------
rem folder with the git checkout (fetch_pdfs.py and venv\)
set REPO=C:\path\to\fetch-papers
rem folder for papers.sqlite, logs\ and reports\ (keep it OUTSIDE OneDrive/Nextcloud)
set DATA=C:\path\to\retracted_pdfs
rem folder for the PDFs (may be inside the Nextcloud sync folder)
set OUT=C:\path\to\Nextcloud\Retracted_Papers
set EMAIL=you@uni.de
rem ------------------------------------------------------------------------------

set PYTHONIOENCODING=utf-8
cd /d "%DATA%"
if not exist logs mkdir logs
echo ===== Phase A started %date% %time% ===== >> logs\phaseA.log
"%REPO%\venv\Scripts\python.exe" -u "%REPO%\windows\keep_awake_run.py" "%REPO%\fetch_pdfs.py" --db papers.sqlite ^
    run --email %EMAIL% --out "%OUT%" --sources unpaywall,openalex --concurrency 16 --progress-every 200 >> logs\phaseA.log 2>&1
echo ===== Phase A ended %date% %time% (exit %errorlevel%) ===== >> logs\phaseA.log
