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

The legacy `scripts/start-hikvision-owner-preview.ps1` remains a
**local Windows OpenCV** tool and must not be described as Dashboard streaming.
