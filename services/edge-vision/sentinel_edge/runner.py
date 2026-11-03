"""Local-only video/webcam runner with opt-in minimally scoped pose trace output.

No media uploads and no automatic storage. Four torso landmarks are potentially
identifying data; export requires explicit opt-in and output is ignored by Git.
"""
import json
from argparse import ArgumentParser
from contextlib import ExitStack
from dataclasses import asdict
from pathlib import Path
from time import monotonic

from sentinel_edge.contracts import REQUIRED_POINTS, Landmark, PoseFrame
from sentinel_edge.detector import TemporalFallDetector
from sentinel_edge.pose_traces import frame_to_trace_record


def parse_args(argv: list[str] | None = None):
    parser = ArgumentParser(
        description="VIIL Sentinel non-clinical fall-candidate prototype (not a safety device)"
    )
    parser.add_argument("--source", required=True, help="Camera integer (e.g. 0) or authorized video")
    parser.add_argument("--model", required=True, type=Path, help="Local MediaPipe pose .task model")
    parser.add_argument("--source-id", default="staged-camera-01")
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
    if fps <= 0:
        raise ValueError("fps must be positive")
    return max(int(index * 1000.0 / fps), prev_ms + 1)


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
            # Open using exclusive creation, even if another process created the file meanwhile.
            trace_file = stack.enter_context(args.trace_output.open("x", encoding="utf-8"))

        options = mp.tasks.vision.PoseLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(args.model.resolve())),
            running_mode=mp.tasks.vision.RunningMode.VIDEO,
            num_poses=1,
        )
        detector = TemporalFallDetector()
        start = monotonic()
        frame_number = 0
        last_timestamp = -1
        file_fps = float(cap.get(cv2.CAP_PROP_FPS))
        if not 0 < file_fps < 240:
            file_fps = 30.0
        try:
            with mp.tasks.vision.PoseLandmarker.create_from_options(options) as landmarker:
                while True:
                    ok, bgr = cap.read()
                    if not ok:
                        break
                    timestamp = (
                        max(int((monotonic() - start) * 1000), last_timestamp + 1)
                        if webcam else timestamp_for_frame(frame_number, file_fps, last_timestamp)
                    )
                    last_timestamp = timestamp
                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                    result = landmarker.detect_for_video(image, timestamp)
                    landmarks = (
                        {
                            idx: Landmark(
                                p.x, p.y,
                                p.visibility if p.visibility is not None else 0.0,
                            )
                            for idx, p in enumerate(result.pose_landmarks[0])
                            if idx in REQUIRED_POINTS
                        }
                        if result.pose_landmarks else {}
                    )
                    frame = PoseFrame(
                        timestamp_ms=timestamp,
                        source_id=args.source_id,
                        landmarks=landmarks,
                    )
                    if trace_file is not None:
                        trace_file.write(frame_to_trace_record(frame) + "\n")
                    event = detector.process(frame)
                    if event:
                        print(json.dumps({"type": "FALL_CANDIDATE", **asdict(event)}), flush=True)
                    frame_number += 1
                    if args.display:
                        cv2.imshow("VIIL Sentinel — local pose video (no recording)", bgr)
                        if cv2.waitKey(1) & 0xFF == ord("q"):
                            break
                    if args.max_frames and frame_number >= args.max_frames:
                        break
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
