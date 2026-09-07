# Keep Windows awake during long crawls (plugged in + on battery).
# Run BEFORE starting crawl. Revert with disable_crawl_power.ps1
#
#   powershell -ExecutionPolicy Bypass -File scripts\enable_crawl_power.ps1

$Backup = Join-Path $PSScriptRoot "..\reports\generated\power_settings_backup.txt"
$BackupDir = Split-Path $Backup -Parent
New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null

function Get-PowerValue([string]$Sub, [string]$Setting, [string]$AcDc) {
    $raw = powercfg /QUERY SCHEME_CURRENT $Sub $Setting 2>$null
    if ($AcDc -eq "AC") {
        ($raw | Select-String "Current AC Power Setting Index").Line
    } else {
        ($raw | Select-String "Current DC Power Setting Index").Line
    }
}

"backup_at=$(Get-Date -Format o)" | Set-Content $Backup
Get-PowerValue "SUB_BUTTONS" "LIDACTION" "AC" | Add-Content $Backup
Get-PowerValue "SUB_SLEEP" "STANDBYIDLE" "AC" | Add-Content $Backup
Get-PowerValue "SUB_BUTTONS" "LIDACTION" "DC" | Add-Content $Backup
Get-PowerValue "SUB_SLEEP" "STANDBYIDLE" "DC" | Add-Content $Backup

# Lid close -> Do nothing (0)
powercfg /SETACVALUEINDEX SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /SETDCVALUEINDEX SCHEME_CURRENT SUB_BUTTONS LIDACTION 0

# Disable sleep timeout (0 = never)
powercfg /CHANGE standby-timeout-ac 0
powercfg /CHANGE hibernate-timeout-ac 0
powercfg /CHANGE standby-timeout-dc 0
powercfg /CHANGE hibernate-timeout-dc 0

powercfg /SETACTIVE SCHEME_CURRENT

Write-Host "Power: lid-close and sleep disabled while crawl runs." -ForegroundColor Green
Write-Host "Backup saved to $Backup"
Write-Host "Revert after crawl: powershell -File scripts\disable_crawl_power.ps1"
