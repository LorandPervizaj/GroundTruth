<#
.SYNOPSIS
  Register the research host's Windows scheduled tasks for the current user.

.DESCRIPTION
  GroundTruth research runner
    At logon. Runs the GitHub self-hosted runner in this user session so jobs
    can reach Docker Desktop and C:\MetrikResearch. Restarts on failure.

  GroundTruth research host prepare
    At logon and every Monday before the research window, with wake-to-run.
    Runs prepare-host.ps1: Docker Desktop, research Postgres, runner task.

  Re-running replaces both tasks. No administrator rights are required.
#>
param(
    [string]$ResearchRoot = 'C:\MetrikResearch',
    # Before 03:00 UTC in both CET and CEST.
    [string]$WakeTime = '03:30'
)

$ErrorActionPreference = 'Stop'
$user = "$env:USERDOMAIN\$env:USERNAME"
$bin = Join-Path $ResearchRoot 'bin'
New-Item -ItemType Directory -Force -Path $bin | Out-Null
Copy-Item -Path (Join-Path $PSScriptRoot 'prepare-host.ps1') -Destination $bin -Force
$pwsh = (Get-Command pwsh).Source
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

$runnerSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew -StartWhenAvailable
$runnerAction = New-ScheduledTaskAction -Execute $pwsh `
    -Argument "-NoProfile -WindowStyle Hidden -Command `"& '$ResearchRoot\runner\run.cmd'; exit `$LASTEXITCODE`"" `
    -WorkingDirectory (Join-Path $ResearchRoot 'runner')
Register-ScheduledTask -TaskName 'GroundTruth research runner' -Force `
    -Action $runnerAction -Principal $principal -Settings $runnerSettings `
    -Trigger (New-ScheduledTaskTrigger -AtLogOn -User $user) | Out-Null

$prepareSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -MultipleInstances IgnoreNew
$prepareAction = New-ScheduledTaskAction -Execute $pwsh `
    -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$bin\prepare-host.ps1`" -ResearchRoot `"$ResearchRoot`""
$prepareTriggers = @(
    (New-ScheduledTaskTrigger -AtLogOn -User $user),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $WakeTime)
)
Register-ScheduledTask -TaskName 'GroundTruth research host prepare' -Force `
    -Action $prepareAction -Principal $principal -Settings $prepareSettings `
    -Trigger $prepareTriggers | Out-Null

Get-ScheduledTask -TaskName 'GroundTruth research*' | Select-Object TaskName, State
