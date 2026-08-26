$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "services\platform-api"
$pythonExe = Join-Path $backendDir ".venv\Scripts\python.exe"

function Assert-LastExitCode {
    param([Parameter(Mandatory)][string]$Step)

    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE."
    }
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Backend virtual environment not found. Run scripts/dev.ps1 first."
}

Push-Location -LiteralPath $backendDir
try {
    & $pythonExe -m ruff check .
    Assert-LastExitCode "Backend lint"
    & $pythonExe -m ruff format --check .
    Assert-LastExitCode "Backend formatting"
    & $pythonExe manage.py check
    Assert-LastExitCode "Django system check"
    & $pythonExe manage.py makemigrations --check
    Assert-LastExitCode "Django migration drift check"
    & $pythonExe -m pytest
    Assert-LastExitCode "Backend tests"
}
finally {
    Pop-Location
}

Push-Location -LiteralPath (Join-Path $repoRoot "apps\web")
try {
    npm run typecheck
    Assert-LastExitCode "Frontend type check"
    npm test
    Assert-LastExitCode "Frontend tests"
    npm run build
    Assert-LastExitCode "Frontend production build"
}
finally {
    Pop-Location
}

Push-Location -LiteralPath $repoRoot
try {
    docker compose config --quiet
    Assert-LastExitCode "Docker Compose validation"
}
finally {
    Pop-Location
}
