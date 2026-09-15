#Requires -Version 7.0
<#
.SYNOPSIS
  Deploy Metrik Azure beta infrastructure (registry → image → full stack).

.NOTES
  Secrets are prompted or read from environment variables — never committed.
  Required env (or prompts):
    METRIK_AZURE_POSTGRES_PASSWORD
    METRIK_AZURE_HEALTH_CHECK_TOKEN
  Optional:
    METRIK_AZURE_SENTRY_DSN
    METRIK_AZURE_INGRESS_IP_ALLOWLIST  (comma-separated CIDRs for invite-only)
#>
param(
  [string]$SubscriptionId = "",
  [string]$ResourceGroup = "rg-metrik-beta-eus2",
  [string]$Location = "eastus2",
  [string]$NameSuffix = "",
  [string]$EnvironmentName = "beta"
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

function Require-Secret([string]$Name, [int]$MinLen = 24) {
  $val = [Environment]::GetEnvironmentVariable($Name)
  if ([string]::IsNullOrWhiteSpace($val)) {
    $secure = Read-Host -AsSecureString "Enter $Name"
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $val = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
  }
  if ([string]::IsNullOrWhiteSpace($val) -or $val.Length -lt $MinLen) {
    throw "$Name must be set (min length $MinLen)"
  }
  if ($val -match "replace-me|changeme") {
    throw "$Name looks like a placeholder"
  }
  return $val
}

Write-Host "==> Azure account"
az account show -o table
if ($SubscriptionId) {
  az account set --subscription $SubscriptionId
}

if (-not $NameSuffix) {
  $NameSuffix = -join ((48..57 + 97..122) | Get-Random -Count 6 | ForEach-Object { [char]$_ })
}

$PostgresPassword = Require-Secret "METRIK_AZURE_POSTGRES_PASSWORD" 16
$HealthToken = Require-Secret "METRIK_AZURE_HEALTH_CHECK_TOKEN" 24
$SentryDsn = [Environment]::GetEnvironmentVariable("METRIK_AZURE_SENTRY_DSN")
if ($null -eq $SentryDsn) { $SentryDsn = "" }
$IpAllow = [Environment]::GetEnvironmentVariable("METRIK_AZURE_INGRESS_IP_ALLOWLIST")
if ($null -eq $IpAllow) { $IpAllow = "" }

Write-Host "==> Resource group $ResourceGroup ($Location)"
az group create --name $ResourceGroup --location $Location -o table | Out-Null

Write-Host "==> Deploy registry + identity"
$regOut = az deployment group create `
  --resource-group $ResourceGroup `
  --name "metrik-registry-$EnvironmentName" `
  --template-file "$Root\infra\azure\registry.bicep" `
  --parameters environmentName=$EnvironmentName nameSuffix=$NameSuffix location=$Location `
  --query properties.outputs -o json | ConvertFrom-Json

$AcrLoginServer = $regOut.acrLoginServer.value
$AcrName = $regOut.acrName.value
Write-Host "ACR=$AcrLoginServer"

Write-Host "==> Build and push immutable image"
& "$Root\scripts\azure\build-push.ps1" -AcrLoginServer $AcrLoginServer
$ImageTag = (git rev-parse --short HEAD).Trim()
$ContainerImage = "${AcrLoginServer}/metrik-api:${ImageTag}"

# Provisional PUBLIC_BASE_URL; updated after FQDN is known.
$PublicBaseUrl = "https://localhost"

Write-Host "==> Deploy Container Apps + PostgreSQL"
$deployArgs = @(
  "deployment", "group", "create",
  "--resource-group", $ResourceGroup,
  "--name", "metrik-main-$EnvironmentName",
  "--template-file", "$Root\infra\azure\main.bicep",
  "--parameters",
  "environmentName=$EnvironmentName",
  "nameSuffix=$NameSuffix",
  "location=$Location",
  "containerImage=$ContainerImage",
  "publicBaseUrl=$PublicBaseUrl",
  "postgresAdminPassword=$PostgresPassword",
  "healthCheckToken=$HealthToken",
  "sentryDsn=$SentryDsn",
  "ingressIpAllowList=$IpAllow",
  "requireSentryDsn=false"
)
$mainOut = az @deployArgs --query properties.outputs -o json | ConvertFrom-Json

$Fqdn = $mainOut.containerAppFqdn.value
$AppUrl = $mainOut.containerAppDefaultUrl.value
Write-Host "APP_URL=$AppUrl"

Write-Host "==> Set PUBLIC_BASE_URL to real FQDN and restart revision"
az containerapp update `
  --name $mainOut.containerAppName.value `
  --resource-group $ResourceGroup `
  --set-env-vars "PUBLIC_BASE_URL=$AppUrl" `
  -o none

Write-Host "==> Wait for readiness"
$ready = $false
for ($i = 0; $i -lt 36; $i++) {
  try {
    $r = Invoke-WebRequest -Uri "$AppUrl/api/ready" -UseBasicParsing -TimeoutSec 20
    if ($r.StatusCode -eq 200) { $ready = $true; break }
  } catch {
    Start-Sleep -Seconds 10
  }
  Start-Sleep -Seconds 10
}
if (-not $ready) {
  Write-Warning "Readiness not yet 200 — inspect logs: az containerapp logs show -n ca-metrik-api -g $ResourceGroup --follow"
} else {
  Write-Host "READY_OK $AppUrl/api/ready"
}

Write-Host @"

DEPLOYMENT_SUMMARY
  resource_group=$ResourceGroup
  acr=$AcrName ($AcrLoginServer)
  image=$ContainerImage
  app_url=$AppUrl
  postgres=$($mainOut.postgresFqdn.value)
  name_suffix=$NameSuffix

Next:
  1. Run scripts/azure/smoke.ps1 -BaseUrl $AppUrl
  2. Optional custom domain: see docs/AZURE_BETA.md
  3. Record results in QA.md
"@
