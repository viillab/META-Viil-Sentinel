"""Prepare local, untransmitted v1 candidate envelopes from pose trace JSONL.

No videos or images, no API requests. This is an integration fixture and
handoff verification command, not an emergency-response workflow.
"""
import json
from argparse import ArgumentParser
from dataclasses import replace
from pathlib import Path

from sentinel_edge.detector import TemporalFallDetector
from sentinel_edge.handoff import SOURCE_ID_PATTERN, to_envelope
from sentinel_edge.pose_traces import read_pose_trace

MAX_EVENTS = 1000


def export_trace(
    trace: Path, *, source_id: str, provenance: str = "synthetic_pose_trace",
    authorized: bool = False, model_sha256: str | None = None,
) -> list[dict]:
    if not SOURCE_ID_PATTERN.fullmatch(source_id):
        raise ValueError("source_id must be a pseudonymous ASCII slug")
    if trace.suffix.lower() != ".jsonl" or not trace.is_file():
        raise ValueError("An existing local .jsonl trace is required")
    if provenance not in ("synthetic_pose_trace", "consented_staged_video"):
        raise ValueError("trace mode must be synthetic or consented staged")
    if provenance == "consented_staged_video" and not authorized:
        raise ValueError("Explicit authorization required for staged trace")
    if provenance == "synthetic_pose_trace" and authorized:
        raise ValueError("Do not mark synthetic demonstrations as authorized real media")

    detector = TemporalFallDetector()
    output: list[dict] = []
    for frame in read_pose_trace(trace, source_id=source_id):
        candidate = detector.process(frame)
        if candidate is None:
            continue
        # Unlike older runner tests, these envelopes *must* label fake data.
        candidate = replace(candidate, simulated=provenance == "synthetic_pose_trace")
        envelope = to_envelope(
            candidate, input_provenance=provenance, model_sha256=model_sha256
        )
        output.append(envelope.to_dict())
        if len(output) > MAX_EVENTS:
            raise ValueError("Too many candidate events; refusing partial export")
    return output


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="Local-only Edge candidate v1 JSONL export")
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--source-id", default="synthetic-clip-01")
    parser.add_argument("--provenance", choices=["synthetic_pose_trace", "consented_staged_video"],
                        default="synthetic_pose_trace")
    parser.add_argument("--authorized-staged-data", action="store_true")
    parser.add_argument("--model-sha256", default=None)
    args = parser.parse_args(argv)
    try:
        events = export_trace(
            args.trace, source_id=args.source_id, provenance=args.provenance,
            authorized=args.authorized_staged_data, model_sha256=args.model_sha256
        )
    except (ValueError, OSError) as exc:
        parser.error(f"Candidate export failed: {exc}")
    # Print only after the entire trace validates; malformed input cannot
    # produce a half-exported stream that downstream tools may trust.
    for event in events:
        print(json.dumps(event, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
