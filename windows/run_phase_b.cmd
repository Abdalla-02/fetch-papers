@echo off
rem Phase B: publisher TDM APIs (Elsevier, Wiley). Safe to run again - it resumes where it stopped.
rem Put the API keys into a file ".env" in the DATA folder (see .env.example in the repo).
rem First run it with TEST=1 (20 papers per publisher), check the log, then set TEST=0 for the full run.
rem Run it from the university network, or with the VPN in full-tunnel mode: with a split tunnel the
rem publishers see the home connection and refuse the full texts.

rem ---- settings ---------------------------------------------------------------
set REPO=C:\path\to\fetch-papers
set DATA=C:\path\to\retracted_pdfs
set OUT=C:\path\to\Nextcloud\Retracted_Papers
set EMAIL=you@uni.de
rem 10.1155 = Hindawi (delivered by the Wiley API, tested Oct 2026); Cochrane reviews are always skipped
set WILEY_PREFIXES=10.1002,10.1111,10.1155
set TEST=1
rem ------------------------------------------------------------------------------

set PYTHONIOENCODING=utf-8
cd /d "%DATA%"
if not exist logs mkdir logs
set PY="%REPO%\venv\Scripts\python.exe" -u "%REPO%\windows\keep_awake_run.py" "%REPO%\fetch_pdfs.py" --db papers.sqlite
set FLAGS=--sources elsevier,wiley --retry-not-found --retry-failed --retry-incomplete --wiley-prefixes %WILEY_PREFIXES% --progress-every 100
echo ===== Phase B started %date% %time% (TEST=%TEST%) ===== >> logs\phaseB.log
if "%TEST%"=="1" (
    %PY% run --email %EMAIL% --out "%OUT%" %FLAGS% --prefix 10.1016 --limit 20 >> logs\phaseB.log 2>&1
    %PY% run --email %EMAIL% --out "%OUT%" %FLAGS% --prefix 10.1002 --limit 20 >> logs\phaseB.log 2>&1
) else (
    %PY% run --email %EMAIL% --out "%OUT%" %FLAGS% >> logs\phaseB.log 2>&1
)
echo ===== Phase B ended %date% %time% (exit %errorlevel%) ===== >> logs\phaseB.log
rem afterwards: check the new PDFs (Elsevier full texts are XML and checked when downloaded;
rem PDFs already decided by hand are not checked again)
%PY% verify --out "%OUT%" --out-dir reports >> logs\phaseB.log 2>&1
