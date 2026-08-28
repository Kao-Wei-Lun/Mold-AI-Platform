param([string]$EnvFile = ".env.sites-demo")

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot $EnvFile
$urlPath = Join-Path $repoRoot ".runtime\sites-demo\tunnel-url.txt"
if (-not (Test-Path -LiteralPath $envPath) -or -not (Test-Path -LiteralPath $urlPath)) {
    throw "Sites Demo runtime state is missing. Run scripts/sites-demo-start.ps1 first."
}
$url = (Get-Content -LiteralPath $urlPath -Raw).Trim()
$tokenLine = Get-Content -LiteralPath $envPath | Where-Object { $_ -match "^MCP_PLATFORM_SERVICE_TOKEN=" } | Select-Object -Last 1
$token = $tokenLine.Substring($tokenLine.IndexOf("=") + 1).Trim()

$web = $null
$health = $null
$deadline = (Get-Date).AddMinutes(2)
while ((Get-Date) -lt $deadline -and (-not $web -or -not $health)) {
    try {
        $web = Invoke-WebRequest -UseBasicParsing -Uri "$url/" -TimeoutSec 15
        $health = Invoke-WebRequest -UseBasicParsing -Uri "$url/api/v1/health/live" -TimeoutSec 15
    } catch {
        $web = $null
        $health = $null
        Start-Sleep -Seconds 2
    }
}
if (-not $web -or -not $health) { throw "Quick Tunnel did not become reachable within two minutes." }
try {
    Invoke-WebRequest -UseBasicParsing -Uri "$url/api/v1/system/info" -TimeoutSec 30 -ErrorAction Stop | Out-Null
    throw "Protected API unexpectedly allowed an anonymous request."
} catch {
    if ([int]$_.Exception.Response.StatusCode -ne 401) { throw }
}
$security = Invoke-RestMethod -Uri "$url/api/v1/security/preflight" -TimeoutSec 30
$secured = Invoke-RestMethod -Uri "$url/api/v1/system/info" -Headers @{
    Authorization = "Bearer $token"
    "X-Mold-AI-Client" = "mcp-gateway"
} -TimeoutSec 30
$mcp = Invoke-RestMethod -Uri "http://127.0.0.1:8002/preflight" -TimeoutSec 10

if ($web.StatusCode -ne 200 -or $health.StatusCode -ne 200) { throw "Public Web or health check failed." }
if ($secured.name -ne "Mold AI Platform") { throw "Authenticated API identity check failed." }
if ($security.auth.mode -ne "local" -or -not $security.auth.local_accounts_enabled) {
    throw "External Web is not using local-account authentication."
}
if (-not $security.auth.local_admin_configured) { throw "Create the first local Platform Admin before external smoke." }
if (-not $security.service_identity.configured -or $security.service_identity.secret_exposed) {
    throw "MCP service identity boundary is not ready."
}
if (-not $mcp.inspector_ready) { throw "Local MCP gateway preflight failed." }
if (-not $mcp.deep_links.ready) { throw "Stable Sites deep-link entry is not ready." }
if ($mcp.deep_links.entry_origin -match "\.invalid$" -or $mcp.deep_links.entry_origin -notmatch "^https://") {
    throw "MCP deep-link entry is not a deployable HTTPS origin."
}
if (-not $web.Headers["Strict-Transport-Security"]) { throw "Web response is missing HSTS." }
if (-not $web.Headers["Content-Security-Policy"]) { throw "Web response is missing CSP." }

Write-Host "Sites Demo external smoke passed: Web/API identity, local accounts, isolated MCP service auth, stable deep links, HSTS and CSP are ready."
