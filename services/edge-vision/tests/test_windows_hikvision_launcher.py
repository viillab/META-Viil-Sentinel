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

from privacy_approval_fixture import make_policy


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
def test_operator_metrics_strict_allowlist_and_native_stderr_redaction():
    # Exercise the production PowerShell functions without launching a camera.
    # The child emits both a valid metric and invented credential leaks.
    code = r"""
$ErrorActionPreference = 'Stop'
$tokens=$null; $errors=$null
$ast = [System.Management.Automation.Language.Parser]::ParseFile(
    $env:VIIL_TEST_LAUNCHER,[ref]$tokens,[ref]$errors
)
if ($errors.Count) { throw 'Launcher syntax error' }
foreach($name in @('ConvertTo-SafeRtspProfileLine','Invoke-PrivateEdgePython')) {
    $fn = $ast.Find({
        param($node)
        ($node -is [System.Management.Automation.Language.FunctionDefinitionAst]) -and
        ($node.Name -eq $name)
    }, $true)
    if ($null -eq $fn) { throw 'Required helper unavailable' }
    . ([ScriptBlock]::Create($fn.Extent.Text))
}
$python = $env:VIIL_TEST_PYTHON
$p = @{
  schema_version='viil.edge.rtsp_profile.v1'
  research_only=$true
  no_camera_or_personal_identifiers=$true
  stream_interrupted=$false
  frames_processed=120
  pose_unavailable_frames=10
  candidate_events_unconfirmed=2
  observed_cycle_throughput_fps=12.35
  cycle_p50_ms=77.2
  cycle_p95_ms=110.4
  sampled_process_rss_max_mib=185.45
  camera_url='rtsp://reader:FAKE-SECRET-NOT-FOR-LOGS@192.168.88.1'
}
$line = 'RESEARCH_RTSP_PROFILE ' + ($p | ConvertTo-Json -Compress)
$parsed = ConvertTo-SafeRtspProfileLine -Message $line
if (-not $parsed -or $parsed -notmatch 'frames=120' -or
    $parsed -notmatch 'cycle_p95_ms=110.40' -or
    $parsed -match 'FAKE-SECRET') { throw 'Profile sanitization failed' }
$p.cycle_p95_ms = 'FAKE-SECRET-NOT-FOR-LOGS'
$malicious = ConvertTo-SafeRtspProfileLine -Message (
    'RESEARCH_RTSP_PROFILE ' + ($p | ConvertTo-Json -Compress)
)
if ($null -ne $malicious) { throw 'Unsafe profile type allowed' }
$p.cycle_p95_ms = 110.4
$p.schema_version = 'VIIL_NOT_THE_PRODUCTION_SCHEMA'
if ($null -ne (ConvertTo-SafeRtspProfileLine -Message (
    'RESEARCH_RTSP_PROFILE ' + ($p | ConvertTo-Json -Compress)
))) { throw 'Wrong schema was accepted' }
$env:VIIL_TEST_SAFE_STDERR = $line +
    [Environment]::NewLine + 'raw-stderr-FAKE-SECRET-NOT-FOR-LOGS'
$env:VIIL_TEST_SAFE_STDOUT = 'stdout-FAKE-SECRET-NOT-FOR-LOGS'
$source = "import os,sys;sys.stderr.write(os.environ['VIIL_TEST_SAFE_STDERR']+chr(10));sys.stdout.write(os.environ['VIIL_TEST_SAFE_STDOUT']+chr(10));sys.exit(23)"
$exit = Invoke-PrivateEdgePython -ShowSafeRtspMetrics -Arguments @('-c',$source)
if ($exit -ne 23 -or $ErrorActionPreference -ne 'Stop') {
    throw ('Native status/EAP not preserved: exit=' + $exit + '; eap=' + $ErrorActionPreference)
}
'FILTER_NATIVE_PASS'
"""
    import os

    env = os.environ.copy()
    env["VIIL_TEST_LAUNCHER"] = str(LAUNCHER)
    env["VIIL_TEST_PYTHON"] = sys.executable
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", code],
        capture_output=True, text=True, timeout=35, check=False, env=env,
    )
    assert result.returncode == 0, result.stderr[-500:]
    combined = result.stdout + result.stderr
    assert "FILTER_NATIVE_PASS" in combined
    assert "EDGE_SAFE_RTSP_METRICS" in combined
    assert "frames=120" in combined
    assert "cycle_fps=12.35" in combined
    assert "FAKE-SECRET-NOT-FOR-LOGS" not in combined
    assert "192.168.88.1" not in combined


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
@pytest.mark.parametrize("case,expected", [
    ("valid", True),
    ("tampered", False),
    ("wrong_camera", False),
    ("expired", False),
    ("missing_key", False),
    ("wrong_key", False),
])
def test_offline_preflight_checks_real_hmac_and_scope_without_capture(
    tmp_path, monkeypatch, case, expected,
):
    import json
    import os
    import re
    from datetime import date, timedelta

    kwargs = {}
    if case == "expired":
        kwargs = {
            "valid_from": (date.today() - timedelta(days=4)).isoformat(),
            "expires_on": (date.today() - timedelta(days=1)).isoformat(),
        }
    policy = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",), **kwargs)
    if case == "tampered":
        contents = json.loads(policy.read_text(encoding="utf-8"))
        contents["notices_confirmed"] = False
        policy.write_text(json.dumps(contents), encoding="utf-8")
    scoped_id = "zone-b" if case == "wrong_camera" else "zone-a"
    env = os.environ.copy()
    if case == "missing_key":
        env.pop("VIIL_PRIVACY_APPROVAL_KEY", None)
    elif case == "wrong_key":
        env["VIIL_PRIVACY_APPROVAL_KEY"] = "different-test-key-that-is-not-valid-123456"
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-File", str(LAUNCHER),
            "-CameraIp", "192.168.50.10", "-SourceId", scoped_id,
            "-PrivacyApproval", str(policy), "-PreflightOnly",
        ],
        capture_output=True, text=True, timeout=35, check=False, env=env,
    )
    assert result.returncode == 0, result.stderr[-300:]
    assert re.search(
        rf"SignedApprovalVerified\s*:\s*{expected}", result.stdout, re.IGNORECASE,
    ), result.stdout
    assert re.search(r"CameraDecoded\s*:\s*False", result.stdout)
    attempted = case != "missing_key"
    assert re.search(rf"ApprovalVerificationAttempted\s*:\s*{attempted}", result.stdout)
    assert "test_approval_0001" not in result.stdout + result.stderr
    assert "synthetic-only-key" not in result.stdout + result.stderr


