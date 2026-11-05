"""Offline local pose-visualization checks. All camera/video/model inputs are fake."""
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS

import pytest

from sentinel_edge import live_preview as preview
from sentinel_edge.pose_preview import TorsoPoseOverlay, validate_local_pose_asset
from sentinel_edge.privacy_gate import PrivacyGateDenied


class Frame:
    shape = (432, 768, 3)
    size = 432 * 768 * 3
    dtype = "uint8"


class Display:
    INTER_AREA = 3
    FONT_HERSHEY_SIMPLEX = 0
    LINE_AA = 16
    COLOR_BGR2RGB = 4

    def __init__(self):
        self.frames = []
        self.lines = []
        self.labels = []
        self.windows_closed = []

    def cvtColor(self, frame, code):
        assert frame is not None and code == self.COLOR_BGR2RGB
        return frame

    def line(self, frame, a, b, color, thickness):
        assert frame.shape == (432, 768, 3)
        self.lines.append((a, b))

    def putText(self, _frame, label, *_):
        self.labels.append(label)

    def imshow(self, _title, frame):
        self.frames.append(frame)

    def waitKey(self, _):
        return -1

    def destroyWindow(self, title):
        self.windows_closed.append(title)


class Capture:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.released = False

    def isOpened(self):
        return True

    def read(self):
        return next(self.frames, (False, None))

    def release(self):
        self.released = True


def landmark_result(multi=False, visible=True):
    points = [NS(x=0.5, y=0.5, visibility=1.0, presence=1.0) for _ in range(33)]
    points[11].x, points[11].y = 0.3, 0.3
    points[12].x, points[12].y = 0.7, 0.3
    points[23].x, points[23].y = 0.4, 0.7
    points[24].x, points[24].y = 0.6, 0.7
    if not visible:
        points[11].visibility = 0.0
    return NS(pose_landmarks=[points, points] if multi else [points])


def install_fake_mediapipe(monkeypatch, events, pose_result):
    mp = ModuleType("mediapipe")

    class Task:
        def __init__(self):
            self.timestamps = []
            self.closed = False

        def detect_for_video(self, _image, timestamp):
            self.timestamps.append(timestamp)
            if isinstance(pose_result, Exception):
                raise pose_result
            return pose_result

        def close(self):
            self.closed = True

    def create(options):
        assert options.num_poses == 2
        task = Task()
        events.append(task)
        return task

    mp.ImageFormat = NS(SRGB=1)
    mp.Image = lambda **kwargs: NS(**kwargs)
    mp.tasks = NS(
        BaseOptions=lambda **kwargs: NS(**kwargs),
        vision=NS(
            PoseLandmarkerOptions=lambda **kwargs: NS(**kwargs),
            RunningMode=NS(VIDEO=1),
            PoseLandmarker=NS(create_from_options=create),
        ),
    )
    monkeypatch.setitem(sys.modules, "mediapipe", mp)


def asset(tmp_path: Path) -> Path:
    model = tmp_path / "pose.task"
    model.write_bytes(b"FAKE MODEL - NO REAL INFERENCE")
    return model


def test_torso_model_draws_only_four_safe_bones(monkeypatch, tmp_path):
    created = []
    install_fake_mediapipe(monkeypatch, created, landmark_result())
    overlay = TorsoPoseOverlay(asset(tmp_path))
    cv2 = Display()
    assert overlay.annotate(cv2, Frame(), 100) is True
    assert len(cv2.lines) == 4
    assert created[0].timestamps == [100]
    assert all(0 <= x < 768 and 0 <= y < 432 for line in cv2.lines for x, y in line)
    overlay.close()
    assert created[0].closed


@pytest.mark.parametrize("mode", ["multiple", "low_visibility", "missing"])
def test_ambiguous_pose_never_draws_a_body(monkeypatch, tmp_path, mode):
    result = (landmark_result(multi=True) if mode == "multiple"
              else landmark_result(visible=False) if mode == "low_visibility"
              else NS(pose_landmarks=[]))
    install_fake_mediapipe(monkeypatch, [], result)
    overlay = TorsoPoseOverlay(asset(tmp_path))
    cv2 = Display()
    assert overlay.annotate(cv2, Frame(), 0) is False
    assert cv2.lines == []
    overlay.close()


def test_native_pose_errors_are_redacted_and_model_closed(monkeypatch, tmp_path):
    created = []
    install_fake_mediapipe(monkeypatch, created, RuntimeError("private-camera-password"))
    overlay = TorsoPoseOverlay(asset(tmp_path))
    with pytest.raises(RuntimeError, match="inference interrupted") as raised:
        overlay.annotate(Display(), Frame(), 0)
    assert "private-camera-password" not in str(raised.value)
    overlay.close()
    assert created[0].closed


