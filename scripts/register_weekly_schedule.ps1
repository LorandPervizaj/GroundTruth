# Register a Windows Task Scheduler job to run the weekly crawl every 7 days.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\register_weekly_schedule.ps1
#
# Remove:
#   Unregister-ScheduledTask -TaskName "GroundTruth-WeeklyCrawl" -Confirm:$false

param(
    [string]$TaskName = "GroundTruth-WeeklyCrawl",
    [string]$Time = "02:00"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Runner = Join-Path $RepoRoot "scripts\run_weekly_crawl.ps1"

if (-not (Test-Path $Runner)) {
    Write-Error "Missing runner: $Runner"
    exit 1
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`"" `
    -WorkingDirectory $RepoRoot

# Every 7 days starting tomorrow at $Time
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $Time -WeeksInterval 1

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 12)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "GroundTruth weekly crawl: all sources, 7-day window, ETL + analytics" `
    -Force | Out-Null

Write-Host "Registered scheduled task: $TaskName" -ForegroundColor Green
Write-Host "  Runs: every Monday at $Time"
Write-Host "  Command: $Runner"
Write-Host ""
Write-Host "Test now: powershell -File scripts\run_weekly_crawl.ps1 -Force"
