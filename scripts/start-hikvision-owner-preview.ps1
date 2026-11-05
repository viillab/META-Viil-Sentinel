# Owner-controlled, one-session Hikvision preview (not public streaming).
# A genuinely reviewed unsigned policy and explicit human attestations are
# mandatory. A new random HMAC key is kept in process memory for THIS session.
# All temporary approvals are removed, even on failure or operator cancellation.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$CameraIp,
    [Parameter(Mandatory=$true)][string]$ReviewedUnsignedApproval,
    [string]$SourceId = 'staged-camera-01',
    [switch]$ConfirmSiteOwnership,
    [switch]$ConfirmPrivacyReviewAndNotices,
    [switch]$ShowPoseOverlay,
    [ValidateRange(1, 8)][int]$PoseStride = 2,
    [ValidateSet('pyav','opencv')][string]$PreviewDecoder = 'pyav',
    [ValidateRange(1, 120)][int]$PreviewSeconds = 20,
    [ValidateRange(1, 900)][int]$PreviewFrames = 200,
    [switch]$VerifyPolicyOnly
)

$ErrorActionPreference = 'Stop'
$edge = 'D:\VIIL-Sentinel\services\edge-vision'
$python = Join-Path $edge '.venv\Scripts\python.exe'
$launcher = 'D:\VIIL-Sentinel\scripts\start-hikvision-staged.ps1'
$oldKey = [Environment]::GetEnvironmentVariable('VIIL_PRIVACY_APPROVAL_KEY', 'Process')
$sessionPath = $null
$keyBytes = $null
$keyText = $null
$exitStatus = 2

try {
    if (-not $ConfirmSiteOwnership -or -not $ConfirmPrivacyReviewAndNotices) {
        throw 'Owner and affected-person privacy confirmations required.'
    }
    if ($SourceId -cnotmatch '^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$') {
        throw 'Invalid approved source ID.'
    }
    if (-not (Test-Path -LiteralPath $python -PathType Leaf) -or
        -not (Test-Path -LiteralPath $launcher -PathType Leaf) -or
        -not (Test-Path -LiteralPath $ReviewedUnsignedApproval -PathType Leaf)) {
        throw 'Required program or reviewed unsigned document unavailable.'
    }
    if ([string]::IsNullOrEmpty($env:LOCALAPPDATA)) {
        throw 'Local user profile unavailable.'
    }
    $base = Join-Path $env:LOCALAPPDATA 'VIIL-Sentinel\OwnerPreviewSessions'
    if (-not (Test-Path -LiteralPath $base -PathType Container)) {
        New-Item -ItemType Directory -Path $base -Force | Out-Null
    }
    $sessionPath = Join-Path $base ('session-' + [Guid]::NewGuid().ToString('N'))
    $null = [IO.Directory]::CreateDirectory($sessionPath)

    # Fail closed if NTFS cannot restrict the temporary signed policy to the
    # interactive Windows owner. Do not allow inherited broad ACLs.
    $acl = New-Object System.Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true, $false)
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $identity, 'FullControl', 'ContainerInherit, ObjectInherit',
        'None', 'Allow'
    )
    $acl.AddAccessRule($rule)
    [IO.Directory]::SetAccessControl($sessionPath, $acl)

    $keyBytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $rng.GetBytes($keyBytes)
    } finally {
        $rng.Dispose()
    }
    $keyText = [Convert]::ToBase64String($keyBytes)
    [Environment]::SetEnvironmentVariable(
        'VIIL_PRIVACY_APPROVAL_KEY', $keyText, 'Process'
    )
    $temporaryApproval = Join-Path $sessionPath 'signed-owner-session.json'

    # Reuse the PRODUCTION signer and full policy validator. Never edit or
    # invent legal references, notices, signatures or site review fields.
    Push-Location $edge
    try {
        & $python '-m' 'sentinel_edge.privacy_approval_operator' 'sign' `
            '--unsigned' $ReviewedUnsignedApproval `
            '--output' $temporaryApproval `
            '--source-id' $SourceId `
            '--confirm-site-authorization' '--confirm-privacy-review' 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Owner policy signing denied.' }

        & $python '-m' 'sentinel_edge.privacy_approval_operator' 'verify' `
            '--signed' $temporaryApproval '--source-id' $SourceId 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Owner policy verification denied.' }
    } finally {
        Pop-Location
    }

    if ($VerifyPolicyOnly) {
        Write-Output 'OWNER_POLICY_VERIFIED_ONLY camera_opened=false video_recorded=false'
        $exitStatus = 0
    } else {
        $cameraArgs = @(
            '-NoProfile', '-File', $launcher,
            '-CameraIp', $CameraIp,
            '-PrivacyApproval', $temporaryApproval,
            '-SourceId', $SourceId,
            '-ShowPreview',
            '-PreviewDecoder', $PreviewDecoder,
            '-PreviewSeconds', [string]$PreviewSeconds,
            '-PreviewFrames', [string]$PreviewFrames
        )
        if ($ShowPoseOverlay) {
            $cameraArgs += @('-ShowPoseOverlay', '-PoseStride', [string]$PoseStride)
        }
        # The existing launcher owns all credential prompts, 12-frame
        # preflight, privacy rechecks, fallback and bounded live GUI.
        & powershell.exe @cameraArgs
        if ($LASTEXITCODE -ne 0) {
            throw 'Protected live camera preview did not complete.'
        }
        $exitStatus = 0
    }
} catch {
    # Never echo native errors, IP, file contents, source IDs, or secrets.
    Write-Warning 'Owner preview denied or unavailable. Review policy and local camera prerequisites.'
} finally {
    [Environment]::SetEnvironmentVariable('VIIL_PRIVACY_APPROVAL_KEY', $oldKey, 'Process')
    if ($null -ne $keyBytes) {
        [Array]::Clear($keyBytes, 0, $keyBytes.Length)
    }
    $keyText = $null
    if ($null -ne $sessionPath -and (Test-Path -LiteralPath $sessionPath)) {
        try {
            Remove-Item -LiteralPath $sessionPath -Force -Recurse -ErrorAction Stop
        } catch {
            $exitStatus = 2
            Write-Warning 'Temporary signed approval cleanup failed; manually secure the owner session folder.'
        }
    }
}
exit $exitStatus
