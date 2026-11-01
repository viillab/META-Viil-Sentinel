# VIIL-Sentinel — Laptop Webcam Demo (Member 1)

**Status (1 November 2026): Browser-local video and optional real MediaPipe Pose inference are implemented; the temporal FALL CANDIDATE is an uncalibrated, non-clinical heuristic requiring human review, not production fall detection.**

Use the **Integrated Camera** of the developer's laptop for the
initial visual demonstration. The webcam mode is intentionally separate
from the production **Hikvision RTSP / HMAC-signed privacy approval**
pipeline. It cannot alter, unlock, fake or replace that protected
network-camera authorization.

## Start the laptop preview and optional local Pose inference

From the user's Windows laptop:

```powershell
cd D:\VIIL-Sentinel\apps\dashboard
npm ci
npm run dev
```

In **Microsoft Edge or Chrome on the same laptop** open
[http://127.0.0.1:5173](http://127.0.0.1:5173). Navigate to
**Integration Center → Laptop camera preview → Start laptop webcam demo**.

1. For local pose inference, choose **Select local MediaPipe .task model**
   and select **D:\\VIIL-Sentinel\\models\\pose_landmarker_lite.task**
   from your own laptop. This explicit browser File selection reads the
   model into memory only; the file is **not uploaded or committed**.
   Without a model, the ordinary local Webcam Preview still works.
2. Click **Start laptop webcam demo** and **Allow** in the browser
   permission prompt. No camera permission is requested before this
   click. The **same browser MediaStream** owns both the live video and
   MediaPipe frame inference, with no second OS device handle.
3. Watch the local green **torso landmark overlay**, Pose status,
   and **Session-only candidate count**. A status of
   **POSSIBLE FALL CANDIDATE · HUMAN REVIEW REQUIRED** is strictly
   unconfirmed. More than one person, missing visibility, or a large
   frame gap causes a fail-closed abstention; **unknown is not safe**.
   A possible-candidate notice remains visible for only 8 seconds, then
   expires. Its counter is session-only and does not confirm a fall.
   The operator-only panel now shows rolling processed FPS, inference
   p50/p95 milliseconds and reliable single-person pose coverage over a
   maximum 4-second/32-sample window. These are local runtime/quality
   diagnostics, **not camera source FPS, model recall, or fall accuracy**.
4. Click **Stop webcam** when done. Video, active model and pose
   history are discarded. Video also auto-stops after **60 seconds**,
   when the tab is hidden, page unloaded, or capture track ends.
   In Pose mode, verified new rendered frames are tracked by the
   browser `requestVideoFrameCallback` API (not `video.currentTime`,
   which may advance despite a frozen webcam). A 3.5-second frame stall
   stops capture and displays a redacted error. Browsers without this
   API fail closed in Pose mode; preview-only mode remains available.
   No alert is sent. Model selection/replacement is disabled during live
   preview and pending capture, and starting a webcam is disabled until
   local model loading completes. Replacing a stopped model closes the
   old instance and clears the former session metrics.
5. After a session ends, read **Local webcam technical smoke report**:
   stop reason, bounded monotonic session duration, counts of freshly
   presented frames and analyzed frames, reliable single-person poses,
   unconfirmed candidates, and the *last* 4-second inference p95.
   This ephemeral browser-only summary has status
   `OPERATOR_REVIEW_REQUIRED`, never hardware acceptance or model
   correctness. It contains no camera identity, video, pose coordinates,
   model path, API calls, disk exports, or timestamps. Dismiss the report
   or start a new session to clear it.
6. A real camera acceptance still requires a human operator to confirm
   that the visible preview moves, the torso overlay tracks a consenting
   subject correctly, a 60-second session produces nonzero actual frames,
   and the camera LED/device tracks stop after Stop, tab-hide or timeout.
   The report alone is **not** evidence that actual camera hardware ran
   unless it is seen during an operator-approved physical test.

The webcam feature uses `navigator.mediaDevices.getUserMedia`
with **audio disabled**, 640×360 preferred at 15fps (maximum 24fps).
The optional MediaPipe `@mediapipe/tasks-vision@1.2.0` is dynamically
loaded **only when the operator selects the private .task**. Four WASM
runtime files are copied from the npm package to a **gitignored
same-origin** `/vendor/mediapipe/wasm` location by `predev` and
`prebuild` npm scripts. No model binary is copied into the public
assets. The app does not send video, pose landmarks, or candidate data
to the backend, Meta/cloud, persistent storage, or caregivers. The
WASM/vendor SDK may have its own usage telemetry/privacy notice; this
developer demo does **not** claim a full offline network guarantee.
Only short-lived numeric landmarks and candidate counts exist in
browser memory; the green canvas draws joints, **not saved image
pixels**. The pre-existing Dashboard may request unrelated metadata
as before.

This feature refuses non-loopback hosts, missing camera support or
insecure browser contexts. Use `localhost` or `127.0.0.1` on the
**same Windows machine**; a phone or remote machine cannot view
the laptop webcam from a remote Dashboard URL.

## If the camera is not visible

- Confirm Windows **Settings → Privacy & security → Camera** permits
  camera access for desktop apps and that Edge/Chrome has permission.
- Close Teams/Zoom/other apps that may have exclusive control of the camera.
- Restart the **local Dashboard** and press Start again. No need to
  configure RTSP, Hikvision camera credentials, Vite API proxy,
  signed Hikvision policy, or Member 2 Backend for this visual demo.
- If the camera prompt is denied, the UI shows an actionable redacted
  error. The feature never retries silently.

## Experimental browser candidate logic and separate Python Edge workflow

The JavaScript `LocalFallCandidateHeuristic` mirrors the Python
temporal detector's **thresholds**, but is independently implemented
for **local research demonstration**, not a validated exported model:
upright torso <=32°, then normalized hip descent >=0.13, torso
horizontal >=56° for >=450ms, with 1600ms history, 700ms max gap,
4000ms cooldown, and min 0.55 landmark visibility. It runs on a
single unambiguous detected pose, at most 5 inference cycles/second,
in a browser CPU backend. It is not trained, calibrated or independently
validated. Do not simulate/induce dangerous falls to test it; use
safe staged movements and synthetic fixtures.

The separate Member 1 **Python Edge runner** also supports local
USB index 0 and a local MediaPipe Pose Landmarker task model. The
Windows host previously reported an **Integrated Camera** and a
nonempty `D:\VIIL-Sentinel\models\pose_landmarker_lite.task`.
Offline `viil-edge-doctor` only verifies software/model file readiness,
**not** camera frames or accuracy.

**Important:** The Python live inference runner is intentionally
**stricter than browser-local preview**. It requires a genuinely
reviewed, camera-scoped signed privacy approval and explicit consent
before reading real video, even from a USB webcam. This guide does not
bypass that gate or generate/sign a false approval. After obtaining
proper approval for the user's own `staged-camera-01` webcam, stop
the browser preview (to avoid two processes competing for the camera),
then run from `services\edge-vision`:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.runner `
  --source 0 `
  --source-id staged-camera-01 `
  --model D:\VIIL-Sentinel\models\pose_landmarker_lite.task `
  --privacy-approval C:\path\to\genuine-signed-webcam-approval.json `
  --candidate-format v1 --confirm-consent --max-frames 300
```

Candidate output is **unconfirmed research metadata on local stdout**,
not human-confirmed fall events, a live Dashboard stream, automated
caregiver alerts, or verified Meta provider inference. Keep real
people's image and derived pose data private and do not transmit it to
Member 2 before that separate authenticated ingestion is ready.

## Testing evidence and remaining work

Dashboard Node contract tests cover secure-origin allowlisting,
actual presented-video-frame freshness, bounded numeric runtime
metrics (processed FPS, inference p50/p95, pose coverage), model lifecycle
replacement guards, camera-frame stall fail-closed
behavior and temporary candidate notice,
camera stop, non-uploads, local model validation, single/multi-person
pose quality, synthetic upright→horizontal hold, safe sitting
non-trigger, occlusion, time gaps, cooldown and source inspection.
TypeScript/Vite Build validates package bundling and local WASM asset
copy. **A human operator must still explicitly Allow webcam access
and confirm actual visible Pose overlay/inference on physical hardware**.
Device Manager "OK", a green build, and synthetic tests do not prove
the browser decoded frames or that the fall heuristic is accurate.

The current integration is **one browser-owned webcam stream with
optional local MediaPipe Pose**. It does not integrate with the
Member 2 Incident API, production Edge Candidate v1 signature
or real Meta provider. No real caregiver notification is sent.
