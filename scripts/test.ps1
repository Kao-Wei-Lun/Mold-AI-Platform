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

function Assert-UnifiedApplicationImage {
    param(
        [Parameter(Mandatory)][object]$Config,
        [Parameter(Mandatory)][string]$Profile
    )

    $applicationServices = @("api", "worker", "worker-cad", "mcp-gateway", "web")
    $applicationImages = @(
        $applicationServices |
            ForEach-Object { $Config.services.$_.image } |
            Where-Object { $_ } |
            Sort-Object -Unique
    )

    if ($applicationImages.Count -ne 1 -or $applicationImages[0] -notlike "mold-ai-platform-app:*") {
        throw "$Profile must resolve API, Web, MCP Gateway and workers to one mold-ai-platform-app image. Resolved: $($applicationImages -join ', ')"
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

Push-Location -LiteralPath (Join-Path $repoRoot "apps\sites-web")
try {
    npm run lint
    Assert-LastExitCode "Sites frontend lint"
    npm test
    Assert-LastExitCode "Sites frontend tests"
    npm run build
    Assert-LastExitCode "Sites frontend production build"
}
finally {
    Pop-Location
}

Push-Location -LiteralPath $repoRoot
try {
    docker compose config --quiet
    Assert-LastExitCode "Docker Compose validation"
    docker compose -f compose.yaml -f compose.release.yaml `
        --env-file release.env.example config --quiet
    Assert-LastExitCode "Release Docker Compose validation"
    $releaseConfigJson = docker compose -f compose.yaml -f compose.release.yaml `
        --env-file release.env.example config --format json
    Assert-LastExitCode "Release Docker Compose rendering"
    Assert-UnifiedApplicationImage -Config ($releaseConfigJson | ConvertFrom-Json) -Profile "Release"

    docker compose -f compose.yaml -f compose.sites-demo.yaml `
        --env-file .env.sites-demo.example config --quiet
    Assert-LastExitCode "Sites Demo Docker Compose validation"
    $sitesDemoConfigJson = docker compose -f compose.yaml -f compose.sites-demo.yaml `
        --env-file .env.sites-demo.example config --format json
    Assert-LastExitCode "Sites Demo Docker Compose rendering"
    Assert-UnifiedApplicationImage -Config ($sitesDemoConfigJson | ConvertFrom-Json) -Profile "Sites Demo"

    docker compose -f compose.yaml -f compose.restore-drill.yaml config --quiet
    Assert-LastExitCode "Restore drill Docker Compose validation"

    $parser = [System.Management.Automation.Language.Parser]
    $opsScripts = Get-ChildItem -LiteralPath (Join-Path $repoRoot "scripts") -Filter "demo-*.ps1"
    foreach ($opsScript in $opsScripts) {
        $tokens = $null
        $errors = $null
        $null = $parser::ParseFile($opsScript.FullName, [ref]$tokens, [ref]$errors)
        if ($errors.Count -gt 0) {
            throw "PowerShell syntax validation failed: $($opsScript.Name): $($errors[0].Message)"
        }
    }
}
finally {
    Pop-Location
}
