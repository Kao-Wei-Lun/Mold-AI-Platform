param([string]$EnvFile = ".env.sites-demo")

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "demo-ops-common.ps1")
$repoRoot = Get-DemoRepoRoot
$envPath = Join-Path $repoRoot $EnvFile
if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Sites Demo environment file not found: $envPath"
}

Write-Host "Stopping only the Sites Demo Compose project; persistent volumes and secrets are retained."
& (Join-Path $PSScriptRoot "sites-demo-stop.ps1") -EnvFile $EnvFile
if ($LASTEXITCODE -ne 0) { throw "Sites Demo stop failed." }

if (Get-Process -Name "tunnel-client" -ErrorAction SilentlyContinue) {
    Write-Host "A tunnel-client process is still running. Stop its owning terminal with Ctrl+C when the MCP Demo is finished."
}
