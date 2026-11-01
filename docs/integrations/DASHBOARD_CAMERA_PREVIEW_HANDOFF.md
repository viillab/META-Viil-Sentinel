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

## 1 Nov 2026 — preflighted decoder ownership across early browser disconnects

A successful native 12-frame preflight and first JPEG happens **before**
the local HTTP bridge sends response headers. If a client disconnects
while headers are being sent, the response body iterator might never
start. Python's `close()` on an *unstarted wrapper generator* does not
run its `finally` block, leaving an already-open native camera iterator
unclosed. Member 1's bridge now wraps the preflighted source in an
explicit closable `PreflightMediaParts` iterator. Its `close()` owns and
closes the **already-started underlying media generator**, even when no
MJPEG body chunk has been requested.

The response still revokes operator access first and uses its synchronized
AnyIO shielded cleanup so an in-flight native decoder read cannot race
with `close()`. The single-decoder capacity slot is freed **only after
verified cleanup**. Preflight decoder close failures return a generic
`503 Protected camera frames unavailable` without leaking camera
credentials; stream teardown failures report only
`Protected media cleanup unavailable (redacted)`. When native cleanup
fails, the capacity slot intentionally stays occupied until the **local
bridge process is safely restarted** by an authorized operator; it is
unsafe to presume the decoder released its resources.

Synthetic ASGI and FastAPI regression tests cover disconnect before
HTTP headers/body, revocation before the first delivered frame,
in-flight close coordination, redacted cleanup failures, and
fail-closed decoder slot capacity. No actual Hikvision images or
signed site approval were accessed during these tests.

## 1 Nov 2026 — independent HTTP output boundary

The local Member 1 bridge now checks **current operator + signed privacy
authorization twice around every outgoing MJPEG part**: once before
advancing the decoder, and again after a potentially blocking frame read.
This second check prevents a frame from leaving even if the session was
revoked *while* a media producer was reading it. The bridge validates
every emitted multipart JPEG header, byte length, JPEG markers and the
256 KiB limit, and permits at most 120 parts per session regardless of
producer behavior. It fails closed on authorization callback errors,
malformed follow-up frames, and excess frames. The underlying producer
still performs its independent checks; these new boundary gates are
defense in depth, not replacements for the native decoder checks.

The synthetic tests include producer stubs intentionally lacking
their own authorization/JPEG guards, revocation during a blocked
follow-up read, over-limit JPEG payloads, and a genuine local HTTP
TestClient transport where an invalid second part is discarded after
the first valid frame. The bridge can no longer change HTTP status
after it has started streaming; a later invalid part **terminates**
that stream with the normal guarded decoder cleanup. No real Hikvision
decode or browser rendering was performed.

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

## 30 Oct 2026 — opt-in Member 1 loopback bridge (local operator demo)

**New:** `services/edge-vision/sentinel_edge/local_media_bridge.py`.
This is a separate, isolated **Member 1 local research-only** adapter, **not**
Member 2's production API, not internet streaming, and not an authenticated
remote-caregiver service. It is disabled unless all operator settings below
are provided. It must not be enabled without site owner and affected-person
privacy review and a genuine, current HMAC-signed camera approval.

The bridge serves only `127.0.0.1:8001`, has no alternate bind argument,
refuses non-loopback clients, and authenticates an operator with a **different
random secret** from the Hikvision viewer password. It sets a SameSite=Strict,
HttpOnly session cookie, checks the browser Origin for all state-changing
requests, limits login retries and grants at most one 25-second, camera-scoped
stream **globally on the local worker**. Up to eight simultaneous operator
login cookies may exist, but the camera decoder has only one active
slot. Deletion, logout and timeout invalidate the in-memory session.
Native streaming slots remain reserved until the decoder has actually
released its resources. The bridge invokes the existing Member 1 Edge JPEG
producer with per-frame signed privacy and session checks.

**Genuine review and private configuration required:** a verified camera-
specific signed approval file, matching HMAC signing key held in the
**local process** environment, operator-chosen high-entropy 16+ character
password, and a **dedicated read-only** Hikvision account used only inside a
private RTSP URL environment variable. Never enter camera passwords in the
Dashboard or chat, Git, a shared .env file, process args or screenshots.
PowerShell's process environment contains secrets for the process lifetime;
close the terminal after use and protect it as an interactive operator session.

