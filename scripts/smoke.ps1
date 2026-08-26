$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $repoRoot

$deadline = (Get-Date).AddSeconds(60)
$ready = $null

while ((Get-Date) -lt $deadline) {
    try {
        $ready = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/ready"
        if ($ready.status -eq "ok") {
            break
        }
    }
    catch {
        Start-Sleep -Seconds 2
        continue
    }

    Start-Sleep -Seconds 2
}

if ($null -eq $ready -or $ready.status -ne "ok") {
    throw "API readiness did not become healthy within 60 seconds."
}

$failedServices = @($ready.services | Where-Object { $_.status -ne "ok" })
if ($failedServices.Count -gt 0) {
    throw "One or more API dependencies are unhealthy."
}

$live = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/health/live"
if ($live.status -ne "ok") {
    throw "API liveness check failed."
}

$web = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing
if ($web.StatusCode -ne 200 -or -not $web.Content.Contains("Mold AI Platform")) {
    throw "Web UI smoke check failed."
}

$workerResult = docker compose exec -T api python manage.py shell -c `
    "from platform_core.tasks import echo; result=echo.apply_async(args=['smoke-ok'], queue='general'); print(result.get(timeout=10))"

if ($LASTEXITCODE -ne 0 -or ($workerResult -join "`n") -notmatch "smoke-ok") {
    throw "Celery worker smoke check failed."
}

$cadFile = Join-Path ([System.IO.Path]::GetTempPath()) "mold-ai-smoke-$([guid]::NewGuid()).stl"
$cadContent = @"
solid tetrahedron
facet normal 0 0 -1
outer loop
vertex 0 0 0
vertex 0 1 0
vertex 1 0 0
endloop
endfacet
facet normal 0 -1 0
outer loop
vertex 0 0 0
vertex 1 0 0
vertex 0 0 1
endloop
endfacet
facet normal -1 0 0
outer loop
vertex 0 0 0
vertex 0 0 1
vertex 0 1 0
endloop
endfacet
facet normal 1 1 1
outer loop
vertex 1 0 0
vertex 0 1 0
vertex 0 0 1
endloop
endfacet
endsolid tetrahedron
"@

try {
    [System.IO.File]::WriteAllText($cadFile, $cadContent, [System.Text.UTF8Encoding]::new($false))
    $idempotencyKey = "stage2-smoke-$([guid]::NewGuid())"
    $uploadJson = curl.exe --silent --show-error --fail `
        --form "file=@$cadFile;type=model/stl" `
        --form "artifact_name=Stage 2 smoke tetrahedron" `
        --form "idempotency_key=$idempotencyKey" `
        "http://localhost:8000/api/v1/cad-artifacts"

    if ($LASTEXITCODE -ne 0) {
        throw "CAD upload smoke check failed."
    }
    $upload = $uploadJson | ConvertFrom-Json
    $cadDeadline = (Get-Date).AddSeconds(90)
    $cadJob = $null
    while ((Get-Date) -lt $cadDeadline) {
        $cadJob = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/jobs/$($upload.job_id)"
        if ($cadJob.state -in @("succeeded", "failed")) {
            break
        }
        Start-Sleep -Seconds 2
    }

    if ($null -eq $cadJob -or $cadJob.state -ne "succeeded") {
        $failureCode = if ($cadJob.error) { $cadJob.error.code } else { "timeout" }
        throw "CAD processing smoke check failed: $failureCode"
    }
    if ($cadJob.result.face_count -ne 4 -or $cadJob.result.edge_count -ne 6) {
        throw "CAD geometry smoke result did not match the tetrahedron fixture."
    }
    if ($cadJob.result.similarity_index.status -ne "indexed") {
        throw "STL similarity feature indexing did not complete."
    }
    $preview = Invoke-WebRequest `
        -Uri "http://localhost:8000$($cadJob.result.preview.download_url)" `
        -UseBasicParsing
    if ($preview.StatusCode -ne 200 -or $preview.RawContentLength -le 84) {
        throw "CAD preview download smoke check failed."
    }
}
finally {
    if (Test-Path -LiteralPath $cadFile) {
        Remove-Item -LiteralPath $cadFile -Force
    }
}

