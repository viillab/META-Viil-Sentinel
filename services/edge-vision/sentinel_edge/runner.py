"""Local-only OpenCV/MediaPipe runner for a non-clinical fall-candidate prototype.

MediaPipe inference is separated from camera opening so full stream behavior
can be tested without activating a camera or calling a real pose model.
"""
from argparse import ArgumentParser
from contextlib import ExitStack
from dataclasses import asdict, dataclass
import json
from math import isfinite
from pathlib import Path
import sys
from time import monotonic, perf_counter
from typing import Any, Callable, TextIO

from sentinel_edge.camera_health import open_rtsp_capture, validate_rtsp_env
from sentinel_edge.camera_inputs import (
    load_camera_registry, parse_usb_index, resolve_camera,
)
from sentinel_edge.rtsp_reconnect import (
    CameraStreamInterrupted, run_bounded_sessions,
)
from sentinel_edge.contracts import FallCandidateEvent, PoseFrame
from sentinel_edge.handoff import SOURCE_ID_PATTERN, to_envelope
from sentinel_edge.model_smoke import _file_sha256
from sentinel_edge.detector import TemporalFallDetector
from sentinel_edge.pose_adapter import extract_torso_landmarks
from sentinel_edge.pose_rejection_diagnostics import pose_adapter_reason
from sentinel_edge.multipose_spatial_diagnostics import multipose_spatial_category
from sentinel_edge.temporal_pose_association import OfflineAssociationObserver
from sentinel_edge.frame_resize import resize_for_inference, validate_max_side
from sentinel_edge.live_profile import LiveCycleProfiler
from sentinel_edge.pose_coverage import PoseCoverageMonitor
from sentinel_edge.pose_traces import frame_to_trace_record



@dataclass(frozen=True)
class StreamStats:
    frames_processed: int
    invalid_pose_frames: int
    candidate_events: int


