"""Isolated LOCAL eight-joint research pose extractor and coverage audit.

Only five ALREADY INSPECTED noncommercial staged human videos are eligible.
This is a research extension, not the Member 1 four-point Edge detector.
Derived eight-joint coordinates are person-related; keep under Git-ignored
data/private, require explicit acknowledgements, never upload/notify/diagnose.

The existing MediaPipe .task asset is used locally; no new downloads or Meta.
"""
import argparse
import json
import math
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path

from app.adl_negative_challenge import CHALLENGE_ROOT
from app.adl_negative_challenge import CLIPS as ADL
from app.adl_negative_challenge import _verify as verify_adl
from app.dev_video_research import DEV, DEV_ROOT
from app.dev_video_research import _validate as verify_dev
from app.public_video_eval import CLIPS as PREVIOUS
from app.public_video_eval import (
    DATA_ROOT,
    MODEL,
    ROOT,
    SOURCE_URL,
    _private_root,
    _probe_video,
    verify_video,
)

POINTS = (11, 12, 23, 24, 25, 26, 27, 28)
SCHEMA = "viil.research.eight_joint_pose.v1"
OUTPUT = ROOT / "data" / "private" / "eight_joint_pose_research_v1"
VISIBILITY_FLOOR = 0.55
# Reuse the earlier evidence-quality policy threshold; not learned from videos.
MIN_LOWER_BODY_COVERAGE = 0.75
MAX_FRAMES = 12_000
MAX_LINE = 2_500
SELECTION = (
    ("FD0012", "sitting_to_fall"),  # Previously missed by both heuristics
    ("FD0032", "sleeping_to_fall"),
    ("FD0011", "sitting_to_fall"),
    ("FD0001", "adl_no_fall"),
    ("FD0005", "adl_no_fall"),
)


@dataclass(frozen=True)
class Source:
    clip_id: str
    path: Path
    label: str
    expected_frames: int


def _input_sources() -> tuple[Source, ...]:
    previous = {c.clip_id: c for c in PREVIOUS}
    dev = {entry[0]: entry for entry in DEV}
    negatives = {c.clip_id: c for c in ADL}
    found: list[Source] = []
    for cid, category in SELECTION:
        if cid in previous:
            c = previous[cid]
            sha = verify_video(DATA_ROOT / (cid + ".mp4"), c)
            if (c.label and category == "adl_no_fall") or (
                not c.label and category != "adl_no_fall"
            ):
                raise ValueError("Pinned publisher clip label mismatch")
            origin = DATA_ROOT / (cid + ".mp4")
        elif cid in dev:
            key, expected_category, _path, length, git_sha = dev[cid]
            if key != cid or category != expected_category:
                raise ValueError("Development publisher label mismatch")
            origin = DEV_ROOT / (cid + ".mp4")
            sha = verify_dev(origin, length, git_sha)
        elif cid in negatives:
            c = negatives[cid]
            if category != "adl_no_fall":
                raise ValueError("Challenge publisher label mismatch")
            origin = CHALLENGE_ROOT / (cid + ".mp4")
            sha = verify_adl(origin, c)
        else:
            raise ValueError("Unapproved source ID")
        if len(sha) != 64:
            raise ValueError("Unverified source SHA-256")
        source_meta = _probe_video(origin)
        found.append(Source(cid, origin, category, source_meta["frames_reported"]))
    if len(found) != len(SELECTION) or len({x.clip_id for x in found}) != len(found):
        raise ValueError("Duplicate/reduced research selection")
    return tuple(found)


def _fixed_record(ts: int, points: dict[int, tuple[float, float, float]]) -> str:
    if type(ts) is not int or ts < 0:
        raise ValueError("Invalid timestamp")
    if set(points) - set(POINTS):
        raise ValueError("Unexpected anatomical joint")
    serial = {}
    for index, values in points.items():
        if (
            len(values) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
            or not 0 <= values[2] <= 1
        ):
            raise ValueError("Nonfinite/invalid restricted pose point")
        serial[str(index)] = {
            "x": values[0], "y": values[1], "visibility": values[2],
        }
    return json.dumps(
        {"schema": SCHEMA, "timestamp_ms": ts, "points": serial},
        separators=(",", ":"), allow_nan=False,
    )


def _no_duplicate_fields(pairs: list[tuple[str, object]]) -> dict:
    fields = {}
    for name, value in pairs:
        if name in fields:
            raise ValueError("Duplicate private pose JSON key")
        fields[name] = value
    return fields


def _reject_nonfinite_constant(value: str):
    raise ValueError("Nonfinite private pose JSON constant")


