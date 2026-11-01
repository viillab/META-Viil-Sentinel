# VIIL-Sentinel — Laptop Webcam Demo (Member 1)

**Status (1 November 2026): Browser-local preview implemented; AI fall classification is NOT connected to this preview.**

Use the **Integrated Camera** of the developer's laptop for the
initial visual demonstration. The webcam mode is intentionally separate
from the production **Hikvision RTSP / HMAC-signed privacy approval**
pipeline. It cannot alter, unlock, fake or replace that protected
network-camera authorization.

## Start the laptop preview

From the user's Windows laptop:

```powershell
cd D:\VIIL-Sentinel\apps\dashboard
npm ci
npm run dev
```

In **Microsoft Edge or Chrome on the same laptop** open
[http://127.0.0.1:5173](http://127.0.0.1:5173). Navigate to
**Integration Center → Laptop camera preview → Start laptop webcam demo**.

1. Click **Start laptop webcam demo** and **Allow** in the browser's
   camera permission prompt. No camera permission is requested before
   this click.
2. Preview the laptop's live image locally. The UI explicitly reports
   **AI Fall Detection: NOT CONNECTED**, **Caregiver alerts: DISABLED**
   and a **LIVE · BROWSER LOCAL · NOT AI ANALYZED** watermark.
3. Click **Stop webcam** when done. It also automatically stops after
   **60 seconds**, when the tab is hidden, the page is unloaded, or
   the camera track ends/disconnects.

The webcam feature uses `navigator.mediaDevices.getUserMedia`
with **audio disabled**, 640×360 preferred video at 15fps and max
24fps, direct `<video srcObject>` playback. There is **no WebSocket,
fetch, upload, canvas extraction, MediaRecorder, frame recording,
snapshot, local file, cloud request or backend API call** in the webcam
component. It does not infer pose, fall likelihood, medical status or
real notifications. Only the page's local JavaScript owns the
MediaStream; the existing Dashboard/backend may still load unrelated
metadata as before.

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

## Real local fall-candidate inference is a separate workflow

The existing Member 1 Python Edge runner supports local USB camera
index 0 and a local MediaPipe Pose Landmarker model. The connected
Windows development machine currently reports an **Integrated Camera**
device and has a nonempty local
`D:\VIIL-Sentinel\models\pose_landmarker_lite.task` asset.
The offline `viil-edge-doctor` probe checks software/model file
availability, **not** camera frame decoding or fall accuracy.

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

Dashboard Node contract tests include local secure-context allowlisting,
video-only constraints, stop-all-tracks, late permission safety
conditions in code review, redacted errors and no recording/API
transport references. The Dashboard TypeScript/Vite build is a
static integration gate. **Opening the real camera and verifying
visible frames in a human-operated browser remains a manual
acceptance test**; device-manager "OK" alone is not proof of actual
successful frames.

A future single-capture laptop **webcam + MediaPipe live inference
overlay** should run pose processing and video from the same local
capture owner, never open the webcam twice or pretend the browser
preview alone is fall detection. That future integration must preserve
explicit consent, short-lived sessions, local-only processing and
no automatic medical/emergency actions.
