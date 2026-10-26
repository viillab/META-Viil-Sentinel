# Run from any directory; activates the repository-local safety hooks.
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
& git -C $repoRoot config --local core.hooksPath .githooks
if ($LASTEXITCODE -ne 0) { throw "Unable to configure Git hook path" }
Write-Host "VIIL Sentinel local Git guardrails installed." -ForegroundColor Green
Write-Host "Main commits and pushes are blocked locally. Configure GitHub branch rules separately."
