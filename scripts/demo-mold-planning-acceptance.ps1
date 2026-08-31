param(
    [string]$EnvFile = ".env.sites-demo",
    [switch]$LocalDevelopment,
    [string]$OutputPath = "",
    [switch]$Json
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "demo-ops-common.ps1")
$repoRoot = Get-DemoRepoRoot
$envPath = Join-Path $repoRoot $EnvFile
$composeArgs = @(Get-DemoComposeArgs -EnvPath $envPath -LocalDevelopment:$LocalDevelopment)

function Get-Percentile([double[]]$Values, [double]$Percentile) {
    $ordered = @($Values | Sort-Object)
    $index = [Math]::Max(0, [Math]::Ceiling($ordered.Count * $Percentile) - 1)
    return [Math]::Round([double]$ordered[$index], 2)
}

$apiOrigin = "http://localhost:8000"
$mcpOrigin = "http://127.0.0.1:8001"
$headers = @{}
if (-not $LocalDevelopment) {
    $runtimeUrlPath = Join-Path $repoRoot ".runtime\sites-demo\tunnel-url.txt"
    if (-not (Test-Path -LiteralPath $runtimeUrlPath)) {
        throw "The current Sites Demo Quick Tunnel URL is unavailable."
    }
    $apiOrigin = (Get-Content -LiteralPath $runtimeUrlPath -Raw).Trim()
    $mcpPort = Get-DemoEnvValue -Path $envPath -Name "MCP_HOST_PORT"
    if (-not $mcpPort) { $mcpPort = "8002" }
    $mcpOrigin = "http://127.0.0.1:$mcpPort"
    $token = Get-DemoEnvValue -Path $envPath -Name "MCP_PLATFORM_SERVICE_TOKEN"
    if (-not $token) { throw "The private MCP-to-Platform service credential is not configured." }
    $headers = @{
        Authorization = "Bearer $token"
        "X-Mold-AI-Client" = "mcp-gateway"
    }
}

Push-Location -LiteralPath $repoRoot
try {
    & docker @composeArgs exec -T `
        -e DJANGO_SECURE_SSL_REDIRECT=false `
        -e DEMO_AUTH_MODE=disabled `
        -e PLATFORM_API_TOKEN=acceptance-test-service-token-0123456789abcdef `
        api python manage.py test `
        platform_core.tests.test_mold_planning `
        platform_core.tests.test_rule_resolution `
        platform_core.tests.test_mcp_gateway `
        --verbosity 0
    if ($LASTEXITCODE -ne 0) { throw "The isolated mold-planning contract scenarios failed." }

    $rendered = (& docker @composeArgs config --format json | Out-String) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "The active Compose configuration could not be rendered." }
    $applicationImages = @(
        @("api", "worker", "worker-cad", "mcp-gateway", "web") |
            ForEach-Object { $rendered.services.$_.image } |
            Sort-Object -Unique
    )
    if ($applicationImages.Count -ne 1 -or $applicationImages[0] -notlike "mold-ai-platform-app:*") {
        throw "The five application roles do not resolve to one versioned Mold AI image."
    }

    $composeProjects = (& docker compose ls --format json | Out-String) | ConvertFrom-Json
    $activeProjects = @(
        $composeProjects |
            Where-Object { $_.Name -like "mold-ai-platform*" -and $_.Status -match "running" }
    )
    $expectedProject = if ($LocalDevelopment) { "mold-ai-platform" } else { "mold-ai-platform-sites-demo" }
    if ($activeProjects.Count -ne 1 -or $activeProjects[0].Name -ne $expectedProject) {
        throw "Exactly one active Mold AI Compose project is required for external Demo acceptance."
    }
}
finally { Pop-Location }

$web = Invoke-WebRequest -UseBasicParsing -Uri "$apiOrigin/engineering/mold-planning" -TimeoutSec 30
$catalog = Invoke-RestMethod -Uri "$apiOrigin/api/v1/mold-plans?page=1&page_size=25" -Headers $headers -TimeoutSec 30
$mcp = Invoke-RestMethod -Uri "$mcpOrigin/preflight" -TimeoutSec 15
if ($web.StatusCode -ne 200) { throw "The external Mold Planning route is unavailable." }
if ($catalog.schema_version -ne "1.0" -or -not $catalog.page) {
    throw "The Mold Plan catalog does not satisfy its canonical list contract."
}
if ($mcp.tool_count -ne 13 -or -not $mcp.deep_links.ready -or -not $mcp.plugin_ui.ready) {
    throw "The MCP mold-planning release contract is incomplete."
}

$durations = @()
for ($sample = 0; $sample -lt 10; $sample++) {
    $timer = [Diagnostics.Stopwatch]::StartNew()
    try {
        $null = Invoke-RestMethod -Uri "$apiOrigin/api/v1/mold-plans?page=1&page_size=25" -Headers $headers -TimeoutSec 15
    }
    finally {
        $timer.Stop()
        $durations += $timer.Elapsed.TotalMilliseconds
    }
}
$catalogP95 = Get-Percentile $durations 0.95
if ($catalogP95 -gt 1000) { throw "Mold Plan catalog p95 exceeded the 1000 ms Demo gate." }

$result = [ordered]@{
    schema_version = "1.0"
    checked_at = (Get-Date).ToUniversalTime().ToString("o")
    status = "passed"
    mode = if ($LocalDevelopment) { "local_development" } else { "sites_demo" }
    golden_scenarios = [ordered]@{
        governed_plan_lifecycle = "passed"
        deterministic_resolution = "passed"
        immutable_requirements = "passed"
        authorized_override_and_redaction = "passed"
        design_review_handoff_and_lineage = "passed"
        assistant_and_mcp_read_only_tools = "passed"
        external_deep_link = "passed"
    }
    performance = [ordered]@{
        mold_plan_catalog_samples = 10
        mold_plan_catalog_p95_ms = $catalogP95
        gate_p95_ms = 1000
    }
    deployment = [ordered]@{
        active_mold_ai_compose_projects = 1
        unified_application_images = 1
        mcp_tool_count = $mcp.tool_count
    }
    redaction = [ordered]@{
        secrets_included = $false
        urls_included = $false
        tunnel_ids_included = $false
    }
}

if (-not $OutputPath) {
    $evidenceDirectory = Join-Path $repoRoot ".runtime\evidence\mold-planning"
    New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null
    $OutputPath = Join-Path $evidenceDirectory "$((Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')).json"
}
$resolvedOutputPath = if ([IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath
} else { Join-Path $repoRoot $OutputPath }
[IO.Directory]::CreateDirectory((Split-Path -Parent $resolvedOutputPath)) | Out-Null
[IO.File]::WriteAllText(
    $resolvedOutputPath,
    ($result | ConvertTo-Json -Depth 10),
    [Text.UTF8Encoding]::new($false)
)

if ($Json) { Write-Output ($result | ConvertTo-Json -Depth 10) }
else {
    Write-Host "Mold Planning golden acceptance: passed" -ForegroundColor Green
    Write-Host "  Catalog p95: $catalogP95 ms (gate 1000 ms)"
    Write-Host "  MCP tools:   $($mcp.tool_count)"
    Write-Host "  Deployment:  one Compose project, one application image"
    Write-Host "  Evidence:    $resolvedOutputPath"
}
