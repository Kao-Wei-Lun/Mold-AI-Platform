param(
    [Parameter(Mandatory)][string]$TargetProjectName,
    [Parameter(Mandatory)][string]$Confirmation,
    [string]$OutputPath = "",
    [switch]$CleanupAfterVerification
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "demo-ops-common.ps1")
$repoRoot = Get-DemoRepoRoot
$requiredConfirmation = "RUN ISOLATED RECOVERY DRILL"
if ($TargetProjectName -notmatch "^[a-z0-9][a-z0-9_-]{2,48}-recovery-drill$") {
    throw "TargetProjectName must be a bounded lowercase name ending in -recovery-drill."
}
if ($Confirmation -ne $requiredConfirmation) {
    throw "Confirmation must exactly equal '$requiredConfirmation'."
}
if (-not $OutputPath) {
    $timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
    $OutputPath = Join-Path $repoRoot ".runtime\evidence\recovery-drill-$timestamp.json"
}
$resolvedOutputPath = [IO.Path]::GetFullPath($OutputPath)
$allowedEvidenceRoot = [IO.Path]::GetFullPath((Join-Path $repoRoot ".runtime\evidence"))
if (-not $resolvedOutputPath.StartsWith($allowedEvidenceRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputPath must remain under the repository .runtime/evidence directory."
}

$composeArgs = @(
    "compose", "-p", $TargetProjectName, "-f", "compose.yaml", "-f",
    "compose.restore-drill.yaml"
)
$baseline = $null
$degraded = $null
$recovered = $null
$taskId = ""
$queuedWhileStopped = $false
$workerRecovered = $false
Push-Location -LiteralPath $repoRoot
try {
    $existing = @(& docker @composeArgs ps -aq 2>$null)
    if ($existing.Count -gt 0) {
        throw "The isolated recovery project already exists; choose a new TargetProjectName."
    }
    & docker @composeArgs up -d --build --wait --wait-timeout 120 `
        db redis qdrant api worker worker-cad
    if ($LASTEXITCODE -ne 0) { throw "Isolated recovery services failed to start." }
    & docker @composeArgs exec -T api python manage.py seed_demo_data
    if ($LASTEXITCODE -ne 0) { throw "Recovery-drill seed failed." }
    & docker @composeArgs exec -T api python manage.py seed_cad_demo --reindex
    if ($LASTEXITCODE -ne 0) { throw "Recovery-drill initial index failed." }

    $baselineRaw = (& docker @composeArgs exec -T api python manage.py shell -c `
        "import json; from platform_core.health import collect_readiness; from platform_core.models import Artifact,FeatureSet,KnowledgeDocument; print(json.dumps({'readiness':collect_readiness(),'artifacts':Artifact.objects.count(),'features':FeatureSet.objects.count(),'knowledge':KnowledgeDocument.objects.count()}))" | Out-String).Trim()
    $baselineJson = @($baselineRaw -split "`r?`n" | Where-Object { $_.Trim().StartsWith("{") }) | Select-Object -Last 1
    $baseline = $baselineJson | ConvertFrom-Json
    if ($baseline.readiness.status -ne "ok") { throw "Recovery-drill baseline is not ready." }

    & docker @composeArgs stop qdrant
    if ($LASTEXITCODE -ne 0) { throw "Qdrant fault injection failed." }
    $degradedRaw = (& docker @composeArgs exec -T api python manage.py shell -c `
        "import json; from platform_core.health import collect_readiness; from platform_core.models import Artifact,FeatureSet,KnowledgeDocument; print(json.dumps({'readiness':collect_readiness(),'artifacts':Artifact.objects.count(),'features':FeatureSet.objects.count(),'knowledge':KnowledgeDocument.objects.count()}))" | Out-String).Trim()
    $degradedJson = @($degradedRaw -split "`r?`n" | Where-Object { $_.Trim().StartsWith("{") }) | Select-Object -Last 1
    $degraded = $degradedJson | ConvertFrom-Json
    $qdrantCheck = @($degraded.readiness.services | Where-Object { $_.name -eq "qdrant" }) | Select-Object -First 1
    if ($degraded.readiness.status -ne "degraded" -or $qdrantCheck.status -ne "error") {
        throw "Qdrant outage did not produce typed readiness degradation."
    }
    if ($degraded.artifacts -ne $baseline.artifacts -or
        $degraded.features -ne $baseline.features -or
        $degraded.knowledge -ne $baseline.knowledge) {
        throw "Canonical records changed during the Qdrant outage."
    }

    & docker @composeArgs start qdrant
    if ($LASTEXITCODE -ne 0) { throw "Qdrant restart failed." }
    & docker @composeArgs up -d --wait --wait-timeout 90 qdrant
    if ($LASTEXITCODE -ne 0) { throw "Qdrant did not become healthy after restart." }
    & docker @composeArgs exec -T api python manage.py seed_demo_data
    if ($LASTEXITCODE -ne 0) { throw "Knowledge re-index after Qdrant recovery failed." }
    & docker @composeArgs exec -T api python manage.py seed_cad_demo --reindex
    if ($LASTEXITCODE -ne 0) { throw "CAD re-index after Qdrant recovery failed." }
    $recoveredRaw = (& docker @composeArgs exec -T api `
        python manage.py demo_release_snapshot --json --strict | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Strict snapshot failed after Qdrant recovery." }
    $recovered = $recoveredRaw | ConvertFrom-Json

    & docker @composeArgs stop worker-cad
    if ($LASTEXITCODE -ne 0) { throw "CAD worker fault injection failed." }
    $taskRaw = (& docker @composeArgs exec -T api python manage.py shell -c `
        "from platform_core.tasks import echo; print(echo.apply_async(args=['worker-recovered'], queue='cad').id)" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Could not enqueue the worker recovery task." }
    $taskId = @($taskRaw -split "`r?`n" | Where-Object { $_ -match "^[0-9a-f-]{36}$" }) | Select-Object -Last 1
    if (-not $taskId) { throw "Worker recovery task ID was not returned." }
    $pendingRaw = (& docker @composeArgs exec -T api python manage.py shell -c `
        "from celery.result import AsyncResult; print('pending' if not AsyncResult('$taskId').ready() else 'unexpected-ready')" | Out-String).Trim()
    $queuedWhileStopped = $pendingRaw -match "pending"
    if (-not $queuedWhileStopped) { throw "Task did not remain queued while the CAD worker was stopped." }

    & docker @composeArgs start worker-cad
    if ($LASTEXITCODE -ne 0) { throw "CAD worker restart failed." }
    $workerRaw = (& docker @composeArgs exec -T api python manage.py shell -c `
        "from celery.result import AsyncResult; print(AsyncResult('$taskId').get(timeout=30))" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Queued task did not complete after CAD worker restart." }
    $workerRecovered = $workerRaw -match "worker-recovered"
    if (-not $workerRecovered) { throw "CAD worker returned an unexpected recovery result." }

    $evidence = [ordered]@{
        schema_version = "1.0"
        checked_at = (Get-Date).ToUniversalTime().ToString("o")
        status = "passed"
        environment = "isolated_compose_recovery_drill"
        qdrant = [ordered]@{
            typed_degradation_observed = $true
            canonical_records_preserved = $true
            reindex_and_strict_snapshot_passed = $true
        }
        worker = [ordered]@{
            task_queued_while_stopped = $queuedWhileStopped
            queued_task_completed_after_restart = $workerRecovered
        }
        datasets = [ordered]@{
            artifacts = $baseline.artifacts
            feature_sets = $baseline.features
            knowledge_documents = $baseline.knowledge
            curated_cad_ready = $recovered.datasets.curated_cad.ready
        }
        isolation = [ordered]@{
            host_ports_published = $false
            active_demo_modified = $false
            unrelated_projects_modified = $false
        }
        redaction = [ordered]@{ secrets_included = $false; urls_included = $false; ids_included = $false }
    }
    $outputDirectory = Split-Path -Parent $resolvedOutputPath
    if (-not (Test-Path -LiteralPath $outputDirectory)) {
        New-Item -ItemType Directory -Path $outputDirectory | Out-Null
    }
    $evidence | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $resolvedOutputPath -Encoding utf8
} finally {
    if ($CleanupAfterVerification) {
        Write-Host "Removing only isolated project '$TargetProjectName' and its recovery-drill volumes."
        & docker @composeArgs down --volumes --remove-orphans
        if ($LASTEXITCODE -ne 0) { Write-Warning "Recovery-drill cleanup needs manual review." }
    }
    Pop-Location
}

Write-Host "Recovery drill passed: Qdrant canonical state preserved/reindexed; queued CAD task completed after worker restart."
Write-Host "Sanitized evidence: $resolvedOutputPath"
