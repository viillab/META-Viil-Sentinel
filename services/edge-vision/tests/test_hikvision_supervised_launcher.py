"""Offline checks for the interactive Hikvision operator launcher.

Never execute it in CI; operator credentials and signed approval are
required for any live camera action.
"""
from pathlib import Path


SCRIPT = (Path(__file__).resolve().parents[1] / "scripts"
          / "run_hikvision_tailscale_supervised.ps1")


def test_supervised_launcher_has_no_real_camera_ip_or_credentials():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "192.168.10.204" not in text
    assert "rtsp://admin:" not in text
    assert "Get-Credential" in text
    assert "Read-Host" in text
    assert "EscapeDataString" in text
    assert "PrivateConfig" in text
    assert "VIIL_HIK_TAILSCALE_RTSP" in text
    assert "VIIL_PRIVACY_APPROVAL_KEY" in text
    assert "Remove-Item Env:VIIL_HIK_TAILSCALE_RTSP" in text
    assert "Remove-Item Env:VIIL_PRIVACY_APPROVAL_KEY" in text


def test_requires_scoped_signed_approval_before_camera_credentials():
    text = SCRIPT.read_text(encoding="utf-8")
    assert text.index("verify_privacy_approval") < text.index("Get-Credential")
    assert "camera_id='hik-tailnet-live'" in text
    assert "if ($LASTEXITCODE -ne 0)" in text
    assert "GetAddressBytes()" in text
    assert "privateNetwork" in text


def test_bounded_live_test_is_the_existing_edge_runner_not_poc_yolo():
    text = SCRIPT.read_text(encoding="utf-8")
    assert "-m sentinel_edge.camera_health" in text
    assert "-m sentinel_edge.runner" in text
    for flag in (
        "--frames 12", "--confirm-authorized-camera", "--confirm-consent",
        "--candidate-format v1", "--max-frames 100",
        "--rtsp-retries 1", "--rtsp-session-seconds 60", "--profile-rtsp",
        "Streaming/Channels/102",
    ):
        assert flag in text
    assert "YOLO" not in text
    assert "--display" not in text
    assert "--trace-output" not in text
    assert "Get-Content -LiteralPath $keyFile -Raw" in text
    assert "if ($LASTEXITCODE -ne 0)" in text
