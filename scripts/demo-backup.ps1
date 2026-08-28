param(
    [string]$EnvFile = ".env.sites-demo",
    [string]$OutputRoot = ".runtime\backups",
    [switch]$LocalDevelopment,
    [switch]$MetadataOnly
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "demo-ops-common.ps1")
$repoRoot = Get-DemoRepoRoot
$envPath = Join-Path $repoRoot $EnvFile
$composeArgs = @(Get-DemoComposeArgs -EnvPath $envPath -LocalDevelopment:$LocalDevelopment)
$dbName = if ($LocalDevelopment) { "mold_ai" } else { Get-DemoEnvValue -Path $envPath -Name "POSTGRES_DB" }
$dbUser = if ($LocalDevelopment) { "mold_ai" } else { Get-DemoEnvValue -Path $envPath -Name "POSTGRES_USER" }
if (-not $dbName) { $dbName = "mold_ai" }
if (-not $dbUser) { $dbUser = "mold_ai" }
if ($dbName -notmatch "^[A-Za-z0-9_]+$" -or $dbUser -notmatch "^[A-Za-z0-9_]+$") {
    throw "Database name and user must contain only letters, numbers, and underscores."
}

$resolvedOutputRoot = if ([IO.Path]::IsPathRooted($OutputRoot)) {
    [IO.Path]::GetFullPath($OutputRoot)
} else { [IO.Path]::GetFullPath((Join-Path $repoRoot $OutputRoot)) }
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$backupDir = Join-Path $resolvedOutputRoot "mold-ai-demo-$timestamp"
New-Item -ItemType Directory -Path $backupDir | Out-Null
$dumpPath = Join-Path $backupDir "postgres.dump"
$snapshotPath = Join-Path $backupDir "release-snapshot.json"
$artifactDir = Join-Path $backupDir "artifacts"
$manifestPath = Join-Path $backupDir "backup-manifest.json"
$remoteDump = "/tmp/mold-ai-demo-backup.dump"

Push-Location -LiteralPath $repoRoot
try {
    & docker @composeArgs exec -T db pg_dump `
        --username=$dbUser --dbname=$dbName --format=custom --file=$remoteDump
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL logical backup failed." }
    & docker @composeArgs cp "db:$remoteDump" $dumpPath
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL dump could not be copied from the container." }
    & docker @composeArgs exec -T db rm -f $remoteDump
    if ($LASTEXITCODE -ne 0) { throw "Temporary database dump cleanup failed." }

    $snapshotJson = (& docker @composeArgs exec -T api `
        python manage.py demo_release_snapshot --json | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Release metadata snapshot failed." }
    $null = $snapshotJson | ConvertFrom-Json
    [IO.File]::WriteAllText($snapshotPath, $snapshotJson, [Text.UTF8Encoding]::new($false))

    if (-not $MetadataOnly) {
        New-Item -ItemType Directory -Path $artifactDir | Out-Null
        & docker @composeArgs cp "api:/data/artifacts/." $artifactDir
        if ($LASTEXITCODE -ne 0) { throw "Artifact backup failed." }
    }

    $imageRows = @(& docker @composeArgs images --format json 2>$null)
} finally { Pop-Location }

$artifactFiles = @()
if (Test-Path -LiteralPath $artifactDir) {
    $artifactPrefix = $artifactDir.TrimEnd("\") + "\"
    $artifactFiles = @(Get-ChildItem -LiteralPath $artifactDir -File -Recurse | ForEach-Object {
        [ordered]@{
            path = $_.FullName.Substring($artifactPrefix.Length).Replace("\", "/")
            size_bytes = $_.Length
            sha256 = Get-DemoFileSha256 -Path $_.FullName
        }
    })
}
$git = Get-DemoGitState -RepoRoot $repoRoot
$imageInventory = @($imageRows | ForEach-Object {
    try { $_ | ConvertFrom-Json } catch { [ordered]@{ raw = $_ } }
})
$manifest = [ordered]@{
    schema_version = "1.0"
    backup_type = if ($MetadataOnly) { "metadata_and_database" } else { "full_demo" }
    created_at = (Get-Date).ToUniversalTime().ToString("o")
    source = [ordered]@{ commit = $git.commit; branch = $git.branch; working_tree_clean = $git.clean }
    database = [ordered]@{
        file = "postgres.dump"
        format = "postgres_custom"
        sha256 = Get-DemoFileSha256 -Path $dumpPath
    }
    release_snapshot = [ordered]@{
        file = "release-snapshot.json"
        sha256 = Get-DemoFileSha256 -Path $snapshotPath
    }
    artifacts = [ordered]@{
        included = -not $MetadataOnly
        file_count = $artifactFiles.Count
        files = $artifactFiles
    }
    images = $imageInventory
    qdrant_restore_policy = "rebuild_from_canonical_feature_sets"
    excluded_sensitive_material = @(
        "environment_files", "api_keys", "demo_bearer_token", "tunnel_runtime_key",
        "browser_session_storage"
    )
    restore_command = ".\scripts\demo-restore.ps1 -BackupDirectory <path> -TargetProjectName mold-ai-verify-restore-drill"
}
[IO.File]::WriteAllText(
    $manifestPath,
    ($manifest | ConvertTo-Json -Depth 12),
    [Text.UTF8Encoding]::new($false)
)
Write-Host "Demo backup completed: $backupDir"
Write-Host "Secrets were excluded; artifact files included=$(-not $MetadataOnly)."
Write-Output $backupDir
