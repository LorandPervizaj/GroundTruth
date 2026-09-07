# Interactive weekly crawl: weeks, parallel/sequential, workers, trailing ETL.
#
#   scripts\run_weekly.cmd
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_weekly.ps1

param(
    [int]$Weeks = 0,
    [ValidateSet("", "Sequential", "Parallel")]
    [string]$Mode = "",
    [int]$Workers = 0,
    [switch]$TrailingEtl,
    [switch]$NoTrailingEtl,
    [switch]$Force,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

$SourceCount = 8
$LogDir = Join-Path $RepoRoot "reports\generated\weekly"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Set-EnvKey {
    param(
        [string]$Path,
        [string]$Key,
        [string]$Value
    )
    $lines = @()
    $found = $false
    if (Test-Path $Path) {
        $lines = @(Get-Content -Path $Path -Encoding utf8)
    }
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$([regex]::Escape($Key))\s*=") {
            $lines[$i] = "$Key=$Value"
            $found = $true
            break
        }
    }
    if (-not $found) {
        if ($lines.Count -gt 0 -and $lines[-1].Trim() -ne "") {
            $lines += ""
        }
        if ($lines.Count -eq 0 -or -not ($lines -match "^\s*#.*Weekly crawl")) {
            $lines += "# Weekly crawl"
        }
        $lines += "$Key=$Value"
    }
    Set-Content -Path $Path -Value $lines -Encoding utf8
}

function Read-YesNo {
    param(
        [string]$Prompt,
        [bool]$Default = $false
    )
    $hint = if ($Default) { "Y/n" } else { "y/N" }
    while ($true) {
        $raw = Read-Host "$Prompt [$hint]"
        if ([string]::IsNullOrWhiteSpace($raw)) { return $Default }
        switch ($raw.Trim().ToLower()) {
            { $_ -in "y", "yes" } { return $true }
            { $_ -in "n", "no" } { return $false }
            default { Write-Host "Enter y or n." -ForegroundColor Red }
        }
    }
}

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$Groundtruth = Join-Path $RepoRoot ".venv\Scripts\groundtruth.exe"
if (-not (Test-Path $Groundtruth)) {
    Write-Error "groundtruth.exe not found. Run: uv sync"
    exit 1
}

# --- Weeks (1-4) ---
if ($Weeks -lt 1 -or $Weeks -gt 4) {
    $suggested = 1
    $elapsed = 0
    $when = "unknown"
    try {
        $hint = & $Python -c "from groundtruth.crawl.weekly import suggested_ingest_weeks, last_crawl_summary; w, d = suggested_ingest_weeks(); last, _ = last_crawl_summary(); print('%s|%s|%s' % (w, d or 0, last or '-'))"
        $parts = @($hint -split "\|")
        if ($parts.Count -ge 1 -and $parts[0] -match '^[1-4]$') { $suggested = [int]$parts[0] }
        if ($parts.Count -ge 2) { [void][int]::TryParse($parts[1], [ref]$elapsed) }
        if ($parts.Count -ge 3 -and $parts[2] -and $parts[2] -ne "-") {
            $when = $parts[2].Split("T")[0]
        }
        if ($elapsed -gt 0) {
            Write-Host "Last crawl: $when ($elapsed days ago). Suggested: $suggested week(s)." -ForegroundColor Cyan
        } else {
            Write-Host "No previous crawl on record. Suggested: 1 week." -ForegroundColor Cyan
        }
    } catch {
        Write-Host "Could not read last crawl date. Suggested: 1 week." -ForegroundColor Yellow
    }

    while ($Weeks -lt 1 -or $Weeks -gt 4) {
        $raw = Read-Host "How many weeks to scrape? [1/2/3/4] (default $suggested)"
        if ([string]::IsNullOrWhiteSpace($raw)) { $Weeks = $suggested; break }
        $parsed = 0
        if (-not [int]::TryParse($raw.Trim(), [ref]$parsed) -or $parsed -lt 1 -or $parsed -gt 4) {
            Write-Host "Enter 1, 2, 3, or 4." -ForegroundColor Red
            continue
        }
        $Weeks = $parsed
    }
}

$Days = $Weeks * 7

# --- Sequential vs parallel ---
if (-not $Mode) {
    Write-Host ""
    Write-Host "Crawl mode:" -ForegroundColor Cyan
    Write-Host "  1) Sequential (one source at a time, slower)"
    Write-Host "  2) Parallel   (multiple sources at once, faster)"
    while (-not $Mode) {
        $raw = Read-Host "Choose mode [1/2] (default 2)"
        if ([string]::IsNullOrWhiteSpace($raw)) { $Mode = "Parallel"; break }
        switch ($raw.Trim()) {
            "1" { $Mode = "Sequential"; break }
            "2" { $Mode = "Parallel"; break }
            default { Write-Host "Enter 1 or 2." -ForegroundColor Red }
        }
    }
}

$parallel = $Mode -eq "Parallel"

# --- Workers (parallel only) ---
if ($parallel -and ($Workers -lt 1)) {
    Write-Host ""
    Write-Host "Parallel workers (sources crawled concurrently):" -ForegroundColor Cyan
    Write-Host "  1) 2 workers"
    Write-Host "  2) 4 workers"
    Write-Host "  3) 8 workers"
    Write-Host "  4) All ($SourceCount sources)"
    while ($Workers -lt 1) {
        $raw = Read-Host "Choose workers [1/2/3/4] (default 4)"
        if ([string]::IsNullOrWhiteSpace($raw)) { $Workers = 4; break }
        switch ($raw.Trim()) {
            "1" { $Workers = 2; break }
            "2" { $Workers = 4; break }
            "3" { $Workers = 8; break }
            "4" { $Workers = $SourceCount; break }
            default { Write-Host "Enter 1, 2, 3, or 4." -ForegroundColor Red }
        }
    }
} elseif (-not $parallel) {
    $Workers = 1
}