@WINDOWS_ONLY
@pytest.mark.parametrize("extra", [
    ["-ShowPreview"], ["-ShowPreview", "-RunEdge"],
])
def test_preview_launcher_fails_closed_without_signed_approval_or_credential_prompts(extra):
    result = subprocess.run(
        [
            "powershell.exe", "-NoProfile", "-File", str(LAUNCHER),
            "-CameraIp", "192.168.50.10", *extra,
            "-PrivacyApproval", "C:\\VIIL_TEST_NONEXISTENT\\signed-policy.json",
        ],
        capture_output=True, text=True, timeout=25, check=False,
    )
    assert result.returncode == 2
    assert "No successful live decode claimed" in result.stdout + result.stderr
    assert "Authorized health probe" not in result.stdout + result.stderr


@WINDOWS_ONLY
def test_preview_switch_routes_to_local_only_gui_and_never_reuses_edge_inference():
    script = LAUNCHER.read_text(encoding="utf-8")
    assert "[switch]$ShowPreview" in script
    assert "'-m', 'sentinel_edge.live_preview'" in script
    assert "'--show-local-preview'" in script
    assert "'--fallback-env', $streamOrder.FallbackEnv" in script
    assert "if ($RunEdge -and $ShowPreview)" in script


@WINDOWS_ONLY
def test_edge_pyav_launcher_selects_matching_health_and_inference_decoder():
    script = LAUNCHER.read_text(encoding="utf-8")
    assert "[ValidateSet('opencv', 'pyav')][string]$EdgeDecoder" in script
    assert "'--rtsp-decoder', $EdgeDecoder" in script
    assert script.count("elseif ($RunEdge) { $EdgeDecoder }") == 2


@WINDOWS_ONLY
def test_edge_pyav_missing_approval_fails_before_credentials_or_decode():
    result = subprocess.run([
        "powershell.exe", "-NoProfile", "-File", str(LAUNCHER),
        "-CameraIp", "192.168.50.10", "-RunEdge", "-EdgeDecoder", "pyav",
        "-PrivacyApproval", "C:\\VIIL_TEST_NONEXISTENT\\signed-policy.json",
    ], capture_output=True, text=True, timeout=25, check=False)
    assert result.returncode == 2
    assert "No successful live decode claimed" in result.stdout + result.stderr
    assert "Authorized health probe" not in result.stdout + result.stderr


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
