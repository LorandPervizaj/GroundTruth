#Requires -Version 7.0
param(
  [Parameter(Mandatory = $true)]
  [string]$BaseUrl
)

$ErrorActionPreference = "Stop"
$BaseUrl = $BaseUrl.TrimEnd("/")

function Hit([string]$Method, [string]$Path, $Body = $null, $Headers = $null) {
  $uri = "$BaseUrl$Path"
  $params = @{
    Uri = $uri
    Method = $Method
    UseBasicParsing = $true
    TimeoutSec = 60
  }
  if ($Headers) { $params.Headers = $Headers }
  if ($null -ne $Body) {
    $params.ContentType = "application/json"
    $params.Body = ($Body | ConvertTo-Json -Compress)
  }
  try {
    $r = Invoke-WebRequest @params
    Write-Host "$Method $Path -> $($r.StatusCode) $($r.Content.Substring(0, [Math]::Min(160, $r.Content.Length)))"
    return $r
  } catch {
    $resp = $_.Exception.Response
    $code = 0
    $text = $_.Exception.Message
    if ($resp) {
      try { $code = [int]$resp.StatusCode } catch { $code = 0 }
    }
    # Prefer curl for reliable non-2xx body capture on Windows PowerShell 7.
    $tmp = Join-Path $env:TEMP ("metrik-smoke-" + [guid]::NewGuid().ToString("n") + ".json")
    if ($Method -eq "GET") {
      $code = curl.exe -sS -m 60 -o $tmp -w "%{http_code}" $uri
    } elseif ($null -ne $Body) {
      $payload = Join-Path $env:TEMP ("metrik-smoke-body-" + [guid]::NewGuid().ToString("n") + ".json")
      Set-Content -Path $payload -Value ($Body | ConvertTo-Json -Compress) -NoNewline
      $code = curl.exe -sS -m 60 -o $tmp -w "%{http_code}" -X $Method $uri -H "content-type: application/json" --data-binary "@$payload"
    }
    if (Test-Path $tmp) { $text = Get-Content $tmp -Raw -ErrorAction SilentlyContinue }
    Write-Host "$Method $Path -> $code $($text.Substring(0, [Math]::Min(160, ($text ?? '').Length)))"
    return [pscustomobject]@{ StatusCode = [int]$code; Content = $text }
  }
}

Write-Host "=== AZURE BETA SMOKE $BaseUrl ==="
$h = Hit GET /api/health
if ($h.StatusCode -ne 200) { throw "health failed" }
$ready = Hit GET /api/ready
if ($ready.StatusCode -ne 200) { throw "ready failed" }

Hit GET /
Hit GET /api/meta
Hit GET "/api/search?q=ulpiana"
Hit GET /api/markets
Hit GET "/api/compare?neighborhoods=ulpiana,arberia"
Hit GET /api/lookup/neighborhood/ulpiana
$ry = Hit GET /api/rent-yield
Hit GET /api/reports/annual_data
foreach ($p in @("/statistics","/compare","/rent-yield","/valuate","/alerts","/contact")) {
  Hit GET $p | Out-Null
}

$alerts = Hit POST /api/alerts @{ email = "beta@example.com"; neighborhood_slug = "ulpiana" }
if ([int]$alerts.StatusCode -notin 503, 429) { throw "alerts should be unavailable or rate-limited" }

$valuate = Hit POST /api/valuate @{ neighborhood = "Ulpiana"; area_sqm = 70; valuation_type = "rent" }
if ([int]$valuate.StatusCode -ne 503) { throw "valuate should be 503 while disabled/unavailable" }

$badCtFile = Join-Path $env:TEMP "metrik-badct.txt"
Set-Content -Path $badCtFile -Value "x" -NoNewline
$badCt = curl.exe -sS -m 30 -o NUL -w "%{http_code}" -X POST "$BaseUrl/api/contact" -H "content-type: text/plain" --data-binary "@$badCtFile"
Write-Host "POST /api/contact wrong CT -> $badCt"
if ($badCt -ne "415") { throw "expected 415 for wrong content-type" }

Write-Host "AZURE_SMOKE_OK"
