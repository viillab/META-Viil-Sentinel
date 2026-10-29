# VIIL-Sentinel — Browser Live Camera Preview (Member 1 / Member 2 handoff)

## Status (29 Oct 2026)

**UI implemented, real live Hikvision playback NOT verified.** The Dashboard
Integration Center now offers *Open live preview* / *Stop preview* controls only
for fresh backend-reported camera health=online and privacy=approved. It is
disabled for the sample/mock layout. The RTSP OPTIONS 200 response proves only
that an RTSP service responded; it does not prove authentication, 12/12 decoded
frames, or playback in a browser.

The browser never receives a camera IP, RTSP URL, Hikvision password, or
provider API token. The browser **does** transiently receive images when a
properly authorized session is live; it does not intentionally record them.
This is a LOCAL, operator-supervised research preview, not a production remote
monitoring feed, authenticated caregiver product or fall classification.

## Member 2 backend media contract — implementation still required

Backend owns authentication/session management, same-origin CSRF prevention,
authorization, per-camera RBAC, signed privacy verification and audit. Only a
private, human-approved camera with valid notices/review can be streamed. A
backend status `privacy: approved` is NOT independently trusted as proof.

The Dashboard uses these endpoints under existing /api same-origin routing:

| Method | Path | Behavior |
| --- | --- | --- |
| POST | /api/v1/cameras/{camera_id}/preview-sessions | After actual operator click, validate auth, role, signed Edge approval, camera scope, validity/notices; allocate at most one 30-second session; return exact JSON schema below, otherwise 401/403/404 |
| GET | /api/v1/cameras/{camera_id}/preview-sessions/{session_id}/mjpeg | Require same authenticated operator and camera RBAC **on request and for every output frame**; 200 Content-Type multipart/x-mixed-replace; boundary=frame; strictly private and no-store; terminate instantly on revocation, expiry, disconnect or absent live decoder |
| DELETE | /api/v1/cameras/{camera_id}/preview-sessions/{session_id} | Idempotently revoke this operator's scoped session; no raw media in response |

POST JSON: `handoff/team/camera_preview_session.v1.schema.json`, exactly
`schema_version`, `camera_id`, `session_id` (random 16–80 safe characters)
and `expires_at` (UTC with Z, <=30 seconds from receipt). No media_url
field, absolute links, camera IP/port, secrets or arbitrary redirect.
Session IDs are not bearer auth; every GET/DELETE requires server session
and RBAC. Reject media requests with stale/revoked privacy checks; enforce
server-side timeout <=30 seconds (frontend timeout is UX only).
Browser may send custom `X-VIIL-Preview-Intent` header on POST/DELETE;
this header is only client intent, **not** authentication or CSRF defense.
Server MUST independently validate Origin/CSRF and use secure SameSite,
HttpOnly operator session cookie in a properly authenticated environment.

Security constraints:
- Real frames must originate ONLY from the approved local Edge worker after
  the genuine signed camera policy and a supervised 12-frame decoder trial.
  Never use fake approvals, a mock file or RTSP OPTIONS as video evidence.
- Do not expose RTSP, direct camera LAN URLs, camera credentials or a media
  gateway bound to `0.0.0.0`/public internet. Do not forward via Meta/cloud.
  Only same-origin private browser path, with backend enforcing authorization
  on every frame/stream. This initial contract targets the local operator
  and does not permit remote camera viewing without additional review.
- Limit one active browser session per operator/camera, concurrent decoders,
  frame resolution, frame rate, and bandwidth. Do not persist raw frames,
  thumbnails, face identity or access tokens. Stop when browser tab hides,
  operator clicks Stop, status/approval expires, video errors or timeout.
