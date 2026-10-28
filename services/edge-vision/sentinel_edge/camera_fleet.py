"""Opt-in bounded launcher for multiple independent local camera workers.

Each camera runs the existing isolated edge runner in its own process.
Never put RTSP URLs or credentials in process arguments. Native decoder stderr
is discarded to avoid copying secrets to shared consoles. This is a staged
demo harness, NOT a high-availability or clinically validated service.
"""
from argparse import ArgumentParser
import os
from pathlib import Path
import subprocess
import sys

from sentinel_edge.camera_inputs import load_camera_registry, resolve_camera
from sentinel_edge.fleet_supervisor import stop_workers, supervise_camera_workers
from sentinel_edge.privacy_gate import (
    KEY_ENV, PrivacyGateDenied, verify_privacy_approval,
)


MAX_CONCURRENT_CAMERAS = 4
MAX_FLEET_FRAMES = 3600


def run_fleet(
    *, registry_path: Path, camera_ids: list[str], model: Path,
    max_frames: int, rtsp_retries: int = 1, rtsp_allow_port: int | None = None,
    privacy_approval: Path | None = None, launcher=None,
    timeout_seconds: int = 900,
) -> int:
    """Run up to four consented camera sources, independent session state.

    Child stdout contains privacy-minimal unconfirmed candidate JSONL. Multi-
    process console output is for local demo only; it is NOT a reliable
    transactional ingestion channel. Child stderr (native libs) is suppressed.
    """
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 3600:
        raise ValueError("Fleet timeout must be 1..3600s")
    if not 1 <= max_frames <= MAX_FLEET_FRAMES:
        raise ValueError("Fleet demo requires a bounded 1..3600 frame budget")
    if not 0 <= rtsp_retries <= 3:
        raise ValueError("RTSP retry budget must be 0..3")
    if not 1 <= len(camera_ids) <= MAX_CONCURRENT_CAMERAS:
        raise ValueError("Select between 1 and 4 cameras")
    if len(set(camera_ids)) != len(camera_ids):
        raise ValueError("Duplicate camera IDs are not allowed")
    if not model.is_file() or model.suffix != ".task":
        raise ValueError("Valid local MediaPipe model required")
    if privacy_approval is None:
        raise ValueError("Signed privacy approval is required")
    cameras = load_camera_registry(registry_path)
    selected = []
    for camera_id in camera_ids:
        if camera_id not in cameras:
            raise ValueError("Unknown camera selected (redacted)")
        camera = cameras[camera_id]
        # Validate every camera authorization and RTSP endpoint before
        # starting ANY worker, avoiding partially authorized fleet launches.
        verify_privacy_approval(privacy_approval, camera_id=camera_id)
        resolve_camera(camera, extra_rtsp_port=rtsp_allow_port)
        selected.append(camera)

    launch = launcher if launcher is not None else subprocess.Popen
    children = []
    try:
        for camera in selected:
            args = [
                sys.executable, "-m", "sentinel_edge.runner",
                "--source", "camera", "--camera-registry", str(registry_path),
                "--camera-id", camera.camera_id,
                "--model", str(model), "--max-frames", str(max_frames),
                "--candidate-format", "v1", "--confirm-consent",
                "--privacy-approval", str(privacy_approval),
            ]
            if camera.kind == "rtsp":
                args += ["--rtsp-retries", str(rtsp_retries)]
                if rtsp_allow_port is not None:
                    args += ["--rtsp-allow-port", str(rtsp_allow_port)]
            # Restrict which camera secret each process can see.
            env = os.environ.copy()
            for key in tuple(env):
                if (key.startswith("VIIL_")
                        and key not in (camera.rtsp_env, KEY_ENV)):
                    env.pop(key, None)
            child = launch(
                args, env=env, stdin=subprocess.DEVNULL,
                stdout=None, stderr=subprocess.DEVNULL, shell=False,
            )
            children.append(child)
        return supervise_camera_workers(children, timeout_seconds=timeout_seconds)
    except (OSError, KeyboardInterrupt):
        stop_workers(children)
        return 2


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Local-only bounded multi-camera research demo")
    parser.add_argument("--camera-registry", type=Path, required=True)
    parser.add_argument("--camera-ids", nargs="+", required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--max-frames", type=int, default=300)
    parser.add_argument("--timeout-seconds", type=int, default=900,
                        help="Hard wall-clock deadline for the full camera fleet, 1..3600s")
    parser.add_argument("--rtsp-retries", type=int, default=1)
    parser.add_argument("--privacy-approval", type=Path, required=True)
    parser.add_argument("--rtsp-allow-port", type=int)
    parser.add_argument("--confirm-authorized-cameras", action="store_true")
    parser.add_argument("--confirm-consent", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_authorized_cameras or not args.confirm_consent:
        parser.error("Explicit authorization and consent acknowledgement required")
    try:
        return run_fleet(
            registry_path=args.camera_registry, camera_ids=args.camera_ids,
            model=args.model, max_frames=args.max_frames,
            rtsp_retries=args.rtsp_retries, rtsp_allow_port=args.rtsp_allow_port,
            privacy_approval=args.privacy_approval,
            timeout_seconds=args.timeout_seconds,
        )
    except (ValueError, PrivacyGateDenied):
        parser.error("Invalid or unsafe camera/privacy configuration (redacted)")


if __name__ == "__main__":
    raise SystemExit(main())
