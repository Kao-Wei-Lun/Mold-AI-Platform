param(
    [string]$EnvFile = ".env.sites-demo",
    [switch]$LocalDevelopment,
    [ValidateRange(5, 100)][int]$Samples = 10,
    [ValidateRange(100, 30000)][int]$MaxP95Ms = 5000,
    [string]$OutputPath = "",
    [switch]$Json
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "demo-ops-common.ps1")
$repoRoot = Get-DemoRepoRoot
$envPath = Join-Path $repoRoot $EnvFile
$composeArgs = @(Get-DemoComposeArgs -EnvPath $envPath -LocalDevelopment:$LocalDevelopment)
$headers = @{}
$apiOrigin = "http://localhost:8000"
if (-not $LocalDevelopment) {
    $runtimeUrlPath = Join-Path $repoRoot ".runtime\sites-demo\tunnel-url.txt"
    if (-not (Test-Path -LiteralPath $runtimeUrlPath)) { throw "The current Web Quick Tunnel URL is unavailable." }
    $apiOrigin = (Get-Content -LiteralPath $runtimeUrlPath -Raw).Trim()
    $token = Get-DemoEnvValue -Path $envPath -Name "DEMO_API_TOKEN"
    if (-not $token) { throw "The private Demo token is not configured." }
    $headers = @{ Authorization = "Bearer $token" }
}

function Get-Percentile([double[]]$Values, [double]$Percentile) {
    $ordered = @($Values | Sort-Object)
    $index = [Math]::Max(0, [Math]::Ceiling($ordered.Count * $Percentile) - 1)
    return [Math]::Round([double]$ordered[$index], 2)
}

$endpointDefinitions = @(
    [ordered]@{ name = "health_ready"; path = "/api/v1/health/ready"; authenticated = $false },
    [ordered]@{ name = "demo_status"; path = "/api/v1/demo/status"; authenticated = $true },
    [ordered]@{ name = "cad_artifacts"; path = "/api/v1/cad-artifacts"; authenticated = $true },
    [ordered]@{ name = "trial_cases"; path = "/api/v1/trial-cases"; authenticated = $true },
    [ordered]@{ name = "cae_studies"; path = "/api/v1/cae-studies"; authenticated = $true }
)
$metrics = @()
foreach ($definition in $endpointDefinitions) {
    $durations = @()
    $errors = 0
    for ($sample = 0; $sample -lt $Samples; $sample++) {
        $timer = [Diagnostics.Stopwatch]::StartNew()
        try {
            $requestHeaders = if ($definition.authenticated) { $headers } else { @{} }
            $null = Invoke-RestMethod -Uri "$apiOrigin$($definition.path)" -Headers $requestHeaders -TimeoutSec 15
        } catch { $errors++ }
        finally { $timer.Stop(); $durations += $timer.Elapsed.TotalMilliseconds }
    }
    $metrics += [ordered]@{
        name = $definition.name
        samples = $Samples
        errors = $errors
        p50_ms = Get-Percentile $durations 0.50
        p95_ms = Get-Percentile $durations 0.95
        max_ms = [Math]::Round(($durations | Measure-Object -Maximum).Maximum, 2)
    }
}

Add-Type -AssemblyName System.Net.Http
$client = [Net.Http.HttpClient]::new()
$client.Timeout = [TimeSpan]::FromSeconds(15)
if ($headers.Authorization) {
    $client.DefaultRequestHeaders.Authorization = [Net.Http.Headers.AuthenticationHeaderValue]::new(
        "Bearer", $headers.Authorization.Substring("Bearer ".Length)
    )
}
$concurrentTimer = [Diagnostics.Stopwatch]::StartNew()
try {
    $concurrentTasks = @(1..3 | ForEach-Object { $client.GetAsync("$apiOrigin/api/v1/demo/status") })
    [Threading.Tasks.Task]::WaitAll([Threading.Tasks.Task[]]$concurrentTasks)
    $concurrentSuccess = @($concurrentTasks | Where-Object { $_.Result.IsSuccessStatusCode }).Count
    foreach ($task in $concurrentTasks) { $task.Result.Dispose() }
} finally {
    $concurrentTimer.Stop()
    $client.Dispose()
}

