# Show background crawl daemon status.
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $RepoRoot "reports\generated\merrjep_daemon.pid"
$StateFile = Join-Path $RepoRoot "reports\generated\merrjep_daemon.state.json"
$LogFile = Join-Path $RepoRoot "reports\generated\merrjep_daemon.log"

if (Test-Path $StateFile) {
    Write-Host "State:" -ForegroundColor Cyan
    Get-Content $StateFile -Raw | Write-Host
}

if (Test-Path $PidFile) {
    $daemonPid = (Get-Content $PidFile -Raw).Trim()
    $proc = Get-Process -Id ([int]$daemonPid) -ErrorAction SilentlyContinue
    if ($proc) {
        Write-Host "Daemon RUNNING (PID $daemonPid, started $($proc.StartTime))" -ForegroundColor Green
    } else {
        Write-Host "Stale PID file ($daemonPid) - process not running" -ForegroundColor Yellow
    }
} else {
    $legacy = Get-CimInstance Win32_Process -Filter "name='python.exe'" |
        Where-Object { $_.CommandLine -match 'crawl merrjep' }
    if ($legacy) {
        Write-Host "No daemon PID file, but MerrJep crawl process found:" -ForegroundColor Yellow
        $legacy | ForEach-Object { Write-Host "  PID $($_.ProcessId): $($_.CommandLine)" }
    } else {
        Write-Host "No crawl daemon running." -ForegroundColor Gray
    }
}

if (Test-Path $LogFile) {
    Write-Host ""
    Write-Host "Last log lines:" -ForegroundColor Cyan
    Get-Content $LogFile -Tail 8
}

Set-Location $RepoRoot
uv run python scripts/crawl_monitor.py --spider merrjep 2>$null
# Or all spiders: uv run python scripts/crawl_monitor.py