def parse_args(argv: list[str] | None = None):
    parser = ArgumentParser(
        description="VIIL Sentinel non-clinical fall-candidate prototype (not a safety device)"
    )
    parser.add_argument("--source", required=True, help="Camera integer (e.g. 0) or authorized video")
    parser.add_argument("--model", required=True, type=Path, help="Local MediaPipe pose .task model")
    parser.add_argument("--rtsp-env", metavar="ENV_NAME", help="Read authorized RTSP URL from an environment variable")
    parser.add_argument("--camera-registry", type=Path,
                        help="Local vendor-neutral camera registry JSON (no secrets)")
    parser.add_argument("--camera-id", help="Select camera ID from the registry")
    parser.add_argument("--rtsp-allow-port", type=int, default=None,
                        help="Explicitly allow a vendor-specific RTSP port")
    parser.add_argument("--profile-rtsp", action="store_true",
                        help="Opt-in privacy-minimal local RTSP cycle/RSS report")
    parser.add_argument("--rtsp-retries", type=int, default=0,
                        help="Explicit opt-in: retry RTSP interruption at most 3 times")
    parser.add_argument("--rtsp-retry-delay-ms", type=int, default=1000,
                        help="Delay between RTSP reconnects, 250..5000 ms")
    parser.add_argument("--rtsp-session-seconds", type=int, default=0,
                        help="Optional per-session experiment limit 1..3600s; 0 disables")
    parser.add_argument("--source-id", default="staged-camera-01")
    parser.add_argument("--candidate-format", choices=["legacy", "v1"], default="legacy",
                        help="Use versioned privacy-minimal Member2 handoff envelopes")
    parser.add_argument("--confirm-consent", action="store_true",
                        help="Explicitly authorize local v1 event export from camera/video")
    parser.add_argument("--early-motion-probe", action="store_true",
                        help="Opt-in 2s heuristic research counts ONLY, never alerts")
    parser.add_argument("--shadow-model", type=Path,
                        help="Optional pinned V1 research prediction counts ONLY (no events)")
    parser.add_argument("--max-frames", type=int, default=0, help="0: process until EOF/interrupt")
    parser.add_argument("--display", action="store_true", help="Display input frames locally; no recording")
    parser.add_argument("--trace-output", type=Path,
                        help="Opt-in local *.pose.jsonl file; saved data may be identifying")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true",
                        help="Confirm authorization to export derived pose landmarks")
    args = parser.parse_args(argv)
    if args.rtsp_env and (not args.rtsp_env.isidentifier() or not args.rtsp_env.startswith("VIIL_")):
        parser.error("--rtsp-env must name a VIIL_ prefixed environment variable")
    if args.rtsp_env and args.source != "rtsp":
        parser.error("--rtsp-env requires --source rtsp")
    if args.source == "rtsp" and not args.rtsp_env:
        parser.error("RTSP requires --rtsp-env; never pass credentials as --source")
    if (args.camera_registry is None) != (args.camera_id is None):
        parser.error("--camera-registry and --camera-id must be provided together")
    if args.source == "camera":
        if args.camera_registry is None:
            parser.error("--source camera requires registry and camera ID")
        try:
            args.selected_camera = load_camera_registry(args.camera_registry)[args.camera_id]
        except (ValueError, KeyError):
            parser.error("Invalid camera registry or unknown camera ID (redacted)")
    elif args.camera_registry is not None:
        parser.error("--camera-registry requires --source camera")
    else:
        args.selected_camera = None
    network_source = args.source == "rtsp" or (
        args.selected_camera is not None and args.selected_camera.kind == "rtsp"
    )
    if "://" in args.source or "@" in args.source:
        parser.error("Network URLs and credentials cannot be passed as --source")
    if args.source.startswith(("\\\\", "//")):
        parser.error("UNC/network paths cannot be used as local video sources")
    if args.rtsp_allow_port is not None and (
        not 1 <= args.rtsp_allow_port <= 65535 or not network_source
    ):
        parser.error("--rtsp-allow-port requires an RTSP source and port 1..65535")
    if args.source not in ("rtsp", "camera"):
        try:
            parse_usb_index(args.source)
        except ValueError:
            parser.error("Local USB/UVC camera index must be between 0 and 15")
    if not 0 <= args.rtsp_retries <= 3:
        parser.error("--rtsp-retries must be 0..3")
    if not 250 <= args.rtsp_retry_delay_ms <= 5000:
        parser.error("--rtsp-retry-delay-ms must be 250..5000")
    if not 0 <= args.rtsp_session_seconds <= 3600:
        parser.error("--rtsp-session-seconds must be 0..3600")
    if args.rtsp_session_seconds and (not network_source or not args.rtsp_retries):
        parser.error("--rtsp-session-seconds requires RTSP retry mode")
    if args.profile_rtsp and (not network_source or not args.rtsp_retries):
        parser.error("--profile-rtsp requires RTSP retry mode")
    if args.rtsp_retries and not network_source:
        parser.error("--rtsp-retries is only supported for RTSP sources")
    if args.rtsp_retries and (
        args.shadow_model is not None or args.early_motion_probe
        or args.trace_output is not None or args.display
    ):
        parser.error("RTSP retry mode disallows research shadow, trace and display")
    if args.rtsp_retries and args.candidate_format != "v1":
        parser.error("RTSP retry mode requires --candidate-format v1")
    if args.max_frames < 0:
        parser.error("--max-frames must be >= 0")
    if not args.model.is_file():
        parser.error(f"Model file not found: {args.model}")
    if not args.source_id.strip() or len(args.source_id) > 128:
        parser.error("--source-id must be between 1 and 128 characters")
    if args.candidate_format == "v1":
        if not args.confirm_consent:
            parser.error("--candidate-format v1 requires --confirm-consent")
        if SOURCE_ID_PATTERN.fullmatch(args.source_id) is None:
            parser.error("v1 source IDs must be pseudonymous ASCII slugs")
    if args.trace_output is not None:
        if not args.acknowledge_pose_privacy:
            parser.error("--trace-output requires --acknowledge-pose-privacy")
        if not args.trace_output.name.endswith(".pose.jsonl"):
            parser.error("Trace filename must end in .pose.jsonl (Git ignored)")
        if not args.trace_output.parent.is_dir():
            parser.error("Trace output parent directory must already exist")
        if args.trace_output.exists():
            parser.error("Trace output already exists; refusing to overwrite")
    if args.shadow_model is not None:
        if not (args.confirm_consent and args.acknowledge_pose_privacy):
            parser.error("Shadow research mode requires consent and privacy acknowledgement")
        if not args.shadow_model.is_file():
            parser.error("Shadow research artifact not found")
    if args.early_motion_probe and not (args.confirm_consent and args.acknowledge_pose_privacy):
        parser.error("--early-motion-probe requires consent and pose privacy acknowledgement")
    return args


