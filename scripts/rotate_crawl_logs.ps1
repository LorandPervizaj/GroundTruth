# Archive oversized MerrJep crawl logs.
param(
    [double]$MinSizeMB = 50
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LogDir = Join-Path $RepoRoot "reports\generated"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"

foreach ($name in @("merrjep_full_crawl.log", "merrjep_daemon.log")) {
    $path = Join-Path $LogDir $name
    if (-not (Test-Path $path)) { continue }
    $sizeMb = (Get-Item $path).Length / 1MB
    if ($sizeMb -lt $MinSizeMB) {
        Write-Host "Skip $name ($([math]::Round($sizeMb, 1)) MB)"
        continue
    }
    $archive = Join-Path $LogDir ("{0}.{1}.bak" -f $name, $stamp)
    Move-Item -Path $path -Destination $archive -Force
    New-Item -ItemType File -Path $path -Force | Out-Null
    Write-Host "Archived $name ($([math]::Round($sizeMb, 1)) MB) -> $(Split-Path $archive -Leaf)"
}
