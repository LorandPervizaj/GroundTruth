<#
.SYNOPSIS
  Start (or stop) a disposable local Metrik for k6 performance tests.

.DESCRIPTION
  Starts only the compose service postgres-perf (127.0.0.1:15434, tmpfs data,
  database groundtruth_perf), migrates it, and starts Metrik on 127.0.0.1 with
  that database. The research database (container groundtruth-postgres) and
  GROUNDTRUTH_ENV_FILE are never used: the server process gets an explicit
  DATABASE_URL and an empty GROUNDTRUTH_ENV_FILE, and the script stops the
  target unless the server reports an empty listings table.

  Public market data is served from the committed release artifacts under
  reports/generated/lookup_cache, exactly as in CI.

  State and logs are written to .tmp/k6/ (gitignored).

.EXAMPLE
  .\scripts\performance\start-local-test-target.ps1
  .\scripts\performance\k6.ps1 smoke
  .\scripts\performance\start-local-test-target.ps1 -Stop
#>
[CmdletBinding()]
param(
    [int]$Port = 8000,
    [int]$TimeoutSeconds = 120,
    [switch]$Stop
)

$ErrorActionPreference = 'Stop'

$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$StateDir = Join-Path $Root '.tmp\k6'
$StateFile = Join-Path $StateDir 'target.json'
$Container = 'groundtruth-perf-postgres'
$Database = 'groundtruth_perf'
$DatabaseUrl = "postgresql+psycopg://groundtruth_perf:groundtruth_perf@127.0.0.1:15434/$Database"
$DatabaseLabel = "127.0.0.1:15434/$Database (container $Container, tmpfs)"

function Stop-Target {
    if (Test-Path $StateFile) {
        $state = Get-Content $StateFile -Raw | ConvertFrom-Json
        if (Get-Process -Id $state.pid -ErrorAction SilentlyContinue) {
            # uv starts Python as a child process; stop the whole tree.
            & taskkill.exe /PID $state.pid /T /F | Out-Null
            Write-Output "Stopped Metrik (pid $($state.pid))."
        }
        Remove-Item $StateFile -Force
    }
    Push-Location $Root
    try {
        docker compose --profile perf rm --stop --force postgres-perf | Out-Null
    } finally {
        Pop-Location
    }
    Write-Output "Removed $Container."
}

if ($Stop) {
    Stop-Target
    exit 0
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $owner = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    throw "Port $Port is already in use by $($owner.ProcessName) (pid $($listener.OwningProcess)). " +
        "It may be a Metrik connected to another database. Stop it, run with -Stop, or pass -Port."
}

New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
Push-Location $Root
$saved = @{}
$overrides = [ordered]@{
    DATABASE_URL           = $DatabaseUrl
    GROUNDTRUTH_ENV_FILE   = ''
    APP_ENV                = 'development'
    API_RATE_LIMIT_ENABLED = 'false'
    SENTRY_DSN             = ''
}
try {
    docker compose --profile perf up -d --no-deps --wait postgres-perf
    if ($LASTEXITCODE) { throw "Could not start $Container (is Docker Desktop running?)." }

    foreach ($name in $overrides.Keys) {
        $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        [Environment]::SetEnvironmentVariable($name, $overrides[$name], 'Process')
    }

    uv run alembic upgrade head
    if ($LASTEXITCODE) { throw 'Alembic migration of the performance database failed.' }

    $stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
    $outLog = Join-Path $StateDir "metrik-$stamp.out.log"
    $errLog = Join-Path $StateDir "metrik-$stamp.err.log"
    $server = Start-Process -FilePath 'uv' `
        -ArgumentList @('run', 'groundtruth', 'serve', '--no-reload', '--host', '127.0.0.1', '--port', "$Port") `
        -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput $outLog -RedirectStandardError $errLog
} finally {
    foreach ($name in $saved.Keys) {
        if ($null -eq $saved[$name]) {
            Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
        } else {
            Set-Item -Path "Env:$name" -Value $saved[$name]
        }
    }
    Pop-Location
}

$baseUrl = "http://127.0.0.1:$Port"
[ordered]@{
    pid        = $server.Id
    base_url   = $baseUrl
    database   = $DatabaseLabel
    started_at = (Get-Date).ToString('o')
    stdout     = $outLog
    stderr     = $errLog
} | ConvertTo-Json | Set-Content -Path $StateFile -Encoding utf8

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    if ($server.HasExited) { break }
    try {
        $response = Invoke-WebRequest -Uri "$baseUrl/api/health" -UseBasicParsing -TimeoutSec 5
        if ($response.StatusCode -eq 200) { $healthy = $true; break }
    } catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $healthy) {
    Write-Warning "Metrik did not become healthy within $TimeoutSeconds s. Last log lines:"
    Get-Content $errLog -Tail 30 -ErrorAction SilentlyContinue
    Stop-Target
    exit 1
}

# Prove isolation: /api/methodology counts listings through the server's own
# database session. The disposable database is empty, the research database is not.
$methodology = Invoke-RestMethod -Uri "$baseUrl/api/methodology" -TimeoutSec 60
$connections = docker exec $Container psql -U groundtruth_perf -d $Database -tAc `
    "SELECT count(*) FROM pg_stat_activity WHERE datname = '$Database' AND pid <> pg_backend_pid()"
$revision = docker exec $Container psql -U groundtruth_perf -d $Database -tAc 'SELECT version_num FROM alembic_version'
if ([int]$methodology.raw_listings -ne 0 -or [int]$connections.Trim() -lt 1) {
    Write-Warning ("Isolation check failed: server reports raw_listings=$($methodology.raw_listings), " +
        "connections to $Database=$($connections.Trim()). Stopping the target.")
    Stop-Target
    exit 1
}

Write-Output ''
Write-Output "Metrik is running at $baseUrl (pid $($server.Id))"
Write-Output "Database:            $DatabaseLabel"
Write-Output "Alembic revision:    $($revision.Trim())"
Write-Output "Isolation check:     server raw_listings=$($methodology.raw_listings); $($connections.Trim()) server connection(s) to $Database"
Write-Output "Logs:                $errLog"
Write-Output ''
Write-Output 'Next:  .\scripts\performance\k6.ps1 smoke'
Write-Output 'Stop:  .\scripts\performance\start-local-test-target.ps1 -Stop'