# --- Trailing ETL ---
$trailing = $parallel
if ($TrailingEtl) { $trailing = $true }
if ($NoTrailingEtl) { $trailing = $false }
if (-not $TrailingEtl -and -not $NoTrailingEtl -and -not $Yes) {
    $defaultTrailing = $parallel
    $trailing = Read-YesNo -Prompt "Trailing ETL (normalize each source as its crawl finishes)?" -Default $defaultTrailing
}

# --- Force ---
$forceRun = [bool]$Force
if (-not $Force -and -not $Yes) {
    $forceRun = Read-YesNo -Prompt "Force run even if last crawl was <7 days ago?" -Default $false
}

# --- Summary ---
Write-Host ""
Write-Host "=== Weekly crawl plan ===" -ForegroundColor Green
Write-Host "  Lookback:    $Weeks week(s) ($Days days)"
Write-Host "  Mode:        $Mode"
if ($parallel) { Write-Host "  Workers:     $Workers" }
Write-Host "  Trailing ETL: $(if ($trailing) { 'yes' } else { 'no' })"
Write-Host "  Force:       $(if ($forceRun) { 'yes' } else { 'no' })"
Write-Host ""

if (-not $Yes) {
    $confirm = Read-YesNo -Prompt "Start weekly crawl with these settings?" -Default $true
    if (-not $confirm) {
        Write-Host "Cancelled." -ForegroundColor Yellow
        exit 0
    }
}

# --- Persist to .env ---
$EnvPath = Join-Path $RepoRoot ".env"
if (-not (Test-Path $EnvPath)) {
    Copy-Item (Join-Path $RepoRoot ".env.example") $EnvPath
}
Set-EnvKey -Path $EnvPath -Key "WEEKLY_CRAWL_PARALLEL_WORKERS" -Value "$Workers"
Set-EnvKey -Path $EnvPath -Key "WEEKLY_CRAWL_TRAILING_ETL" -Value ($(if ($trailing) { "true" } else { "false" }))
Write-Host "Updated .env: WEEKLY_CRAWL_PARALLEL_WORKERS=$Workers, WEEKLY_CRAWL_TRAILING_ETL=$trailing" -ForegroundColor DarkGray

# --- Guard: already running ---
$PidFile = Join-Path $LogDir "weekly_crawl.pid"
if (Test-Path $PidFile) {
    $oldPid = (Get-Content $PidFile -Raw).Trim()
    if ($oldPid -match '^\d+$') {
        $proc = Get-Process -Id ([int]$oldPid) -ErrorAction SilentlyContinue
        if ($proc) {
            Write-Error "Weekly crawl already running (PID $oldPid). Log: $(Join-Path $LogDir 'weekly_crawl.log')"
            exit 1
        }
    }
}

$LogFile = Join-Path $LogDir "weekly_crawl.log"
$workerScript = Join-Path $LogDir "_run_weekly_worker.ps1"

$workerBody = @'
param(
    [string]$RepoRoot,
    [string]$Groundtruth,
    [string]$Python,
    [string]$LogFile,
    [string]$PidFile,
    [string]$Days,
    [string]$Force,
    [string]$Parallel,
    [string]$TrailingEtl
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
$env:PYTHONUTF8 = "1"
Log "weekly crawl started pid=$PID days=$Days force=$Force parallel=$Parallel trailing_etl=$TrailingEtl"

try {
    $args = @("crawl", "weekly", "--days", $Days)
    if ($Force -eq "true") { $args += "--force" }
    if ($Parallel -ne "true") { $args += "--no-parallel" }
    if ($TrailingEtl -eq "true") { $args += "--trailing-etl" }
    elseif ($TrailingEtl -eq "false") { $args += "--no-trailing-etl" }
    & $Groundtruth @args 2>&1 | ForEach-Object {
        try { Log $_ } catch { Log "[log line omitted: encoding]" }
    }
    & $Python (Join-Path $RepoRoot "scripts\update_home_trust_snapshot.py") 2>&1 | ForEach-Object { Log $_ }
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

Set-Content -Path $workerScript -Value $workerBody -Encoding utf8

& (Join-Path $RepoRoot "scripts\enable_crawl_power.ps1") | Out-Null

$launchArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $workerScript,
    "-RepoRoot", $RepoRoot,
    "-Groundtruth", $Groundtruth,
    "-Python", $Python,
    "-LogFile", $LogFile,
    "-PidFile", $PidFile,
    "-Days", "$Days",
    "-Force", ($(if ($forceRun) { "true" } else { "false" })),
    "-Parallel", ($(if ($parallel) { "true" } else { "false" })),
    "-TrailingEtl", ($(if ($trailing) { "true" } else { "false" }))
)

$proc = Start-Process -FilePath "powershell.exe" `
    -ArgumentList $launchArgs `
    -WorkingDirectory $RepoRoot `
    -WindowStyle Hidden `
    -PassThru

Write-Host ""
Write-Host "Weekly crawl started (PID $($proc.Id))" -ForegroundColor Green
Write-Host "  Log:        $LogFile"
Write-Host "  PID file:   $PidFile"
Write-Host "  Checkpoint: $LogDir\checkpoints\"
Write-Host "  State:      $LogDir\weekly_crawl_state.json"
