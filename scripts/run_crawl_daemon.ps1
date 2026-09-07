# Run MerrJep crawl detached from this terminal, with system sleep blocked.
#
# Start (closes safely — crawl keeps running):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_crawl_daemon.ps1
#
# Full pipeline (rent → ETL → sale → ETL → corpus):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_crawl_daemon.ps1 -FullPipeline
#
# Status:  powershell -File scripts\crawl_daemon_status.ps1
# Stop:    powershell -File scripts\stop_crawl_daemon.ps1

param(
    [ValidateSet("apartments_rent", "apartments_sale", "rent", "sale", "apartments")]
    [string]$Index = "apartments_rent",
    [int]$StartPage = 1,
    [switch]$FullPipeline,
    [switch]$KeepAwakeOnly,
    [switch]$NoSkipExisting
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot "reports\generated"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir "merrjep_daemon.log"
$PidFile = Join-Path $LogDir "merrjep_daemon.pid"
$StateFile = Join-Path $LogDir "merrjep_daemon.state.json"

function Write-Log([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -Path $LogFile -Value $line -Encoding utf8
    Write-Host $line
}

if (Test-Path $PidFile) {
    $oldPid = Get-Content $PidFile -Raw
    $oldPid = $oldPid.Trim()
    if ($oldPid -match '^\d+$') {
        $proc = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Error "Crawl daemon already running (PID $oldPid). Use scripts\stop_crawl_daemon.ps1 first."
            exit 1
        }
    }
}

$Groundtruth = Join-Path $RepoRoot ".venv\Scripts\groundtruth.exe"
if (-not (Test-Path $Groundtruth)) {
    Write-Error "groundtruth.exe not found. Run: uv sync"
    exit 1
}

$daemonScript = @'
param(
    [string]$RepoRoot,
    [string]$Groundtruth,
    [string]$LogFile,
    [string]$PidFile,
    [string]$StateFile,
    [string]$Index,
    [string]$FullPipeline,
    [string]$StartPage,
    [string]$SkipExisting
)

$runFull = ($FullPipeline -eq "true")
$startPageNum = [int]$StartPage

Set-Location $RepoRoot

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class CrawlPower {
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

[CrawlPower]::PreventSleep()
Log "daemon started pid=$PID index=$Index start_page=$StartPage full=$FullPipeline"

@{
    pid = $PID
    started_at = (Get-Date).ToUniversalTime().ToString("o")
    index = $Index
    start_page = $StartPage
    skip_existing = $SkipExisting
    full_pipeline = $FullPipeline
} | ConvertTo-Json | Set-Content -Path $StateFile -Encoding utf8

Set-Content -Path $PidFile -Value $PID -Encoding ascii

try {
    $crawlOut = Join-Path (Split-Path $LogFile) "merrjep_crawl_output.log"

    if ($runFull) {
        Log "=== apartments_rent crawl (output: $crawlOut) ==="
        & $Groundtruth crawl merrjep --detail --index apartments_rent *> $crawlOut
        Log "=== ETL merrjep ==="
        & $Groundtruth etl run --source merrjep >> $crawlOut 2>&1
        Log "=== apartments_sale crawl ==="
        & $Groundtruth crawl merrjep --detail --index apartments_sale >> $crawlOut 2>&1
        Log "=== ETL merrjep ==="
        & $Groundtruth etl run --source merrjep >> $crawlOut 2>&1
        Log "=== corpus report ==="
        & $Groundtruth corpus report >> $crawlOut 2>&1
        Log "=== full pipeline finished exit=$LASTEXITCODE ==="
    } else {
        Log "=== crawl index=$Index start_page=$StartPage (output: $crawlOut) ==="
        $crawlArgs = @("crawl", "merrjep", "--detail", "--index", $Index)
        if ($startPageNum -gt 1) { $crawlArgs += @("--start-page", $StartPage) }
        if ($SkipExisting -eq "false") { $crawlArgs += "--no-skip-existing" }
        & $Groundtruth @crawlArgs 2>&1 | Out-File -FilePath $crawlOut -Encoding utf8
        Log "=== crawl finished index=$Index exit=$LASTEXITCODE ==="
    }
} catch {
    Log "ERROR: $_"
    exit 1
} finally {
    [CrawlPower]::AllowSleep()
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
    Log "daemon exited"
}
'@

$innerPath = Join-Path $LogDir "_crawl_daemon_worker.ps1"
Set-Content -Path $innerPath -Value $daemonScript -Encoding utf8

$args = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $innerPath,
    "-RepoRoot", $RepoRoot,
    "-Groundtruth", $Groundtruth,
    "-LogFile", $LogFile,
    "-PidFile", $PidFile,
    "-StateFile", $StateFile,
    "-Index", $Index,
    "-FullPipeline", ($(if ($FullPipeline) { "true" } else { "false" })),
    "-StartPage", "$StartPage",
    "-SkipExisting", ($(if ($NoSkipExisting) { "false" } else { "true" }))
)

$proc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList $args `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Crawl daemon started (PID $($proc.Id))" -ForegroundColor Green
Write-Host "  Log:  $LogFile"
Write-Host "  PID:  $PidFile"
Write-Host ""
Write-Host "Monitor:  uv run python scripts/crawl_monitor.py"
Write-Host "Status:   powershell -File scripts\crawl_daemon_status.ps1"
Write-Host "Stop:     powershell -File scripts\stop_crawl_daemon.ps1"
