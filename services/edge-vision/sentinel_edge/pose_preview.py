"""Opt-in, local-only torso pose visualization for approved camera preview.

Only MediaPipe's four non-facial torso joints are painted on transient frames.
No scores, fall decisions, face landmarks, event records, files or network output.
The caller must verify signed live-camera privacy approval before constructing
this session and before/after every inference and display.
"""
from pathlib import Path

from sentinel_edge.contracts import LEFT_HIP, LEFT_SHOULDER, RIGHT_HIP, RIGHT_SHOULDER
from sentinel_edge.pose_adapter import extract_torso_landmarks


_TORSO_EDGES = (
    (LEFT_SHOULDER, RIGHT_SHOULDER),
    (LEFT_SHOULDER, LEFT_HIP),
    (RIGHT_SHOULDER, RIGHT_HIP),
    (LEFT_HIP, RIGHT_HIP),
)


def validate_local_pose_asset(path: Path) -> Path:
    """Reject absent, unexpected, symlinked and implausibly large model assets."""
    if not isinstance(path, Path) or path.suffix.lower() != ".task":
        raise ValueError("A local MediaPipe .task model is required")
    try:
        if (path.is_symlink() or not path.is_file()
                or not 0 < path.stat().st_size <= 50_000_000):
            raise ValueError
        return path.resolve(strict=True)
    except (OSError, RuntimeError, ValueError):
        raise ValueError("Local MediaPipe model unavailable") from None


class TorsoPoseOverlay:
    """One model per uninterrupted stream epoch, always closed before fallback."""

    def __init__(self, model_path: Path):
        # The entrypoint performs signed approval verification BEFORE instantiating
        # any MediaPipe model or opening camera sockets.
        local_model = validate_local_pose_asset(model_path)
        try:
            import mediapipe as mp
            options = mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(local_model)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_poses=2,
            )
            self._task = mp.tasks.vision.PoseLandmarker.create_from_options(options)
            self._mp = mp
        except Exception:
            # MediaPipe's native errors may include sensitive local paths.
            raise RuntimeError("Local pose model could not initialize") from None

    def annotate(self, cv2, frame, timestamp_ms: int) -> bool:
        """Draw accepted single-person torso geometry only; return pose availability."""
        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
            result = self._task.detect_for_video(image, timestamp_ms)
            points = extract_torso_landmarks(result)
            if not points:
                return False
            height, width, _ = frame.shape
            for a, b in _TORSO_EDGES:
                pa, pb = points[a], points[b]
                start = (min(width - 1, int(pa.x * width)),
                         min(height - 1, int(pa.y * height)))
                end = (min(width - 1, int(pb.x * width)),
                       min(height - 1, int(pb.y * height)))
                cv2.line(frame, start, end, (0, 230, 180), 2)
            return True
        except Exception:
            # If inference/drawing is unavailable, stop this supervised mode;
            # never pretend to show valid pose or expose private native errors.
            raise RuntimeError("Local torso preview inference interrupted") from None

    def close(self) -> None:
        task = getattr(self, "_task", None)
        self._task = None
        if task is not None:
            try:
                task.close()
            except Exception:
                pass  # Never surface private native codec/model diagnostics.
