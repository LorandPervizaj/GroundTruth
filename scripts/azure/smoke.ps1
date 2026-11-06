#Requires -Version 7.0
param(
  [Parameter(Mandatory=$true)][string]$BaseUrl,
  [Parameter(Mandatory=$true)][string]$ExpectedReleaseId,
  [Parameter(Mandatory=$true)][string]$ExpectedRevision,
  [Parameter(Mandatory=$true)][string]$ExpectedServingSha,
  [Parameter(Mandatory=$true)][string]$ExpectedImage
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$env:PYTHONPATH = Join-Path $root 'src'
$arguments = @((Join-Path $PSScriptRoot 'read_smoke.py'), '--url', $BaseUrl, '--release-id', $ExpectedReleaseId)
if ($ExpectedRevision) { $arguments += @('--revision', $ExpectedRevision, '--serving-sha', $ExpectedServingSha, '--image', $ExpectedImage) }
& python @arguments
if ($LASTEXITCODE) { throw 'Critical read-only smoke gate failed' }
