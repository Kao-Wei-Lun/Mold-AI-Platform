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

$serviceSummary = $ready.services | ForEach-Object { "$($_.name)=$($_.status)" }
Write-Host "Smoke tests passed: API=ok; Web=ok; Worker=ok; $($serviceSummary -join '; ')"
