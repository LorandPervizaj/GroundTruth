# Stop background crawl daemon (or legacy foreground crawl).
param([switch]$Force)

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PidFile = Join-Path $RepoRoot "reports\generated\merrjep_daemon.pid"

function Stop-Tree([int]$ProcessId) {
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId=$ProcessId" -ErrorAction SilentlyContinue
    foreach ($c in $children) { Stop-Tree $c.ProcessId }
    Stop-Process -Id $ProcessId -Force:$Force -ErrorAction SilentlyContinue
}

$stopped = $false

if (Test-Path $PidFile) {
    $daemonPid = (Get-Content $PidFile -Raw).Trim()
    if ($daemonPid -match '^\d+$') {
        Write-Host "Stopping daemon PID $daemonPid..."
        Stop-Tree ([int]$daemonPid)
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        $stopped = $true
    }
}

$legacy = Get-CimInstance Win32_Process -Filter "name='python.exe'" |
    Where-Object { $_.CommandLine -match 'groundtruth.*crawl merrjep' }
foreach ($p in $legacy) {
    Write-Host "Stopping crawl PID $($p.ProcessId)..."
    Stop-Tree $p.ProcessId
    $stopped = $true
}

if ($stopped) {
    Write-Host "Crawl stopped." -ForegroundColor Green
} else {
    Write-Host "No MerrJep crawl process found." -ForegroundColor Gray
}