def _read_private_trace(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Private research trace missing or symlinked")
    count = 0
    last = -1
    with path.open("r", encoding="utf-8") as stream:
        for raw in stream:
            count += 1
            if count > MAX_FRAMES or len(raw) > MAX_LINE:
                raise ValueError("Oversized or unbounded research pose trace")
            try:
                obj = json.loads(
                    raw, object_pairs_hook=_no_duplicate_fields,
                    parse_constant=_reject_nonfinite_constant,
                )
                if type(obj) is not dict or set(obj) != {
                    "schema", "timestamp_ms", "points"
                } or obj["schema"] != SCHEMA:
                    raise ValueError("Research pose schema mismatch")
                ts, raw_pts = obj["timestamp_ms"], obj["points"]
                if type(ts) is not int or ts <= last or type(raw_pts) is not dict:
                    raise ValueError("Research pose timestamps must increase")
                last = ts
                if set(raw_pts) - set(map(str, POINTS)):
                    raise ValueError("Unapproved research landmark ID")
                pts = {}
                for idx, p in raw_pts.items():
                    if type(p) is not dict or set(p) != {"x", "y", "visibility"}:
                        raise ValueError("Invalid point fields")
                    vals = tuple(p[key] for key in ("x", "y", "visibility"))
                    if (
                        any(type(v) not in (int, float) or not math.isfinite(v) for v in vals)
                        or not 0 <= vals[2] <= 1
                    ):
                        raise ValueError("Invalid point coordinates / confidence")
                    pts[int(idx)] = vals
            except (json.JSONDecodeError, KeyError, TypeError) as e:
                raise ValueError("Malformed private pose trace") from e
            yield ts, pts
    if not count:
        raise ValueError("Empty research trace")


def _knee_angle(points: dict[int, tuple[float, float, float]], *, side: str):
    a, b, c = ((23, 25, 27) if side == "left" else (24, 26, 28))
    if any(i not in points or points[i][2] < VISIBILITY_FLOOR for i in (a, b, c)):
        return None
    ax, ay = points[a][:2]
    bx, by = points[b][:2]
    cx, cy = points[c][:2]
    u = (ax - bx, ay - by)
    v = (cx - bx, cy - by)
    norms = math.hypot(*u) * math.hypot(*v)
    if norms < 0.0001:
        return None
    cos = max(-1.0, min(1.0, (u[0] * v[0] + u[1] * v[1]) / norms))
    return math.degrees(math.acos(cos))


def aggregate_trace(trace: Path, *, clip_id: str, expected_frames: int) -> dict:
    if clip_id not in {x[0] for x in SELECTION} or expected_frames <= 0:
        raise ValueError("Unknown or empty research clip")
    frame_count = 0
    any_person_frames = 0
    torso_valid = 0
    legs_complete = 0
    ankles_both_visible = 0
    knee_both_valid = 0
    min_angle = 180.0
    max_angle = 0.0
    lower_body_visibility = []
    for _, joints in _read_private_trace(trace):
        frame_count += 1
        if joints:
            any_person_frames += 1
        if all(i in joints and joints[i][2] >= VISIBILITY_FLOOR for i in (11, 12, 23, 24)):
            torso_valid += 1
        if all(i in joints and joints[i][2] >= VISIBILITY_FLOOR for i in POINTS):
            legs_complete += 1
        if all(i in joints and joints[i][2] >= VISIBILITY_FLOOR for i in (27, 28)):
            ankles_both_visible += 1
        angles = [_knee_angle(joints, side=s) for s in ("left", "right")]
        if all(a is not None for a in angles):
            knee_both_valid += 1
            min_angle = min(min_angle, *angles)
            max_angle = max(max_angle, *angles)
        lower = [joints[i][2] for i in (25, 26, 27, 28) if i in joints]
        if lower:
            lower_body_visibility.append(sum(lower) / len(lower))
    if frame_count != expected_frames:
        raise ValueError("Research pose trace has missing or extra video frames")
    return {
        "clip_id": clip_id,
        "frames": frame_count,
        "frames_with_any_pose": any_person_frames,
        "torso_4point_visible_frames": torso_valid,
        "all_8_joints_visible_frames": legs_complete,
        "ankles_both_visible_frames": ankles_both_visible,
        "both_knees_geometry_valid_frames": knee_both_valid,
        "all_8_joint_coverage": round(legs_complete / frame_count, 4),
        "both_knees_geometry_coverage": round(knee_both_valid / frame_count, 4),
        "lower_body_evidence_state": (
            "exploratory_joint_geometry_available"
            if legs_complete / frame_count >= MIN_LOWER_BODY_COVERAGE
            else "abstain_incomplete_lower_body_visibility"
        ),
        "lower_body_min_coverage_required": MIN_LOWER_BODY_COVERAGE,
        "knee_angle_min_deg": round(min_angle, 1) if knee_both_valid else None,
        "knee_angle_max_deg": round(max_angle, 1) if knee_both_valid else None,
        "mean_visible_lower_body_confidence": round(
            sum(lower_body_visibility) / len(lower_body_visibility), 4,
        ) if lower_body_visibility else None,
        "raw_pose_coordinates_exported": False,
        "fall_confirmed": False,
        "alert_permitted": False,
    }


def extract_locally(target: Path = OUTPUT) -> dict:
    """Use MediaPipe strictly on local checked MP4s; create private pose files only."""
    import cv2
    import mediapipe as mp

    if MODEL.is_symlink() or not MODEL.is_file():
        raise ValueError("Local MediaPipe model unavailable")
    folder = _private_root(target)
    sources = _input_sources()  # revalidates exact upstream SHA-256
    # Avoid partly regenerating traces if any output already exists.
    if any((folder / (s.clip_id + ".eight.pose.jsonl")).exists()
           or (folder / (s.clip_id + ".eight.pose.jsonl")).is_symlink()
           for s in sources):
        raise ValueError("Existing person-derived trace; refusing overwrite")
    report = []
    for s in sources:
        cap = cv2.VideoCapture(str(s.path))
        if not cap.isOpened():
            raise ValueError("Local video could not be opened")
        with ExitStack() as stack:
            stack.callback(cap.release)
            output = stack.enter_context(
                (folder / (s.clip_id + ".eight.pose.jsonl")).open("x", encoding="utf-8")
            )
            options = mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL.resolve())),
                running_mode=mp.tasks.vision.RunningMode.VIDEO, num_poses=1,
            )
            fps = float(cap.get(cv2.CAP_PROP_FPS))
            if not 0 < fps <= 240:
                raise ValueError("Unsupported video frame rate")
            with mp.tasks.vision.PoseLandmarker.create_from_options(options) as model:
                count = 0
                last_timestamp = -1
                while count < MAX_FRAMES:
                    ok, bgr = cap.read()
                    if not ok:
                        break
                    timestamp = max(round(count * 1000 / fps), last_timestamp + 1)
                    last_timestamp = timestamp
                    image = mp.Image(
                        image_format=mp.ImageFormat.SRGB,
                        data=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB),
                    )
                    result = model.detect_for_video(image, timestamp)
                    points = {}
                    if result.pose_landmarks:
                        poses = result.pose_landmarks[0]
                        for idx in POINTS:
                            p = poses[idx]
                            points[idx] = (
                                p.x, p.y,
                                p.visibility if p.visibility is not None else 0.0,
                            )
                    output.write(_fixed_record(timestamp, points) + "\n")
                    count += 1
                if count != s.expected_frames:
                    raise ValueError("Actual local media extraction incomplete")
        report.append({"clip_id": s.clip_id, "frames_processed": count})
    return {
        "status": "EIGHT_JOINT_LOCAL_EXTRACTION_COMPLETED",
        "clips": report, "meta_called": False,
        "media_uploaded": False, "private_pose_data_written": True,
    }


