"""One-target, non-video Hikvision operator readiness report.

Only RTSP OPTIONS is sent, without authentication. Optional privacy policy is
verified using the real local HMAC gate, never generated here. No DESCRIBE,
SETUP, PLAY, credentials, frame capture, AI inference or camera-setting edits.
The output deliberately never includes camera addresses or policy references.
"""
from argparse import ArgumentParser
import json
from pathlib import Path

from sentinel_edge.privacy_gate import PrivacyGateDenied, verify_privacy_approval
from sentinel_edge.rtsp_protocol_probe import probe_options, validate_target


SCHEMA = "viil.camera.operator_readiness.v1"


def diagnose_camera(
    camera_ip: str, *,
    rtsp_port: int = 554,
    timeout_seconds: float = 2.5,
    privacy_approval: Path | None = None,
    source_id: str | None = None,
    options_probe=None,
    approval_verifier=None,
) -> dict:
    """Classify only bounded transport/authz facts, never media readiness.

    The human operator must have independent site permission even to probe
    a target. This diagnostic does not grant access or authorize video.
    """
    validate_target(camera_ip, rtsp_port, timeout_seconds)
    if (privacy_approval is None) != (source_id is None):
        raise ValueError("Signed approval and its scoped camera ID must be supplied together")
    if privacy_approval is not None and (
        not isinstance(privacy_approval, Path)
        or not isinstance(source_id, str)
        or not 1 <= len(source_id) <= 80
    ):
        raise ValueError("Invalid approval input")

    # No video, URL path, RTSP credentials or personal data are requested.
    safe_options_probe = options_probe or probe_options
    safe_approval_verifier = approval_verifier or verify_privacy_approval
    raw = safe_options_probe(camera_ip, port=rtsp_port, timeout_seconds=timeout_seconds)
    status = raw.get("result")
    if status not in (
        "rtsp_server_responded", "transport_or_protocol_timeout",
        "non_rtsp_or_invalid_response",
    ):
        status = "unknown"
    code = raw.get("rtsp_status_code")
    if type(code) is not int or code < 100 or code > 599 or status != "rtsp_server_responded":
        code = None

    approval_status = "not_provided"
    if privacy_approval is not None:
        try:
            safe_approval_verifier(privacy_approval, camera_id=source_id)
        except (PrivacyGateDenied, ValueError, OSError, TypeError):
            approval_status = "denied"
        else:
            approval_status = "verified"

    # OPTIONS 200/401 says the RTSP endpoint exists, not that credentials or
    # DESCRIBE/SETUP/PLAY will work. Do not promote other codes to readiness.
    eligible = status == "rtsp_server_responded" and code in (200, 401)
    can_trial = eligible and approval_status == "verified"
    if not eligible:
        next_step = "verify_routing_and_rtsp_service_without_video"
    elif approval_status != "verified":
        next_step = "complete_genuine_site_and_signed_privacy_approval"
    else:
        next_step = "operator_may_run_separate_signed_12_frame_decode_trial"

    return {
        "schema_version": SCHEMA,
        "scope": "one_authorized_private_target_metadata_only",
        "transport_status": status,
        "rtsp_status_code": code,
        "rtsp_authentication_challenge": code == 401,
        "privacy_approval_status": approval_status,
        "eligible_for_separate_supervised_decode_trial": can_trial,
        "next_step": next_step,
        "rtsp_credentials_checked": False,
        "video_authentication_checked": False,
        "frames_decoded": 0,
        "video_recorded": False,
        "edge_inference_run": False,
        "camera_settings_modified": False,
        "real_world_fall_detection_verified": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = ArgumentParser(description="One-target RTSP+approval readiness, never opens video")
    parser.add_argument("--camera-ip", required=True, help="Operator-authorized RFC1918 camera IPv4")
    parser.add_argument("--rtsp-port", type=int, default=554, choices=(554, 8554))
    parser.add_argument("--timeout-seconds", type=float, default=2.5)
    parser.add_argument("--privacy-approval", type=Path,
                        help="Optional existing genuine signed policy file")
    parser.add_argument("--source-id", help="Pseudonymous camera ID matching policy")
    args = parser.parse_args(argv)
    try:
        report = diagnose_camera(
            args.camera_ip, rtsp_port=args.rtsp_port,
            timeout_seconds=args.timeout_seconds,
            privacy_approval=args.privacy_approval, source_id=args.source_id,
        )
    except (ValueError, TypeError):
        parser.error("Invalid private camera/approval inputs (details redacted)")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["eligible_for_separate_supervised_decode_trial"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
