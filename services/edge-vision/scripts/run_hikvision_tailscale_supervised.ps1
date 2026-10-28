# VIIL-Sentinel Member 1 — supervised Hikvision via Tailscale local-only test.
# No credentials in CLI arguments, source files, logs, output or repository.
# RUN IN AN INTERACTIVE WINDOWS POWERSHELL ON THE AUTHORIZED EDGE HOST.
[CmdletBinding()]
param(
    [ValidateSet("Health", "Both")]
    [string] $Mode = "Both"
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = "D:\VIIL-Sentinel"
$python = Join-Path $root "services\edge-vision\.venv\Scripts\python.exe"
$registry = "C:\PrivateConfig\cameras.json"
$approval = "C:\PrivateConfig\privacy_approval.json"
$keyFile = "C:\PrivateConfig\.session_key"
$model = Join-Path $root "models\pose_landmarker_lite.task"
$cameraId = "hik-tailnet-live"
$port = 554
# Do not commit a site's private camera IP. Enter it locally per session.
$privateIP = (Read-Host "Enter your approved private-LAN camera IPv4 address").Trim()
$address = $null
if (-not [System.Net.IPAddress]::TryParse(
    $privateIP, [ref] $address
) -or $address.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw "Camera address must be a verified private IPv4 literal."
}
$octets = $address.GetAddressBytes()
$privateNetwork = (
    $octets[0] -eq 10 -or
    ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
    ($octets[0] -eq 192 -and $octets[1] -eq 168)
)
if (-not $privateNetwork) { throw "Camera address must be in an RFC1918 private network." }
$workingDir = Join-Path $root "services\edge-vision"

foreach ($required in @($python, $registry, $approval, $keyFile, $model)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required local runtime configuration is missing. Do not attempt capture."
    }
}
$tcp = [System.Net.Sockets.TcpClient]::new()
try {
    $pending = $tcp.BeginConnect($privateIP, $port, $null, $null)
    if (-not $pending.AsyncWaitHandle.WaitOne(4000)) {
        throw "Authorized camera RTSP TCP port is unreachable"
    }
    $tcp.EndConnect($pending)
} finally {
    $tcp.Dispose()
}
Write-Host "Tailscale-routed camera TCP endpoint is reachable (not an RTSP decode result)."

# The operator must confirm legal authorization for this particular session.
$agreement = Read-Host "Type AUTHORIZED to confirm consent and a supervised non-clinical camera test"
if ($agreement -cne "AUTHORIZED") { throw "Camera test cancelled: no operator authorization." }

# Verify the signed camera-scoped privacy approval BEFORE asking for credentials.
# The key stays in this PowerShell process and its child Python process only.
try {
    $env:VIIL_PRIVACY_APPROVAL_KEY = (
        Get-Content -LiteralPath $keyFile -Raw -ErrorAction Stop
    ).Trim()
    & $python -c "import sys; from pathlib import Path; sys.path.insert(0,r'$workingDir'); from sentinel_edge.privacy_gate import verify_privacy_approval; verify_privacy_approval(Path(r'C:\PrivateConfig\privacy_approval.json'),camera_id='hik-tailnet-live'); print('Signed live-camera approval verified')" 2>$null
    if ($LASTEXITCODE -ne 0) { throw "Signed camera-specific privacy approval was denied." }

    Write-Host "Enter the ROTATED, READ-ONLY Hikvision account in the local credential prompt."
    $credential = Get-Credential -Message "Hikvision read-only camera account (local only)"
    if ($null -eq $credential) { throw "No camera credentials provided." }
    $userPart = [Uri]::EscapeDataString($credential.UserName)
    $passwordPart = [Uri]::EscapeDataString($credential.GetNetworkCredential().Password)
    if ([string]::IsNullOrEmpty($userPart) -or [string]::IsNullOrEmpty($passwordPart)) {
        throw "Camera username or password missing"
    }

    # Sensitive URL is carried ONLY in a private process environment variable.
    # It is never emitted as a shell command argument, URL log or saved file.
    $env:VIIL_HIK_TAILSCALE_RTSP = "rtsp://${userPart}:${passwordPart}@${privateIP}:${port}/Streaming/Channels/102"
    $passwordPart = $null
    $credential = $null
    $env:OPENCV_LOG_LEVEL = "SILENT"
    $env:OPENCV_FFMPEG_LOGLEVEL = "0"
    Push-Location $workingDir
    try {
        Write-Host "Running authorized 12-frame RTSP decode health check..."
        & $python -m sentinel_edge.camera_health `
            --camera-registry $registry `
            --camera-id $cameraId `
            --privacy-approval $approval `
            --frames 12 `
            --confirm-authorized-camera 2>$null
        if ($LASTEXITCODE -ne 0) {
            throw "RTSP health check did not return a readable 12-frame result."
        }
        if ($Mode -eq "Both") {
            Write-Host "RTSP decode passed. Running bounded 100-frame pose / fall candidate smoke test..."
            & $python -m sentinel_edge.runner `
                --source camera `
                --camera-registry $registry `
                --camera-id $cameraId `
                --privacy-approval $approval `
                --model $model `
                --candidate-format v1 `
                --confirm-consent `
                --rtsp-retries 1 `
                --rtsp-session-seconds 60 `
                --max-frames 100 `
                --profile-rtsp 2>$null
            if ($LASTEXITCODE -ne 0) {
                throw "Edge smoke test did not finish successfully."
            }
        }
    } finally {
        Pop-Location
    }
    Write-Host "Bounded test complete. This does not measure fall accuracy or validate emergency use."
} finally {
    Remove-Item Env:VIIL_HIK_TAILSCALE_RTSP -ErrorAction SilentlyContinue
    Remove-Item Env:VIIL_PRIVACY_APPROVAL_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:OPENCV_LOG_LEVEL -ErrorAction SilentlyContinue
    Remove-Item Env:OPENCV_FFMPEG_LOGLEVEL -ErrorAction SilentlyContinue
    $userPart = $null
    $passwordPart = $null
    $credential = $null
}