def analyze_private(target: Path = OUTPUT) -> dict:
    folder = _private_root(target)
    sources = _input_sources()  # reject modified public video before reading poses
    clips = []
    for s in sources:
        stats = aggregate_trace(
            folder / (s.clip_id + ".eight.pose.jsonl"),
            clip_id=s.clip_id, expected_frames=s.expected_frames,
        )
        stats["source_category"] = s.label
        clips.append(stats)
    return {
        "status": "LOCAL_EIGHT_JOINT_COVERAGE_AUDIT_COMPLETE",
        "source": SOURCE_URL,
        "license": "CC BY-NC 4.0 noncommercial research only",
        "previously_inspected_not_blind": True,
        "clip_count": len(clips),
        "total_frames": sum(item["frames"] for item in clips),
        "purpose": "joint_visibility_and_knee_geometry_feasibility_not_fall_prediction",
        "human_video_or_joint_pose_uploaded": False,
        "meta_api_called": False,
        "fall_confirmation_enabled": False,
        "notification_enabled": False,
        "clips": clips,
    }


def main() -> int:
    cli = argparse.ArgumentParser(description="Local-only licensed eight-joint research")
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--extract", action="store_true")
    mode.add_argument("--analyze", action="store_true")
    cli.add_argument("--acknowledge-noncommercial-license", action="store_true")
    cli.add_argument("--acknowledge-pose-privacy", action="store_true")
    args = cli.parse_args()
    if not (args.acknowledge_noncommercial_license and args.acknowledge_pose_privacy):
        cli.error("Noncommercial source license and person-derived pose privacy required")
    try:
        result = extract_locally() if args.extract else analyze_private()
        if args.analyze:
            report = OUTPUT / "aggregate-8joint-coverage.json"
            if report.is_symlink():
                raise ValueError("Private aggregate output symlink rejected")
            report.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)
        return 0
    except (OSError, ValueError):
        print(json.dumps({"status": "LOCAL_EIGHT_JOINT_RESEARCH_REJECTED"}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
