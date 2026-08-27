param(
    [string]$EnvFile = ".env.sites-demo",
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$envPath = Join-Path $repoRoot $EnvFile
$examplePath = Join-Path $repoRoot ".env.sites-demo.example"
$runtimeDir = Join-Path $repoRoot ".runtime\sites-demo"
$composeArgs = @("compose", "-f", "compose.yaml", "-f", "compose.sites-demo.yaml", "--env-file", $envPath)

function New-HexSecret([int]$ByteCount) {
    $bytes = New-Object byte[] $ByteCount
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return -join ($bytes | ForEach-Object { $_.ToString("x2") })
}

function Read-EnvValue([string]$Name) {
    $line = Get-Content -LiteralPath $envPath | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -Last 1
    if (-not $line) { return "" }
    return $line.Substring($line.IndexOf("=") + 1).Trim()
}

function Test-StableSitesEntry([string]$Value) {
    $uri = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri)) { return $false }
    return $uri.Scheme -eq "https" `
        -and -not $uri.UserInfo `
        -and $uri.AbsolutePath -eq "/" `
        -and -not $uri.Query `
        -and -not $uri.Fragment `
        -and $uri.Host -ne "localhost" `
        -and -not $uri.Host.EndsWith(".invalid")
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker CLI was not found. Start Docker Desktop and retry."
}
$previousPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
docker info 2>$null | Out-Null
$dockerInfoExitCode = $LASTEXITCODE
$ErrorActionPreference = $previousPreference
if ($dockerInfoExitCode -ne 0) { throw "Docker Desktop is not ready." }

if (-not (Test-Path -LiteralPath $envPath)) {
    $template = Get-Content -LiteralPath $examplePath -Raw
    $template = $template.Replace("POSTGRES_PASSWORD=GENERATED_AT_FIRST_START", "POSTGRES_PASSWORD=$(New-HexSecret 24)")
    $template = $template.Replace("DJANGO_SECRET_KEY=GENERATED_AT_FIRST_START", "DJANGO_SECRET_KEY=$(New-HexSecret 48)")
    $template = $template.Replace("DEMO_API_TOKEN=GENERATED_AT_FIRST_START", "DEMO_API_TOKEN=$(New-HexSecret 32)")
    [IO.File]::WriteAllText($envPath, $template, [Text.UTF8Encoding]::new($false))
    Write-Host "Created private runtime configuration: $envPath"
}

$sitesEntryUrl = Read-EnvValue "PUBLIC_WEB_ENTRY_BASE_URL"
if (-not (Test-StableSitesEntry $sitesEntryUrl)) {
    throw "Set PUBLIC_WEB_ENTRY_BASE_URL in $envPath to the stable HTTPS origin of your private Sites portal."
}

$upArgs = $composeArgs + @("up", "-d")
if (-not $NoBuild) { $upArgs += "--build" }
$upArgs += @("db", "redis", "qdrant", "api", "worker", "worker-cad", "web", "mcp-gateway", "web-tunnel")
Push-Location -LiteralPath $repoRoot
try {
    & docker @upArgs
    if ($LASTEXITCODE -ne 0) { throw "Sites Demo containers failed to start." }

    $demoDataReady = $false
    $seedDeadline = (Get-Date).AddMinutes(2)
    while ((Get-Date) -lt $seedDeadline -and -not $demoDataReady) {
        & docker @composeArgs exec -T api python manage.py seed_demo_data
        if ($LASTEXITCODE -eq 0) {
            $demoDataReady = $true
            break
        }
        Start-Sleep -Seconds 2
    }
    if (-not $demoDataReady) { throw "Governed Demo datasets could not be loaded." }

    $tunnelUrl = ""
    $deadline = (Get-Date).AddMinutes(2)
    while ((Get-Date) -lt $deadline -and -not $tunnelUrl) {
        $logs = & docker @composeArgs logs --no-color web-tunnel 2>&1 | Out-String
        $match = [regex]::Match($logs, "https://[a-z0-9-]+\.trycloudflare\.com")
        if ($match.Success) { $tunnelUrl = $match.Value; break }
        Start-Sleep -Seconds 2
    }
    if (-not $tunnelUrl) { throw "Quick Tunnel did not publish a URL within two minutes. Check web-tunnel logs." }
    if ($tunnelUrl -eq $sitesEntryUrl) { throw "Sites entry and Workspace Quick Tunnel must be different URLs." }

    $demoToken = Read-EnvValue "DEMO_API_TOKEN"
    $mcpHostPort = Read-EnvValue "MCP_HOST_PORT"
    if (-not $mcpHostPort) { $mcpHostPort = "8002" }
    $headers = @{ Authorization = "Bearer $demoToken"; "X-Mold-AI-Client" = "sites-demo-preflight" }
    $systemInfo = $null
    $externalDeadline = (Get-Date).AddMinutes(2)
    while ((Get-Date) -lt $externalDeadline -and -not $systemInfo) {
        try {
            $null = Invoke-WebRequest -UseBasicParsing -Uri "$tunnelUrl/" -TimeoutSec 15
            $systemInfo = Invoke-RestMethod -Uri "$tunnelUrl/api/v1/system/info" -Headers $headers -TimeoutSec 15
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $systemInfo) { throw "Quick Tunnel URL was published but did not become externally reachable." }
    if ($systemInfo.name -ne "Mold AI Platform") { throw "Unexpected system identity through Quick Tunnel." }

    [IO.Directory]::CreateDirectory($runtimeDir) | Out-Null
    [IO.File]::WriteAllText((Join-Path $runtimeDir "tunnel-url.txt"), $tunnelUrl, [Text.UTF8Encoding]::new($false))
}
finally { Pop-Location }

Write-Host ""
Write-Host "Sites Demo is ready." -ForegroundColor Green
Write-Host "Stable entry: $sitesEntryUrl"
Write-Host "HTTPS Tunnel: $tunnelUrl"
Write-Host "Demo token:    $demoToken"
Write-Host "MCP endpoint:  http://127.0.0.1:$mcpHostPort/mcp (loopback-only)"
Write-Host "Paste the current HTTPS Tunnel and Demo token into the private Sites portal when prompted."
Write-Host "Quick Tunnel changes do not require refreshing the ChatGPT MCP connection."
Write-Host "Run scripts/mcp-secure-tunnel.ps1 in a second terminal for ChatGPT MCP."
