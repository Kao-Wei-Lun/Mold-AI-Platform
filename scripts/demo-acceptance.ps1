param(
    [string]$EnvFile = ".env.sites-demo",
    [string]$OutputRoot = ".runtime\evidence\demo-v1",
    [switch]$LocalDevelopment,
    [switch]$AllowDirtyWorkingTree,
    [switch]$SkipAutomatedTests,
    [switch]$SkipSmoke,
    [switch]$SkipPerformance
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "demo-ops-common.ps1")
$repoRoot = Get-DemoRepoRoot
$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
$resolvedOutputRoot = if ([IO.Path]::IsPathRooted($OutputRoot)) {
    [IO.Path]::GetFullPath($OutputRoot)
} else { [IO.Path]::GetFullPath((Join-Path $repoRoot $OutputRoot)) }
$evidenceDir = Join-Path $resolvedOutputRoot $timestamp
New-Item -ItemType Directory -Path $evidenceDir | Out-Null

$statusParameters = @{
    EnvFile = $EnvFile
    Json = $true
    LocalDevelopment = $LocalDevelopment
}
$statusJson = (& (Join-Path $PSScriptRoot "demo-status.ps1") @statusParameters | Out-String).Trim()
$status = $statusJson | ConvertFrom-Json
[IO.File]::WriteAllText(
    (Join-Path $evidenceDir "environment.json"),
    $statusJson,
    [Text.UTF8Encoding]::new($false)
)
if ($status.redaction.secrets_included -or $status.redaction.urls_included -or $status.redaction.tunnel_ids_included) {
    throw "Status evidence violated the redaction contract."
}
if (-not $AllowDirtyWorkingTree -and -not $status.git.clean) {
    throw "Working tree is dirty. Review/commit changes or use -AllowDirtyWorkingTree during development verification."
}
if ($status.api.readiness -ne "ok" -or -not $status.datasets.curated_cad.reconciled) {
    throw "Core API or curated dataset is not ready for acceptance."
}
if ($status.mcp.tool_count -ne 10) { throw "MCP tool count is not the expected 10." }
if (-not $status.mcp.plugin_ui_ready) { throw "MCP Plugin UI launcher is not ready." }

$testResult = [ordered]@{ status = "skipped"; command = "scripts/test.ps1" }
if (-not $SkipAutomatedTests) {
    Push-Location -LiteralPath $repoRoot
    try {
        & (Join-Path $PSScriptRoot "test.ps1")
        if ($LASTEXITCODE -ne 0) { throw "Automated release test gate failed." }
        $testResult.status = "passed"
    } finally { Pop-Location }
}
$testResult.checked_at = (Get-Date).ToUniversalTime().ToString("o")
[IO.File]::WriteAllText(
    (Join-Path $evidenceDir "automated-tests.json"),
    ($testResult | ConvertTo-Json -Depth 5),
    [Text.UTF8Encoding]::new($false)
)

$smokeResult = [ordered]@{ status = "skipped"; command = "scripts/smoke.ps1" }
if (-not $SkipSmoke) {
    if (-not $LocalDevelopment) {
        & (Join-Path $PSScriptRoot "sites-demo-smoke.ps1") -EnvFile $EnvFile
        if ($LASTEXITCODE -ne 0) { throw "Sites Demo external smoke gate failed." }
        $smokeResult.command = "scripts/sites-demo-smoke.ps1"
    } else {
        & (Join-Path $PSScriptRoot "smoke.ps1")
        if ($LASTEXITCODE -ne 0) { throw "Local running-stack smoke gate failed." }
    }
    $smokeResult.status = "passed"
}
$smokeResult.checked_at = (Get-Date).ToUniversalTime().ToString("o")
[IO.File]::WriteAllText(
    (Join-Path $evidenceDir "smoke-summary.json"),
    ($smokeResult | ConvertTo-Json -Depth 5),
    [Text.UTF8Encoding]::new($false)
)

