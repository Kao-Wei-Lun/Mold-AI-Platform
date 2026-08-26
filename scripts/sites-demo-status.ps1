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

if (Test-Path -LiteralPath $urlPath) { Write-Host "HTTPS Tunnel: $((Get-Content -LiteralPath $urlPath -Raw).Trim())" }
if ($ShowToken) {
    $line = Get-Content -LiteralPath $envPath | Where-Object { $_ -match "^DEMO_API_TOKEN=" } | Select-Object -Last 1
    Write-Host "Demo token:    $($line.Substring($line.IndexOf('=') + 1).Trim())"
} else {
    Write-Host "Token hidden. Add -ShowToken only when entering it into your private Sites portal."
}
