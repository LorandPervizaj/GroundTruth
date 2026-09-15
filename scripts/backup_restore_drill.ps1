# Disposable backup/restore drill for Windows hosts (Docker required).
# Does NOT touch production volumes.
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$Work = Join-Path $Root ".tmp\backup_restore_drill"
$Image = if ($env:POSTGRES_IMAGE) { $env:POSTGRES_IMAGE } else { "postgres:16-alpine" }
$Container = "metrik-backup-drill-$PID"
$UserName = "drill"
$Password = "drill_password"
$DbName = "groundtruth"

function Cleanup {
  # Ignore missing container / already-removed state.
  cmd /c "docker rm -f `"$Container`" >nul 2>&1"
  if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
}


try {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI not found"
  }
  docker info 2>$null | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Docker daemon is not running"
  }

  Cleanup
  New-Item -ItemType Directory -Force -Path $Work | Out-Null

  Write-Host "==> Starting disposable Postgres ($Image)"
  docker run -d --name $Container `
    -e "POSTGRES_USER=$UserName" `
    -e "POSTGRES_PASSWORD=$Password" `
    -e "POSTGRES_DB=$DbName" `
    $Image | Out-Null

  Write-Host "==> Waiting for readiness"
  $ready = $false
  for ($i = 0; $i -lt 30; $i++) {
    docker exec $Container pg_isready -U $UserName -d $DbName 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 1
  }
  if (-not $ready) { throw "Postgres did not become ready" }

  Write-Host "==> Seeding fixture table + row"
  $seed = @"
CREATE TABLE product_submissions_drill (
  id serial PRIMARY KEY,
  kind text NOT NULL,
  payload jsonb NOT NULL
);
INSERT INTO product_submissions_drill (kind, payload)
VALUES ('contact', '{"email":"drill@example.com","message":"restore-me"}');
"@
  $seed | docker exec -i $Container psql -U $UserName -d $DbName | Out-Null

  $Dump = Join-Path $Work "postgres_drill.sql.gz"
  Write-Host "==> Creating backup at $Dump"
  $Sql = Join-Path $Work "postgres_drill.sql"
  docker exec $Container pg_dump -U $UserName -d $DbName --no-owner --no-acl |
    Out-File -FilePath $Sql -Encoding ascii
  uv run python -c "import gzip,pathlib; p=pathlib.Path(r'$Sql'); gzip.open(r'$Dump','wb').write(p.read_bytes()); print('backup_created', p.stat().st_size)"
  uv run python -c "import gzip; gzip.open(r'$Dump').read(16); print('backup_readable_ok')"

  Write-Host "==> Dropping data and restoring"
  "DROP TABLE product_submissions_drill;" | docker exec -i $Container psql -U $UserName -d $DbName | Out-Null
  uv run python -c "import gzip,subprocess; data=gzip.open(r'$Dump','rb').read(); subprocess.run(['docker','exec','-i','$Container','psql','-U','$UserName','-d','$DbName'], input=data, check=True); print('restore_applied')"

  $Count = docker exec $Container psql -U $UserName -d $DbName -Atc "SELECT count(*) FROM product_submissions_drill WHERE payload->>'email' = 'drill@example.com';"
  if ($Count.Trim() -ne "1") { throw "Restore failed, count=$Count" }
  Write-Host "Restore OK - recovered row count=$Count"

  Write-Host "==> Adversarial: corrupt backup must fail integrity check"
  $Corrupt = Join-Path $Work "postgres_drill_corrupt.sql.gz"
  Set-Content -Path $Corrupt -Value "not-a-gzip" -NoNewline
  # Native Python failure is exit-code based; try/catch does not catch it.
  $env:DRILL_CORRUPT = $Corrupt
  $py = Join-Path $Root ".venv\Scripts\python.exe"
  & $py -c "import gzip, os; gzip.open(os.environ['DRILL_CORRUPT']).read(); raise SystemExit('unexpected success')"
  if ($LASTEXITCODE -eq 0) { throw "Corrupt backup unexpectedly readable" }
  Write-Host "Corrupt backup correctly rejected"

  Write-Host "BACKUP_RESTORE_DRILL_PASSED"
}
finally {
  Cleanup
}
