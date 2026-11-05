"""Synthetic-only checks of frozen V1 shadow inference safety and video wiring."""
from hashlib import sha256
import json


import pytest

from sentinel_edge.contracts import Landmark, PoseFrame
from sentinel_edge.runner import parse_args, process_capture
from sentinel_edge import shadow_inference as shadow


class ConstantPredictor:
    threshold = .53

    def __init__(self, score=.75):
        self.score = score
        self.calls = 0

    def predict_probability(self, x):
        assert x.shape == (30,)
        self.calls += 1
        return self.score


def pose(time_ms, *, source="fixture", visible=True):
    return PoseFrame(
        timestamp_ms=time_ms,
        source_id=source,
        landmarks=({11: Landmark(.45, .25, .99),
                    12: Landmark(.55, .25, .99),
                    23: Landmark(.45, .5, .99),
                    24: Landmark(.55, .5, .99)} if visible else {}),
    )


def test_shadow_requires_real_eight_seconds_and_fixed_rolling_hops():
    fake = ConstantPredictor()
    model = shadow.RollingModelShadow(fake)
    for i in range(240):
        model.observe(pose(i * 1000 // 30))
    assert fake.calls == 0
    assert model.summary()["scored_windows"] == 0
    for i in range(240, 301):
        model.observe(pose(i * 1000 // 30))
    summary = model.summary()
    assert summary["incoming_frames"] == 301
    assert summary["scored_windows"] == 3
    assert summary["candidate_windows"] == 3
    assert summary["below_threshold_windows"] == 0
    assert summary["frozen_threshold"] == .53
    assert summary["shadow_never_emits_incidents_or_modifies_heuristic"] is True
    assert summary["no_coordinates_frames_probabilities_or_timestamps_persisted"] is True
    assert "source_id" not in json.dumps(summary).lower()


def test_shadow_abstains_without_sufficient_poses():
    fake = ConstantPredictor()
    observed = shadow.RollingModelShadow(fake)
    for i in range(241):
        observed.observe(pose(i * 1000 // 30, visible=i > 220))
    assert observed.summary()["pose_abstained_windows"] == 1
    assert fake.calls == 0
    assert observed.summary()["candidate_windows"] == 0


def test_frame_gap_and_new_source_restart_evidence():
    fake = ConstantPredictor()
    observed = shadow.RollingModelShadow(fake)
    for i in range(210):
        observed.observe(pose(i * 33))
    observed.observe(pose(8000))  # >700ms gap -> must not score
    assert observed.summary()["frame_time_gap_resets"] == 1
    assert fake.calls == 0
    observed.observe(pose(10, source="other"))  # new source resets time
    assert observed.summary()["source_resets"] == 1
    assert fake.calls == 0
    for i in range(1, 241):
        observed.observe(pose(10 + 100 * i // 3, source="other"))
    assert fake.calls >= 1


def test_backward_timestamp_refused_and_bad_probability_fails():
    model = shadow.RollingModelShadow(ConstantPredictor())
    model.observe(pose(0))
    with pytest.raises(ValueError, match="strictly increase"):
        model.observe(pose(0))
    bad = shadow.RollingModelShadow(ConstantPredictor(score=float("nan")))
    with pytest.raises(ValueError, match="Nonfinite"):
        for i in range(241):
            bad.observe(pose(i * 1000 // 30))


def test_private_model_sha_and_threshold_verified(tmp_path, monkeypatch):
    blob = b"synthetic-model-only"
    p = tmp_path / "frozen.json"
    p.write_bytes(blob)
    monkeypatch.setattr(shadow, "FROZEN_LINEAR_SHA256", sha256(blob).hexdigest())
    monkeypatch.setattr(shadow, "read_private_artifact",
                        lambda path: ConstantPredictor())
    loaded = shadow.load_verified_linear_shadow(p)
    assert loaded.threshold == .53
    p.write_bytes(b"changed-artifact")
    with pytest.raises(ValueError, match="SHA256"):
        shadow.load_verified_linear_shadow(p)
    p.write_bytes(blob)
    monkeypatch.setattr(shadow, "read_private_artifact",
                        lambda path: ConstantPredictor())
    with pytest.raises(ValueError, match="threshold"):
        monkeypatch.setattr(shadow, "FROZEN_THRESHOLD", .9)
        shadow.load_verified_linear_shadow(p)


def test_cli_demands_consent_and_known_model(tmp_path):
    task = tmp_path / "pose.task"
    task.write_bytes(b"test")
    weight = tmp_path / "research.json"
    weight.write_bytes(b"test")
    base = ["--source", "offline-research.mp4", "--model", str(task),
            "--shadow-model", str(weight)]
    with pytest.raises(SystemExit):
        parse_args(base)
    flags = base + ["--confirm-consent", "--acknowledge-pose-privacy"]
    assert parse_args(flags).shadow_model == weight


def test_shadow_observer_cannot_change_legacy_event_flow():
    import io
    from types import SimpleNamespace as NS
    class Cv2:
        CAP_PROP_FPS = 1
        COLOR_BGR2RGB = 2
        @staticmethod
        def cvtColor(obj, how):
            return obj

    class Video:
        def __init__(self):
            self.i = 0
        def get(self, key):
            return 30.
        def read(self):
            if self.i >= 3:
                return (False, None)
            self.i += 1
            return (True, object())

    class MP:
        ImageFormat = NS(SRGB=1)
        Image = NS
    class Detector:
        def __init__(self):
            self.i = 0
        def process(self, frame):
            self.i += 1
            return (NS(timestamp_ms=frame.timestamp_ms, source_id="test")
                    if self.i == 2 else None)
    class Marker:
        def detect_for_video(self, img, ts):
            return NS(pose_landmarks=[])

    def run(observer):
        output = io.StringIO()
        stats = process_capture(
            Video(), cv2=Cv2, mp=MP, landmarker=Marker(),
            webcam=False, source_id="fixture", output=output,
            detector=Detector(), on_frame=observer,
            event_encoder=lambda _: {"synthetic_candidate": True},
        )
        return stats, output.getvalue()
    original, orig_events = run(None)
    seen = []
    with_shadow, new_events = run(seen.append)
    assert with_shadow == original
    assert new_events == orig_events
    assert len(seen) == 3
    assert all(frame.landmarks == {} for frame in seen)
