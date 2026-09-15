#Requires -Version 7.0
<#
.SYNOPSIS
  Build the Metrik production image with verified release artifacts and push to ACR.

.DESCRIPTION
  Artifact strategy (Option A): bake a verified lookup_cache + annual_report into the
  immutable image tagged by git SHA. Do not use :latest as the only deploy identity.
#>
param(
  [Parameter(Mandatory = $true)]
  [string]$AcrLoginServer,

  [string]$Repository = "metrik-api",

  [string]$ImageTag = "",

  [switch]$SkipVerify
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

if (-not $ImageTag) {
  $ImageTag = (git rev-parse --short HEAD).Trim()
}

$Manifest = Join-Path $Root "reports\generated\lookup_cache\manifest.json"
$Annual = Join-Path $Root "data\api\annual_report.json"
if (-not (Test-Path $Manifest)) {
  throw "Missing $Manifest — run: uv run groundtruth release build-artifacts"
}
if (-not (Test-Path $Annual)) {
  throw "Missing $Annual — required release artifact"
}

if (-not $SkipVerify) {
  Write-Host "==> Verifying release artifacts"
  uv run groundtruth release verify-artifacts
}

$Image = "${AcrLoginServer}/${Repository}:${ImageTag}"
Write-Host "==> Building $Image (artifacts baked into image)"
docker build -t $Image -f Dockerfile .

Write-Host "==> Confirm research tooling absent"
docker run --rm --entrypoint uv $Image run python -c `
  "import importlib.util as u; assert u.find_spec('scrapy') is None; assert u.find_spec('playwright') is None; assert u.find_spec('fastapi') is not None"

Write-Host "==> Azure ACR login"
az acr login --name ($AcrLoginServer.Split('.')[0]) | Out-Null

Write-Host "==> Push $Image"
docker push $Image

$Digest = docker inspect --format='{{index .RepoDigests 0}}' $Image
Write-Host "PUSHED_IMAGE=$Image"
Write-Host "IMAGE_DIGEST=$Digest"
