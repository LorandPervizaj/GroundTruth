<#
.SYNOPSIS
  Make the local research host ready for the self-hosted GitHub runner.

.DESCRIPTION
  Starts Docker Desktop if its engine is not answering, starts only the
  research Postgres container, and starts the runner task if the runner
  listener is not running. It never starts crawlers or the pipeline; the
  GitHub workflow owns all GroundTruth logic.
#>
param(
    [string]$ResearchRoot = 'C:\MetrikResearch',
    [string]$PostgresContainer = 'groundtruth-postgres',
    [string]$RunnerTask = 'GroundTruth research runner',
    [int]$DockerTimeoutSeconds = 300
)

$ErrorActionPreference = 'Stop'
$log = Join-Path $ResearchRoot 'logs\prepare-host.log'
New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null

function Write-Log([string]$Message) {
    "$(Get-Date -Format o) $Message" | Add-Content -Path $log -Encoding utf8
}

function Test-DockerEngine {
    docker info --format '{{.ServerVersion}}' *> $null
    return $LASTEXITCODE -eq 0
}

Write-Log 'prepare-host started'

if (-not (Test-DockerEngine)) {
    $desktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    Write-Log 'Docker engine not answering; starting Docker Desktop'
    Start-Process -FilePath $desktop
    $deadline = (Get-Date).AddSeconds($DockerTimeoutSeconds)
    while (-not (Test-DockerEngine)) {
        if ((Get-Date) -gt $deadline) {
            Write-Log 'Docker engine did not start in time'
            exit 1
        }
        Start-Sleep -Seconds 5
    }
}
Write-Log 'Docker engine ready'

$state = docker inspect --format '{{.State.Running}}' $PostgresContainer 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Log "Container $PostgresContainer does not exist; refusing to create one"
    exit 1
}
if ($state -ne 'true') {
    docker start $PostgresContainer | Out-Null
    Write-Log "Started $PostgresContainer"
}

if (-not (Get-Process -Name 'Runner.Listener' -ErrorAction SilentlyContinue)) {
    Start-ScheduledTask -TaskName $RunnerTask
    Write-Log "Started scheduled task '$RunnerTask'"
}
Write-Log 'prepare-host finished'
