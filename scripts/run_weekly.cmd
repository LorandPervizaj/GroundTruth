@echo off
REM Interactive weekly crawl: weeks, parallel/sequential, workers, trailing ETL.
REM
REM   scripts\run_weekly.cmd
REM   scripts\run_weekly.cmd

setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_weekly.ps1" %*
exit /b %ERRORLEVEL%
