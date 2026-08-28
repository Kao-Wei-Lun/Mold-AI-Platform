param([string]$EnvFile = ".env.sites-demo")

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot $EnvFile
$urlPath = Join-Path $repoRoot ".runtime\sites-demo\tunnel-url.txt"
if (-not (Test-Path -LiteralPath $envPath)) { throw "Run scripts/sites-demo-start.ps1 first." }

Push-Location -LiteralPath $repoRoot
try {
    docker compose -f compose.yaml -f compose.sites-demo.yaml --env-file $envPath ps
    if ($LASTEXITCODE -ne 0) { throw "Unable to read Sites Demo container status." }
} finally { Pop-Location }

$entryLine = Get-Content -LiteralPath $envPath | Where-Object { $_ -match "^PUBLIC_WEB_ENTRY_BASE_URL=" } | Select-Object -Last 1
if ($entryLine) { Write-Host "Stable entry: $($entryLine.Substring($entryLine.IndexOf('=') + 1).Trim())" }

if (Test-Path -LiteralPath $urlPath) { Write-Host "HTTPS Tunnel: $((Get-Content -LiteralPath $urlPath -Raw).Trim())" }
$tunnelUrl = if (Test-Path -LiteralPath $urlPath) { (Get-Content -LiteralPath $urlPath -Raw).Trim() } else { "" }
if ($tunnelUrl) {
    $security = Invoke-RestMethod -Uri "$tunnelUrl/api/v1/security/preflight" -TimeoutSec 15
    Write-Host "Web auth:      $($security.auth.mode)"
    Write-Host "Local admin:   $(if ($security.auth.local_admin_configured) { 'ready' } else { 'bootstrap required' })"
    Write-Host "MCP service:   $(if ($security.service_identity.configured) { 'configured' } else { 'not configured' })"
}
$mcpPreflight = Invoke-RestMethod -Uri "http://127.0.0.1:8002/preflight" -TimeoutSec 10
Write-Host "MCP tools:     $($mcpPreflight.tool_count)"
Write-Host "Deep links:    $(if ($mcpPreflight.deep_links.ready) { 'ready' } else { 'not ready' })"
Write-Host "Plugin UI:     $(if ($mcpPreflight.plugin_ui.ready) { 'ready' } else { 'not ready' })"
Write-Host "Browser secret: none; Sites stores only the current Quick Tunnel origin."
