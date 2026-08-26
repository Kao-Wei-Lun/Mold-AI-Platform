param(
    [string]$TunnelClient = "",
    [string]$Profile = "mold-ai-local",
    [int]$McpPort = 8002,
    [switch]$Initialize
)

$ErrorActionPreference = "Stop"
$mcpUrl = "http://127.0.0.1:$McpPort/mcp"
$repoRoot = Split-Path -Parent $PSScriptRoot
$localClient = Join-Path $repoRoot ".runtime\tools\tunnel-client\tunnel-client.exe"
if (-not $TunnelClient) { $TunnelClient = if (Test-Path -LiteralPath $localClient) { $localClient } else { "tunnel-client" } }

if (-not $env:OPENAI_TUNNEL_ID) { throw "Set OPENAI_TUNNEL_ID to the tunnel_id from OpenAI Platform tunnel settings." }
if (-not $env:CONTROL_PLANE_API_KEY) { throw "Set CONTROL_PLANE_API_KEY to a runtime API key for tunnel-client." }
$clientCommand = Get-Command $TunnelClient -ErrorAction SilentlyContinue
if (-not $clientCommand) {
    throw "tunnel-client was not found. Run scripts/install-tunnel-client.ps1, then retry."
}

try {
    $preflight = Invoke-RestMethod -Uri "http://127.0.0.1:$McpPort/preflight" -TimeoutSec 10
} catch {
    throw "The local MCP gateway is not ready. Run scripts/sites-demo-start.ps1 first."
}
if (-not $preflight.inspector_ready) { throw "MCP gateway preflight is not ready." }

if ($Initialize) {
    & $clientCommand.Source init --profile $Profile --tunnel-id $env:OPENAI_TUNNEL_ID --mcp-server-url $mcpUrl
    if ($LASTEXITCODE -ne 0) { throw "tunnel-client profile initialization failed." }
}

& $clientCommand.Source doctor --profile $Profile --explain
if ($LASTEXITCODE -ne 0) { throw "tunnel-client doctor failed. Fix the reported condition before connecting ChatGPT." }

Write-Host "Secure MCP Tunnel is starting. Keep this terminal open during the ChatGPT test."
& $clientCommand.Source run --profile $Profile
if ($LASTEXITCODE -ne 0) { throw "Secure MCP Tunnel stopped with an error." }