Install optional tooling (on the same Windows machine where the Edge worker
and camera Tailscale route exist):

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m pip install -e ".[dev,media,pyav,jpeg]"
```

After the owner has *truthfully completed and reviewed* the private unsigned
policy, sign it with `sentinel_edge.privacy_approval_operator` per
`docs/security/SIGNED_CAMERA_APPROVAL_OPERATOR_WORKFLOW.md`. Do not make up
notice/impact/rights review references. Prepare the following settings in an
interactive **private** PowerShell process (the placeholders MUST be supplied
securely; these are **environment variable names**, not values):

```powershell
$env:VIIL_BRIDGE_ENABLED = '1'
$env:VIIL_BRIDGE_CAMERA_ID = 'staged-camera-01'
$env:VIIL_BRIDGE_RTSP_ENV = 'VIIL_CAMERA_RTSP'
$env:VIIL_BRIDGE_APPROVAL_PATH = "$env:USERPROFILE\VIIL-Private\approved-privacy.json"
# Set VIIL_PRIVACY_APPROVAL_KEY to the secret used to sign the real file.
# Set VIIL_BRIDGE_OPERATOR_PASSWORD to a NEW strong operator-only password.
# Set VIIL_CAMERA_RTSP to the dedicated camera read-only viewer RTSP URL.
# Set these three secrets securely in the interactive process, not in Git.
.\.venv\Scripts\python.exe -m sentinel_edge.local_media_bridge
```

Separately, start the dashboard in another local PowerShell terminal:

```powershell
cd D:\VIIL-Sentinel\apps\dashboard
$env:VIIL_LOCAL_CAMERA_BRIDGE = '1'
npm run dev
```

Visit `http://127.0.0.1:5173` and open **Integration Center**.
Select local operator sign-in, enter the **operator password, not the
Hikvision camera password**, and refresh. Only a genuinely signed approved
camera appears with `privacy: approved` and `health: unknown`.
`UNKNOWN` deliberately does not claim decoded frames. The owner may click
**Open live preview** to try the supervised stream. Actual media can only be
shown after the 12-frame Edge preflight. The browser never receives an
RTSP URL. A missing policy reports unverified and cannot open.

**30 Oct safety improvement:** the GET `.../mjpeg` endpoint now waits for the
Edge's required **12/12 real decoded-frame preflight AND the first validated
JPEG part** *before* returning HTTP 200. If the camera fails to decode,
privacy is revoked, there are no JPEGs, or the first bytes are malformed,
the endpoint fails closed with a redacted 503/403 instead of a fake-success
`200 multipart`. Opening a camera session (201) alone is never a video success.
The UI stays in `WAITING FOR FIRST FRAME` until a browser image event and
auto-stops on an error or 25-second expiration. Offline tests cover both
11-frame failure and 13-frame success using **synthetic capture**, plus
empty/malformed frames, exception redaction, capacity and revocation.
A synthetic HTTP 200 test does NOT establish a real Hikvision 200.

**30 Oct browser stream lifecycle hardening:** when a user explicitly opens
the camera, Dashboard waits for an actual browser image event, bounded to
**20 seconds** and always shorter than the server's 25-second session
deadline. If the event never arrives, the browser detaches the image and
sends a best-effort DELETE to revoke the local session, displaying a
redacted, actionable timeout error. A missing browser image event does NOT
prove that the Edge had no decoded frames; multipart MJPEG image events
may vary by browser. On genuine image load the pending timeout is cancelled.
Late browser `onLoad`/`onError` events after Stop, tab hide, permission
loss or session replacement do not overwrite the intentionally closed UI.
The server still independently enforces signed approval and expiry.

New offline concurrency regressions verify that DELETE and logout
**while decoder preflight is in flight** revoke the session and block
another camera decoder until the first worker has finished unwinding;
the session slot is then reusable. These tests exercise synthetic
captures, not actual Hikvision or browser networking.

### Fast-fail RTSP and first-frame budget (30 Oct 2026)

