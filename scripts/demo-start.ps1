param(
    [string]$EnvFile = ".env.sites-demo",
    [switch]$NoBuild,
    [switch]$RotateDemoToken,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "demo-ops-common.ps1")
$repoRoot = Get-DemoRepoRoot
$envPath = Join-Path $repoRoot $EnvFile

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw "Demo v1.0 is currently validated for a Windows host."
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Install or start Docker Desktop."
}
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
docker info 2>$null | Out-Null
$dockerExit = $LASTEXITCODE
$ErrorActionPreference = $previousPreference
if ($dockerExit -ne 0) { throw "Docker Desktop is not ready." }

$drive = Get-PSDrive -Name ([IO.Path]::GetPathRoot($repoRoot).TrimEnd("\").TrimEnd(":"))
$freeDiskGb = [math]::Round($drive.Free / 1GB, 1)
if ($freeDiskGb -lt 10) { throw "At least 10 GB free disk is required; detected $freeDiskGb GB." }

if ($ValidateOnly) {
    if (-not (Test-Path -LiteralPath $envPath)) {
        throw "Sites Demo environment file is missing: $envPath"
    }
    $entry = Get-DemoEnvValue -Path $envPath -Name "PUBLIC_WEB_ENTRY_BASE_URL"
    if (-not (Test-DemoHttpsOrigin $entry)) {
        throw "PUBLIC_WEB_ENTRY_BASE_URL must be a stable non-placeholder HTTPS origin."
    }
    $composeArgs = @(Get-DemoComposeArgs -EnvPath $envPath)
    Push-Location -LiteralPath $repoRoot
    try {
        & docker @composeArgs config --quiet
        if ($LASTEXITCODE -ne 0) { throw "Sites Demo Compose validation failed." }
    } finally { Pop-Location }
    Write-Host "Demo host/config validation passed; free_disk_gb=$freeDiskGb."
    exit 0
}

$startParameters = @{
    EnvFile = $EnvFile
    NoBuild = $NoBuild
    RotateDemoToken = $RotateDemoToken
}
& (Join-Path $PSScriptRoot "sites-demo-start.ps1") @startParameters
if ($LASTEXITCODE -ne 0) { throw "Sites Demo startup failed." }

& (Join-Path $PSScriptRoot "demo-status.ps1") -EnvFile $EnvFile
