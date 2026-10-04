<#
.SYNOPSIS
  Install a new Telegram bot token everywhere GroundTruth and Metrik use it.

.DESCRIPTION
  Prompts for the token with hidden input, verifies it with Telegram, then
  updates:
    - C:\MetrikResearch\config\research.env      (research runner)
    - <repo>\.env                                 (local development)
    - GitHub environment secret azure-beta/TELEGRAM_BOT_TOKEN
    - Azure Container App secret telegram-bot-token, then restarts the active
      revision so the public app picks it up
  and re-registers the Telegram webhook if it no longer points at the app.

  The token never appears on screen, in logs, or in the repository. Revoke the
  old token in BotFather (/revoke) before running this.
#>
param(
    [string]$ResearchEnv = 'C:\MetrikResearch\config\research.env',
    [string]$Repository = 'LorandPervizaj/GroundTruth',
    [string]$GitHubEnvironment = 'azure-beta',
    [string]$ResourceGroup = 'rg-metrik-beta-eus2',
    [string]$ContainerApp = 'ca-metrik-api'
)

$ErrorActionPreference = 'Stop'
$RepoEnv = Join-Path (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path '.env'

function Get-EnvValue([string]$Path, [string]$Key) {
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        if ($line -match "^\s*$([regex]::Escape($Key))\s*=\s*(.*)$") {
            return $Matches[1].Trim().Trim("'").Trim('"')
        }
    }
    return $null
}

function Set-EnvValue([string]$Path, [string]$Key, [string]$Value, [string]$Quote) {
    $lines = [Collections.Generic.List[string]]::new([IO.File]::ReadAllLines($Path))
    $entry = "$Key=$Quote$Value$Quote"
    $index = -1
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ($lines[$i] -match "^\s*$([regex]::Escape($Key))\s*=") { $index = $i; break }
    }
    if ($index -ge 0) { $lines[$index] = $entry } else { $lines.Add($entry) }
    [IO.File]::WriteAllLines($Path, $lines, [Text.UTF8Encoding]::new($false))
}

function Invoke-Telegram([string]$Token, [string]$Method, [hashtable]$Body = @{}) {
    # Telegram puts the token in the URL path; keep it out of error messages.
    try {
        return Invoke-RestMethod -Method Post -Uri "https://api.telegram.org/bot$Token/$Method" -Body $Body
    } catch {
        $status = $_.Exception.Response.StatusCode.value__
        throw "Telegram $Method failed (HTTP $status)."
    }
}

$secure = Read-Host -AsSecureString 'Paste the new Telegram bot token (input is hidden)'
$token = [Net.NetworkCredential]::new('', $secure).Password.Trim()
$secure.Dispose()

try {
    if ($token -notmatch '^\d+:[A-Za-z0-9_-]{30,}$') { throw 'That does not look like a bot token (expected <digits>:<secret>).' }

    $oldToken = Get-EnvValue $ResearchEnv 'TELEGRAM_BOT_TOKEN'
    if ($oldToken -eq $token) { throw 'This is the same token that is already installed. Revoke it in BotFather and use the new one.' }

    $me = (Invoke-Telegram $token 'getMe').result
    Write-Host "Token verified for @$($me.username)." -ForegroundColor Green
    if ($oldToken -and ($oldToken.Split(':')[0] -ne [string]$me.id)) {
        $answer = Read-Host "This token belongs to a different bot than before (@$($me.username)). Continue? [y/N]"
        if ($answer -notin 'y', 'yes') { throw 'Cancelled; nothing was changed.' }
    }

    Set-EnvValue $ResearchEnv 'TELEGRAM_BOT_TOKEN' $token "'"
    Write-Host "Updated $ResearchEnv"
    if (Test-Path $RepoEnv) {
        Set-EnvValue $RepoEnv 'TELEGRAM_BOT_TOKEN' $token ''
        Write-Host "Updated $RepoEnv"
    }

    $token | gh secret set TELEGRAM_BOT_TOKEN --repo $Repository --env $GitHubEnvironment
    if ($LASTEXITCODE) { throw 'gh secret set failed.' }
    Write-Host "Updated GitHub secret $GitHubEnvironment/TELEGRAM_BOT_TOKEN"

    az containerapp secret set -g $ResourceGroup -n $ContainerApp --secrets "telegram-bot-token=$token" --only-show-errors | Out-Null
    if ($LASTEXITCODE) { throw 'az containerapp secret set failed.' }
    $revisions = az containerapp revision list -g $ResourceGroup -n $ContainerApp --query '[?properties.active].name' -o tsv
    foreach ($revision in $revisions) {
        az containerapp revision restart -g $ResourceGroup -n $ContainerApp --revision $revision --only-show-errors | Out-Null
        if ($LASTEXITCODE) { throw "Restarting revision $revision failed." }
    }
    Write-Host "Updated Azure secret telegram-bot-token and restarted $($revisions -join ', ')"

    $fqdn = az containerapp show -g $ResourceGroup -n $ContainerApp --query properties.configuration.ingress.fqdn -o tsv
    $webhookUrl = "https://$fqdn/api/telegram/webhook"
    $webhook = (Invoke-Telegram $token 'getWebhookInfo').result
    if ($webhook.url -ne $webhookUrl) {
        $webhookSecret = az containerapp secret show -g $ResourceGroup -n $ContainerApp --secret-name telegram-webhook-secret --query value -o tsv
        if (-not $webhookSecret) { throw 'Could not read telegram-webhook-secret from Azure.' }
        Invoke-Telegram $token 'setWebhook' @{ url = $webhookUrl; secret_token = $webhookSecret } | Out-Null
        $webhookSecret = $null
        Write-Host "Registered Telegram webhook $webhookUrl"
    } else {
        Write-Host 'Telegram webhook already points at the app.'
    }

    $chatId = Get-EnvValue $ResearchEnv 'TELEGRAM_CHAT_ID'
    Invoke-Telegram $token 'sendMessage' @{ chat_id = $chatId; text = 'GroundTruth: new Telegram bot token installed.' } | Out-Null
    Write-Host 'Sent a test message to your Telegram chat.' -ForegroundColor Green
} finally {
    $token = $null
    $oldToken = $null
    [GC]::Collect()
}