$pythonExe = Join-Path $repoRoot "services\platform-api\.venv\Scripts\python.exe"
$stepFile = Join-Path ([System.IO.Path]::GetTempPath()) "mold-ai-step-smoke-$([guid]::NewGuid()).step"
try {
    $fixtureScript = @"
import cadquery as cq
import os
import sys
box = cq.Workplane(cq.Plane.XY()).box(10, 20, 30)
cq.exporters.export(box, sys.argv[1])
sys.stdout.flush()
sys.stderr.flush()
os._exit(0)
"@
    & $pythonExe -c $fixtureScript $stepFile
    if ($LASTEXITCODE -ne 0) {
        throw "STEP smoke fixture generation failed."
    }

    $stepUploadJson = curl.exe --silent --show-error --fail `
        --form "file=@$stepFile;type=model/step" `
        --form "artifact_name=Stage 2 smoke STEP box" `
        --form "idempotency_key=stage2-step-smoke-$([guid]::NewGuid())" `
        "http://localhost:8000/api/v1/cad-artifacts"
    if ($LASTEXITCODE -ne 0) {
        throw "STEP upload smoke check failed."
    }

    $stepUpload = $stepUploadJson | ConvertFrom-Json
    $stepDeadline = (Get-Date).AddSeconds(90)
    $stepJob = $null
    while ((Get-Date) -lt $stepDeadline) {
        $stepJob = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/jobs/$($stepUpload.job_id)"
        if ($stepJob.state -in @("succeeded", "failed")) {
            break
        }
        Start-Sleep -Seconds 2
    }

    if ($null -eq $stepJob -or $stepJob.state -ne "succeeded") {
        $failureCode = if ($stepJob.error) { $stepJob.error.code } else { "timeout" }
        throw "STEP processing smoke check failed: $failureCode"
    }
    $volumeDelta = [math]::Abs($stepJob.result.volume - 6000)
    if ($stepJob.result.face_count -ne 6 -or $stepJob.result.edge_count -ne 12 -or $volumeDelta -gt 0.01) {
        throw "STEP geometry smoke result did not match the 10 x 20 x 30 box fixture."
    }
    if ($stepJob.result.similarity_index.status -ne "indexed") {
        throw "STEP similarity feature indexing did not complete."
    }
}
finally {
    if (Test-Path -LiteralPath $stepFile) {
        Remove-Item -LiteralPath $stepFile -Force
    }
}

$similarityRequest = @{
    schema_version = "1.0"
    idempotency_key = "stage3-similarity-smoke-$([guid]::NewGuid())"
    query = @{
        cad_artifact_version_id = $stepUpload.artifact_version_id
    }
    profile = "demo-general@1.0"
    filters = @{
        dataset_ids = @("public-demo-v1")
    }
    top_k = 5
} | ConvertTo-Json -Depth 5

$similarityAccepted = Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/similarity-searches" `
    -Method Post `
    -ContentType "application/json" `
    -Body $similarityRequest

if ($similarityAccepted.status -ne "accepted") {
    throw "Similarity search was not accepted."
}

$similarityDeadline = (Get-Date).AddSeconds(60)
$similarityJob = $null
while ((Get-Date) -lt $similarityDeadline) {
    $similarityJob = Invoke-RestMethod `
        -Uri "http://localhost:8000/api/v1/jobs/$($similarityAccepted.job_id)"
    if ($similarityJob.state -in @("succeeded", "failed")) {
        break
    }
    Start-Sleep -Seconds 1
}

if ($null -eq $similarityJob -or $similarityJob.state -ne "succeeded") {
    $failureCode = if ($similarityJob.error) { $similarityJob.error.code } else { "timeout" }
    throw "Similarity search smoke check failed: $failureCode"
}
if ($similarityJob.result.result_count -lt 1) {
    throw "Similarity search did not return an indexed candidate."
}
if ($similarityJob.result.results[0].artifact_version_id -eq $stepUpload.artifact_version_id) {
    throw "Similarity search returned the query artifact as its own candidate."
}
if ($null -eq $similarityJob.result.results[0].sub_scores.geometry -or `
    $null -eq $similarityJob.result.results[0].sub_scores.topology) {
    throw "Similarity result is missing required deterministic score lanes."
}
if ($similarityJob.result.results[0].similarities.Count -eq 0 -and `
    $similarityJob.result.results[0].differences.Count -eq 0) {
    throw "Similarity result does not contain engineering evidence."
}
if (-not $similarityJob.result.lineage_ref.StartsWith("similarity-search:")) {
    throw "Similarity result lineage reference is missing."
}

$similarityDetail = Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/similarity-searches/$($similarityAccepted.search_id)"
if ($similarityDetail.state -ne "succeeded" -or `
    $similarityDetail.result.search_id -ne $similarityAccepted.search_id) {
    throw "Persisted similarity result endpoint smoke check failed."
}

