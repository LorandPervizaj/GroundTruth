<#
.SYNOPSIS
  Start the disposable pytest database and migrate it to head.

.DESCRIPTION
  Starts only the compose service postgres-test (127.0.0.1:15433, tmpfs data)
  and runs Alembic against it. Then run pytest with:

    $env:GROUNDTRUTH_TEST_DATABASE_URL = 'postgresql+psycopg://groundtruth_test:groundtruth_test@127.0.0.1:15433/groundtruth_test'
    uv run pytest

  or put GROUNDTRUTH_TEST_DATABASE_URL in .env. Tests refuse any database whose
  name lacks "test" and any database named by DATABASE_URL in .env or the
  research env file.
#>
$ErrorActionPreference = 'Stop'
$url = 'postgresql+psycopg://groundtruth_test:groundtruth_test@127.0.0.1:15433/groundtruth_test'

docker compose --profile test up -d --no-deps --wait postgres-test
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$previous = $env:DATABASE_URL
$previousEnvFile = $env:GROUNDTRUTH_ENV_FILE
try {
    $env:DATABASE_URL = $url
    $env:GROUNDTRUTH_ENV_FILE = $null
    uv run alembic upgrade head
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
} finally {
    $env:DATABASE_URL = $previous
    $env:GROUNDTRUTH_ENV_FILE = $previousEnvFile
}
Write-Output "Test database ready: $url"