$performancePath = Join-Path $evidenceDir "performance-baseline.json"
if ($SkipPerformance) {
    $performance = [ordered]@{ schema_version = "1.0"; status = "skipped" }
    [IO.File]::WriteAllText($performancePath, ($performance | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
} else {
    $performanceParameters = @{
        EnvFile = $EnvFile
        LocalDevelopment = $LocalDevelopment
        Json = $true
        OutputPath = $performancePath
    }
    $performanceJson = (& (Join-Path $PSScriptRoot "demo-performance.ps1") @performanceParameters | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Performance baseline gate failed." }
    $performance = $performanceJson | ConvertFrom-Json
    if ($performance.status -ne "passed" -or $performance.redaction.secrets_included -or $performance.redaction.urls_included) {
        throw "Performance evidence failed or violated its redaction contract."
    }
}

$composeArgs = @(Get-DemoComposeArgs -EnvPath (Join-Path $repoRoot $EnvFile) -LocalDevelopment:$LocalDevelopment)
Push-Location -LiteralPath $repoRoot
try {
    $snapshotJson = (& docker @composeArgs exec -T api `
        python manage.py demo_release_snapshot --json --strict | Out-String).Trim()
    if ($LASTEXITCODE -ne 0) { throw "Strict release snapshot failed." }
} finally { Pop-Location }
$snapshot = $snapshotJson | ConvertFrom-Json
[IO.File]::WriteAllText(
    (Join-Path $evidenceDir "dataset-reconciliation.json"),
    ($snapshot.datasets | ConvertTo-Json -Depth 10),
    [Text.UTF8Encoding]::new($false)
)

$externalState = if ($LocalDevelopment) { "pending_manual_external_uat" } else { "automated_external_smoke_passed" }
$liveProviderState = if ($snapshot.assistant_provider.status -eq "ready") { "ready" } else { "optional_live_uat_pending" }
$uat = @"
# Mold AI Demo v1 Acceptance Summary

- Generated: $((Get-Date).ToUniversalTime().ToString("o"))
- Commit: $($status.git.commit)
- Mode: $($status.mode)
- Automated tests: $($testResult.status)
- Running-stack smoke: $($smokeResult.status)
- Performance baseline: $($performance.status)
- Curated CAD: $($snapshot.datasets.curated_cad.ready)/$($snapshot.datasets.curated_cad.expected)
- MCP tools: $($status.mcp.tool_count)
- External Sites/ChatGPT UAT: $externalState
- Optional live OpenAI provider UAT: $liveProviderState

This sanitized bundle contains no access token, API key, tunnel ID, private URL, or browser state.
Manual UAT-01, UAT-06 live-provider checks, UAT-07 ChatGPT account/workspace checks, and visual
3D interaction remain human evidence gates when their external dependencies are selected.
"@
[IO.File]::WriteAllText(
    (Join-Path $evidenceDir "uat-results.md"),
    $uat,
    [Text.UTF8Encoding]::new($false)
)

$limitations = @"
# Known Release Limitations

- Owner-only Sites is required until enterprise OAuth/SSO and public rate limiting are implemented.
- Secure MCP Tunnel readiness depends on the selected OpenAI organization/workspace.
- The OpenAI provider is optional; deterministic fallback preserves core engineering results.
- CAD similarity uses deterministic engineered features, not a trained semantic embedding model.
- Rib/draft review measurements are explicitly supplied Demo context, not automatic STL measurement.
- Public/synthetic Demo results are not company engineering validation or production guidance.
"@
[IO.File]::WriteAllText(
    (Join-Path $evidenceDir "known-limitations.md"),
    $limitations,
    [Text.UTF8Encoding]::new($false)
)

$evidenceFiles = @(Get-ChildItem -LiteralPath $evidenceDir -File | Sort-Object Name | ForEach-Object {
    [ordered]@{ file = $_.Name; sha256 = Get-DemoFileSha256 -Path $_.FullName }
})
$releaseManifest = [ordered]@{
    schema_version = "1.0"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    commit = $status.git.commit
    working_tree_clean = $status.git.clean
    automated_tests = $testResult.status
    smoke = $smokeResult.status
    performance = $performance.status
    external_uat = $externalState
    live_provider_uat = $liveProviderState
    release_candidate = (
        $testResult.status -eq "passed" -and $smokeResult.status -eq "passed" -and
        $performance.status -eq "passed" -and
        $status.git.clean -and -not $LocalDevelopment
    )
    files = $evidenceFiles
    secrets_included = $false
}
[IO.File]::WriteAllText(
    (Join-Path $evidenceDir "release-manifest.json"),
    ($releaseManifest | ConvertTo-Json -Depth 8),
    [Text.UTF8Encoding]::new($false)
)

Write-Host "Demo acceptance gates completed. Sanitized evidence: $evidenceDir"
Write-Host "Release candidate=$($releaseManifest.release_candidate); external/manual gates remain explicit."
Write-Output $evidenceDir