def timestamp_for_frame(index: int, fps: float, prev_ms: int) -> int:
    if not 0 < fps < float("inf"):
        raise ValueError("fps must be finite and positive")
    return max(int(index * 1000.0 / fps), prev_ms + 1)


def process_capture(
    cap: Any, *,
    cv2: Any, mp: Any, landmarker: Any,
    webcam: bool, source_id: str, max_frames: int = 0,
    display: bool = False, trace_file: TextIO | None = None,
    output: TextIO | None = None, clock: Callable[[], float] = monotonic,
    on_frame: Callable[[PoseFrame], None] | None = None,
    on_frame_cycle: Callable[[float, bool, bool], None] | None = None,
    pose_reason_consumer: Callable[[str], None] | None = None,
    multipose_category_consumer: Callable[[str], None] | None = None,
    association_category_consumer: Callable[[str], None] | None = None,
    event_encoder: Callable[[FallCandidateEvent], dict] | None = None,
    on_event: Callable[[FallCandidateEvent], None] | None = None,
    detector: TemporalFallDetector | None = None,
    max_inference_side: int = 0,
    fail_on_loss: bool = False,
    max_duration_seconds: float = 0.0,
) -> StreamStats:
    """Read local frames and emit only candidate metadata to an output stream.

    This function does not own/close the capture, model, display or trace file:
    the caller manages these resources. Fail-closed pose conversion sends an
    empty frame to the detector when pose data are absent or invalid.
    """
    if max_frames < 0:
        raise ValueError("max_frames must be non-negative")
    if (type(max_duration_seconds) not in (int, float)
            or not isfinite(max_duration_seconds)
            or not 0 <= max_duration_seconds <= 3600):
        raise ValueError("max_duration_seconds must be finite and in 0..3600")
    validate_max_side(max_inference_side)
    output = output if output is not None else sys.stdout
    detector = detector if detector is not None else TemporalFallDetector()
    started = clock()
    frame_number, invalid_poses, candidate_count = 0, 0, 0
    last_timestamp = -1
    association_observer = (
        OfflineAssociationObserver() if association_category_consumer is not None
        else None
    )
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not 0 < fps < 240:
        fps = 30.0

    while True:
        if max_duration_seconds and clock() - started >= max_duration_seconds:
            break
        cycle_start = perf_counter() if on_frame_cycle is not None else None
        try:
            success, bgr = cap.read()
        except Exception:
            if fail_on_loss:
                raise CameraStreamInterrupted("Camera stream read failed") from None
            raise
        if not success or bgr is None:
            if fail_on_loss:
                raise CameraStreamInterrupted("Camera stream interrupted")
            break
        # A blocking read may cross the test budget: discard that final frame
        # before inference so no candidates are emitted after the deadline.
        if max_duration_seconds and clock() - started >= max_duration_seconds:
            break
        timestamp = (
            max(int((clock() - started) * 1000), last_timestamp + 1)
            if webcam else timestamp_for_frame(frame_number, fps, last_timestamp)
        )
        last_timestamp = timestamp
        inference_bgr = resize_for_inference(bgr, cv2, max_side=max_inference_side)
        rgb = cv2.cvtColor(inference_bgr, cv2.COLOR_BGR2RGB)
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        result = landmarker.detect_for_video(image, timestamp)
        landmarks = extract_torso_landmarks(result)
        if pose_reason_consumer is not None:
            pose_reason_consumer(pose_adapter_reason(result))
        if multipose_category_consumer is not None:
            multipose_category_consumer(multipose_spatial_category(result))
        if association_observer is not None:
            association_category_consumer(association_observer.observe(result))
        if not landmarks:
            invalid_poses += 1
        frame = PoseFrame(
            timestamp_ms=timestamp,
            source_id=source_id,
            landmarks=landmarks,
        )
        if trace_file is not None:
            trace_file.write(frame_to_trace_record(frame) + "\n")
        if on_frame is not None:
            on_frame(frame)
        event = detector.process(frame)
        if event is not None:
            if on_event is not None:
                on_event(event)
            encoded = (event_encoder(event) if event_encoder is not None
                       else {"type": "FALL_CANDIDATE", **asdict(event)})
            print(json.dumps(encoded, allow_nan=False), file=output)
            output.flush()
            candidate_count += 1

        if on_frame_cycle is not None and cycle_start is not None:
            on_frame_cycle(perf_counter() - cycle_start, bool(landmarks), event is not None)
        frame_number += 1
        if display:
            cv2.imshow("VIIL Sentinel — local pose video (no recording)", bgr)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        if max_frames and frame_number >= max_frames:
            break

    return StreamStats(frame_number, invalid_poses, candidate_count)


