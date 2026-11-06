# Local test fixture only. No Docker, Azure login, external interface or real keys.
param([ValidateSet('Start','Restart','Stop')][string]$Mode = 'Start')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dir = Join-Path $root '.tmp/table-emulator'
$script = Join-Path $dir 'node_modules/azurite/dist/src/table/main.js'
$stateFile = Join-Path $dir 'owned-process.json'
if (-not (Test-Path -LiteralPath $script)) { throw 'Install the pinned local Azurite test dependency first' }
if (Test-Path -LiteralPath $stateFile) {
  $state = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
  $owned = Get-CimInstance Win32_Process -Filter "ProcessId=$($state.process_id)"
  if ($owned) {
    if ($owned.Name -ne 'node.exe' -or -not $owned.CommandLine.Contains($script)) { throw 'Fixture PID identity mismatch; refusing to stop' }
    if ($Mode -eq 'Start') { throw 'Owned fixture is already running' }
    Stop-Process -Id $state.process_id -ErrorAction Stop
    Wait-Process -Id $state.process_id -Timeout 10 -ErrorAction SilentlyContinue
  }
}
if ($Mode -eq 'Stop') { exit 0 }
$env:AZURITE_ACCOUNTS = 'localmetrik:' + [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes(('0' * 32)))
$data = Join-Path $dir 'data'
New-Item -ItemType Directory -Force -Path $data | Out-Null
$node = (Get-Command node.exe).Source
$fixtureProcess = Start-Process -FilePath $node -ArgumentList @($script,'--tableHost','127.0.0.1','--tablePort','27402','--location',$data,'--silent','--skipApiVersionCheck') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $dir 'stdout.log') -RedirectStandardError (Join-Path $dir 'stderr.log')
@{ process_id = $fixtureProcess.Id; script = $script; loopback_port = 27402 } | ConvertTo-Json | Set-Content -LiteralPath $stateFile
Write-Output 'Owned loopback Table fixture started; all data is disposable local test state.'
