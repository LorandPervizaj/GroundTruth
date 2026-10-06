<#
.SYNOPSIS
  Run the k6 public-read suite (tests/load/k6_public_api.js) against Metrik.

.DESCRIPTION
  Targets http://127.0.0.1:8000 by default. Only localhost targets are allowed
  unless -AllowRemote is given; Azure Container Apps hosts additionally need
  -AllowProduction. Start a disposable local target first with
  scripts/performance/start-local-test-target.ps1.

  Results go to .tmp/k6/ (gitignored):
    <timestamp>-<profile>.txt            console output and end-of-test summary
    <timestamp>-<profile>-summary.json   k6 summary export
    <timestamp>-<profile>-meta.json      target, database, commit, k6 version, exit code

  Exits with k6's exit code (99 means a threshold failed).

.EXAMPLE
  .\scripts\performance\k6.ps1 smoke
  .\scripts\performance\k6.ps1 baseline
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('smoke', 'baseline')]
    [string]$LoadProfile = 'smoke',

    [string]$BaseUrl = 'http://127.0.0.1:8000',

    [switch]$AllowRemote,

    [switch]$AllowProduction
)

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Script = Join-Path $Root 'tests\load\k6_public_api.js'
$ResultsDir = Join-Path $Root '.tmp\k6'
$StateFile = Join-Path $ResultsDir 'target.json'
$LocalHosts = @('localhost', '127.0.0.1', '::1', '[::1]')
$ProductionHostPattern = '(^|\.)azurecontainerapps\.io$'

function Fail([string]$Message, [int]$Code = 2) {
    Write-Host "k6.ps1: $Message" -ForegroundColor Red
    exit $Code
}

# --- target safety ---------------------------------------------------------
$BaseUrl = $BaseUrl.TrimEnd('/')
$uri = $null
if (-not [Uri]::TryCreate($BaseUrl, [UriKind]::Absolute, [ref]$uri) -or $uri.Scheme -notin @('http', 'https')) {
    Fail "BaseUrl must be an absolute http(s) URL, got '$BaseUrl'."
}
$targetHost = $uri.Host.ToLowerInvariant()
$isLocal = $LocalHosts -contains $targetHost
$isProduction = $targetHost -match $ProductionHostPattern

if (-not $isLocal -and -not $AllowRemote) {
    Fail "Refusing to load-test non-local host '$targetHost'. Pass -AllowRemote only for a target you own and intend to load."
}
if ($isProduction -and -not $AllowProduction) {
    Fail "Refusing to load-test '$targetHost': it looks like Azure production. This needs both -AllowRemote and -AllowProduction."
}

# --- k6 --------------------------------------------------------------------
$k6 = (Get-Command k6 -ErrorAction SilentlyContinue).Source
if (-not $k6) {
    $default = Join-Path $env:ProgramFiles 'k6\k6.exe'
    if (Test-Path $default) { $k6 = $default }
}
if (-not $k6) {
    Fail 'k6 is not installed. Install it with: winget install --id GrafanaLabs.k6 --exact'
}
$k6Version = (& $k6 version | Select-Object -First 1).Trim()

# --- target health ---------------------------------------------------------
try {
    $health = Invoke-WebRequest -Uri "$BaseUrl/api/health" -UseBasicParsing -TimeoutSec 10
} catch {
    Fail ("Metrik is not responding at $BaseUrl/api/health ($($_.Exception.Message)).`n" +
        "Start a disposable local target with: .\scripts\performance\start-local-test-target.ps1")
}
if ($health.StatusCode -ne 200) {
    Fail "$BaseUrl/api/health returned HTTP $($health.StatusCode)."
}

$database = 'unknown (target was not started by start-local-test-target.ps1)'
if (Test-Path $StateFile) {
    $state = Get-Content $StateFile -Raw | ConvertFrom-Json
    if ($state.base_url -eq $BaseUrl -and (Get-Process -Id $state.pid -ErrorAction SilentlyContinue)) {
        $database = $state.database
    }
}

# --- run -------------------------------------------------------------------
New-Item -ItemType Directory -Force -Path $ResultsDir | Out-Null
$stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$prefix = Join-Path $ResultsDir "$stamp-$LoadProfile"
$textPath = "$prefix.txt"
$summaryPath = "$prefix-summary.json"
$metaPath = "$prefix-meta.json"
$commit = (git -C $Root rev-parse --short HEAD 2>$null)

$header = @(
    "profile:  $LoadProfile",
    "target:   $BaseUrl",
    "database: $database",
    "commit:   $commit",
    "k6:       $k6Version",
    ''
)
$header | Tee-Object -FilePath $textPath

$arguments = @(
    'run', '--quiet', '--no-usage-report',
    '--summary-trend-stats', 'avg,min,med,p(90),p(95),p(99),max',
    '--summary-export', $summaryPath,
    '-e', "BASE_URL=$BaseUrl",
    '-e', "K6_PROFILE=$LoadProfile",
    $Script
)
$started = Get-Date
$ErrorActionPreference = 'Continue'
& $k6 @arguments 2>&1 | ForEach-Object { "$_" } | Tee-Object -FilePath $textPath -Append
$exitCode = $LASTEXITCODE
$ErrorActionPreference = 'Stop'

[ordered]@{
    profile      = $LoadProfile
    base_url     = $BaseUrl
    database     = $database
    commit       = $commit
    k6_version   = $k6Version
    started_at   = $started.ToString('o')
    finished_at  = (Get-Date).ToString('o')
    exit_code    = $exitCode
    summary_json = $summaryPath
} | ConvertTo-Json | Set-Content -Path $metaPath -Encoding utf8

Write-Host ''
if ($exitCode -eq 0) {
    Write-Host "k6 $LoadProfile passed." -ForegroundColor Green
} elseif ($exitCode -eq 99) {
    Write-Host "k6 $LoadProfile ran, but one or more thresholds failed (exit 99)." -ForegroundColor Red
} else {
    Write-Host "k6 $LoadProfile failed (exit $exitCode)." -ForegroundColor Red
}
Write-Host "Results: $textPath"
Write-Host "         $summaryPath"
Write-Host "         $metaPath"
exit $exitCode
