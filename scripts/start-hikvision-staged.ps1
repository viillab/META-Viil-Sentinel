# VIIL-Sentinel one-shot authorized Hikvision health + optional Edge experiment.
# This script never saves credentials, approval keys, images or RTSP URLs to disk.
# Only execute with genuine site authorization and signed privacy approval.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$CameraIp,
    [ValidateRange(1, 65535)][int]$RtspPort = 554,
    [string]$SourceId = 'staged-camera-01',
    [string]$PrivacyApproval,
    [string]$ModelPath = 'D:\VIIL-Sentinel\models\pose_landmarker_lite.task',
    [switch]$RunEdge,
    [ValidateSet('opencv', 'pyav')][string]$EdgeDecoder = 'opencv',
    [switch]$ShowPreview,
    [ValidateSet('opencv', 'pyav')][string]$PreviewDecoder = 'opencv',
    [ValidateRange(1, 120)][int]$PreviewSeconds = 30,
    [ValidateRange(1, 900)][int]$PreviewFrames = 450,
    [switch]$RequireDirectWifi,
    [switch]$PreflightOnly
)

$ErrorActionPreference = 'Stop'
$edge = 'D:\VIIL-Sentinel\services\edge-vision'
$python = Join-Path $edge '.venv\Scripts\python.exe'
$oldSub = [Environment]::GetEnvironmentVariable('VIIL_HIK_LAN_SUB', 'Process')
$oldMain = [Environment]::GetEnvironmentVariable('VIIL_HIK_LAN_MAIN', 'Process')
$oldKey = [Environment]::GetEnvironmentVariable('VIIL_PRIVACY_APPROVAL_KEY', 'Process')
$exitStatus = 2
$passSecure = $null
$keySecure = $null

function Resolve-PreferredHikvisionStreams {
    # Select only the environment VARIABLE names; never return RTSP secrets.
    # A successful health probe is bounded decode evidence, not reliability.
    param([Parameter(Mandatory=$true)][bool]$SubstreamReadable)
    if ($SubstreamReadable) {
        return [pscustomobject]@{
            PrimaryEnv = 'VIIL_HIK_LAN_SUB'
            FallbackEnv = 'VIIL_HIK_LAN_MAIN'
        }
    }
    return [pscustomobject]@{
        PrimaryEnv = 'VIIL_HIK_LAN_MAIN'
        FallbackEnv = 'VIIL_HIK_LAN_SUB'
    }
}

function Invoke-PrivateEdgePython {
    # PowerShell 5.1 promotes redirected native stderr to NativeCommandError
    # under ErrorActionPreference=Stop. That previously skipped fallback.
    # Keep codec stderr private, return the real child exit code, and continue
    # only on explicit success. Never stringify native exceptions (URL secrets).
    param([Parameter(Mandatory=$true)][string[]]$Arguments)
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $python @Arguments 2>$null | Out-Host
        if ($null -eq $LASTEXITCODE) { return 2 }
        return [int]$LASTEXITCODE
    } catch {
        return 2
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
}

function Test-SignedPrivacyApproval {
    # Offline application verifier: checks HMAC, dates, camera scope and flags.
    # No network, OpenCV imports, camera credentials or policy contents logged.
    param(
        [Parameter(Mandatory=$true)][string]$PolicyPath,
        [Parameter(Mandatory=$true)][string]$ApprovedSourceId
    )
    $verifyCode = 'import sys; from pathlib import Path; from sentinel_edge.privacy_gate import verify_privacy_approval; verify_privacy_approval(Path(sys.argv[1]), camera_id=sys.argv[2])'
    return (0 -eq (Invoke-PrivateEdgePython -Arguments @(
        '-c', $verifyCode, $PolicyPath, $ApprovedSourceId
    )))
}

