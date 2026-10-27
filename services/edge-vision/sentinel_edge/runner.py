"""Local-only OpenCV/MediaPipe runner for a non-clinical fall-candidate prototype.

MediaPipe inference is separated from camera opening so full stream behavior
can be tested without activating a camera or calling a real pose model.
"""
from argparse import ArgumentParser
from contextlib import ExitStack
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
from time import monotonic
from typing import Any, Callable, TextIO

from sentinel_edge.contracts import FallCandidateEvent, PoseFrame
from sentinel_edge.handoff import SOURCE_ID_PATTERN, to_envelope
from sentinel_edge.model_smoke import _file_sha256
from sentinel_edge.detector import TemporalFallDetector
from sentinel_edge.pose_adapter import extract_torso_landmarks
from sentinel_edge.pose_rejection_diagnostics import pose_adapter_reason
from sentinel_edge.frame_resize import resize_for_inference, validate_max_side
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
    parser.add_argument("--source-id", default="staged-camera-01")
    parser.add_argument("--candidate-format", choices=["legacy", "v1"], default="legacy",
                        help="Use versioned privacy-minimal Member2 handoff envelopes")
    parser.add_argument("--confirm-consent", action="store_true",
                        help="Explicitly authorize local v1 event export from camera/video")
    parser.add_argument("--max-frames", type=int, default=0, help="0: process until EOF/interrupt")
    parser.add_argument("--display", action="store_true", help="Display input frames locally; no recording")
    parser.add_argument("--trace-output", type=Path,
                        help="Opt-in local *.pose.jsonl file; saved data may be identifying")
    parser.add_argument("--acknowledge-pose-privacy", action="store_true",
                        help="Confirm authorization to export derived pose landmarks")
    args = parser.parse_args(argv)
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
    pose_reason_consumer: Callable[[str], None] | None = None,
    event_encoder: Callable[[FallCandidateEvent], dict] | None = None,
    on_event: Callable[[FallCandidateEvent], None] | None = None,
    detector: TemporalFallDetector | None = None,
    max_inference_side: int = 0,
) -> StreamStats:
    """Read local frames and emit only candidate metadata to an output stream.

    This function does not own/close the capture, model, display or trace file:
    the caller manages these resources. Fail-closed pose conversion sends an
    empty frame to the detector when pose data are absent or invalid.
    """
    if max_frames < 0:
        raise ValueError("max_frames must be non-negative")
    validate_max_side(max_inference_side)
    output = output if output is not None else sys.stdout
    detector = detector if detector is not None else TemporalFallDetector()
    started = clock()
    frame_number, invalid_poses, candidate_count = 0, 0, 0
    last_timestamp = -1
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not 0 < fps < 240:
        fps = 30.0

    while True:
        success, bgr = cap.read()
        if not success:
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

        frame_number += 1
        if display:
            cv2.imshow("VIIL Sentinel — local pose video (no recording)", bgr)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        if max_frames and frame_number >= max_frames:
            break

    return StreamStats(frame_number, invalid_poses, candidate_count)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        import cv2
        import mediapipe as mp
    except ImportError as exc:
        raise SystemExit(
            "Video extras are missing. Run: python -m pip install -e '.[video,dev]'"
        ) from exc

    webcam = args.source.isdigit()
    source = int(args.source) if webcam else str(Path(args.source).expanduser())
    if not webcam and not Path(source).is_file():
        raise SystemExit(f"Video file not found: {source}")

    with ExitStack() as stack:
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            cap.release()
            raise SystemExit(f"Cannot open source: {args.source}")
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
        encoder = None
        if args.candidate_format == "v1":
            provenance = "authorized_local_camera" if webcam else "consented_staged_video"
            asset_hash = _file_sha256(args.model)
            def encode_candidate(candidate: FallCandidateEvent) -> dict:
                return to_envelope(
                    candidate, input_provenance=provenance, model_sha256=asset_hash
                ).to_dict()
            encoder = encode_candidate
        try:
            stats = process_capture(
                cap, cv2=cv2, mp=mp, landmarker=landmarker,
                webcam=webcam, source_id=args.source_id,
                max_frames=args.max_frames, display=args.display,
                trace_file=trace_file, event_encoder=encoder,
            )
        except KeyboardInterrupt:
            print("Interrupted by operator; local capture closed.", file=sys.stderr)
            return 130

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
