param(
    [string]$EnvFile = ".env.sites-demo",
    [switch]$LocalDevelopment,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "demo-ops-common.ps1")
$repoRoot = Get-DemoRepoRoot
$envPath = Join-Path $repoRoot $EnvFile
$runtimeUrlPath = Join-Path $repoRoot ".runtime\sites-demo\tunnel-url.txt"
$composeArgs = @(Get-DemoComposeArgs -EnvPath $envPath -LocalDevelopment:$LocalDevelopment)
$expectedServices = if ($LocalDevelopment) {
    @("db", "redis", "qdrant", "api", "worker", "worker-cad", "web", "mcp-gateway")
} else {
    @("db", "redis", "qdrant", "api", "worker", "worker-cad", "web", "mcp-gateway", "web-tunnel")
}

$containerRows = @()
Push-Location -LiteralPath $repoRoot
try {
    $rawRows = @(& docker @composeArgs ps --format json 2>$null)
    foreach ($rawRow in $rawRows) {
        if (-not $rawRow) { continue }
        try {
            $parsed = $rawRow | ConvertFrom-Json
            if ($parsed -is [array]) { $containerRows += $parsed } else { $containerRows += ,$parsed }
        } catch { }
    }
} finally { Pop-Location }

$services = foreach ($name in $expectedServices) {
    $row = $containerRows | Where-Object { $_.Service -eq $name } | Select-Object -First 1
    [ordered]@{
        name = $name
        state = if ($row) { [string]$row.State } else { "missing" }
        health = if ($row -and $row.Health) { [string]$row.Health } else { $null }
        image = if ($row) { [string]$row.Image } else { $null }
    }
}
$containersReady = @($services | Where-Object { $_.state -ne "running" }).Count -eq 0

$workerResponding = 0
$workerError = $null
Push-Location -LiteralPath $repoRoot
try {
    $workerRaw = (& docker @composeArgs exec -T api celery -A mold_platform inspect ping --timeout 2 --json 2>$null | Out-String).Trim()
    if ($LASTEXITCODE -eq 0 -and $workerRaw) {
        $workerPayload = $workerRaw | ConvertFrom-Json
        $workerResponding = @($workerPayload.psobject.Properties).Count
    } else { $workerError = "Celery workers did not answer the bounded ping." }
} catch { $workerError = "Celery worker status is unavailable." }
$workersReady = $workerResponding -ge 2

$apiOrigin = "http://localhost:8000"
$mcpOrigin = "http://127.0.0.1:8001"
$entryConfigured = $true
$tunnelKnown = $true
$headers = @{}
if (-not $LocalDevelopment) {
    $entry = Get-DemoEnvValue -Path $envPath -Name "PUBLIC_WEB_ENTRY_BASE_URL"
    $entryConfigured = Test-DemoHttpsOrigin $entry
    $tunnelKnown = Test-Path -LiteralPath $runtimeUrlPath
    $apiOrigin = if ($tunnelKnown) { (Get-Content -LiteralPath $runtimeUrlPath -Raw).Trim() } else { "" }
    $mcpPort = Get-DemoEnvValue -Path $envPath -Name "MCP_HOST_PORT"
    if (-not $mcpPort) { $mcpPort = "8002" }
    $mcpOrigin = "http://127.0.0.1:$mcpPort"
    $token = Get-DemoEnvValue -Path $envPath -Name "MCP_PLATFORM_SERVICE_TOKEN"
    if ($token) {
        $headers = @{
            Authorization = "Bearer $token"
            "X-Mold-AI-Client" = "mcp-gateway"
        }
    }
}

$readiness = $null
$demoStatus = $null
$security = $null
$apiError = $null
if ($apiOrigin) {
    try {
        $readiness = Invoke-RestMethod -Uri "$apiOrigin/api/v1/health/ready" -TimeoutSec 15
        $demoStatus = Invoke-RestMethod -Uri "$apiOrigin/api/v1/demo/status" -Headers $headers -TimeoutSec 15
        $security = Invoke-RestMethod -Uri "$apiOrigin/api/v1/security/preflight" -TimeoutSec 15
    } catch { $apiError = $_.Exception.Message }
}

