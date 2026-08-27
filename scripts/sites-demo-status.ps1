param(
    [string]$EnvFile = ".env.sites-demo",
    [switch]$ShowToken
)

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
$mcpPreflight = Invoke-RestMethod -Uri "http://127.0.0.1:8002/preflight" -TimeoutSec 10
Write-Host "MCP tools:     $($mcpPreflight.tool_count)"
Write-Host "Deep links:    $(if ($mcpPreflight.deep_links.ready) { 'ready' } else { 'not ready' })"
if ($ShowToken) {
    $line = Get-Content -LiteralPath $envPath | Where-Object { $_ -match "^DEMO_API_TOKEN=" } | Select-Object -Last 1
    Write-Host "Demo token:    $($line.Substring($line.IndexOf('=') + 1).Trim())"
} else {
    Write-Host "Token hidden. Add -ShowToken only when entering it into your private Sites portal."
}
