"""Offline readiness probe for optional webcam/video components.

No camera opens, no model loads, and no network requests are made.
"""
from argparse import ArgumentParser
from importlib import metadata
import json
from pathlib import Path
import re


def _parse_version(value: str) -> tuple[int, int, int] | None:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        return None
    return tuple(map(int, match.groups()))


def probe(*, model: Path | None = None) -> dict:
    checks: dict[str, dict] = {}
    for package, minimum in (("mediapipe", (0, 10, 20)),):
        try:
            actual = metadata.version(package)
        except metadata.PackageNotFoundError:
            actual = None
        parsed = _parse_version(actual) if actual else None
        checks[package] = {
            "version": actual,
            "ready": parsed is not None and parsed >= minimum and parsed < (0, 11, 0),
            "supported_range": ">=0.10.20,<0.11",
        }

    cv_versions = {}
    for package in ("opencv-python", "opencv-contrib-python", "opencv-python-headless"):
        try:
            cv_versions[package] = metadata.version(package)
        except metadata.PackageNotFoundError:
            pass
    checks["opencv"] = {
        "ready": len(cv_versions) == 1,
        "installed": cv_versions,
        "note": "Exactly one cv2 provider should be installed in the environment",
    }

    valid_model = (
        model is not None
        and model.suffix.lower() == ".task"
        and model.is_file()
        and model.stat().st_size > 0
    )
    checks["pose_model"] = {
        "ready": valid_model,
        "supplied": model is not None,
        "asset_check": "file exists, .task extension, nonempty only; actual validity requires inference",
    }
    return {
        "ready_for_video_smoke_test": all(v["ready"] for v in checks.values()),
        "tests_only_mode_available": True,
        "checks": checks,
        "note": "This probe does not access camera, load a model, or confirm accuracy.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Offline Pose Landmarker readiness check")
    parser.add_argument("--model", type=Path, default=None,
                        help="Locally licensed .task file, not a model to download")
    args = parser.parse_args(argv)
    report = probe(model=args.model)
    print(json.dumps(report, indent=2))
    return 0 if report["ready_for_video_smoke_test"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
