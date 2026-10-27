"""Entirely synthetic persistent runtime/replay tests, no camera or people."""
from pathlib import Path
from types import SimpleNamespace as N

import pytest

from sentinel_edge import persistent_pose_session as ps


def fake_pose():
    points = [N(x=.50, y=.25, visibility=.95, presence=.95) for _ in range(33)]
    for idx in (23, 24):
        points[idx] = N(x=.50, y=.60, visibility=.95, presence=.95)
    return N(pose_landmarks=[points])


class FakeCapture:
    instances = []

    def __init__(self, _name):
        self.n = 0
        self.released = False
        FakeCapture.instances.append(self)

    def isOpened(self):
        return True

    def get(self, key):
        return 30 if key == 1 else 3

    def read(self):
        if self.n >= 3:
            return False, None
        self.n += 1
        return True, N(shape=(100, 100, 3))

    def release(self):
        self.released = True


class FakeCV2:
    CAP_PROP_FPS = 1
    CAP_PROP_FRAME_COUNT = 2
    COLOR_BGR2RGB = 42
    VideoCapture = FakeCapture

    @staticmethod
    def cvtColor(x, code):
        assert code == FakeCV2.COLOR_BGR2RGB
        return x


class FakePoseLandmarker:
    instances = []
    timestamps = []
    model_options = []

    @classmethod
    def create_from_options(cls, opt):
        cls.model_options.append(opt)
        return cls()

    def __init__(self):
        self.closed = False
        FakePoseLandmarker.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.closed = True

    def detect_for_video(self, _image, timestamp):
        FakePoseLandmarker.timestamps.append(timestamp)
        return fake_pose()


class FakeMP:
    ImageFormat = N(SRGB=1)
    Image = N

    class tasks:
        BaseOptions = N
        vision = N(
            PoseLandmarkerOptions=N,
            RunningMode=N(VIDEO=1),
            PoseLandmarker=FakePoseLandmarker,
        )


class FakeClock:
    def __init__(self, step=1.0):
        self.value = -step
        self.step = step

    def __call__(self):
        self.value += self.step
        return self.value


def clips(tmp_path):
    return [
        (f"{category}_{idx}", tmp_path / f"{category}_{idx}.mp4", 3)
        for category in ps.CATEGORIES for idx in ps.SELECTED_IDS
    ]


def test_one_model_all_videos_monotonic_frame_timestamps_and_detector_isolation(
    tmp_path, monkeypatch,
):
    FakePoseLandmarker.instances.clear()
    FakePoseLandmarker.timestamps.clear()
    FakePoseLandmarker.model_options.clear()
    FakeCapture.instances.clear()
    detectors = []
    class FakeDetector:
        def __init__(self):
            self.frames = []
            detectors.append(self)

        def process(self, frame):
            assert not self.frames or frame.source_id == self.frames[-1].source_id
            self.frames.append(frame)
            return None

    monkeypatch.setattr(ps, "TemporalFallDetector", FakeDetector)
    model = tmp_path / "pose.task"
    model.write_bytes(b"fake")
    report = ps.replay_persistent_session(
        clips(tmp_path), model, cv2=FakeCV2, mp=FakeMP,
        sample_rss=lambda: 100 * 1048576,
        wall_clock=FakeClock(step=10.), cpu_clock=FakeClock(step=4.),
    )
    assert report["videos"] == 8
    assert report["fully_decoded_frames"] == 24
    assert report["strict_accepted_torso_frames"] == 24
    assert report["pose_landmarker_instances"] == 1
    assert report["temporal_heuristic_instances"] == 8
    assert len(FakePoseLandmarker.instances) == 1
    assert FakePoseLandmarker.instances[0].closed
    assert len(FakePoseLandmarker.timestamps) == 24
    assert all(b > a for a, b in zip(
        FakePoseLandmarker.timestamps, FakePoseLandmarker.timestamps[1:]
    ))
    assert all(FakePoseLandmarker.timestamps[i] -
               FakePoseLandmarker.timestamps[i - 1] >= 1000
               for i in range(3, 24, 3))
    assert all(len(detector.frames) == 3 for detector in detectors)
    assert all(cap.released for cap in FakeCapture.instances)
    assert report["persisted_coordinates_frames_events_or_timestamps"] is False
    assert report["max_sampled_own_process_rss_mib"] == 100
    assert report["complete_replay_fps"] == pytest.approx(1.2)
    assert FakePoseLandmarker.model_options[0].num_poses == 2


