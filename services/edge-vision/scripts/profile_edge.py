"""Read-only on-device benchmark profiler: no recordings/landmarks uploaded.

Uses a child process to isolate startup time. On Windows the direct child
process may be wrapped by an execution harness; RAM and CPU are measured
INSIDE the model process by optional psutil, not by inspecting wrapper PID.
"""
from argparse import ArgumentParser
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter


def run_once(manifest: Path, model: Path, *, buffered: bool = False,
             max_inference_side: int = 0) -> dict:
    cmd = [sys.executable, "-m", "sentinel_edge.video_benchmark",
           "--manifest", str(manifest), "--model", str(model),
           "--confirm-consent", "--profile-resource"]
    if buffered:
        cmd.append("--buffered-eval")
    if max_inference_side:
        cmd.extend(["--max-inference-side", str(max_inference_side)])
    start = perf_counter()
    process = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, text=True, encoding="utf-8", timeout=240,
        check=False
    )
    elapsed = perf_counter() - start
    if process.returncode:
        raise RuntimeError(f"Benchmark child exit code: {process.returncode}")
    result = json.loads(process.stdout)
    resource = result.get("resource_profile", {})
    return {
        "evaluation_path": "buffered" if buffered else "streaming",
        "inference_max_side_px": max_inference_side,
        "elapsed_s": round(elapsed, 3),
        "peak_working_set_mb": resource.get("peak_working_set_mb"),
        "cpu_seconds": resource.get("cpu_seconds"),
        "resource_measurement": resource.get("measurement"),
        "total_frames": result["total_video_frames"],
        "throughput_frames_s": round(result["total_video_frames"] / elapsed, 2),
        "valid_pose_frames": result["total_video_frames"] - result["unavailable_pose_frames"],
        "metrics": result["metrics"],
        "candidate_times": {
            item["clip_id"]: [item["candidate_count"], item["first_candidate_ms"]]
            for item in result["clips"]
        },
    }


def directory_bytes(root: Path) -> int | None:
    if not root.exists():
        return None
    if root.is_file():
        return root.stat().st_size
    return sum(item.stat().st_size for item in root.rglob("*")
               if item.is_file() and not item.is_symlink())


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Private Edge inference time/RAM and disk inspection")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--confirm-consent", action="store_true")
    parser.add_argument("--buffered-reference", action="store_true")
    parser.add_argument("--max-inference-side", type=int, default=0)
    parser.add_argument("--disk-summary", action="store_true")
    args = parser.parse_args(argv)
    if not args.confirm_consent:
        parser.error("--confirm-consent is required")
    try:
        result = run_once(args.manifest, args.model, buffered=args.buffered_reference,
                          max_inference_side=args.max_inference_side)
        if args.disk_summary:
            paths = {
                "model_file": args.model,
                "edge_venv": Path(sys.executable).resolve().parents[1],
                "private_dataset_root": args.manifest.parent,
                "private_dataset_archive": args.manifest.parent.parent / "IKAR_dataset.tar.gz",
            }
            result["disk_mb"] = {
                key: round(size / 1048576, 2) if (size := directory_bytes(path))
                is not None else None for key, path in paths.items()
            }
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
