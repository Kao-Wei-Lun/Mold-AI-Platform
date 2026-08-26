param(
    [string]$EnvFile = "release.env"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot $EnvFile

if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Release environment file not found: $envPath. Copy release.env.example and replace every CHANGE_ME value."
}

if ((Get-Content -LiteralPath $envPath -Raw) -match "CHANGE_ME") {
    throw "Release environment still contains CHANGE_ME placeholders."
}

Push-Location -LiteralPath $repoRoot
try {
    docker compose -f compose.yaml -f compose.release.yaml --env-file $envPath config --quiet
    if ($LASTEXITCODE -ne 0) {
        throw "Release Compose validation failed."
    }

    docker compose -f compose.yaml -f compose.release.yaml --env-file $envPath `
        run --rm --no-deps api python manage.py deployment_preflight --strict
    if ($LASTEXITCODE -ne 0) {
        throw "Application deployment preflight failed."
    }
}
finally {
    Pop-Location
}

Write-Host "Release preflight passed. External ChatGPT account/workspace and tunnel checks are still required."
