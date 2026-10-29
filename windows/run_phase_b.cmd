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
rem Optional first argument: only these sources, e.g. "run_phase_b.cmd elsevier" and "run_phase_b.cmd wiley"
rem in two windows at the same time (their papers don't overlap). Each then logs to its own file.
set SOURCES=elsevier,wiley
set LOG=logs\phaseB.log
if not "%~1"=="" (
    set SOURCES=%~1
    set LOG=logs\phaseB_%~1.log
)
rem ------------------------------------------------------------------------------

set PYTHONIOENCODING=utf-8
cd /d "%DATA%"
if not exist logs mkdir logs
set PY="%REPO%\venv\Scripts\python.exe" -u "%REPO%\windows\keep_awake_run.py" "%REPO%\fetch_pdfs.py" --db papers.sqlite
set FLAGS=--sources %SOURCES% --retry-not-found --retry-failed --retry-incomplete --wiley-prefixes %WILEY_PREFIXES% --progress-every 100
echo ===== Phase B started %date% %time% (TEST=%TEST%, sources %SOURCES%) ===== >> %LOG%
if "%TEST%"=="1" (
    %PY% run --email %EMAIL% --out "%OUT%" %FLAGS% --prefix 10.1016 --limit 20 >> %LOG% 2>&1
    %PY% run --email %EMAIL% --out "%OUT%" %FLAGS% --prefix 10.1002 --limit 20 >> %LOG% 2>&1
) else (
    %PY% run --email %EMAIL% --out "%OUT%" %FLAGS% >> %LOG% 2>&1
)
echo ===== Phase B ended %date% %time% (exit %errorlevel%) ===== >> %LOG%
rem afterwards: check the new PDFs (Elsevier full texts are XML and checked when downloaded;
rem PDFs already decided by hand are not checked again)
if not "%SOURCES%"=="elsevier" %PY% verify --out "%OUT%" --out-dir reports >> %LOG% 2>&1
