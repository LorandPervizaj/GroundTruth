# Weekly crawl: all sources → ETL → analytics refresh.
#
# Run manually:
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_weekly_crawl.ps1
#
# Register Windows Task Scheduler (every 7 days at 02:00):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register_weekly_schedule.ps1
#
# Force run (ignore 7-day guard):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_weekly_crawl.ps1 -Force

param(
    [int]$Days = 7,
    [switch]$Force,
    [switch]$SkipCrawl
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot "reports\generated\weekly"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "weekly_crawl.log"
$PidFile = Join-Path $LogDir "weekly_crawl.pid"

function Write-Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    Write-Host $line
}

if (Test-Path $PidFile) {
    $oldPid = (Get-Content $PidFile -Raw).Trim()
    if ($oldPid -match '^\d+$') {
        $proc = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Error "Weekly crawl already running (PID $oldPid). Log: $LogFile"
            exit 1
        }
    }
}

$Groundtruth = Join-Path $RepoRoot ".venv\Scripts\groundtruth.exe"
if (-not (Test-Path $Groundtruth)) {
    Write-Error "groundtruth.exe not found. Run: uv sync"
    exit 1
}

$workerScript = @'
param(
    [string]$RepoRoot,
    [string]$Groundtruth,
    [string]$LogFile,
    [string]$PidFile,
    [string]$Days,
    [string]$Force,
    [string]$SkipCrawl
)

Set-Location $RepoRoot
Set-Content -Path $PidFile -Value $PID -Encoding ascii

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class WeeklyCrawlPower {
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

function Log([string]$msg) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $msg
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

[WeeklyCrawlPower]::PreventSleep()
$env:PYTHONIOENCODING = "utf-8"
Log "weekly crawl started pid=$PID days=$Days force=$Force skip_crawl=$SkipCrawl"

try {
    $args = @("crawl", "weekly", "--days", $Days)
    if ($Force -eq "true") { $args += "--force" }
    if ($SkipCrawl -eq "true") { $args += "--skip-crawl" }
    & $Groundtruth @args 2>&1 | ForEach-Object { Log $_ }
    & (Join-Path $RepoRoot ".venv\Scripts\python.exe") `
        (Join-Path $RepoRoot "scripts\update_home_trust_snapshot.py") 2>&1 | ForEach-Object { Log $_ }
    Log "weekly crawl finished exit=$LASTEXITCODE"
    exit $LASTEXITCODE
} catch {
    Log "ERROR: $_"
    exit 1
} finally {
    [WeeklyCrawlPower]::AllowSleep()
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
}
'@

$innerPath = Join-Path $LogDir "_weekly_crawl_worker.ps1"
Set-Content -Path $innerPath -Value $workerScript -Encoding utf8

$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $innerPath,
    "-RepoRoot", $RepoRoot,
    "-Groundtruth", $Groundtruth,
    "-LogFile", $LogFile,
    "-PidFile", $PidFile,
    "-Days", "$Days",
    "-Force", ($(if ($Force) { "true" } else { "false" })),
    "-SkipCrawl", ($(if ($SkipCrawl) { "true" } else { "false" }))
)

$proc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList $args `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Weekly crawl started (PID $($proc.Id))" -ForegroundColor Green
Write-Host "  Log: $LogFile"
Write-Host "  State: $LogDir\weekly_crawl_state.json"
