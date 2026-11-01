"""Opt-in LOOPBACK-ONLY camera media bridge owned by Member 1.

Not Member 2's production backend. No public listener, network bridge,
automatic onboarding, cloud streaming, saved frames or medical inference.
A real owner-signed, current local camera policy and distinct high-entropy
operator password are mandatory. No camera password reaches the browser.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from importlib.util import find_spec
import hmac
import ipaddress
import os
from pathlib import Path
import re
import secrets
from threading import Lock
from time import monotonic
from typing import Callable, Iterator

import anyio
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ConfigDict

from sentinel_edge.camera_health import validate_rtsp_env
from sentinel_edge.edge_mjpeg import (
    MAX_MJPEG_PART_BYTES, MJPEG_CONTENT_TYPE, iter_authorized_mjpeg_parts,
)
from sentinel_edge.privacy_gate import CAMERA_PATTERN, PrivacyGateDenied, verify_privacy_approval
from sentinel_edge.privacy_approval_operator import inspect_unsigned_draft

SESSION_SECONDS = 600
PREVIEW_SECONDS = 25
COOKIE_NAME = "viil_local_operator"
MEDIA_SCHEMA = "viil.backend.camera_preview_session.v1"
OVERVIEW_SCHEMA = "viil.backend.integration_overview.v1"
READINESS_SCHEMA = "viil.local.camera_readiness.v1"
DRAFT_CHECKLIST_SCHEMA = "viil.local.unsigned_approval_checklist.v1"
TRANSPORT_STATUS_SCHEMA = "viil.local.preview_transport_status.v1"
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,80}$", re.ASCII)
LOOPBACK_ORIGINS = frozenset({
    "http://127.0.0.1:5173", "http://localhost:5173",
    "http://127.0.0.1:8001", "http://localhost:8001",
})
HEADERS = {
    "Cache-Control": "no-store, private",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Referrer-Policy": "no-referrer",
}


class SynchronizedMediaParts:
    """Coordinate a native generator's next/close across worker threads.

    Starlette iterates sync generators in an AnyIO worker. A disconnect can
    race with its blocking decoder read, so closing without a lock would
    raise 'generator already executing' and leave a camera handle open.
    """

    def __init__(self, source: Iterator[bytes]):
        self._source = source
        self._lock = Lock()

    def __iter__(self):
        return self

    def __next__(self):
        with self._lock:
            return next(self._source)

    def close(self) -> None:
        with self._lock:
            self._source.close()


class PreflightMediaParts:
    """Own an already-started native generator even before ASGI body iteration.

    Closing an *unstarted generator wrapper* cannot execute its finally block.
    After the first JPEG has been decoded, ownership must live in a concrete
    object whose close() always reaches the original decoder.
    """

    def __init__(self, first: bytes, source: Iterator[bytes], *,
                 authorized: Callable[[], bool]):
        self._first = first
        self._source = source
        self._authorized = authorized
        self._first_sent = False
        self._closed = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._closed:
            raise StopIteration
        if not self._first_sent:
            self._first_sent = True
            if self._authorized() is not True:
                raise StopIteration
            return self._first
        return next(self._source)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._source.close()


class RevocableMediaResponse(StreamingResponse):
    """Always revoke and close the native decoder on HTTP disconnect/error.

    The owner callback revokes the viewer before closing; the release
    callback frees the global camera slot only *after* generator cleanup.
    """

    def __init__(self, source: Iterator[bytes], *, revoke: Callable[[], None],
                 released: Callable[[], None]):
        self._managed_parts = SynchronizedMediaParts(source)
        self._revoke = revoke
        self._released = released
        super().__init__(self._managed_parts, media_type=MJPEG_CONTENT_TYPE,
                         headers=HEADERS)

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self._revoke()
            # A disconnect cancels the response task. Shield native release
            # and wait for any in-flight worker-thread read before closing.
            with anyio.CancelScope(shield=True):
                try:
                    await anyio.to_thread.run_sync(self._managed_parts.close)
                except Exception:
                    # A native decoder close exception can contain a
                    # credentialed RTSP URL. Keep the global slot reserved
                    # rather than claiming its native handle was released.
                    raise RuntimeError(
                        "Protected media cleanup unavailable (redacted)"
                    ) from None
                self._released()


def valid_first_mjpeg_part(part: object) -> bool:
    """Reject missing/malformed frames before an HTTP 200 media response."""
    if type(part) is not bytes or len(part) > MAX_MJPEG_PART_BYTES + 128:
        return False
    header, delimiter, payload = part.partition(b"\r\n\r\n")
    prefix = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
    if delimiter != b"\r\n\r\n" or not header.startswith(prefix):
        return False
    size_text = header[len(prefix):]
    if not 1 <= len(size_text) <= 6 or not size_text.isdigit():
        return False
    jpeg = payload[:-2] if payload.endswith(b"\r\n") else b""
    return (
        len(jpeg) == int(size_text)
        and len(jpeg) <= MAX_MJPEG_PART_BYTES
        and jpeg.startswith(b"\xff\xd8")
        and jpeg.endswith(b"\xff\xd9")
    )


class OperatorLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1, max_length=256)


@dataclass(frozen=True)
class BridgeConfig:
    enabled: bool = False
    camera_id: str = "staged-camera-01"
    source_env: str = "VIIL_CAMERA_RTSP"
    approval_path: Path | None = None
    operator_password: str = ""
    unsigned_draft_path: Path | None = None

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        raw_path = os.getenv("VIIL_BRIDGE_APPROVAL_PATH", "").strip()
        draft_path = os.getenv("VIIL_BRIDGE_UNSIGNED_DRAFT_PATH", "").strip()
        return cls(
            enabled=os.getenv("VIIL_BRIDGE_ENABLED", "0") == "1",
            camera_id=os.getenv("VIIL_BRIDGE_CAMERA_ID", "staged-camera-01"),
            source_env=os.getenv("VIIL_BRIDGE_RTSP_ENV", "VIIL_CAMERA_RTSP"),
            approval_path=Path(raw_path) if raw_path else None,
            operator_password=os.getenv("VIIL_BRIDGE_OPERATOR_PASSWORD", ""),
            unsigned_draft_path=Path(draft_path) if draft_path else None,
        )

    def valid(self) -> bool:
        return (
            self.enabled is True
            and isinstance(self.camera_id, str)
            and CAMERA_PATTERN.fullmatch(self.camera_id) is not None
            and isinstance(self.source_env, str)
            and self.source_env.startswith("VIIL_")
            and self.source_env.isidentifier()
            and isinstance(self.approval_path, Path)
            and self.approval_path.is_absolute()
            and isinstance(self.operator_password, str)
            and 16 <= len(self.operator_password) <= 256
            and not self.operator_password.isspace()
        )


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_loopback(request: Request) -> bool:
    try:
        host = request.client.host if request.client else ""
        return ipaddress.ip_address(host).is_loopback
    except (ValueError, TypeError):
        return False


def require_loopback(request: Request) -> None:
    if not is_loopback(request):
        raise HTTPException(403, "Local operator interface only")
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site is not None and fetch_site != "same-origin":
        raise HTTPException(403, "Same-origin operator interface only")


def require_origin(request: Request) -> None:
    require_loopback(request)
    origin = request.headers.get("origin")
    if origin not in LOOPBACK_ORIGINS:
        raise HTTPException(403, "Operator origin check denied")


def verify_policy(config: BridgeConfig) -> bool:
    if config.approval_path is None:
        return False
    try:
        verify_privacy_approval(config.approval_path, camera_id=config.camera_id)
        return True
    except (PrivacyGateDenied, OSError, ValueError):
        return False


def create_bridge_app(
    config: BridgeConfig | None = None, *,
    media_factory: Callable = iter_authorized_mjpeg_parts,
    cv2_loader: Callable | None = None,
    clock: Callable[[], float] = monotonic,
) -> FastAPI:
    """Create isolated Edge bridge; injection is solely for offline tests."""
    cfg = config or BridgeConfig.from_env()
    app = FastAPI(title="VIIL local operator media bridge", docs_url=None,
                  redoc_url=None, openapi_url=None)
    tokens: dict[str, float] = {}
    previews: dict[str, tuple[str, str, float]] = {}
    streaming: set[str] = set()
    edge_first_jpeg_verified: set[str] = set()
    failed_logins: list[float] = []
    guard = Lock()

    @app.middleware("http")
    async def protect_headers(request: Request, call_next):
        response = await call_next(request)
        for name, value in HEADERS.items():
            response.headers[name] = value
        return response

    def require_enabled(request: Request) -> None:
        require_loopback(request)
        if not cfg.valid():
            raise HTTPException(503, "Local media bridge disabled")

    def active_operator(request: Request) -> str:
        require_enabled(request)
        token = request.cookies.get(COOKIE_NAME, "")
        with guard:
            alive = bool(token) and tokens.get(token, 0) > clock()
        if not alive:
            raise HTTPException(401, "Local operator login required")
        return token

    def preview_authorized(sid: str, token: str, camera_id: str) -> bool:
        with guard:
            state = previews.get(sid)
            return (
                state is not None and state[0] == token
                and state[1] == camera_id
                and state[2] > clock()
                and tokens.get(token, 0) > clock()
            )

    @app.get("/health")
    def health(request: Request):
        require_loopback(request)
        return {"status": "ok", "mode": "LOCAL_ONLY", "media_bridge_enabled": cfg.valid()}

    @app.post("/api/v1/operator/login")
    def login(request: Request, payload: OperatorLogin, response: Response):
        require_origin(request)
        require_enabled(request)
        expected = cfg.operator_password
        now = clock()
        with guard:
            failed_logins[:] = [t for t in failed_logins if now - t < 60]
            if len(failed_logins) >= 5:
                raise HTTPException(429, "Operator login temporarily unavailable")
        if not hmac.compare_digest(payload.password, expected):
            with guard:
                failed_logins.append(now)
            raise HTTPException(401, "Operator credentials rejected")
        token = secrets.token_urlsafe(32)
        with guard:
            for old, expires in list(tokens.items()):
                if expires <= clock():
                    tokens.pop(old, None)
            if len(tokens) >= 8:
                raise HTTPException(429, "Operator login capacity reached")
            failed_logins.clear()
            tokens[token] = clock() + SESSION_SECONDS
        response.set_cookie(
            COOKIE_NAME, token, httponly=True, secure=False, samesite="strict",
            max_age=SESSION_SECONDS, path="/api/v1",
        )
        return {"authenticated": True, "mode": "local_operator"}

    @app.post("/api/v1/operator/logout", status_code=204)
    def logout(request: Request, response: Response):
        require_origin(request)
        token = active_operator(request)
        with guard:
            tokens.pop(token, None)
            for key, (operator, _, _) in list(previews.items()):
                if operator == token:
                    previews.pop(key, None)
                    edge_first_jpeg_verified.discard(key)
                    # Do not start another decoder until the active native
                    # generator has released its resources in finally.
        response.delete_cookie(COOKIE_NAME, path="/api/v1", samesite="strict")

    @app.get("/api/v1/integrations/overview")
    def overview(request: Request):
        active_operator(request)
        timestamp = utc_now().isoformat(timespec="milliseconds").replace("+00:00", "Z")
        approved = verify_policy(cfg)
        camera = {
            "camera_id": cfg.camera_id,
            "transport": "rtsp",
            # Never call the camera from a read-only metadata request.
            "health": "unknown", "privacy": "approved" if approved else "unverified",
            "last_heartbeat_at": None, "observed_fps": None,
        }
        return {
            "schema_version": OVERVIEW_SCHEMA, "generated_at": timestamp,
            "access_scope": "authenticated_operator",
            "edge": {"state": "degraded", "last_heartbeat_at": None},
            "cameras": [camera],
            "meta": {"provider": "mock", "state": "not_configured",
                     "evidence_pipeline": "not_configured", "last_verified_call_at": None},
            "notification": {"state": "not_configured"},
        }

    @app.get("/api/v1/operator/camera-readiness")
    def camera_readiness(request: Request):
        """Metadata-only prerequisites: never connects to or probes a camera.

        Even if everything here is true, zero live frames have been verified
        by this check. Only an actual supervised, signed Edge decode may
        establish whether video is available.
        """
        active_operator(request)
        policy_ok = verify_policy(cfg)
        try:
            validate_rtsp_env(cfg.source_env)
            rtsp_ok = True
        except (ValueError, TypeError, OSError):
            rtsp_ok = False
        pyav_ok = find_spec("av") is not None
        cv2_ok = find_spec("cv2") is not None
        return {
            "schema_version": READINESS_SCHEMA,
            "camera_id": cfg.camera_id,
            "signed_privacy_approval_verified": policy_ok,
            "private_rtsp_configured": rtsp_ok,
            "pyav_decoder_installed": pyav_ok,
            "opencv_jpeg_encoder_installed": cv2_ok,
            "eligible_for_supervised_trial": (
                policy_ok and rtsp_ok and pyav_ok and cv2_ok
            ),
            "real_camera_frame_verified": False,
        }

    @app.get("/api/v1/operator/approval-checklist")
    def approval_checklist(request: Request):
        """Read-only, redacted unsigned draft field review for local operator.

        No camera, signing key, reference value, legal approval or signature
        access. Only a small set of known field names can leave this route.
        """
        active_operator(request)
        draft = cfg.unsigned_draft_path
        available = False
        complete = False
        issues: list[str] = []
        if isinstance(draft, Path) and draft.is_absolute():
            try:
                report = inspect_unsigned_draft(draft, cfg.camera_id)
                safe_issue_names = frozenset({
                    "schema_version", "purpose", "approval_ref", "controller_ref",
                    "notice_ref", "privacy_impact_review_ref",
                    "sensitive_data_review_ref", "rights_procedure_ref",
                    "jurisdictions", "legal_basis_by_jurisdiction",
                    "approved_camera_ids", "validity_window",
                    "site_authorization_confirmed", "notices_confirmed",
                    "human_review_required", "local_only",
                    "cloud_transfer_enabled", "face_identification_enabled",
                    "training_reuse_enabled", "automatic_emergency_dispatch_enabled",
                    "raw_frame_retention_days",
                })
                raw_issues = report["issues"]
                if (isinstance(raw_issues, list)
                        and len(raw_issues) <= len(safe_issue_names)
                        and all(type(v) is str and v in safe_issue_names
                                for v in raw_issues)
                        and len(raw_issues) == len(set(raw_issues))):
                    issues = raw_issues
                    available = True
                    complete = report["draft_fields_structurally_complete"] is True
            except (OSError, ValueError, TypeError, KeyError):
                pass
        return {
            "schema_version": DRAFT_CHECKLIST_SCHEMA,
            "draft_available": available,
            "draft_fields_structurally_complete": available and complete,
            "issues": issues,
            "genuine_site_permission_confirmed_by_tool": False,
            "signed_policy_verified": False,
            "camera_access_granted": False,
        }

    @app.post("/api/v1/cameras/{camera_id}/preview-sessions", status_code=201)
    def create_preview(camera_id: str, request: Request):
        require_origin(request)
        token = active_operator(request)
        if camera_id != cfg.camera_id or not verify_policy(cfg):
            raise HTTPException(403, "Camera authorization denied")
        try:
            validate_rtsp_env(cfg.source_env)
        except (ValueError, TypeError):
            raise HTTPException(503, "Private camera source not configured") from None
        sid = secrets.token_urlsafe(24)
        deadline = clock() + PREVIEW_SECONDS
        with guard:
            # One live decoder globally, including revoked/expired sessions
            # whose generator has not yet released the native camera handle.
            for key, (_, _, expires) in list(previews.items()):
                if expires <= clock() and key not in streaming:
                    previews.pop(key, None)
                    edge_first_jpeg_verified.discard(key)
            if previews or streaming:
                raise HTTPException(409, "Local camera already has an active preview")
            previews[sid] = (token, camera_id, deadline)
        return {
            "schema_version": MEDIA_SCHEMA, "camera_id": camera_id,
            "session_id": sid,
            "expires_at": (utc_now() + timedelta(seconds=PREVIEW_SECONDS)).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z"),
        }

    @app.get("/api/v1/cameras/{camera_id}/preview-sessions/{sid}/status")
    def preview_transport_status(camera_id: str, sid: str, request: Request):
        """Local-only diagnostics; never opens the camera or carries image data.

        The server knows its decoder produced a JPEG, but cannot verify the
        browser displayed it. No camera configuration or frame content leaks.
        """
        token = active_operator(request)
        if (camera_id != cfg.camera_id or SESSION_ID_RE.fullmatch(sid) is None
                or not verify_policy(cfg)):
            raise HTTPException(403, "Protected preview status denied")
        with guard:
            state = previews.get(sid)
            if (state is None or state[0] != token or state[1] != camera_id
                    or state[2] <= clock() or tokens.get(token, 0) <= clock()):
                raise HTTPException(403, "Protected preview status denied")
            edge_verified = sid in edge_first_jpeg_verified
            preflight_started = sid in streaming
        return {
            "schema_version": TRANSPORT_STATUS_SCHEMA,
            "camera_id": camera_id,
            "session_id": sid,
            "edge_first_jpeg_verified": edge_verified,
            "edge_preflight_started": preflight_started,
            "browser_image_display_verified": False,
        }

    @app.get("/api/v1/cameras/{camera_id}/preview-sessions/{sid}/mjpeg")
    def get_preview(camera_id: str, sid: str, request: Request):
        token = active_operator(request)
        if (camera_id != cfg.camera_id or SESSION_ID_RE.fullmatch(sid) is None
                or not preview_authorized(sid, token, camera_id)
                or not verify_policy(cfg)):
            raise HTTPException(403, "Camera session expired or denied")

        # Single-use stream. The <img> uses the HttpOnly cookie. Opaque URL
        # IDs are never authorization. Reject concurrent/replayed GETs.
        with guard:
            if sid in streaming or sid not in previews:
                raise HTTPException(403, "Camera session unavailable")
            streaming.add(sid)

        def parts():
            source = None
            try:
                # cv2 is optional until a genuinely authorized camera
                # request has reached this route.
                if cv2_loader:
                    cv2 = cv2_loader()
                else:
                    import cv2
                source = iter(media_factory(
                    cv2, source_env=cfg.source_env, source_id=camera_id,
                    privacy_approval=cfg.approval_path,
                    viewer_check=lambda: preview_authorized(sid, token, camera_id),
                    duration_seconds=PREVIEW_SECONDS,
                ))
                while True:
                    try:
                        part = next(source)
                    except StopIteration:
                        return
                    except Exception:
                        # A native read error can include RTSP credentials.
                        return
                    yield part
            except Exception:
                # Import/opener errors may include private camera details.
                return
            finally:
                try:
                    if source is not None:
                        # Close after even a failed preflight, cancelled ASGI
                        # send or generator return. Do NOT suppress failures
                        # here: unresolved cleanup must retain camera capacity.
                        source.close()
                finally:
                    with guard:
                        previews.pop(sid, None)
                        edge_first_jpeg_verified.discard(sid)
                        # Release the streaming slot only after a confirmed
                        # close, outside this generator's cleanup block.

        # Synchronous endpoint thread: actually open/decode the camera's
        # 12-frame privacy-gated preflight BEFORE committing HTTP status 200.
        # A dead camera must produce a redacted 503, not a misleading 200 MJPEG.
        iterator = parts()
        try:
            first = next(iterator)
            if (not valid_first_mjpeg_part(first)
                    or not preview_authorized(sid, token, camera_id)
                    or not verify_policy(cfg)):
                raise ValueError("Camera media unavailable")
        except Exception:
            try:
                iterator.close()
            except Exception:
                # Native cleanup is uncertain. Never leak an exception that
                # might include RTSP credentials or permit a second decoder.
                pass
            else:
                with guard:
                    streaming.discard(sid)
            raise HTTPException(503, "Protected camera frames unavailable") from None

        with guard:
            # A successful RTSP OPTIONS or session POST never sets this flag:
            # only 12/12 decoded frames followed by a valid first JPEG can.
            if sid in previews and sid in streaming:
                edge_first_jpeg_verified.add(sid)

        def revoke():
            with guard:
                previews.pop(sid, None)
                edge_first_jpeg_verified.discard(sid)

        def released():
            with guard:
                streaming.discard(sid)

        return RevocableMediaResponse(
            PreflightMediaParts(
                first, iterator,
                authorized=lambda: (
                    preview_authorized(sid, token, camera_id) and verify_policy(cfg)
                ),
            ),
            revoke=revoke, released=released,
        )

    @app.delete("/api/v1/cameras/{camera_id}/preview-sessions/{sid}",
                status_code=204)
    def delete_preview(camera_id: str, sid: str, request: Request):
        require_origin(request)
        token = active_operator(request)
        if camera_id != cfg.camera_id or SESSION_ID_RE.fullmatch(sid) is None:
            raise HTTPException(403, "Camera session denied")
        with guard:
            if previews.get(sid, ("", "", 0))[0] == token:
                previews.pop(sid, None)
                edge_first_jpeg_verified.discard(sid)
                # Keep the streaming lock until the native generator releases.

    return app


def main() -> None:
    """No --host argument by design; binds only to 127.0.0.1."""
    import uvicorn

    cfg = BridgeConfig.from_env()
    if not cfg.valid():
        raise SystemExit("Local media bridge disabled: operator setup incomplete")
    uvicorn.run(create_bridge_app(cfg), host="127.0.0.1", port=8001,
                log_level="warning", access_log=False)


if __name__ == "__main__":
    main()