@pytest.mark.parametrize("arguments", [
    {"last_ms": -2, "start_ms": 0, "frame": 0, "fps": 30},
    {"last_ms": 10, "start_ms": 10, "frame": 0, "fps": 30},
    {"last_ms": 0, "start_ms": 0, "frame": -1, "fps": 30},
    {"last_ms": 0, "start_ms": 100, "frame": 2, "fps": float("nan")},
    {"last_ms": 0, "start_ms": 100, "frame": 2, "fps": 0},
    {"last_ms": 0, "start_ms": 100, "frame": 2, "fps": 500},
])
def test_timestamp_validation_refuses_nonmonotonicity(arguments):
    with pytest.raises(ValueError):
        ps.session_timestamp_ms(**arguments)


def test_missing_video_frames_fail_closed_and_capture_closes(tmp_path, monkeypatch):
    class TruncatedCapture(FakeCapture):
        def read(self):
            if self.n >= 2:
                return False, None
            return super().read()
    cv2 = N(CAP_PROP_FPS=1, CAP_PROP_FRAME_COUNT=2,
            COLOR_BGR2RGB=42, VideoCapture=TruncatedCapture,
            cvtColor=lambda bgr, code: bgr)
    model = tmp_path / "pose.task"
    model.write_bytes(b"fake")
    with pytest.raises(ValueError, match="declared.*decoded"):
        ps.replay_persistent_session(
            clips(tmp_path), model, cv2=cv2, mp=FakeMP,
            sample_rss=lambda: 2 ** 20,
            wall_clock=FakeClock(), cpu_clock=FakeClock(),
        )


def test_bad_pose_ram_and_source_ids_are_refused(tmp_path):
    model = tmp_path / "pose.task"
    model.write_bytes(b"fake")
    with pytest.raises(ValueError, match="RSS"):
        ps.replay_persistent_session(
            clips(tmp_path), model, cv2=FakeCV2, mp=FakeMP,
            sample_rss=lambda: -1,
        )
    with pytest.raises(ValueError, match="unique"):
        ps.replay_persistent_session([
            ("trips_0", tmp_path / "first.mp4", 3),
            ("trips_0", tmp_path / "second.mp4", 3),
        ], model)


def test_invented_source_manifests_generate_aggregate_only(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "_private_root", lambda path: Path(path))
    monkeypatch.setattr(ps, "_private_output_path", lambda path: Path(path))
    manifest = {"archive_sha256": "a" * 64, "selection": []}
    for cat in ps.CATEGORIES:
        for i in ps.SELECTED_IDS:
            path = tmp_path / "selected" / cat / "videos" / f"{cat}_{i}.mp4"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fictional media")
            manifest["selection"].append({
                "category": cat, "publisher_action_id": i,
                "videos_sha256": ps.sha256_file(path),
                "videos_bytes": path.stat().st_size,
            })
    monkeypatch.setattr(ps, "validate_subset", lambda root: manifest)
    import sentinel_edge.caucafall_curator as cauca
    monkeypatch.setattr(cauca, "_video_metadata", lambda path: (3, 30))
    model = tmp_path / "pose.task"
    model.write_bytes(b"task")
    def mock_runner(rows, task):
        assert len(rows) == 8
        assert task == model
        return {
            "videos": 8, "fully_decoded_frames": 24,
            "pose_landmarker_instances": 1,
            "temporal_heuristic_instances": 8,
            "strict_accepted_torso_frames": 24,
        }
    target = tmp_path / "result.json"
    report = ps.profile_ikar_session(tmp_path, model, target, runner=mock_runner)
    assert report["research_only"]
    assert report["new_fall_detector_at_each_video_boundary"]
    assert report["no_PII_pose_video_event_timestamps_or_paths_persisted"]
    assert str(tmp_path) not in target.read_text()
    with pytest.raises(FileExistsError):
        ps.profile_ikar_session(tmp_path, model, target, runner=mock_runner)
    video = tmp_path / "selected" / "trips" / "videos" / "trips_0.mp4"
    video.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="changed"):
        ps.profile_ikar_session(tmp_path, model, tmp_path / "new.json",
                                runner=mock_runner)
