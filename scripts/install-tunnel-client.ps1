param([string]$InstallDirectory = ".runtime\tools\tunnel-client")

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$targetDir = Join-Path $repoRoot $InstallDirectory
$downloadDir = Join-Path $repoRoot ".runtime\downloads\tunnel-client"
$architecture = if ([Environment]::Is64BitOperatingSystem) { "amd64" } else { throw "Only 64-bit Windows is supported by this installer." }
$headers = @{ "User-Agent" = "Mold-AI-Platform-Setup" }

$release = Invoke-RestMethod -Headers $headers -Uri "https://api.github.com/repos/openai/tunnel-client/releases/latest"
$assetName = "tunnel-client-$($release.tag_name)-windows-$architecture.zip"
$asset = $release.assets | Where-Object { $_.name -eq $assetName } | Select-Object -First 1
$checksums = $release.assets | Where-Object { $_.name -eq "SHA256SUMS.txt" } | Select-Object -First 1
if (-not $asset -or -not $checksums) { throw "The latest official release does not contain the expected Windows artifact or checksum manifest." }

[IO.Directory]::CreateDirectory($downloadDir) | Out-Null
[IO.Directory]::CreateDirectory($targetDir) | Out-Null
$zipPath = Join-Path $downloadDir $assetName
$checksumPath = Join-Path $downloadDir "SHA256SUMS.txt"
Invoke-WebRequest -UseBasicParsing -Headers $headers -Uri $asset.browser_download_url -OutFile $zipPath
Invoke-WebRequest -UseBasicParsing -Headers $headers -Uri $checksums.browser_download_url -OutFile $checksumPath

$checksumLine = Get-Content -LiteralPath $checksumPath | Where-Object { $_ -match "\s\*?$([regex]::Escape($assetName))$" } | Select-Object -First 1
if (-not $checksumLine) { throw "The official checksum manifest does not list $assetName." }
$expectedHash = ($checksumLine -split "\s+")[0].ToUpperInvariant()
$actualHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualHash -ne $expectedHash) { throw "tunnel-client SHA-256 verification failed." }

Expand-Archive -LiteralPath $zipPath -DestinationPath $targetDir -Force
$client = Get-ChildItem -LiteralPath $targetDir -Filter "tunnel-client.exe" -File -Recurse | Select-Object -First 1
if (-not $client) { throw "The verified archive did not contain tunnel-client.exe." }
$version = & $client.FullName --version 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { throw "The installed tunnel-client executable did not start." }

Write-Host "Installed verified OpenAI tunnel-client $($release.tag_name): $($client.FullName)"
Write-Host $version.Trim()
