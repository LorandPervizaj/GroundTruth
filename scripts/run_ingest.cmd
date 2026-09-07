@echo off
REM Asks 1-4 weeks since last scrape, then scrapes and prompts before normalize.
REM
REM   scripts\run_ingest.cmd
REM   scripts\run_ingest.cmd -Weeks 3
REM   scripts\run_ingest.cmd -SkipCrawl

setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_ingest.ps1" %*
exit /b %ERRORLEVEL%