$mcp = $null
$mcpError = $null
try { $mcp = Invoke-RestMethod -Uri "$mcpOrigin/preflight" -TimeoutSec 10 }
catch { $mcpError = $_.Exception.Message }

$curated = if ($demoStatus) { $demoStatus.demo_data.curated_cad } else { $null }
$coreReady = $containersReady `
    -and $workersReady `
    -and $readiness `
    -and $readiness.status -eq "ok" `
    -and $curated `
    -and $curated.reconciled `
    -and $mcp `
    -and $mcp.tool_count -eq 9
$externalReady = $LocalDevelopment -or (
    $entryConfigured -and $tunnelKnown -and $mcp.deep_links.ready `
        -and $mcp.connection.secure_tunnel_configured `
        -and $null -ne (Get-Process -Name "tunnel-client" -ErrorAction SilentlyContinue)
)
$git = Get-DemoGitState -RepoRoot $repoRoot
$overall = if (-not $coreReady -or -not $externalReady) {
    "not_ready"
} elseif (-not $git.clean -or ($demoStatus.assistant_provider.status -ne "ready")) {
    "degraded"
} else { "ready" }

$nextActions = @()
if (-not $containersReady) { $nextActions += "Run scripts/demo-start.ps1 and inspect missing services." }
if (-not $workersReady) { $nextActions += "Restore both Celery workers before creating asynchronous jobs." }
if (-not $curated -or -not $curated.reconciled) { $nextActions += "Run seed_cad_demo and repair Qdrant before UAT." }
if (-not $mcp -or $mcp.tool_count -ne 9) { $nextActions += "Restore the local MCP gateway and verify its preflight." }
if (-not $LocalDevelopment -and -not $entryConfigured) { $nextActions += "Configure a stable private Sites HTTPS entry." }
if (-not $LocalDevelopment -and -not $tunnelKnown) { $nextActions += "Start the Web Quick Tunnel." }
if (-not $LocalDevelopment -and $mcp -and -not $mcp.connection.secure_tunnel_configured) {
    $nextActions += "Load SECURE_MCP_TUNNEL_ID into the MCP Gateway configuration."
}
if (-not $LocalDevelopment -and $null -eq (Get-Process -Name "tunnel-client" -ErrorAction SilentlyContinue)) {
    $nextActions += "Start scripts/mcp-secure-tunnel.ps1 in its operator terminal."
}
if ($demoStatus -and $demoStatus.job_recovery.counts.total -gt 0) {
    $nextActions += "Preview stale-job recovery with recover_stale_jobs before UAT."
}
if (-not $git.clean) { $nextActions += "Review and commit the working tree before release." }
if ($demoStatus -and $demoStatus.assistant_provider.status -ne "ready") {
    $nextActions += "Assistant is using its safe deterministic fallback; live provider UAT remains optional."
}

$payload = [ordered]@{
    schema_version = "1.0"
    operations_contract_version = "1.0"
    checked_at = (Get-Date).ToUniversalTime().ToString("o")
    mode = if ($LocalDevelopment) { "local_development" } else { "sites_demo" }
    overall = $overall
    compose = [ordered]@{ services = @($services); all_expected_running = $containersReady }
    workers = [ordered]@{
        expected = 2
        responding = $workerResponding
        ready = $workersReady
        error = $workerError
    }
    api = [ordered]@{
        reachable = $null -ne $readiness
        readiness = if ($readiness) { $readiness.status } else { "unavailable" }
        dependencies = if ($readiness) { $readiness.services } else { @() }
        error = $apiError
    }
    datasets = if ($demoStatus) { $demoStatus.demo_data } else { $null }
    job_recovery = if ($demoStatus) { $demoStatus.job_recovery } else { $null }
    assistant_provider = if ($demoStatus) { $demoStatus.assistant_provider } else { $null }
    security = [ordered]@{
        external_mode = if ($security) { $security.external_mode } else { $null }
        production_ready = if ($security) { $security.production_ready } else { $false }
        quick_tunnel_ready = if ($security) { $security.quick_tunnel.ready } else { $false }
    }
    web = [ordered]@{ stable_entry_configured = $entryConfigured; quick_tunnel_known = $tunnelKnown }
    mcp = [ordered]@{
        reachable = $null -ne $mcp
        tool_count = if ($mcp) { $mcp.tool_count } else { 0 }
        deep_links_ready = if ($mcp) { $mcp.deep_links.ready } else { $false }
        secure_tunnel_configured = if ($mcp) { $mcp.connection.secure_tunnel_configured } else { $false }
        tunnel_client_running = $null -ne (Get-Process -Name "tunnel-client" -ErrorAction SilentlyContinue)
        error = $mcpError
    }
    git = $git
    readiness_summary = [ordered]@{
        core = if ($coreReady) { "ready" } else { "not_ready" }
        external_access = if ($LocalDevelopment) { "not_applicable" } elseif ($externalReady) { "ready" } else { "not_ready" }
        assistant = if ($demoStatus -and $demoStatus.assistant_provider.status -eq "ready") { "ready" } else { "optional_fallback" }
        security_profile = if ($LocalDevelopment) { "local_development" } elseif ($security -and $security.quick_tunnel.ready) { "private_quick_tunnel_ready" } else { "external_not_ready" }
    }
    next_actions = $nextActions
    redaction = [ordered]@{
        secrets_included = $false
        urls_included = $false
        tunnel_ids_included = $false
    }
}

if ($Json) {
    Write-Output ($payload | ConvertTo-Json -Depth 12)
    exit 0
}

Write-Host "Mold AI Demo status: $($payload.overall)" -ForegroundColor $(
    if ($overall -eq "ready") { "Green" } elseif ($overall -eq "degraded") { "Yellow" } else { "Red" }
)
Write-Host "Mode:        $($payload.mode)"
Write-Host "Containers:  $(if ($containersReady) { 'ready' } else { 'not ready' })"
Write-Host "API:         $($payload.api.readiness)"
Write-Host "Dependencies:$((@($payload.api.dependencies | ForEach-Object { " $($_.name)=$($_.status)" })) -join ',')"
Write-Host "Workers:     $($payload.workers.responding)/$($payload.workers.expected) responding"
Write-Host "Curated CAD: $(if ($curated) { "$($curated.ready)/$($curated.expected), indexed=$($curated.indexed)" } else { 'unavailable' })"
Write-Host "Datasets:    Knowledge=$($payload.datasets.indexed_knowledge_documents), Trial=$($payload.datasets.process_trial_cases), CAE=$($payload.datasets.cae_studies), HMI=$($payload.datasets.hmi_extractions)"
Write-Host "Stale jobs:  $(if ($payload.job_recovery) { $payload.job_recovery.counts.total } else { 'unavailable' })"
Write-Host "Core Demo:   $($payload.readiness_summary.core)"
if (-not $LocalDevelopment) {
    Write-Host "Sites entry: $(if ($payload.web.stable_entry_configured) { 'ready' } else { 'not ready' })"
    Write-Host "Web tunnel:  $(if ($payload.web.quick_tunnel_known -and $payload.security.quick_tunnel_ready) { 'ready' } else { 'not ready' })"
    Write-Host "Security:    $($payload.readiness_summary.security_profile)"
}
Write-Host "MCP:         tools=$($payload.mcp.tool_count), deep-links=$(if ($payload.mcp.deep_links_ready) { 'ready' } else { 'not ready' })"
if (-not $LocalDevelopment) {
    Write-Host "MCP tunnel:  configured=$($payload.mcp.secure_tunnel_configured), client-running=$($payload.mcp.tunnel_client_running)"
}
Write-Host "Assistant:   $($payload.readiness_summary.assistant) ($(if ($payload.assistant_provider) { $payload.assistant_provider.provider } else { 'unavailable' }))"
Write-Host "Git:         $(if ($git.clean) { 'clean' } else { "dirty ($($git.changed_path_count) paths)" })"
foreach ($action in $nextActions) { Write-Host "Next:        $action" }
