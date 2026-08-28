function Get-DemoRepoRoot {
    return Split-Path -Parent $PSScriptRoot
}

function Get-DemoEnvValue {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$Name
    )
    if (-not (Test-Path -LiteralPath $Path)) { return "" }
    $line = Get-Content -LiteralPath $Path | Where-Object {
        $_ -match "^$([regex]::Escape($Name))="
    } | Select-Object -Last 1
    if (-not $line) { return "" }
    return $line.Substring($line.IndexOf("=") + 1).Trim()
}

function Get-DemoComposeArgs {
    param(
        [Parameter(Mandatory)][string]$EnvPath,
        [switch]$LocalDevelopment
    )
    if ($LocalDevelopment) { return @("compose") }
    return @(
        "compose", "-f", "compose.yaml", "-f", "compose.sites-demo.yaml",
        "--env-file", $EnvPath
    )
}

function Test-DemoHttpsOrigin {
    param([string]$Value)
    $uri = $null
    if (-not [Uri]::TryCreate($Value, [UriKind]::Absolute, [ref]$uri)) { return $false }
    return $uri.Scheme -eq "https" `
        -and -not $uri.UserInfo `
        -and -not $uri.Query `
        -and -not $uri.Fragment `
        -and $uri.Host -ne "localhost" `
        -and -not $uri.Host.EndsWith(".invalid")
}

function Get-DemoGitState {
    param([Parameter(Mandatory)][string]$RepoRoot)
    $commit = (& git -C $RepoRoot rev-parse HEAD 2>$null | Out-String).Trim()
    $branch = (& git -C $RepoRoot branch --show-current 2>$null | Out-String).Trim()
    $changes = @(& git -C $RepoRoot status --porcelain 2>$null)
    return [ordered]@{
        commit = $commit
        branch = $branch
        clean = $changes.Count -eq 0
        changed_path_count = $changes.Count
    }
}

function Get-DemoFileSha256 {
    param([Parameter(Mandatory)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