def _run_rtsp_retry_mode(
    args, cv2: Any, mp: Any, source: str, *, source_id: str | None = None,
) -> int:
    """Run isolated RTSP epochs. Never reuse native tracker or temporal state."""
    model_sha = _file_sha256(args.model)

    def run_one_epoch(epoch_source_id: str) -> None:
        profiler = LiveCycleProfiler() if args.profile_rtsp else None
        coverage = PoseCoverageMonitor()

        def observe_pose(frame: PoseFrame) -> None:
            transition = coverage.observe(
                bool(frame.landmarks), timestamp_ms=frame.timestamp_ms,
            )
            if transition is not None:
                print("EDGE_POSE_COVERAGE " + json.dumps(
                    transition, sort_keys=True,
                ), file=sys.stderr)
        with ExitStack() as stack:
            try:
                cap = open_rtsp_capture(cv2, source)
            except Exception:
                raise CameraStreamInterrupted("Camera open failed") from None
            if cap is None:
                raise CameraStreamInterrupted("Camera unavailable")
            stack.callback(cap.release)
            try:
                opened = cap.isOpened()
            except Exception:
                raise CameraStreamInterrupted("Camera open check failed") from None
            if not opened:
                raise CameraStreamInterrupted("Camera unavailable")

            # A fresh MediaPipe task is mandatory: native tracking state can survive
            # source changes even when our Python detector has been reset.
            options = mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(
                    model_asset_path=str(args.model.resolve())
                ),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_poses=2,
            )
            landmarker = stack.enter_context(
                mp.tasks.vision.PoseLandmarker.create_from_options(options)
            )

            def encode(event: FallCandidateEvent) -> dict:
                return to_envelope(
                    event, input_provenance="authorized_local_camera",
                    model_sha256=model_sha,
                ).to_dict()

            # process_capture creates a new TemporalFallDetector each invocation.
            try:
                stats = process_capture(
                    cap, cv2=cv2, mp=mp, landmarker=landmarker,
                    webcam=True, source_id=epoch_source_id,
                    max_frames=args.max_frames, event_encoder=encode,
                    fail_on_loss=True,
                    on_frame_cycle=profiler.observe if profiler is not None else None,
                    on_frame=observe_pose,
                    max_duration_seconds=args.rtsp_session_seconds,
                )
                if stats.frames_processed == 0:
                    raise CameraStreamInterrupted("RTSP epoch had no processed frames")
            except CameraStreamInterrupted:
                if profiler is not None:
                    print("RESEARCH_RTSP_PROFILE " + json.dumps(
                        profiler.report(interrupted=True), sort_keys=True,
                    ), file=sys.stderr)
                raise
            finally:
                print("EDGE_POSE_COVERAGE_SUMMARY " + json.dumps(
                    coverage.summary(), sort_keys=True,
                ), file=sys.stderr)
            if profiler is not None:
                print("RESEARCH_RTSP_PROFILE " + json.dumps(
                    profiler.report(interrupted=False), sort_keys=True,
                ), file=sys.stderr)
            print(
                f"RTSP session ended at configured frame/time bound: "
                f"{stats.frames_processed} frames, {stats.candidate_events} "
                "unconfirmed candidates.",
                file=sys.stderr,
            )

    try:
        outcome = run_bounded_sessions(
            run_one_epoch,
            source_id=source_id or args.source_id,
            retries=args.rtsp_retries,
            delay_seconds=args.rtsp_retry_delay_ms / 1000,
            status=lambda message: print(message, file=sys.stderr),
        )
    except KeyboardInterrupt:
        print("RTSP stopped by operator; no monitoring.", file=sys.stderr)
        return 130
    if not outcome.completed:
        print("RTSP retries exhausted; camera unavailable, no monitoring.", file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        import cv2
        import mediapipe as mp
    except ImportError as exc:
        raise SystemExit(
            "Video extras are missing. Run: python -m pip install -e '.[video,dev]'"
        ) from exc

    is_rtsp = args.source == "rtsp"
    webcam = False
    source_id = args.source_id
    if args.selected_camera is not None:
        try:
            selected_kind, source = resolve_camera(
                args.selected_camera, extra_rtsp_port=args.rtsp_allow_port,
            )
        except ValueError:
            raise SystemExit("Camera registry source unavailable (redacted)") from None
        is_rtsp = selected_kind == "rtsp"
        webcam = selected_kind == "usb"
        if args.source_id == "staged-camera-01":
            source_id = args.selected_camera.camera_id
    elif is_rtsp:
        try:
            source = validate_rtsp_env(args.rtsp_env, extra_port=args.rtsp_allow_port)
        except ValueError:
            raise SystemExit("Invalid or unsafe RTSP environment setting (redacted)") from None
    else:
        usb_index = parse_usb_index(args.source)
        webcam = usb_index is not None
        source = usb_index if webcam else str(Path(args.source).expanduser())
        if not webcam and not Path(source).is_file():
            raise SystemExit(f"Video file not found: {source}")

    if is_rtsp and args.rtsp_retries:
        return _run_rtsp_retry_mode(args, cv2, mp, source, source_id=source_id)

    if args.shadow_model is not None:
        # Keep training-window imports out of the camera runner module to
        # avoid a circular import through offline video_benchmark.
        from sentinel_edge.shadow_inference import (
            RollingModelShadow, load_verified_linear_shadow,
        )
    if args.early_motion_probe:
        from sentinel_edge.early_motion_probe import CausalMotionProbe
    with ExitStack() as stack:
        try:
            cap = open_rtsp_capture(cv2, source) if is_rtsp else cv2.VideoCapture(source)
        except Exception:
            raise SystemExit("Cannot initialize authorized camera source (redacted)") from None
        if not cap.isOpened():
            cap.release()
            raise SystemExit("Cannot open authorized capture source (credentials redacted)")
        stack.callback(cap.release)
        if args.display:
            stack.callback(cv2.destroyAllWindows)
        trace_file = None
        if args.trace_output:
            # Exclusive creation; never overwrite an existing privacy-sensitive trace.
            trace_file = stack.enter_context(args.trace_output.open("x", encoding="utf-8"))

        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(args.model.resolve())),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=2,  # Detect a second person and abstain on ambiguous multi-person frames.
        )
        landmarker = stack.enter_context(
            mp.tasks.vision.PoseLandmarker.create_from_options(options)
        )
        shadow = (RollingModelShadow(load_verified_linear_shadow(args.shadow_model))
                  if args.shadow_model is not None else None)
        early_probe = CausalMotionProbe() if args.early_motion_probe else None
        def consume_research(frame: PoseFrame) -> None:
            if shadow is not None:
                shadow.observe(frame)
            if early_probe is not None:
                early_probe.observe(frame)
        encoder = None
        if args.candidate_format == "v1":
            provenance = "authorized_local_camera" if (webcam or is_rtsp) else "consented_staged_video"
            asset_hash = _file_sha256(args.model)
            def encode_candidate(candidate: FallCandidateEvent) -> dict:
                return to_envelope(
                    candidate, input_provenance=provenance, model_sha256=asset_hash
                ).to_dict()
            encoder = encode_candidate
        try:
            stats = process_capture(
                cap, cv2=cv2, mp=mp, landmarker=landmarker,
                webcam=(webcam or is_rtsp), source_id=source_id,
                max_frames=args.max_frames, display=args.display,
                trace_file=trace_file, event_encoder=encoder,
                on_frame=consume_research if (shadow is not None or early_probe is not None)
                else None,
                fail_on_loss=is_rtsp,
            )
        except CameraStreamInterrupted:
            print("Camera stream interrupted; no reliable monitoring (redacted).", file=sys.stderr)
            return 2
        except KeyboardInterrupt:
            print("Interrupted by operator; local capture closed.", file=sys.stderr)
            return 130

        if shadow is not None:
            print("RESEARCH_MODEL_SHADOW " + json.dumps(shadow.summary(), sort_keys=True),
                  file=sys.stderr)
        if early_probe is not None:
            print("RESEARCH_EARLY_MOTION_PROBE "
                  + json.dumps(early_probe.summary(), sort_keys=True), file=sys.stderr)
        # Status goes to stderr; stdout contains only machine-readable event JSONL.
        print(
            f"Processed {stats.frames_processed} frames; "
            f"invalid/unavailable poses: {stats.invalid_pose_frames}; "
            f"candidate events: {stats.candidate_events}. "
            "Events require human review.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