$reviewRequest = @{
    schema_version = "1.0"
    idempotency_key = "stage4-design-review-smoke-$([guid]::NewGuid())"
    cad_artifact_version_id = $stepUpload.artifact_version_id
    profile = "demo-general-design@1.0"
    context = @{
        nominal_wall_thickness_mm = 2.0
        max_rib_thickness_mm = 1.5
    }
} | ConvertTo-Json -Depth 5

$reviewAccepted = Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/design-reviews" `
    -Method Post `
    -ContentType "application/json" `
    -Body $reviewRequest

if ($reviewAccepted.status -ne "accepted") {
    throw "Design review was not accepted."
}

$reviewDeadline = (Get-Date).AddSeconds(60)
$reviewJob = $null
while ((Get-Date) -lt $reviewDeadline) {
    $reviewJob = Invoke-RestMethod `
        -Uri "http://localhost:8000/api/v1/jobs/$($reviewAccepted.job_id)"
    if ($reviewJob.state -in @("succeeded", "failed")) {
        break
    }
    Start-Sleep -Seconds 1
}

if ($null -eq $reviewJob -or $reviewJob.state -ne "succeeded") {
    $failureCode = if ($reviewJob.error) { $reviewJob.error.code } else { "timeout" }
    throw "Design review smoke check failed: $failureCode"
}
if ($reviewJob.result.summary.total -ne 13 -or `
    $reviewJob.result.summary.counts.PASS -lt 1 -or `
    $reviewJob.result.summary.counts.FAIL -lt 1 -or `
    $reviewJob.result.summary.counts.NOT_EVALUATED -lt 1) {
    throw "Design review did not preserve PASS, FAIL, and NOT_EVALUATED semantics."
}

$ribFinding = $reviewJob.result.findings | `
    Where-Object { $_.rule.rule_id -eq "DEMO-RIB-RATIO-012" } | `
    Select-Object -First 1
if ($null -eq $ribFinding -or $ribFinding.result -ne "FAIL" -or `
    [math]::Abs($ribFinding.actual_value - 0.75) -gt 0.0001 -or `
    $ribFinding.limit_value -ne 0.6 -or `
    $ribFinding.geometry_location.scope -ne "context:rib-measurement") {
    throw "Rib design-review evidence did not match the controlled Demo measurement."
}

$waiverRequest = @{
    decision = "waived"
    reason = "Approved for automated Stage 4 smoke validation only."
    decided_by = "smoke-reviewer"
    approved_by = "smoke-approver"
} | ConvertTo-Json
$waiver = Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/design-reviews/$($reviewAccepted.review_id)/findings/$($ribFinding.finding_id)/decisions" `
    -Method Post `
    -ContentType "application/json" `
    -Body $waiverRequest
if ($waiver.finding_result -ne "FAIL" -or $waiver.record.decision -ne "waived") {
    throw "Review waiver changed the deterministic finding or was not persisted."
}

$reviewDetail = Invoke-RestMethod `
    -Uri "http://localhost:8000/api/v1/design-reviews/$($reviewAccepted.review_id)"
$persistedRib = $reviewDetail.findings | `
    Where-Object { $_.finding_id -eq $ribFinding.finding_id } | `
    Select-Object -First 1
if ($persistedRib.result -ne "FAIL" -or $persistedRib.decisions.Count -ne 1) {
    throw "Persisted design-review result or immutable decision history is incorrect."
}

$serviceSummary = $ready.services | ForEach-Object { "$($_.name)=$($_.status)" }
Write-Host `
    "Smoke tests passed: API=ok; Web=ok; Worker=ok; CAD=ok; Similarity=ok; DesignReview/Audit=ok; $($serviceSummary -join '; ')"
