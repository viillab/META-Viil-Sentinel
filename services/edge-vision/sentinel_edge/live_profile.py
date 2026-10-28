"""Privacy-minimal opt-in RTSP live-frame cycle profiler.

No frame, pose, source address, source id, individual event or credentials are
retained. This measures LOCAL blocking-read + inference + metadata emission,
not camera acquisition delay, network transport latency, fall accuracy,
notification latency, or a patient safety guarantee.
"""
from collections import deque
from math import ceil, isfinite
from typing import Callable


MAX_RECENT_SAMPLES = 2048
RSS_SAMPLE_EVERY = 32


def local_process_rss() -> int | None:
    """Best-effort current-process RSS, never a guaranteed instantaneous peak."""
    try:
        import psutil
        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError, RuntimeError, ValueError):
        return None


class LiveCycleProfiler:
    """Bounded recent percentiles plus all-session throughput and counts."""

    def __init__(self, *, rss_sample: Callable[[], int | None] = local_process_rss,
                 recent_limit: int = MAX_RECENT_SAMPLES) -> None:
        if not 1 <= recent_limit <= MAX_RECENT_SAMPLES:
            raise ValueError("recent_limit must be between 1 and 2048")
        self._recent_ms: deque[float] = deque(maxlen=recent_limit)
        self._rss_sample = rss_sample
        self._rss_peak: int | None = None
        self._total_ms = 0.0
        self.frames_processed = 0
        self.pose_unavailable_frames = 0
        self.candidate_events = 0
        self._take_rss()

    def _take_rss(self) -> None:
        try:
            rss = self._rss_sample()
        except Exception:
            # Optional memory instrumentation must not break camera inference.
            return
        if type(rss) is int and rss > 0:
            self._rss_peak = max(rss, self._rss_peak or 0)

    def observe(self, cycle_seconds: float, pose_available: bool,
                candidate_emitted: bool) -> None:
        """One observation per successfully decoded AND processed frame."""
        if (type(cycle_seconds) not in (int, float)
                or not isfinite(cycle_seconds) or cycle_seconds <= 0):
            raise ValueError("cycle time must be finite and positive")
        if type(pose_available) is not bool or type(candidate_emitted) is not bool:
            raise ValueError("pose and candidate flags must be boolean")
        milliseconds = cycle_seconds * 1000
        self._recent_ms.append(milliseconds)
        self._total_ms += milliseconds
        self.frames_processed += 1
        self.pose_unavailable_frames += int(not pose_available)
        self.candidate_events += int(candidate_emitted)
        if self.frames_processed % RSS_SAMPLE_EVERY == 0:
            self._take_rss()

    def report(self, *, interrupted: bool) -> dict:
        if type(interrupted) is not bool:
            raise ValueError("interrupted must be a bool")
        ordered = sorted(self._recent_ms)
        count = len(ordered)

        def percentile(p: float) -> float | None:
            if not count:
                return None
            return round(ordered[ceil(count * p) - 1], 3)

        self._take_rss()
        return {
            "schema_version": "viil.edge.rtsp_profile.v1",
            "research_only": True,
            "stream_interrupted": interrupted,
            "frames_processed": self.frames_processed,
            "pose_unavailable_frames": self.pose_unavailable_frames,
            "candidate_events_unconfirmed": self.candidate_events,
            "cycle_time_includes_rtsp_blocking_read_and_local_inference": True,
            "camera_acquisition_or_network_latency_measured": False,
            "real_world_fall_accuracy_measured": False,
            "cycle_sample_window": "most_recent_frames",
            "cycle_samples": count,
            "cycle_p50_ms": percentile(0.50),
            "cycle_p95_ms": percentile(0.95),
            "cycle_mean_ms_all_frames": (
                round(self._total_ms / self.frames_processed, 3)
                if self.frames_processed else None
            ),
            "observed_cycle_throughput_fps": (
                round(self.frames_processed * 1000 / self._total_ms, 3)
                if self._total_ms > 0 else None
            ),
            "sampled_process_rss_max_mib": (
                round(self._rss_peak / 1048576, 2) if self._rss_peak else None
            ),
            "rss_is_sampled_not_true_peak": True,
            "no_camera_or_personal_identifiers": True,
        }