- Return `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
  restrictive `Content-Security-Policy`/frame ancestor policy as appropriate,
  and avoid credentials/video content in logs. Deny CORS by default.
- The browser labels the first `<img>` onLoad as **FRAME RECEIVED** (only an
  in-browser image event, not independent evidence of source authenticity).
  Inference/pose overlays remain a distinct, unverified milestone. Neither
  the feed nor the UI should infer or confirm a real fall.

## Readiness steps

1. The camera owner finalizes genuine site/privacy review and affected-person
   notices. The last checked private unsigned policy was incomplete; do not
   treat the template, owner password or CLI switch as consent.
2. Using the Windows operator launcher, verify HMAC gate and decode 12
   *real* frames on the controlled Hikvision substream (102).
3. Member 2 implements the three endpoints and server-side authorization,
   Member 1 connects a gated local Edge MJPEG gateway (or approved adapter)
   **without passing the camera password to the browser**.
4. In `apps/dashboard`, start local dev with `npm run dev`, open Integration
   Center, confirm fresh authenticated overview metadata, click
   **Open live preview**. Without a backend media endpoint the UI must
   say `Protected camera media gateway unavailable`, not show fake video.
5. Verify manual Stop, idle tab, expired privacy, denied 401/403, stream
   errors, frame budget, no raw recording and redacted errors.

## Member 1: bounded in-process JPEG media adapter (new)

`services/edge-vision/sentinel_edge/edge_mjpeg.py` now exports
`iter_authorized_mjpeg_parts` and `MJPEG_CONTENT_TYPE`. **This is not
an HTTP server, a deployed media gateway or a camera-login bypass.**
It has no socket listener, cannot create a browser session, and imports no
FastAPI. A *trusted server-side* Member 2 integration may use it only
after session RBAC and CSRF checks, and must continue to authenticate
the same viewer on every request and output frame.

Contract (conceptual backend pseudocode, **not currently deployed**):

```python
from sentinel_edge.edge_mjpeg import (
    MJPEG_CONTENT_TYPE, iter_authorized_mjpeg_parts,
)

# In a session-verified, authenticated backend handler (Member 2):
# - Require current operator login + camera RBAC + CSRF/Origin checks
# - source_env names an administrator-provisioned VIIL_ RTSP env variable,
#   never input controlled by the browser
# - verify that the genuine signed Edge policy covers this camera
# - check current server-side viewer session on EVERY callback invocation
parts = iter_authorized_mjpeg_parts(
    cv2,
    source_env="VIIL_HIK_LAN_SUB",
    source_id="staged-camera-01",
    privacy_approval=operator_approved_policy_path,
    viewer_check=trusted_current_session_authorizer,
    decoder="pyav",
)
# Server would then pass parts into a guarded StreamingResponse with
# media_type=MJPEG_CONTENT_TYPE, no-store headers and disconnect cleanup.
```

The Edge producer:
- Requires verified genuine HMAC approval for the exact pseudonymous camera ID
  **and** the trusted server-side per-frame authorization callback before native
  camera open and after each capture / encode.
- Accepts only a preconfigured private-IP RTSP URL via the VIIL_ environment
  validator; public IP, arbitrary hostname, unsafe URL or browser-supplied URL
  is not accepted.
- Requires **12/12 successfully decoded camera frames** as an in-memory
  preflight *before yielding any browser-bound JPEG bytes*.
- Defaults to max 120 output frames, <=25 seconds, <=5 FPS, 768x432 and
  <=256 KiB JPEG/frame; configuration never permits >30s or >10 FPS.
  Native capture is released on stop, error or client iterator close.
- Never saves a frame, image, key or credential; converts authorized frames
  to transient JPEG parts solely for a trusted private backend.
- Rejects a revoked/expired signed policy or viewer session immediately on
  the next check, without yielding further frames. It **cannot** retract a
  frame already yielded or replace backend-side authorization.

The synthetic tests verify codec errors, revocation during preflight and
after emission, invalid IP and session inputs, JPEG/size limits, bounded
resolution and pacing. These are **not real Hikvision tests**. To finish real
Dashboard playback, Member 2 must implement protected routes/session storage
and integrate this producer with correct same-origin browser access, and the
operator must complete the genuine review and supervised 12-frame trial.

The legacy `scripts/start-hikvision-owner-preview.ps1` remains a
**local Windows OpenCV** tool and must not be described as Dashboard streaming.
