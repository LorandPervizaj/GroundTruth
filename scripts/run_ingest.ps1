# Gated ingest: asks 1–4 weeks since last scrape, crawls, then asks before ETL.
#
#   scripts\run_ingest.cmd
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_ingest.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_ingest.ps1 -Weeks 3
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_ingest.ps1 -SkipCrawl

param(
    [int]$Days = 0,
    [int]$Weeks = 0,
    [switch]$Yes,
    [switch]$SkipCrawl,
    [switch]$NoParallel
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot "reports\generated\weekly"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "ingest_$Stamp.log"
$PidFile = Join-Path $LogDir "ingest.pid"

if (Test-Path $PidFile) {
    $oldPid = (Get-Content $PidFile -Raw).Trim()
    if ($oldPid -match '^\d+$') {
        $proc = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Error "Ingest already running (PID $oldPid)."
            exit 1
        }
    }
}
Set-Content -Path $PidFile -Value $PID -Encoding ascii

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class IngestCrawlPower {
    [DllImport("kernel32.dll", CharSet=CharSet.Auto, SetLastError=true)]
    public static extern uint SetThreadExecutionState(uint esFlags);
    public const uint ES_CONTINUOUS = 0x80000000;
    public const uint ES_SYSTEM_REQUIRED = 0x00000001;
    public static void PreventSleep() {
        SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED);
    }
    public static void AllowSleep() {
        SetThreadExecutionState(ES_CONTINUOUS);
    }
}
"@

[IngestCrawlPower]::PreventSleep()
$env:PYTHONIOENCODING = "utf-8"

$Groundtruth = Join-Path $RepoRoot ".venv\Scripts\groundtruth.exe"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$useUv = -not (Test-Path $Groundtruth)

if ($Days -le 0 -and $Weeks -le 0) {
    $suggested = 1
    $elapsed = 0
    $when = "unknown"
    try {
        if (Test-Path $Python) {
            $hint = & $Python -c "from groundtruth.crawl.weekly import suggested_ingest_weeks, last_crawl_summary; w, d = suggested_ingest_weeks(); last, _ = last_crawl_summary(); print('%s|%s|%s' % (w, d or 0, last or '-'))"
            $parts = @($hint -split "\|")
            if ($parts.Count -ge 1 -and $parts[0] -match '^[1-4]$') {
                $suggested = [int]$parts[0]
            }
            if ($parts.Count -ge 2) { [void][int]::TryParse($parts[1], [ref]$elapsed) }
            if ($parts.Count -ge 3 -and $parts[2] -and $parts[2] -ne "-") {
                $when = $parts[2].Split("T")[0]
            }
        }
        if ($elapsed -gt 0) {
            Write-Host "Last scrape: $when ($elapsed days ago). Suggested: $suggested week(s)." -ForegroundColor Cyan
        } else {
            Write-Host "No previous scrape on record. Suggested: 1 week." -ForegroundColor Cyan
        }
    } catch {
        Write-Host "Could not read last scrape date. Suggested: 1 week." -ForegroundColor Yellow
    }

    while ($Weeks -lt 1 -or $Weeks -gt 4) {
        $raw = Read-Host "How many weeks to scrape since the last one? [1/2/3/4] (default $suggested)"
        if ([string]::IsNullOrWhiteSpace($raw)) {
            $Weeks = $suggested
            break
        }
        $parsed = 0
        if (-not [int]::TryParse($raw.Trim(), [ref]$parsed) -or $parsed -lt 1 -or $parsed -gt 4) {
            Write-Host "Enter 1, 2, 3, or 4." -ForegroundColor Red
            continue
        }
        $Weeks = $parsed
    }
}

$gtArgs = @("crawl", "ingest")
if ($Days -gt 0) { $gtArgs += @("--days", "$Days") }
if ($Weeks -gt 0) { $gtArgs += @("--weeks", "$Weeks") }
if ($Yes) { $gtArgs += "--yes" }
if ($SkipCrawl) { $gtArgs += "--skip-crawl" }
if ($NoParallel) { $gtArgs += "--no-parallel" }

Write-Host "Log: $LogFile" -ForegroundColor DarkGray
Write-Host "When crawlers finish, type y to continue to normalization and website update." -ForegroundColor Cyan

Start-Transcript -Path $LogFile | Out-Null
try {
    Write-Host ("{0} ingest started pid={1} args={2}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $PID, ($gtArgs -join " "))
    if ($useUv) {
        Write-Host "using: uv run groundtruth"
        & uv run groundtruth @gtArgs
    } else {
        Write-Host "using: $Groundtruth"
        & $Groundtruth @gtArgs
    }
    $code = $LASTEXITCODE
    Write-Host ("{0} ingest finished exit={1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $code)
    if ($null -eq $code) { $code = 0 }
    exit $code
} catch {
    Write-Host "ERROR: $_"
    exit 1
} finally {
    Stop-Transcript | Out-Null
    [IngestCrawlPower]::AllowSleep()
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
}