The Member 1 local PyAV RTSP adapter now requests a **4-second connection/
header timeout and 2-second per-read timeout** (FFmpeg `rw_timeout`:
2,000,000 microseconds). The existing Edge MJPEG producer additionally
requires its **first validated JPEG** within an elapsed-time budget of
10 seconds (or shorter if the caller's session duration is shorter).
It checks that budget after the native open, after each of the 12 decoded
preflight reads, after the next frame read and after JPEG encoding. A
too-slow attempt fails closed: no multipart HTTP 200, no image emitted;
the native capture is released and the session slot becomes reusable.

These controls improve typical fail-fast behavior, **not** a hard 10-second
OS-level termination guarantee. PyAV/FFmpeg timeouts apply to individual
network operations; a native codec, file conversion, OS driver or socket
may exceed the aggregate budget before control returns to Python.
Do not claim a guaranteed RTSP timeout or live camera reliability without
a genuinely approved hardware test. Operator review of private camera
and site policy is still mandatory before any real decoding.

See PyAV timeout API: https://pyav.basswood.io/docs/13.1/api/_globals.html

### Authenticated first-frame transport diagnostics (30 Oct 2026)

Member 1's local bridge exposes an additional **optional, read-only** route
`GET /api/v1/cameras/{camera_id}/preview-sessions/{session_id}/status`
only to the owner of a fresh, approved preview session. No additional
camera open/RTSP request is made by this status call. The bounded JSON
contains the pseudonymous camera and session IDs, `edge_preflight_started`,
`edge_first_jpeg_verified`, and
`browser_image_display_verified: false`. The Edge JPEG flag becomes true
**only after** 12 decoded BGR preflight frames and one size-validated JPEG
from the existing secure Edge producer. RTSP OPTIONS, a session POST or
the presence of PyAV never sets this flag.

The Dashboard polls this *local optional* route only while a preview is
active and shows `EDGE JPEG VERIFIED · WAITING FOR BROWSER` when that
flag is true but the browser has not confirmed an image event. The
`BROWSER FRAME RECEIVED · SUPERVISED` label only appears after the
browser's own `onLoad` event. Both are session-scoped, short-lived,
and are removed on Stop, logout, expiry, policy revocation or failed
requests. A status 403/404 never produces a positive frame claim; Member 2
production backend does **not** need this optional local route.

Neither local status flag alone proves real-world reliability or a
working physical Hikvision feed. The status returns **no** frames, camera
IP/RTSP URL, password, HMAC key, source configuration or native errors.
Tests use synthetic JPEGs and mock decoders only.

### Local camera readiness diagnostics (30 Oct 2026)

After signing into the opt-in loopback operator bridge, Dashboard Integration
Center now shows a metadata-only **Local Edge camera prerequisites** panel.
Its authenticated `GET /api/v1/operator/camera-readiness` endpoint checks
four independently useful prerequisites: the camera-scoped HMAC signed
approval is currently valid, a private-IP RTSP environment value is present
and passes validation, PyAV is installed, and OpenCV's JPEG encoder package
is installed. This GET endpoint **does not open the camera, use credentials,
decode a frame, save an image, or call Meta AI**. It never returns raw RTSP
values, credentials, HMAC keys, URLs or video bytes. Cross-site requests and
unauthenticated operators are denied. Missing Media Bridge/Member 2 API causes
the panel to disappear rather than show fabricated green statuses.

`eligible_for_supervised_trial` means the four checks pass; it does **not**
prove successful RTSP authentication, actual camera connectivity, video decode
or actual permission of any people on camera. `real_camera_frame_verified`
remains `false` from this diagnostic by design. No real camera may be
claimed online until the separate signed-policy supervised decode succeeds.

For a fresh Windows installation, use
`python -m pip install -e ".[dev,media,pyav,jpeg]"` in Edge's environment.
The optional `jpeg` extra explicitly supplies `opencv-python` for JPEG
encoding. Keep third-party packages pinned and validate licensing/usage for
the hackathon, and avoid installing both `opencv-python` and
`opencv-python-headless` in one environment unless separately verified.

**This is NOT verified Hikvision playback:** the local operator's private
`approved-privacy.json` was absent at the last inspection, camera credentials
were not tested and real decoded frames remain at zero. The new API tests use
synthetic JPEG bytes only. Member 2's proper authenticated multi-user Backend
Media Session remains a separate integration workstream.

### Private unsigned approval checklist in Dashboard

Set `VIIL_BRIDGE_UNSIGNED_DRAFT_PATH` in the private Windows process
environment to the **absolute path** of the existing unsigned draft
(e.g. `$env:USERPROFILE\\VIIL-Private\\unsigned-privacy.json`).
This is optional and does not enable a camera or require a signing key.
The separately authenticated, loopback-only
`GET /api/v1/operator/approval-checklist` reads the draft with the
existing offline reviewer. It sends **only allowlisted missing field names**
to the browser, never the draft's contents, document references, legal
basis values, camera IP, file path or secret. If missing/invalid, the
dashboard shows the draft as unavailable instead of leaking exception
details. If structurally complete, it still displays an explicit notice
that actual human site authorization, privacy review and genuine signed
approval are outstanding. It never signs, changes an approval flag,
connects to a camera, certifies compliance or grants access.

This operator-only panel appears next to the camera readiness diagnostics
and disappears if its backend is unavailable, authentication is revoked,
or the report is stale. The only way to resolve a flagged issue is for
the responsible human reviewer to complete and document that requirement
**truthfully** outside the repository. Do not set approval flags to true
just to make the UI green. Review the offline instructions at
`docs/security/SIGNED_CAMERA_APPROVAL_OPERATOR_WORKFLOW.md`.

### 30 Oct: HTTP disconnect-safe decoder lifecycle

The loopback `GET .../mjpeg` now wraps the authorized Edge generator in
`RevocableMediaResponse`. Starlette runs synchronous MJPEG reads in a
worker thread; when a browser disconnects or the HTTP send fails, the
response must **revoke the viewer session and close the native generator**.
The new response uses a cancellation-shielded `finally` block, coordinates
`next()` and `close()` with one lock, and frees the camera-wide slot only
**after** the generator has closed. A connection that never starts delivering
its first part must also release its pending global slot.

The backend's signed privacy verification, per-frame viewer authorization,
25-second session TTL, 12/12 decode preflight and no-secret/no-storage
policies remain unchanged. Synthetic tests cover browser disconnect before
headers or during frame delivery, normal EOF, simultaneous decoder read and
generator close, idempotent close and opening another stream after normal
completion. A failed/disconnected or revoked stream must not leave the
camera slot occupied. **These tests do not show real Hikvision frames.**

Security warning: Only use this optional gateway on a controlled Windows
desktop. Cookie `Secure=false` intentionally supports HTTP loopback only;
do not run Vite with public `--host`, port-forward the gateway, or expose
either port to the internet. For production, Member 2 must implement TLS,
auth/RBAC, audited policy and session management, and its own deployment review.
