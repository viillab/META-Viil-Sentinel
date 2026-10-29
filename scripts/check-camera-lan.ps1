# Targeted, credential-free route and TCP diagnostic for an authorized camera IP.
# This does NOT verify camera consent, RTSP decode, or direct Wi-Fi routing.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string] $CameraIp,
    [ValidateRange(1,65535)] [int] $RtspPort = 554
)
$ErrorActionPreference = 'Stop'
try { $ip = [System.Net.IPAddress]::Parse($CameraIp) }
catch { throw 'CameraIp must be a literal private IPv4 address' }
if ($ip.AddressFamily -ne [System.Net.Sockets.AddressFamily]::InterNetwork) {
    throw 'CameraIp must be a private IPv4 literal'
}
$b = $ip.GetAddressBytes()
$isPrivate = ($b[0] -eq 10) -or (
    $b[0] -eq 172 -and $b[1] -ge 16 -and $b[1] -le 31
) -or ($b[0] -eq 192 -and $b[1] -eq 168)
if (-not $isPrivate) { throw 'Only RFC1918 private camera IPs are permitted' }
$routeName = 'unavailable'
try {
    $routes = @(Find-NetRoute -RemoteIPAddress $CameraIp -ErrorAction Stop)
    if ($routes.Count -gt 0) { $routeName = $routes[0].InterfaceAlias }
} catch { $routeName = 'route-query-failed' }
# One authorized target only: no subnet discovery or credential access.
$test = Test-NetConnection -ComputerName $CameraIp -Port $RtspPort -InformationLevel Detailed -WarningAction SilentlyContinue
[pscustomobject]@{
    Scope = 'One private target TCP handshake only'
    SelectedRoute = $routeName
    ActualInterface = $test.InterfaceAlias
    TcpConnect = [bool]$test.TcpTestSucceeded
    IsDirectWifi = [bool]($test.TcpTestSucceeded -and $test.InterfaceAlias -eq 'Wi-Fi')
    RtspDecoded = $false
    PrivacyApprovalVerified = $false
}
