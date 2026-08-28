param(
    [ValidateSet("operations", "datasets", "full-demo-volume")][string]$Mode = "operations",
    [string]$EnvFile = ".env.sites-demo",
    [string]$Confirmation = "",
    [string]$SecondaryConfirmation = "",
    [string]$TargetProjectName = "",
    [switch]$LocalDevelopment,
    [switch]$SkipBackup,
    [switch]$DryRun,
    [switch]$CleanupAfterVerification
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "demo-ops-common.ps1")
$repoRoot = Get-DemoRepoRoot
$envPath = Join-Path $repoRoot $EnvFile
$composeArgs = @(Get-DemoComposeArgs -EnvPath $envPath -LocalDevelopment:$LocalDevelopment)
$confirmationByMode = @{
    operations = "RESET OPERATIONS"
    datasets = "RESET DATASETS"
    "full-demo-volume" = "REBUILD ISOLATED DEMO VOLUMES"
}
$requiredConfirmation = $confirmationByMode[$Mode]

if ($Mode -eq "full-demo-volume") {
    if ($TargetProjectName -notmatch "^[a-z0-9][a-z0-9_-]{2,48}-rebuild-drill$") {
        throw "TargetProjectName must be a bounded lowercase name ending in -rebuild-drill."
    }
    if ($DryRun -or -not $Confirmation) {
        Write-Host "DRY RUN: a fresh isolated Compose project '$TargetProjectName' would be built without host ports."
        Write-Host "The active Demo, Secure MCP Tunnel, repository, env files and all unrelated Docker projects remain unchanged."
        Write-Host "Execute with -Confirmation '$requiredConfirmation' -SecondaryConfirmation '$TargetProjectName'."
        exit 0
    }
    if ($Confirmation -ne $requiredConfirmation) {
        throw "Confirmation must exactly equal '$requiredConfirmation'."
    }
    if ($SecondaryConfirmation -ne $TargetProjectName) {
        throw "SecondaryConfirmation must exactly equal TargetProjectName."
    }
    if ($SkipBackup) {
        throw "full-demo-volume always requires a backup; -SkipBackup is not allowed."
    }
    $backupParameters = @{
        EnvFile = $EnvFile
        LocalDevelopment = $LocalDevelopment
    }
    & (Join-Path $PSScriptRoot "demo-backup.ps1") @backupParameters | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Mandatory pre-rebuild backup failed." }
    & (Join-Path $PSScriptRoot "demo-volume-rebuild.ps1") `
        -TargetProjectName $TargetProjectName `
        -Confirmation $requiredConfirmation `
        -SecondaryConfirmation $SecondaryConfirmation `
        -CleanupAfterVerification:$CleanupAfterVerification
    if ($LASTEXITCODE -ne 0) { throw "Isolated full Demo volume rebuild failed." }
    exit 0
}

$managementCommand = if ($Mode -eq "datasets") {
    "demo_reset_datasets"
} else {
    "demo_reset_operations"
}

if ($DryRun -or -not $Confirmation) {
    Push-Location -LiteralPath $repoRoot
    try {
        & docker @composeArgs exec -T api python manage.py $managementCommand --json
        if ($LASTEXITCODE -ne 0) { throw "$Mode reset preview failed." }
    } finally { Pop-Location }
    Write-Host "No data was changed. Execute with -Confirmation '$requiredConfirmation'."
    exit 0
}
if ($Confirmation -ne $requiredConfirmation) {
    throw "Confirmation must exactly equal '$requiredConfirmation'."
}
if (-not $SkipBackup) {
    $backupParameters = @{
        EnvFile = $EnvFile
        LocalDevelopment = $LocalDevelopment
    }
    & (Join-Path $PSScriptRoot "demo-backup.ps1") @backupParameters | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Mandatory pre-reset backup failed." }
} else {
    Write-Warning "Backup explicitly skipped by the operator."
}

Push-Location -LiteralPath $repoRoot
try {
    & docker @composeArgs exec -T api python manage.py $managementCommand `
        --confirm $requiredConfirmation --json
    if ($LASTEXITCODE -ne 0) { throw "$Mode reset failed." }
    & docker @composeArgs exec -T api python manage.py seed_demo_data
    if ($LASTEXITCODE -ne 0) { throw "Post-reset canonical seed failed." }
    if ($Mode -eq "datasets") {
        & docker @composeArgs exec -T api python manage.py seed_cad_demo --reindex
        if ($LASTEXITCODE -ne 0) { throw "Post-reset Qdrant reconciliation failed." }
    }
} finally { Pop-Location }

$statusParameters = @{
    EnvFile = $EnvFile
    Json = $true
    LocalDevelopment = $LocalDevelopment
}
$status = (& (Join-Path $PSScriptRoot "demo-status.ps1") @statusParameters | Out-String) | ConvertFrom-Json
if ($status.api.readiness -ne "ok" -or -not $status.datasets.curated_cad.reconciled) {
    throw "Post-reset status verification failed."
}
if ($Mode -eq "datasets") {
    Write-Host "Demo datasets reset completed and canonical datasets were reseeded; configuration, audit history and secrets were preserved."
} else {
    Write-Host "Demo operations reset completed; curated datasets and secrets were preserved."
}