$queueRaw = ""
Push-Location -LiteralPath $repoRoot
try {
    $queueRaw = (& docker @composeArgs exec -T api python manage.py shell -c `
        "import json,time; from platform_core.tasks import echo; start=time.perf_counter(); results=[echo.apply_async(args=[i], queue='general') for i in range(5)]; values=[result.get(timeout=15) for result in results]; print(json.dumps({'jobs':len(values),'duration_ms':round((time.perf_counter()-start)*1000,2),'success':values==list(range(5))}))" | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "The five-job queue baseline failed." }
} finally { Pop-Location }
$queueJson = @($queueRaw -split "`r?`n" | Where-Object { $_.Trim().StartsWith("{") }) | Select-Object -Last 1
if (-not $queueJson) { throw "The five-job queue baseline did not return its JSON result." }
$queue = $queueJson | ConvertFrom-Json

$failedMetrics = @($metrics | Where-Object { $_.errors -gt 0 -or $_.p95_ms -gt $MaxP95Ms })
$passed = $failedMetrics.Count -eq 0 -and $concurrentSuccess -eq 3 -and $queue.success
$gpu = @(Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name)
$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
$result = [ordered]@{
    schema_version = "1.0"
    checked_at = (Get-Date).ToUniversalTime().ToString("o")
    mode = if ($LocalDevelopment) { "local_development" } else { "sites_demo" }
    status = if ($passed) { "passed" } else { "failed" }
    gate = [ordered]@{ max_p95_ms = $MaxP95Ms; zero_request_errors = $true }
    environment = [ordered]@{
        commit = (Get-DemoGitState -RepoRoot $repoRoot).commit
        os = if ($os) { "$($os.Caption) $($os.Version)" } else { "Windows" }
        memory_gb = if ($os) { [Math]::Round($os.TotalVisibleMemorySize / 1MB, 1) } else { $null }
        gpu = $gpu
        docker = (& docker version --format '{{.Server.Version}}' 2>$null | Out-String).Trim()
    }
    http = $metrics
    concurrent_sessions = [ordered]@{
        requested = 3
        succeeded = $concurrentSuccess
        duration_ms = [Math]::Round($concurrentTimer.Elapsed.TotalMilliseconds, 2)
    }
    queued_jobs = [ordered]@{
        requested = 5
        succeeded = if ($queue.success) { $queue.jobs } else { 0 }
        duration_ms = $queue.duration_ms
    }
    limitations = @(
        "This operator baseline measures bounded read APIs and queue throughput, not production capacity.",
        "CAD parse and similarity algorithm microbenchmarks remain a separate hardware-specific profile.",
        "Live provider latency is excluded unless the opt-in provider UAT is run separately."
    )
    redaction = [ordered]@{ secrets_included = $false; urls_included = $false }
}

if (-not $OutputPath) {
    $directory = Join-Path $repoRoot ".runtime\evidence\performance"
    New-Item -ItemType Directory -Path $directory -Force | Out-Null
    $OutputPath = Join-Path $directory "$((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')).json"
}
$resolvedOutputPath = if ([IO.Path]::IsPathRooted($OutputPath)) { $OutputPath } else { Join-Path $repoRoot $OutputPath }
[IO.Directory]::CreateDirectory((Split-Path -Parent $resolvedOutputPath)) | Out-Null
[IO.File]::WriteAllText($resolvedOutputPath, ($result | ConvertTo-Json -Depth 10), [Text.UTF8Encoding]::new($false))

if ($Json) { Write-Output ($result | ConvertTo-Json -Depth 10) }
else {
    Write-Host "Demo performance baseline: $($result.status)"
    foreach ($metric in $metrics) { Write-Host "  $($metric.name): p50=$($metric.p50_ms)ms p95=$($metric.p95_ms)ms errors=$($metric.errors)" }
    Write-Host "  Concurrent sessions: $concurrentSuccess/3 in $($result.concurrent_sessions.duration_ms)ms"
    Write-Host "  Queued jobs: $($result.queued_jobs.succeeded)/5 in $($result.queued_jobs.duration_ms)ms"
    Write-Host "  Sanitized evidence: $resolvedOutputPath"
}
if (-not $passed) { exit 2 }
