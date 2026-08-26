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
}
finally {
    if (Test-Path -LiteralPath $stepFile) {
        Remove-Item -LiteralPath $stepFile -Force
    }
}

$serviceSummary = $ready.services | ForEach-Object { "$($_.name)=$($_.status)" }
Write-Host `
    "Smoke tests passed: API=ok; Web=ok; Worker=ok; STL/STEP upload/parse/preview=ok; $($serviceSummary -join '; ')"
