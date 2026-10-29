"""Windows-only RTSP launcher regression checks; never contact a camera.

The native exception-path test deliberately writes fake stderr. PowerShell 5.1
converts redirected stderr into NativeCommandError when EAP is Stop, so the
launcher helper must preserve the child exit status without raising and
prevent suppression from skipping same-camera fallback.
"""
from pathlib import Path
import subprocess
import sys

import pytest


REPO = Path(__file__).resolve().parents[3]
LAUNCHER = REPO / "scripts" / "start-hikvision-staged.ps1"
WINDOWS_ONLY = pytest.mark.skipif(sys.platform != "win32", reason="Windows PowerShell 5.1 native stderr semantics")


@WINDOWS_ONLY
def test_native_stderr_does_not_skip_fallback_and_exit_code_preserved():
    # Extract ONLY the helper declaration: don't execute the launcher or probe.
    code = r"""
$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:VIIL_TEST_LAUNCHER,[ref]$tokens,[ref]$errors)
if($errors.Count) { throw 'Launcher syntax error' }
$fn = $ast.Find({
  param($node)
  ($node -is [System.Management.Automation.Language.FunctionDefinitionAst]) -and
    ($node.Name -eq 'Invoke-PrivateEdgePython')
}, $true)
if($null -eq $fn) { throw 'Helper unavailable' }
. ([ScriptBlock]::Create($fn.Extent.Text))
$python = $env:VIIL_TEST_PYTHON
$fail = Invoke-PrivateEdgePython -Arguments @('-c','import sys;sys.stderr.write(chr(88));sys.exit(23)')
$ok = Invoke-PrivateEdgePython -Arguments @('-c','import sys;sys.exit(0)')
if($fail -ne 23 -or $ok -ne 0 -or $ErrorActionPreference -ne 'Stop') {
  throw 'Native stderr error leaked into fallback control flow'
}
'LAUNCHER_NATIVE_ERROR_PASS'
"""
    import os

    env = os.environ.copy()
    env["VIIL_TEST_LAUNCHER"] = str(LAUNCHER)
    env["VIIL_TEST_PYTHON"] = sys.executable
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", code],
        capture_output=True, text=True, timeout=25, env=env, check=False,
    )
    assert result.returncode == 0, result.stderr[-500:]
    assert "LAUNCHER_NATIVE_ERROR_PASS" in result.stdout


@WINDOWS_ONLY
def test_missing_authorization_never_opens_a_camera():
    # A deliberately nonexistent policy path must fail before credential
    # prompts, FFmpeg/MediaPipe imports, or RTSP connection attempts.
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-File", str(LAUNCHER),
            "-CameraIp", "192.168.50.10",
            "-PrivacyApproval", "C:\\VIIL_TEST_NONEXISTENT\\signed-policy.json",
        ],
        capture_output=True, text=True, timeout=25, check=False,
    )
    assert result.returncode == 2
    assert "No successful live decode claimed" in result.stdout + result.stderr


@WINDOWS_ONLY
def test_health_pass_selects_verified_stream_as_edge_primary():
    # Offline function-level contract: neither RTSP URL nor camera is accessed.
    code = r"""
$ErrorActionPreference = 'Stop'
$t=$null; $e=$null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($env:VIIL_TEST_LAUNCHER,[ref]$t,[ref]$e)
if($e.Count){throw 'launcher syntax invalid'}
$fn = $ast.Find({
  param($node)
  ($node -is [System.Management.Automation.Language.FunctionDefinitionAst]) -and
    ($node.Name -eq 'Resolve-PreferredHikvisionStreams')
},$true)
if($null -eq $fn){throw 'missing selection'}
. ([ScriptBlock]::Create($fn.Extent.Text))
$sub = Resolve-PreferredHikvisionStreams -SubstreamReadable $true
$main = Resolve-PreferredHikvisionStreams -SubstreamReadable $false
if ($sub.PrimaryEnv -ne 'VIIL_HIK_LAN_SUB' -or
    $sub.FallbackEnv -ne 'VIIL_HIK_LAN_MAIN' -or
    $main.PrimaryEnv -ne 'VIIL_HIK_LAN_MAIN' -or
    $main.FallbackEnv -ne 'VIIL_HIK_LAN_SUB') {
  throw 'No verified stream preference'
}
'HEALTH_SELECTED_STREAM_PASS'
"""
    import os

    env = os.environ.copy()
    env["VIIL_TEST_LAUNCHER"] = str(LAUNCHER)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", code],
        capture_output=True, text=True, timeout=25, env=env, check=False,
    )
    assert result.returncode == 0, result.stderr[-500:]
    assert "HEALTH_SELECTED_STREAM_PASS" in result.stdout
    launcher_text = LAUNCHER.read_text(encoding="utf-8")
    assert "'--rtsp-env', $streamOrder.PrimaryEnv" in launcher_text
    assert "'--rtsp-fallback-env', $streamOrder.FallbackEnv" in launcher_text


@WINDOWS_ONLY
def test_preflight_only_reports_no_real_decode():
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-File", str(LAUNCHER),
            "-CameraIp", "192.168.50.10", "-PreflightOnly",
        ],
        capture_output=True, text=True, timeout=25, check=False,
    )
    assert result.returncode == 0
    assert "CameraDecoded" in result.stdout
    assert "False" in result.stdout
