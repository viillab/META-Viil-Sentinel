"""Offline operator-readiness contract tests; never access a real camera."""
import json
from pathlib import Path

import pytest

from privacy_approval_fixture import make_policy
from sentinel_edge import hikvision_operator_readiness as readiness


def fake_options(status="rtsp_server_responded", code=200):
    def invoke(camera_ip, *, port, timeout_seconds):
        assert camera_ip == "192.168.10.204"
        assert port == 554 and timeout_seconds == 2.5
        return {"result": status, "rtsp_status_code": code}
    return invoke


def test_verified_policy_and_rtsp_200_only_allows_separate_trial(monkeypatch, tmp_path):
    signed = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    report = readiness.diagnose_camera(
        "192.168.10.204", privacy_approval=signed,
        source_id="zone-a", options_probe=fake_options(),
    )
    assert report["privacy_approval_status"] == "verified"
    assert report["eligible_for_separate_supervised_decode_trial"] is True
    assert report["next_step"] == "operator_may_run_separate_signed_12_frame_decode_trial"
    assert report["frames_decoded"] == 0
    assert report["rtsp_credentials_checked"] is False
    assert report["video_authentication_checked"] is False
    assert report["video_recorded"] is False
    assert report["edge_inference_run"] is False
    assert report["real_world_fall_detection_verified"] is False
    assert "192.168" not in str(report)
    assert "test_approval" not in str(report)
    assert "synthetic-only-key" not in str(report)


@pytest.mark.parametrize(("response", "code", "allowed"), [
    ("rtsp_server_responded", 200, True),
    ("rtsp_server_responded", 401, True),
    ("rtsp_server_responded", 404, False),
    ("rtsp_server_responded", 500, False),
    ("transport_or_protocol_timeout", None, False),
    ("non_rtsp_or_invalid_response", None, False),
    ("malicious_status", 200, False),
])
def test_network_and_status_are_not_mistaken_for_video_authorization(
    response, code, allowed, monkeypatch, tmp_path,
):
    signed = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    report = readiness.diagnose_camera(
        "192.168.10.204", privacy_approval=signed,
        source_id="zone-a", options_probe=fake_options(response, code),
    )
    assert report["eligible_for_separate_supervised_decode_trial"] is allowed
    assert report["frames_decoded"] == 0


def test_no_approval_never_claims_ready_even_with_options_200():
    report = readiness.diagnose_camera(
        "192.168.10.204", options_probe=fake_options(),
    )
    assert report["privacy_approval_status"] == "not_provided"
    assert report["eligible_for_separate_supervised_decode_trial"] is False
    assert report["next_step"] == "complete_genuine_site_and_signed_privacy_approval"


def test_wrong_camera_policy_is_denied_without_echo(monkeypatch, tmp_path):
    signed = make_policy(tmp_path, monkeypatch, camera_ids=("other",))
    report = readiness.diagnose_camera(
        "192.168.10.204", privacy_approval=signed,
        source_id="zone-a", options_probe=fake_options(),
    )
    assert report["privacy_approval_status"] == "denied"
    assert not report["eligible_for_separate_supervised_decode_trial"]


@pytest.mark.parametrize("ip", ["8.8.8.8", "127.0.0.1", "169.254.169.254",
                                 "::1", "camera.example"])
def test_unsafe_ip_is_rejected_before_network(ip):
    calls = []
    def should_never_call(*_a, **_kw):
        calls.append(True)
        raise AssertionError("Unexpected network")
    with pytest.raises(ValueError):
        readiness.diagnose_camera(ip, options_probe=should_never_call)
    assert calls == []


def test_policy_input_pair_is_required_before_network(tmp_path):
    def should_never_call(*_a, **_kw):
        raise AssertionError("Unexpected network")
    with pytest.raises(ValueError):
        readiness.diagnose_camera(
            "192.168.10.204", privacy_approval=tmp_path / "approved.json",
            options_probe=should_never_call,
        )
    with pytest.raises(ValueError):
        readiness.diagnose_camera(
            "192.168.10.204", source_id="zone-a",
            options_probe=should_never_call,
        )


def test_cli_is_non_video_and_prints_only_safe_summary(monkeypatch, capsys):
    monkeypatch.setattr(readiness, "probe_options", fake_options())
    assert readiness.main(["--camera-ip", "192.168.10.204"]) == 2
    output = capsys.readouterr().out
    result = json.loads(output)
    assert result["schema_version"] == readiness.SCHEMA
    assert result["privacy_approval_status"] == "not_provided"
    assert "192.168" not in output
    assert "rtsp://" not in output
    assert "password" not in output


def test_cli_signed_approval_requires_real_matching_policy(monkeypatch, tmp_path, capsys):
    signed = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    monkeypatch.setattr(readiness, "probe_options", fake_options())
    assert readiness.main([
        "--camera-ip", "192.168.10.204",
        "--privacy-approval", str(signed), "--source-id", "zone-a",
    ]) == 0
    assert json.loads(capsys.readouterr().out)["privacy_approval_status"] == "verified"


def test_no_video_actions_or_media_libraries_imported_in_readiness():
    source = Path(readiness.__file__).read_text(encoding="utf-8")
    # The only permitted network call is the reuse of the existing OPTIONS probe.
    assert "probe_options(" not in source or "options_probe(" in source
    assert "cv2" not in source
    assert "av.open" not in source
    assert "VideoCapture" not in source
    assert "imshow" not in source
