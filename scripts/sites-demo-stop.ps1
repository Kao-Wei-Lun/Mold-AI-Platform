param([string]$EnvFile = ".env.sites-demo")

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot $EnvFile
if (-not (Test-Path -LiteralPath $envPath)) { throw "Sites Demo environment file not found: $envPath" }

Push-Location -LiteralPath $repoRoot
try {
    docker compose -f compose.yaml -f compose.sites-demo.yaml --env-file $envPath down
    if ($LASTEXITCODE -ne 0) { throw "Sites Demo containers did not stop cleanly." }
} finally { Pop-Location }
Write-Host "Sites Demo stopped. Persistent Docker volumes were retained."
