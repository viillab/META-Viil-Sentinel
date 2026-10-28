"""Revocation tests are synthetic and never open a real camera."""
from types import SimpleNamespace as NS
import json

import pytest

from privacy_approval_fixture import make_policy
from sentinel_edge.live_approval import LiveApprovalGuard
from sentinel_edge.privacy_gate import PrivacyGateDenied
from sentinel_edge.runner import parse_args, process_capture


class ManualClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_recheck_not_per_frame_and_invalid_policy_blocks_after_interval(
    tmp_path, monkeypatch,
):
    approval = make_policy(tmp_path, monkeypatch, camera_ids=("zone-a",))
    clock = ManualClock()
    guard = LiveApprovalGuard(approval, camera_id="zone-a", clock=clock)
    guard.check()
    clock.now = 0.9
    guard.check()
    # File modified after approval: do not trust it at the next recheck.
    record = json.loads(approval.read_text("utf-8"))
    record["notices_confirmed"] = False
    approval.write_text(json.dumps(record), encoding="utf-8")
    guard.check()  # Still inside bounded verification interval
    clock.now = 1.05
    with pytest.raises(PrivacyGateDenied):
        guard.check()


def test_key_rotation_or_file_deletion_revokes_approval(tmp_path, monkeypatch):
    path = make_policy(tmp_path, monkeypatch)
    clock = ManualClock()
    guard = LiveApprovalGuard(path, camera_id="staged-camera-01", clock=clock)
    monkeypatch.setenv("VIIL_PRIVACY_APPROVAL_KEY", "rotated-key-" * 4)
    clock.now = 1.1
    with pytest.raises(PrivacyGateDenied):
        guard.check()
    from privacy_approval_fixture import TEST_KEY
    monkeypatch.setenv("VIIL_PRIVACY_APPROVAL_KEY", TEST_KEY)
    path.unlink()
    with pytest.raises(PrivacyGateDenied):
        guard.check()


def test_approval_can_be_rechecked_after_system_clock_goes_backward(tmp_path, monkeypatch):
    path = make_policy(tmp_path, monkeypatch)
    clock = ManualClock()
    clock.now = 20
    guard = LiveApprovalGuard(path, camera_id="staged-camera-01", clock=clock)
    path.unlink()
    clock.now = 5
    with pytest.raises(PrivacyGateDenied):
        guard.check()


@pytest.mark.parametrize("interval", [0, -2, 11, None, True])
def test_invalid_recheck_interval_fails_closed(tmp_path, monkeypatch, interval):
    path = make_policy(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        LiveApprovalGuard(path, camera_id="staged-camera-01", interval_seconds=interval)


class FrameCapture:
    def __init__(self):
        self.reads = 0

    def get(self, _):
        return 15

    def read(self):
        self.reads += 1
        return True, object()


class FakeCv2:
    CAP_PROP_FPS = 5
    COLOR_BGR2RGB = 1

    @staticmethod
    def cvtColor(frame, _):
        return frame


class FakeMp:
    ImageFormat = NS(SRGB=1)

    @staticmethod
    def Image(*, image_format, data):
        return data


class NeverInfer:
    def detect_for_video(self, *_):
        raise AssertionError("Privacy denied but inference still ran")


def test_revocation_immediately_after_capture_read_prevents_inference_and_events():
    capture = FrameCapture()
    checks = 0

    def revoke():
        nonlocal checks
        checks += 1
        if checks >= 2:
            raise PrivacyGateDenied("Live camera privacy approval invalid")

    with pytest.raises(PrivacyGateDenied):
        process_capture(
            capture, cv2=FakeCv2, mp=FakeMp, landmarker=NeverInfer(),
            webcam=True, source_id="zone-a", privacy_check=revoke,
        )
    assert capture.reads == 1
    assert checks == 2


def test_revocation_before_read_prevents_capture():
    capture = FrameCapture()

    def revoke():
        raise PrivacyGateDenied("Revoked")

    with pytest.raises(PrivacyGateDenied):
        process_capture(
            capture, cv2=FakeCv2, mp=FakeMp, landmarker=NeverInfer(),
            webcam=True, source_id="zone-a", privacy_check=revoke,
        )
    assert capture.reads == 0


def test_policy_revoked_before_candidate_emit_drops_event():
    from io import StringIO
    capture = FrameCapture()
    output = StringIO()
    callbacks = []
    class EmptyPose:
        def detect_for_video(self, *_):
            return NS(pose_landmarks=[])
    class EventDetector:
        def process(self, _):
            return object()
    def check():
        callbacks.append(True)
        if len(callbacks) == 3:
            raise PrivacyGateDenied("Approval revoked before event export")
    with pytest.raises(PrivacyGateDenied):
        process_capture(
            capture, cv2=FakeCv2, mp=FakeMp, landmarker=EmptyPose(),
            webcam=True, source_id="zone-a", privacy_check=check,
            detector=EventDetector(), output=output,
        )
    assert capture.reads == 1
    assert output.getvalue() == ""
    assert len(callbacks) == 3


@pytest.mark.parametrize("source", ["0", "usb:2", "rtsp", "camera"])
def test_live_sources_refuse_legacy_and_tracking_extensions(tmp_path, source):
    model = tmp_path / "pose.task"
    model.write_bytes(b"placeholder")
    base = ["--source", source, "--model", str(model)]
    if source == "rtsp":
        base += ["--rtsp-env", "VIIL_CAMERA_RTSP"]
    if source == "camera":
        catalog = tmp_path / "cameras.json"
        catalog.write_text(json.dumps({
            "schema_version": "viil.edge.camera_registry.v1",
            "cameras": [{"id": "zone-a", "kind": "usb", "device_index": 0}],
        }), encoding="utf-8")
        base += ["--camera-registry", str(catalog), "--camera-id", "zone-a"]
    with pytest.raises(SystemExit):
        parse_args(base)
    consent = base + ["--candidate-format", "v1", "--confirm-consent"]
    assert parse_args(consent).candidate_format == "v1"
    with pytest.raises(SystemExit):
        parse_args(consent + ["--display"])
    trace = tmp_path / "sensitive.pose.jsonl"
    with pytest.raises(SystemExit):
        parse_args(consent + ["--trace-output", str(trace),
                              "--acknowledge-pose-privacy"])
    with pytest.raises(SystemExit):
        parse_args(consent + ["--early-motion-probe", "--acknowledge-pose-privacy"])
    weight = tmp_path / "weights.json"
    weight.write_text("test", encoding="utf-8")
    with pytest.raises(SystemExit):
        parse_args(consent + ["--shadow-model", str(weight),
                              "--acknowledge-pose-privacy"])
