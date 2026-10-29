# Read-only Hikvision ISAPI configuration audit (NOT VIDEO).
# Requires only camera operator access. No signed VIDEO approval is implied.
# This command does not change camera config or save credentials or images.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$CameraIp,
    [ValidateSet(80, 8080)][int]$HttpPort = 80
)
$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '..\services\edge-vision\.venv\Scripts\python.exe'
$edge = Join-Path $PSScriptRoot '..\services\edge-vision'
$oldUser = [Environment]::GetEnvironmentVariable('VIIL_HIK_HTTP_USER', 'Process')
$oldPass = [Environment]::GetEnvironmentVariable('VIIL_HIK_HTTP_PASS', 'Process')
$secret = $null
$plain = $null
$ptr = [IntPtr]::Zero
$exitStatus = 2
try {
    if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
        throw 'Edge Python environment missing.'
    }
    # Reject non-private targets before requesting credentials or network.
    $ip = [Net.IPAddress]::Parse($CameraIp)
    if ($ip.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        throw 'RFC1918 camera IPv4 required.'
    }
    $octets = $ip.GetAddressBytes()
    $private = ($octets[0] -eq 10) -or
        ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
        ($octets[0] -eq 192 -and $octets[1] -eq 168)
    if (-not $private) { throw 'Private camera IPv4 required.' }
    Write-Host 'READ ONLY: Inspecting Hikvision ISAPI stream configuration (no video).'
    $user = Read-Host 'Authorized read-only Hikvision username'
    if ([string]::IsNullOrWhiteSpace($user)) { throw 'Camera username required.' }
    $secret = Read-Host 'Hikvision password (masked, never saved)' -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    if ([string]::IsNullOrEmpty($plain)) { throw 'Camera password required.' }
    $env:VIIL_HIK_HTTP_USER = $user
    $env:VIIL_HIK_HTTP_PASS = $plain
    $user = $null
    $plain = $null
    Push-Location $edge
    try {
        # Child output contains ALLOWLISTED configuration fields only.
        # Native stderr can include secrets; do not display it.
        $previous = $ErrorActionPreference
        try {
            $ErrorActionPreference = 'Continue'
            & $python -m sentinel_edge.hikvision_isapi_audit --camera-ip $CameraIp --http-port $HttpPort 2>$null
            if ($LASTEXITCODE -eq 0) { $exitStatus = 0 }
        } finally {
            $ErrorActionPreference = $previous
        }
    } finally {
        Pop-Location
    }
} catch {
    Write-Warning 'Read-only camera configuration audit unavailable (details redacted).'
} finally {
    [Environment]::SetEnvironmentVariable('VIIL_HIK_HTTP_USER', $oldUser, 'Process')
    [Environment]::SetEnvironmentVariable('VIIL_HIK_HTTP_PASS', $oldPass, 'Process')
    if ($ptr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    }
    $secret = $null
    $plain = $null
}
exit $exitStatus
