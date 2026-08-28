param(
    [Parameter(Mandatory)][string]$BackupDirectory,
    [Parameter(Mandatory)][string]$TargetProjectName,
    [switch]$CleanupAfterVerification
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "demo-ops-common.ps1")
$repoRoot = Get-DemoRepoRoot
$backupDir = [IO.Path]::GetFullPath($BackupDirectory)
$manifestPath = Join-Path $backupDir "backup-manifest.json"
$dumpPath = Join-Path $backupDir "postgres.dump"
$snapshotPath = Join-Path $backupDir "release-snapshot.json"
$artifactDir = Join-Path $backupDir "artifacts"
if ($TargetProjectName -notmatch "^[a-z0-9][a-z0-9_-]{2,48}-restore-drill$") {
    throw "TargetProjectName must be a bounded lowercase name ending in -restore-drill."
}
if (-not (Test-Path -LiteralPath $manifestPath) -or -not (Test-Path -LiteralPath $dumpPath)) {
    throw "Backup manifest or PostgreSQL dump is missing."
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.schema_version -ne "1.0") { throw "Unsupported backup manifest version." }
if ((Get-DemoFileSha256 -Path $dumpPath) -ne $manifest.database.sha256) {
    throw "PostgreSQL dump checksum mismatch."
}
if ((Get-DemoFileSha256 -Path $snapshotPath) -ne $manifest.release_snapshot.sha256) {
    throw "Release snapshot checksum mismatch."
}
if ($manifest.artifacts.included -and -not (Test-Path -LiteralPath $artifactDir)) {
    throw "The backup declares artifacts, but the artifact directory is missing."
}
foreach ($file in $manifest.artifacts.files) {
    $candidate = [IO.Path]::GetFullPath((Join-Path $artifactDir $file.path))
    if (-not $candidate.StartsWith([IO.Path]::GetFullPath($artifactDir))) {
        throw "Artifact manifest contains an unsafe path."
    }
    if (-not (Test-Path -LiteralPath $candidate) -or
        (Get-DemoFileSha256 -Path $candidate) -ne $file.sha256) {
        throw "Artifact checksum mismatch: $($file.path)"
    }
}

$composeArgs = @(
    "compose", "-p", $TargetProjectName, "-f", "compose.yaml", "-f",
    "compose.restore-drill.yaml"
)
$remoteDump = "/tmp/mold-ai-demo-restore.dump"
$verification = $null
Push-Location -LiteralPath $repoRoot
try {
    $existing = @(& docker @composeArgs ps -aq 2>$null)
    if ($existing.Count -gt 0) {
        throw "The isolated restore project already exists; choose a new TargetProjectName."
    }
    & docker @composeArgs up -d --wait --wait-timeout 90 db redis qdrant
    if ($LASTEXITCODE -ne 0) { throw "Restore dependencies failed to start." }
    & docker @composeArgs cp $dumpPath "db:$remoteDump"
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL dump could not be copied to the restore project." }
    & docker @composeArgs exec -T db pg_restore `
        --username=mold_ai --dbname=mold_ai --clean --if-exists --no-owner $remoteDump
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL restore failed." }
    & docker @composeArgs exec -T db rm -f $remoteDump
    if ($LASTEXITCODE -ne 0) { throw "Temporary restore dump cleanup failed." }

    & docker @composeArgs up -d api worker worker-cad
    if ($LASTEXITCODE -ne 0) { throw "Restored application services failed to start." }
    if ($manifest.artifacts.included) {
        & docker @composeArgs cp "$artifactDir/." "api:/data/artifacts"
        if ($LASTEXITCODE -ne 0) { throw "Artifact restore failed." }
        & docker @composeArgs exec -T --user root api chown -R app:app /data/artifacts
        if ($LASTEXITCODE -ne 0) { throw "Restored artifact ownership could not be normalized." }
    }
    & docker @composeArgs exec -T api python manage.py seed_demo_data
    if ($LASTEXITCODE -ne 0) { throw "Restored canonical Demo seed failed." }
    & docker @composeArgs exec -T api python manage.py seed_cad_demo --reindex
    if ($LASTEXITCODE -ne 0) { throw "Restored curated CAD Qdrant rebuild failed." }
    $verificationJson = (& docker @composeArgs exec -T api `
        python manage.py demo_release_snapshot --json --strict | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Restore verification did not pass." }
    $verification = $verificationJson | ConvertFrom-Json
    if (-not $verification.datasets.curated_cad.reconciled) {
        throw "Restored curated dataset is not reconciled."
    }
} finally {
    if ($CleanupAfterVerification) {
        Write-Host "Removing only isolated project '$TargetProjectName' and its restore-drill volumes."
        & docker @composeArgs down --volumes --remove-orphans
        if ($LASTEXITCODE -ne 0) { Write-Warning "Restore-drill cleanup needs manual review." }
    }
    Pop-Location
}

Write-Host "Restore drill passed: project=$TargetProjectName, curated_cad=$($verification.datasets.curated_cad.ready)."
