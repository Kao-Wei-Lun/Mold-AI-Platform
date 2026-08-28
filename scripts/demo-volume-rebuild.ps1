param(
    [Parameter(Mandatory)][string]$TargetProjectName,
    [Parameter(Mandatory)][string]$Confirmation,
    [Parameter(Mandatory)][string]$SecondaryConfirmation,
    [switch]$CleanupAfterVerification
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "demo-ops-common.ps1")
$repoRoot = Get-DemoRepoRoot
$requiredConfirmation = "REBUILD ISOLATED DEMO VOLUMES"
if ($TargetProjectName -notmatch "^[a-z0-9][a-z0-9_-]{2,48}-rebuild-drill$") {
    throw "TargetProjectName must be a bounded lowercase name ending in -rebuild-drill."
}
if ($Confirmation -ne $requiredConfirmation) {
    throw "Confirmation must exactly equal '$requiredConfirmation'."
}
if ($SecondaryConfirmation -ne $TargetProjectName) {
    throw "SecondaryConfirmation must exactly equal TargetProjectName."
}

$composeArgs = @(
    "compose", "-p", $TargetProjectName, "-f", "compose.yaml", "-f",
    "compose.restore-drill.yaml"
)
$verification = $null
$queue = $null
Push-Location -LiteralPath $repoRoot
try {
    $existing = @(& docker @composeArgs ps -aq 2>$null)
    if ($existing.Count -gt 0) {
        throw "The isolated rebuild project already exists; choose a new TargetProjectName."
    }
    & docker @composeArgs up -d --build --wait --wait-timeout 120 `
        db redis qdrant api worker worker-cad
    if ($LASTEXITCODE -ne 0) { throw "Fresh isolated Demo services failed to start." }

    & docker @composeArgs exec -T api python manage.py seed_demo_data
    if ($LASTEXITCODE -ne 0) { throw "Fresh canonical Demo seed failed." }
    & docker @composeArgs exec -T api python manage.py seed_cad_demo --reindex
    if ($LASTEXITCODE -ne 0) { throw "Fresh Qdrant reconciliation failed." }

    $verificationJson = (& docker @composeArgs exec -T api `
        python manage.py demo_release_snapshot --json --strict | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Fresh-volume strict snapshot did not pass." }
    $verification = $verificationJson | ConvertFrom-Json

    $queueRaw = (& docker @composeArgs exec -T api python manage.py shell -c `
        "import json; from platform_core.tasks import echo; r=echo.apply_async(args=['volume-rebuild-ok'], queue='general'); print(json.dumps({'success':r.get(timeout=30)=='volume-rebuild-ok'}))" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Fresh-volume worker verification failed." }
    $queueJson = @($queueRaw -split "`r?`n" | Where-Object { $_.Trim().StartsWith("{") }) | Select-Object -Last 1
    if (-not $queueJson) { throw "Fresh-volume worker verification returned no JSON." }
    $queue = $queueJson | ConvertFrom-Json
    if (-not $queue.success) { throw "Fresh-volume worker did not complete the verification job." }
} finally {
    if ($CleanupAfterVerification) {
        Write-Host "Removing only isolated project '$TargetProjectName' and its rebuild-drill volumes."
        & docker @composeArgs down --volumes --remove-orphans
        if ($LASTEXITCODE -ne 0) { Write-Warning "Rebuild-drill cleanup needs manual review." }
    }
    Pop-Location
}

Write-Host "Isolated full Demo volume rebuild passed: project=$TargetProjectName, curated_cad=$($verification.datasets.curated_cad.ready), worker=$($queue.success)."