def test_pose_preview_uses_new_epoch_after_fallback_and_never_emits_fall_decision():
    cv2 = Display()
    cap1 = Capture([(True, Frame()), (False, None)])
    cap2 = Capture([(True, Frame()), (True, Frame())])
    captures = iter([cap1, cap2])
    epochs = []

    class FakePose:
        def __init__(self):
            self.times = []
            self.closed = False

        def annotate(self, _, frame, timestamp_ms):
            assert frame.shape == (432, 768, 3)
            self.times.append(timestamp_ms)
            return True

        def close(self):
            self.closed = True

    def factory():
        p = FakePose()
        epochs.append(p)
        return p

    report = preview.preview_authorized_stream(
        cv2, primary_url="primary", alternate_url="fallback",
        privacy_check=lambda: None, open_capture=lambda *_: next(captures),
        pose_factory=factory, max_frames=3, clock=lambda: 1.0,
    )
    assert report["frames_displayed"] == 3
    assert report["torso_pose_inference_frames"] == 3
    assert report["torso_pose_accepted_frames"] == 3
    assert report["fall_decision_run"] is False
    assert report["ai_inference_run"] is True
    assert report["remote_streamed"] is False and report["video_saved"] is False
    assert report["fallback_used"] is True
    assert len(epochs) == 2 and all(e.closed for e in epochs)
    assert epochs[0].times == [0] and epochs[1].times == [0, 1]
    assert cap1.released and cap2.released
    assert all("NO FALL DECISION" in s for s in cv2.labels if s.startswith("TORSO"))


def test_approval_revoked_during_pose_inference_never_displays_or_falls_back():
    cv2 = Display()
    cap = Capture([(True, Frame())])
    created = []
    opened = []
    def make_pose():
        p = NS(close=lambda: created.append("closed"))
        def infer(*_a):
            created.append("inferred")
            return True
        p.annotate = infer
        return p
    def privacy_check():
        if "inferred" in created:
            raise PrivacyGateDenied("revoked after inference")

    with pytest.raises(PrivacyGateDenied):
        preview.preview_authorized_stream(
            cv2, primary_url="primary", alternate_url="fallback",
            privacy_check=privacy_check,
            open_capture=lambda *_a: (opened.append(True), cap)[1],
            pose_factory=make_pose, max_frames=1, clock=lambda: 1.0,
        )
    assert cv2.frames == []
    assert cap.released and created[-1] == "closed"
    assert len(opened) == 1


def test_model_and_missing_signing_policy_fail_before_capture(
    monkeypatch, tmp_path, capsys,
):
    monkeypatch.setenv("VIIL_TEST_POSE", "rtsp://192.168.10.204:554/Streaming/Channels/102")
    path = asset(tmp_path)
    # No genuine signed authorization is supplied; never import cv2/MediaPipe.
    with pytest.raises(SystemExit):
        preview.main([
            "--rtsp-env", "VIIL_TEST_POSE", "--source-id", "zone-a",
            "--privacy-approval", str(tmp_path / "missing.json"),
            "--confirm-authorized-camera", "--show-local-preview",
            "--pose-model", str(path),
        ])
    assert "rtsp://" not in capsys.readouterr().err


def test_pose_asset_is_local_task_file_only(tmp_path):
    path = asset(tmp_path)
    assert validate_local_pose_asset(path) == path.resolve()
    with pytest.raises(ValueError):
        validate_local_pose_asset(tmp_path / "absent.task")
    with pytest.raises(ValueError):
        validate_local_pose_asset(tmp_path / "fake.pkl")


def test_launcher_has_explicit_supervised_pose_option_and_no_unsafe_inference_flags():
    script = (Path(__file__).resolve().parents[3] / "scripts" /
              "start-hikvision-staged.ps1").read_text(encoding="utf-8")
    assert "[switch]$ShowPoseOverlay" in script
    assert "$posePreviewArgs = @('--pose-model', $ModelPath, '--pose-stride', [string]$PoseStride)" in script
    assert "[ValidateRange(1, 8)][int]$PoseStride = 2" in script
    assert script.count(") + $posePreviewArgs)") == 2
    assert "$ShowPoseOverlay -and (-not $ShowPreview -or $RunEdge -or $PreflightOnly)" in script

def test_stride_reduces_pose_calls_without_counting_skipped_frames_as_accepted():
    cv2 = Display()
    cap = Capture([(True, Frame())] * 5)
    seen = []

    class FakePose:
        def annotate(self, _, _frame, timestamp):
            seen.append(timestamp)
            return True
        def close(self):
            pass

    latency = iter([10.0, 10.005, 20.0, 20.025, 30.0, 30.030])
    report = preview.preview_authorized_stream(
        cv2, primary_url="offline", alternate_url=None,
        privacy_check=lambda: None, open_capture=lambda *_: cap,
        pose_factory=FakePose, pose_stride=2, max_frames=5,
        clock=lambda: 1.0, latency_clock=lambda: next(latency),
    )
    assert seen == [0, 1, 2]
    assert report["frames_displayed"] == 5
    assert report["torso_pose_inference_frames"] == 3
    assert report["torso_pose_accepted_frames"] == 3
    assert report["torso_pose_skipped_frames"] == 2
    assert report["torso_pose_stride"] == 2
    assert report["torso_inference_p50_ms"] == 25.0
    assert report["torso_inference_p95_ms"] == 30.0
    assert [s.split(" | ")[0] for s in cv2.labels if s.startswith("TORSO")] == [
        "TORSO AVAILABLE", "TORSO NOT SAMPLED", "TORSO AVAILABLE",
        "TORSO NOT SAMPLED", "TORSO AVAILABLE",
    ]
    assert report["video_saved"] is False
    assert report["remote_streamed"] is False
    assert report["fall_decision_run"] is False