try {
    if ($RunEdge -and $ShowPreview) {
        throw 'Choose either Edge inference or local preview for this supervised session.'
    }
    $ip = [Net.IPAddress]::Parse($CameraIp)
    if ($ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        throw 'A literal private IPv4 camera IP is required.'
    }
    $octets = $ip.GetAddressBytes()
    $private = ($octets[0] -eq 10) -or
        ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
        ($octets[0] -eq 192 -and $octets[1] -eq 168)
    if (-not $private) { throw 'Only private camera IPs are allowed.' }
    if ($SourceId -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$') {
        throw 'Invalid pseudonymous SourceId.'
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'Edge Python environment is missing.'
    }
    if ($RunEdge -and -not (Test-Path -LiteralPath $ModelPath -PathType Leaf)) {
        throw 'Pose Landmarker .task model is missing.'
    }

    # The best route can be a subnet/default route, not only an exact /32.
    # Do not change the OS route or infer direct Wi-Fi just because one VPN
    # alias is absent. This query performs no camera capture.
    $routes = @(Find-NetRoute -RemoteIPAddress $CameraIp -ErrorAction Stop)
    $selected = $routes | Where-Object { $_.InterfaceAlias } | Select-Object -First 1
    $routeAlias = if ($null -ne $selected) {
        [string]$selected.InterfaceAlias
    } else { 'unknown' }
    if ($RequireDirectWifi -and $routeAlias -ne 'Wi-Fi') {
        throw 'Direct Wi-Fi required but Windows selected a different interface. No routes changed.'
    }

    if ($PreflightOnly) {
        $approvalFileProvided = [bool]($PrivacyApproval -and
            (Test-Path -LiteralPath $PrivacyApproval -PathType Leaf))
        $signingKeyPresent = -not [string]::IsNullOrEmpty($oldKey)
        $approvalVerificationAttempted = $approvalFileProvided -and $signingKeyPresent
        $approvalVerified = $false
        if ($approvalVerificationAttempted) {
            Push-Location $edge
            try {
                $approvalVerified = Test-SignedPrivacyApproval -PolicyPath $PrivacyApproval -ApprovedSourceId $SourceId
            } finally {
                Pop-Location
            }
        }
        [pscustomobject]@{
            PreflightOnly = $true
            PrivateCameraIp = $true
            Route = $routeAlias
            PoseModelReady = (Test-Path -LiteralPath $ModelPath -PathType Leaf)
            SignedApprovalFileProvided = $approvalFileProvided
            SigningKeyPresent = $signingKeyPresent
            ApprovalVerificationAttempted = $approvalVerificationAttempted
            SignedApprovalVerified = $approvalVerified
            CameraDecoded = $false
            EdgeInferenceRun = $false
        } | Format-List
        $exitStatus = 0
    } else {
        if ([string]::IsNullOrWhiteSpace($PrivacyApproval) -or
            -not (Test-Path -LiteralPath $PrivacyApproval -PathType Leaf)) {
            throw 'A genuine locally signed privacy approval file is required before video capture.'
        }
        if ($routeAlias -eq 'Tailscale') {
            Write-Warning 'The camera destination currently routes through Tailscale, not direct Wi-Fi.'
        }
        if ([string]::IsNullOrEmpty($oldKey)) {
            $keySecure = Read-Host 'Existing official privacy signing key (masked; not saved)' -AsSecureString
            $keyPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($keySecure)
            try {
                $env:VIIL_PRIVACY_APPROVAL_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($keyPtr)
            } finally {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($keyPtr)
            }
        }
        if ([string]::IsNullOrEmpty($env:VIIL_PRIVACY_APPROVAL_KEY) -or
            [Text.Encoding]::UTF8.GetByteCount($env:VIIL_PRIVACY_APPROVAL_KEY) -lt 32) {
            throw 'Signed approval verification key is missing/too short.'
        }
        # Check the signed policy before prompting for camera credentials.
        Push-Location $edge
        try {
            if (-not (Test-SignedPrivacyApproval -PolicyPath $PrivacyApproval -ApprovedSourceId $SourceId)) {
                throw 'Signed privacy approval was denied; camera not opened.'
            }

            $cameraUser = Read-Host 'Dedicated read-only Hikvision username (local input)'
            if ([string]::IsNullOrWhiteSpace($cameraUser)) {
                throw 'Camera username is required.'
            }
            $passSecure = Read-Host 'Hikvision camera password (masked; not saved)' -AsSecureString
            $passPtr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($passSecure)
            try {
                $passText = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passPtr)
                $usernameEncoded = [Uri]::EscapeDataString($cameraUser)
                $passwordEncoded = [Uri]::EscapeDataString($passText)
                # Credential exists in this process environment only, for the child Python runner.
                $authority = "rtsp://${usernameEncoded}:${passwordEncoded}@$CameraIp`:$RtspPort"
                $env:VIIL_HIK_LAN_SUB = "$authority/Streaming/Channels/102"
                $env:VIIL_HIK_LAN_MAIN = "$authority/Streaming/Channels/101"
            } finally {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passPtr)
                $passText = $null
                $passwordEncoded = $null
                $authority = $null
            }
            Write-Host 'Authorized health probe: attempting 12 frames (no saved video)...'
            $subHealthExit = Invoke-PrivateEdgePython -Arguments @(
                '-m', 'sentinel_edge.camera_health',
                '--rtsp-env', 'VIIL_HIK_LAN_SUB',
                '--source-id', $SourceId,
                '--privacy-approval', $PrivacyApproval,
                '--confirm-authorized-camera', '--frames', '12',
                '--decoder', $(if ($ShowPreview) { $PreviewDecoder } elseif ($RunEdge) { $EdgeDecoder } else { 'opencv' }),
                '--rtsp-allow-port', [string]$RtspPort
            )
            $healthExit = $subHealthExit
            if ($subHealthExit -ne 0) {
                # The first native decoder may fail with stderr. Retry through the
                # same signed privacy gate on a distinct stream of THIS camera.
                Write-Warning 'Substream decode failed. Trying same-camera mainstream once.'
                $healthExit = Invoke-PrivateEdgePython -Arguments @(
                    '-m', 'sentinel_edge.camera_health',
                    '--rtsp-env', 'VIIL_HIK_LAN_MAIN',
                    '--source-id', $SourceId,
                    '--privacy-approval', $PrivacyApproval,
                    '--confirm-authorized-camera', '--frames', '12',
                    '--decoder', $(if ($ShowPreview) { $PreviewDecoder } elseif ($RunEdge) { $EdgeDecoder } else { 'opencv' }),
                    '--rtsp-allow-port', [string]$RtspPort
                )
            }
            if ($healthExit -ne 0) {
                throw 'No authorized stream produced 12 decoded frames; Edge was not started.'
            }
            # Prefer the stream that actually decoded in this authorized probe.
            # If 102 was unreadable, do not waste the next Edge attempt on 102.
            $streamOrder = Resolve-PreferredHikvisionStreams -SubstreamReadable ($subHealthExit -eq 0)
            Write-Host 'Verified: authorized RTSP decoder read 12/12 frames.'
            if ($ShowPreview) {
                Write-Host 'Opening authorized local-only video preview (press q / Esc to stop; no recording)...'
                $previewExit = Invoke-PrivateEdgePython -Arguments @(
                    '-m', 'sentinel_edge.live_preview',
                    '--rtsp-env', $streamOrder.PrimaryEnv,
                    '--fallback-env', $streamOrder.FallbackEnv,
                    '--source-id', $SourceId,
                    '--privacy-approval', $PrivacyApproval,
                    '--confirm-authorized-camera', '--show-local-preview',
                    '--decoder', $PreviewDecoder,
                    '--duration-seconds', [string]$PreviewSeconds,
                    '--max-frames', [string]$PreviewFrames,
                    '--rtsp-allow-port', [string]$RtspPort
                )
                if ($previewExit -ne 0) {
                    throw 'Local camera preview did not complete (details redacted).'
                }
                Write-Host 'Local camera preview ended; no video was saved or sent to the dashboard.'
            }
            if ($RunEdge) {
                Write-Host 'Starting bounded local Edge trial (max 120 frames / 60 seconds per attempt; max 2 attempts)...'
                $edgeExit = Invoke-PrivateEdgePython -Arguments @(
                    '-m', 'sentinel_edge',
                    '--source', 'rtsp',
                    '--rtsp-env', $streamOrder.PrimaryEnv,
                    '--rtsp-fallback-env', $streamOrder.FallbackEnv,
                    '--source-id', $SourceId,
                    '--privacy-approval', $PrivacyApproval,
                    '--model', $ModelPath, '--candidate-format', 'v1', '--confirm-consent',
                    '--rtsp-retries', '1', '--rtsp-retry-delay-ms', '500',
                    '--rtsp-session-seconds', '60', '--max-frames', '120', '--profile-rtsp',
                    '--rtsp-decoder', $EdgeDecoder,
                    '--rtsp-allow-port', [string]$RtspPort
                )
                if ($edgeExit -ne 0) {
                    throw 'Edge bounded trial could not complete (details redacted).'
                }
                Write-Host 'Bounded Edge trial completed; candidate events require human review.'
            }
            $exitStatus = 0
        } finally {
            Pop-Location
        }
    }
} catch {
    # The error could originate in a native codec carrying RTSP credentials.
    Write-Warning 'Camera workflow not ready or failed. No successful live decode claimed. See operator prerequisites.'
} finally {
    [Environment]::SetEnvironmentVariable('VIIL_HIK_LAN_SUB', $oldSub, 'Process')
    [Environment]::SetEnvironmentVariable('VIIL_HIK_LAN_MAIN', $oldMain, 'Process')
    [Environment]::SetEnvironmentVariable('VIIL_PRIVACY_APPROVAL_KEY', $oldKey, 'Process')
    $passSecure = $null
    $keySecure = $null
}
exit $exitStatus
