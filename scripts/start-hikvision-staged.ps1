# VIIL-Sentinel one-shot authorized Hikvision health + optional Edge experiment.
# This script never saves credentials, approval keys, images or RTSP URLs to disk.
# Only execute with genuine site authorization and signed privacy approval.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$CameraIp,
    [ValidateRange(1, 65535)][int]$RtspPort = 554,
    [ValidateSet(80, 8080)][int]$HttpPort = 80,
    [string]$SourceId = 'staged-camera-01',
    [string]$PrivacyApproval,
    [string]$ModelPath = 'D:\VIIL-Sentinel\models\pose_landmarker_lite.task',
    [switch]$RunEdge,
    [ValidateSet('opencv', 'pyav', 'http-mjpeg')][string]$EdgeDecoder = 'opencv',
    [switch]$ShowPreview,
    [ValidateSet('opencv', 'pyav', 'http-mjpeg')][string]$PreviewDecoder = 'opencv',
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
$oldHttpUrl = [Environment]::GetEnvironmentVariable('VIIL_HIK_HTTP_URL', 'Process')
$oldHttpUser = [Environment]::GetEnvironmentVariable('VIIL_HIK_HTTP_USER', 'Process')
$oldHttpPass = [Environment]::GetEnvironmentVariable('VIIL_HIK_HTTP_PASS', 'Process')
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

function ConvertTo-SafeRtspProfileLine {
    # Strictly reconstruct numeric/boolean summaries from known Edge JSON.
    # NEVER display raw native stderr: FFmpeg may embed RTSP credentials.
    param([string]$Message)
    if ([string]::IsNullOrWhiteSpace($Message) -or $Message.Length -gt 4096) {
        return $null
    }
    $marker = 'RESEARCH_RTSP_PROFILE '
    $at = $Message.IndexOf($marker, [StringComparison]::Ordinal)
    if ($at -lt 0) { return $null }
    $payload = $Message.Substring($at + $marker.Length).Trim()
    if (-not ($payload.StartsWith('{') -and $payload.EndsWith('}'))) {
        return $null
    }
    try {
        $p = ConvertFrom-Json -InputObject $payload -ErrorAction Stop
        if ($null -eq $p -or $p.schema_version -cne 'viil.edge.rtsp_profile.v1' -or
            $p.research_only -cne $true -or
            $p.no_camera_or_personal_identifiers -cne $true -or
            $p.stream_interrupted -isnot [bool]) {
            return $null
        }
        foreach ($name in @(
            'frames_processed', 'pose_unavailable_frames',
            'candidate_events_unconfirmed'
        )) {
            $n = $p.$name
            if (($n -isnot [int] -and $n -isnot [long]) -or
                $n -lt 0 -or $n -gt 10000000) {
                return $null
            }
        }
        if ($p.pose_unavailable_frames -gt $p.frames_processed -or
            $p.candidate_events_unconfirmed -gt $p.frames_processed) {
            return $null
        }
        foreach ($name in @(
            'observed_cycle_throughput_fps', 'cycle_p50_ms',
            'cycle_p95_ms', 'sampled_process_rss_max_mib'
        )) {
            $n = $p.$name
            if ($null -eq $n) { continue }
            if (($n -isnot [int] -and $n -isnot [long] -and
                 $n -isnot [double] -and $n -isnot [decimal]) -or
                [double]::IsNaN([double]$n) -or
                [double]::IsInfinity([double]$n) -or
                $n -lt 0 -or $n -gt 1000000000) {
                return $null
            }
        }
        $fps = if ($null -eq $p.observed_cycle_throughput_fps) {
            'n/a'
        } else { '{0:F2}' -f [double]$p.observed_cycle_throughput_fps }
        $p95 = if ($null -eq $p.cycle_p95_ms) {
            'n/a'
        } else { '{0:F2}' -f [double]$p.cycle_p95_ms }
        $rss = if ($null -eq $p.sampled_process_rss_max_mib) {
            'n/a'
        } else { '{0:F2}' -f [double]$p.sampled_process_rss_max_mib }
        $interrupted = if ($p.stream_interrupted) { 'yes' } else { 'no' }
        $safeFormat = ('EDGE_SAFE_RTSP_METRICS frames={0} pose_unavailable={1} ' +
                       'candidates_unconfirmed={2} cycle_fps={3} ' +
                       'cycle_p95_ms={4} rss_sampled_mib={5} interrupted={6}')
        return ($safeFormat -f $p.frames_processed, $p.pose_unavailable_frames,
                $p.candidate_events_unconfirmed, $fps, $p95, $rss,
                $interrupted)
    } catch {
        # Never print parse errors, malicious content, or source text.
        return $null
    }
}

