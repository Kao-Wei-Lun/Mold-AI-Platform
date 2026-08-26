param(
    [Parameter(Mandatory)][string]$BaseUrl,
    [Parameter(Mandatory)][string]$DemoToken
)

$ErrorActionPreference = "Stop"
$base = $BaseUrl.TrimEnd("/")
$preflight = Invoke-RestMethod -Uri "$base/api/v1/security/preflight"

if (-not $preflight.production_ready) {
    $failed = @($preflight.checks.PSObject.Properties | Where-Object { -not $_.Value }).Name
    throw "External release preflight is not ready: $($failed -join ', ')"
}

try {
    Invoke-WebRequest -Uri "$base/api/v1/system/info" -UseBasicParsing | Out-Null
    throw "Protected endpoint unexpectedly accepted an unauthenticated request."
}
catch {
    if ($_.Exception.Response.StatusCode.value__ -ne 401) {
        throw
    }
}

$headers = @{ Authorization = "Bearer $DemoToken"; "X-Mold-AI-Client" = "release-smoke" }
$systemInfo = Invoke-RestMethod -Uri "$base/api/v1/system/info" -Headers $headers
if ($systemInfo.name -ne "Mold AI Platform") {
    throw "Authenticated external API check returned an unexpected response."
}

$web = Invoke-WebRequest -Uri $base -UseBasicParsing
if ($web.StatusCode -ne 200 -or -not $web.Content.Contains("Mold AI Platform")) {
    throw "External Web UI check failed."
}

Write-Host "External release smoke passed: TLS Web=ok; unauthenticated deny=ok; authenticated API=ok."