def test_stride_resets_on_same_camera_fallback_and_does_not_keep_old_pose():
    first = Capture([(True, Frame()), (True, Frame()), (False, None)])
    second = Capture([(True, Frame()), (True, Frame())])
    caps = iter([first, second])
    sessions = []

    class FakePose:
        def __init__(self):
            self.calls = 0
            self.closed = False
        def annotate(self, *_):
            self.calls += 1
            return True
        def close(self):
            self.closed = True

    def factory():
        pose = FakePose()
        sessions.append(pose)
        return pose

    summary = preview.preview_authorized_stream(
        Display(), primary_url="sub", alternate_url="main",
        privacy_check=lambda: None, open_capture=lambda *_: next(caps),
        pose_factory=factory, pose_stride=3, max_frames=4, clock=lambda: 1,
    )
    assert summary["fallback_used"] is True
    assert summary["torso_pose_inference_frames"] == 2
    assert summary["torso_pose_skipped_frames"] == 2
    assert [s.calls for s in sessions] == [1, 1]
    assert all(s.closed for s in sessions)


def test_reused_native_capture_buffer_never_retains_old_pose_when_skipped():
    class Reused(Frame):
        def __init__(self):
            self.drawings = []
        def copy(self):
            return Reused()

    class PaintedDisplay(Display):
        def __init__(self):
            super().__init__()
            self.snapshots = []
        def putText(self, frame, label, *_):
            frame.drawings.append(label)
            super().putText(frame, label, *_)
        def imshow(self, _title, frame):
            self.snapshots.append(list(frame.drawings))
            super().imshow(_title, frame)

    class FakePose:
        def annotate(self, _, frame, _timestamp):
            frame.drawings.append("POSE")
            return True
        def close(self):
            pass

    original = Reused()
    cv2 = PaintedDisplay()
    report = preview.preview_authorized_stream(
        cv2, primary_url="camera", alternate_url=None,
        privacy_check=lambda: None,
        open_capture=lambda *_: Capture([(True, original)] * 3),
        pose_factory=FakePose, pose_stride=2, max_frames=3, clock=lambda: 1,
    )
    assert report["torso_pose_skipped_frames"] == 1
    assert ["POSE" in s for s in cv2.snapshots] == [True, False, True]
    assert original.drawings == []


@pytest.mark.parametrize("stride", [False, True, 0, -1, 9, 1.5, "2"])
def test_invalid_inference_stride_rejected_before_any_camera_or_pose_factory(stride):
    created = []
    with pytest.raises(ValueError, match="Pose stride"):
        preview.preview_authorized_stream(
            Display(), primary_url="offline", alternate_url=None,
            privacy_check=lambda: None,
            open_capture=lambda *_: created.append("capture"),
            pose_factory=lambda: created.append("pose"),
            pose_stride=stride,
        )
    assert created == []


def test_preview_without_pose_retains_false_claims_and_no_latency_sample():
    report = preview.preview_authorized_stream(
        Display(), primary_url="offline", alternate_url=None,
        privacy_check=lambda: None,
        open_capture=lambda *_: Capture([(True, Frame())]),
        max_frames=1, clock=lambda: 1,
    )
    assert report["torso_pose_stride"] is None
    assert report["torso_pose_skipped_frames"] == 0
    assert report["torso_inference_p50_ms"] is None
    assert report["torso_inference_p95_ms"] is None
    assert report["ai_inference_run"] is False


def test_cli_rejects_invalid_pose_stride_before_approval_or_capture(
    monkeypatch, tmp_path, capsys,
):
    monkeypatch.setenv("VIIL_LOCAL_INVALID", "rtsp://192.168.10.204:554/Streaming/Channels/102")
    with pytest.raises(SystemExit):
        preview.main([
            "--rtsp-env", "VIIL_LOCAL_INVALID", "--source-id", "zone-a",
            "--privacy-approval", str(tmp_path / "missing.json"),
            "--confirm-authorized-camera", "--show-local-preview",
            "--pose-model", str(asset(tmp_path)), "--pose-stride", "9",
        ])
    err = capsys.readouterr().err
    assert "Unsafe or missing camera configuration" in err
    assert "rtsp://" not in err