function Invoke-PrivateEdgePython {
    # PowerShell 5.1 promotes redirected native stderr to NativeCommandError
    # under ErrorActionPreference=Stop. That previously skipped fallback.
    # Keep codec stderr private, return the real child exit code, and continue
    # only on explicit success. Never stringify native exceptions (URL secrets).
    param(
        [Parameter(Mandatory=$true)][string[]]$Arguments,
        [switch]$ShowSafeRtspMetrics
    )
    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if ($ShowSafeRtspMetrics) {
            # Native stderr and stdout are parsed IN MEMORY, never printed
            # directly. Even forged metric JSON can only produce sanitized
            # numeric/boolean output; raw video, credentials and events stay out.
            & $python @Arguments 2>&1 | ForEach-Object {
                $safeLine = ConvertTo-SafeRtspProfileLine -Message ([string]$_)
                if (-not [string]::IsNullOrEmpty($safeLine)) {
                    Write-Host $safeLine
                }
            }
        } else {
            & $python @Arguments 2>$null | Out-Host
        }
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
    if ($EdgeDecoder -eq 'http-mjpeg' -and -not $RunEdge) {
        throw 'HTTP MJPEG Edge decoder requires -RunEdge.'
    }
    if ($PreviewDecoder -eq 'http-mjpeg' -and (-not $ShowPreview -or $RunEdge)) {
        throw 'HTTP MJPEG is only available for authorized local preview.'
    }
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
                if (($ShowPreview -and $PreviewDecoder -eq 'http-mjpeg') -or
                    ($RunEdge -and $EdgeDecoder -eq 'http-mjpeg')) {
                    $env:VIIL_HIK_HTTP_URL = "http://$CameraIp`:$HttpPort/ISAPI/Streaming/channels/102/httpPreview"
                    $env:VIIL_HIK_HTTP_USER = $cameraUser
                    $env:VIIL_HIK_HTTP_PASS = $passText
                }
            } finally {
                [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passPtr)
                $passText = $null
                $passwordEncoded = $null
                $authority = $null
            }
            if (($ShowPreview -and $PreviewDecoder -eq 'http-mjpeg') -or
                ($RunEdge -and $EdgeDecoder -eq 'http-mjpeg')) {
                Write-Host 'Authorized HTTP Digest MJPEG probe: 12 frames, in-memory only...'
                $httpHealthExit = Invoke-PrivateEdgePython -Arguments @(
                    '-m', 'sentinel_edge.camera_health',
                    '--http-mjpeg-env', 'VIIL_HIK_HTTP_URL',
                    '--decoder', 'http-mjpeg',
                    '--source-id', $SourceId,
                    '--privacy-approval', $PrivacyApproval,
                    '--confirm-authorized-camera', '--frames', '12',
                    '--rtsp-allow-port', [string]$HttpPort
                )
                if ($httpHealthExit -ne 0) {
                    throw 'HTTP MJPEG unavailable: verify camera supports MJPEG substream 102.'
                }
                Write-Host 'Verified: authorized HTTP MJPEG decoder read 12/12 frames.'
                if ($ShowPreview) {
                $httpPreviewExit = Invoke-PrivateEdgePython -Arguments @(
                    '-m', 'sentinel_edge.live_preview',
                    '--http-mjpeg-env', 'VIIL_HIK_HTTP_URL',
                    '--decoder', 'http-mjpeg',
                    '--source-id', $SourceId,
                    '--privacy-approval', $PrivacyApproval,
                    '--confirm-authorized-camera', '--show-local-preview',
                    '--duration-seconds', [string]$PreviewSeconds,
                    '--max-frames', [string]$PreviewFrames,
                    '--rtsp-allow-port', [string]$HttpPort
                )
                if ($httpPreviewExit -ne 0) {
                    throw 'Authorized local HTTP MJPEG preview failed (details redacted).'
                }
                Write-Host 'HTTP MJPEG preview ended; video was not saved or transmitted.'
                }
                if ($RunEdge) {
                    Write-Host 'Starting bounded HTTP MJPEG Edge trial (120 frames / 60 seconds maximum)...'
                    $httpEdgeExit = Invoke-PrivateEdgePython -ShowSafeRtspMetrics -Arguments @(
                        '-m', 'sentinel_edge',
                        '--source', 'http-mjpeg',
                        '--http-mjpeg-env', 'VIIL_HIK_HTTP_URL',
                        '--source-id', $SourceId,
                        '--privacy-approval', $PrivacyApproval,
                        '--model', $ModelPath,
                        '--candidate-format', 'v1', '--confirm-consent',
                        '--max-frames', '120'
                    )
                    if ($httpEdgeExit -ne 0) {
                        throw 'Bounded HTTP MJPEG Edge trial failed (details redacted).'
                    }
                    Write-Host 'HTTP MJPEG Edge trial completed; candidates require human review.'
                }
            } else {
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
                $edgeExit = Invoke-PrivateEdgePython -ShowSafeRtspMetrics -Arguments @(
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
    [Environment]::SetEnvironmentVariable('VIIL_HIK_HTTP_URL', $oldHttpUrl, 'Process')
    [Environment]::SetEnvironmentVariable('VIIL_HIK_HTTP_USER', $oldHttpUser, 'Process')
    [Environment]::SetEnvironmentVariable('VIIL_HIK_HTTP_PASS', $oldHttpPass, 'Process')
    [Environment]::SetEnvironmentVariable('VIIL_PRIVACY_APPROVAL_KEY', $oldKey, 'Process')
    $passSecure = $null
    $keySecure = $null
}
exit $exitStatus
