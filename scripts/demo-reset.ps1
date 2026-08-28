param(
    [ValidateSet("operations")][string]$Mode = "operations",
    [string]$EnvFile = ".env.sites-demo",
    [string]$Confirmation = "",
    [switch]$LocalDevelopment,
    [switch]$SkipBackup,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "demo-ops-common.ps1")
$repoRoot = Get-DemoRepoRoot
$envPath = Join-Path $repoRoot $EnvFile
$composeArgs = @(Get-DemoComposeArgs -EnvPath $envPath -LocalDevelopment:$LocalDevelopment)

if ($DryRun -or -not $Confirmation) {
    Push-Location -LiteralPath $repoRoot
    try {
        & docker @composeArgs exec -T api python manage.py demo_reset_operations --json
        if ($LASTEXITCODE -ne 0) { throw "Operations reset preview failed." }
    } finally { Pop-Location }
    Write-Host "No data was changed. Execute with -Confirmation 'RESET OPERATIONS'."
    exit 0
}
if ($Confirmation -ne "RESET OPERATIONS") {
    throw "Confirmation must exactly equal 'RESET OPERATIONS'."
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
    & docker @composeArgs exec -T api python manage.py demo_reset_operations `
        --confirm "RESET OPERATIONS" --json
    if ($LASTEXITCODE -ne 0) { throw "Operations reset failed." }
    & docker @composeArgs exec -T api python manage.py seed_demo_data
    if ($LASTEXITCODE -ne 0) { throw "Post-reset canonical seed failed." }
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
Write-Host "Demo operations reset completed; curated datasets and secrets were preserved."
