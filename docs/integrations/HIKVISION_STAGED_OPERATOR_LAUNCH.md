# VIIL-Sentinel: Local operator launcher for an authorized Hikvision camera

This launcher is a **bounded, non-clinical staged demo**. It cannot grant itself access to a camera and does not replace written consent, privacy notices, site permission or legal review.

## What is automated

`scripts/start-hikvision-staged.ps1` runs on the **Windows Edge host**, accepts one operator-approved RFC1918 camera IP, uses the local MediaPipe virtual environment and private pose asset, and:

1. Supports a camera-credential-free `-PreflightOnly` check: private IPv4, Windows route, model asset and signed policy readiness. If the policy file and verification key are already available in the local process environment, it also runs the real offline HMAC/date/camera-scope policy verifier (no camera/network access); otherwise it explicitly reports that verification was not attempted. The check prints booleans only, not approval contents or secrets.
2. Before capture, requires a private **signed** approval JSON matching `-SourceId`, verifies its HMAC and dates through the application privacy gate, and requires an operator-approved read-only camera account.
3. Prompts locally for the camera password and for the existing signing key if not already configured; neither value is passed on the command line nor intentionally written to disk.
4. Sets temporary `VIIL_HIK_LAN_SUB` (Hikvision channel 102) and `VIIL_HIK_LAN_MAIN` (channel 101) only in the launcher process environment.
5. Runs at most two separate 12-frame, no-recording RTSP health probes (substream, then mainstream if needed). The PowerShell 5.1 native-command helper intentionally preserves a failed decoder's exit status even if FFmpeg writes to stderr, so the alternate stream can be tried. If neither decodes, returns nonzero and never starts the AI. **If only the mainstream probe passes, Edge starts with that verified mainstream as primary**, keeping the substream as the bounded retry fallback; it does not needlessly reopen the already-failed substream first.
6. With `-RunEdge`, runs a bounded metadata-only Edge experiment with **at most 120 frames or 60 seconds per attempt** and at most two attempts (one retry), each with fresh model/capture state. These limits are not a single global 120-frame/60-second budget. The RTSP inference path rechecks frame metadata (nonempty HxWx3 BGR uint8) before MediaPipe; an unusable frame is treated as a camera interruption eligible for the same-camera bounded fallback, without emitting a candidate from the corrupt frame.
7. With **`-ShowPreview`**, opens an explicit operator-only OpenCV window on the Windows desktop, shows live decoded BGR frames (max 960px), responds to `Q` / `Esc`, and falls back to the other verified same-camera channel if the stream breaks. The preview is bounded (default max 450 frames / 30 seconds, configurable 1–900 frames and 1–120 seconds), re-verifies the real signed policy before and after every read and before display, saves **no** frames and sends **no** video to a backend, browser, cloud or other machine. Preview and Edge inference are separate, mutually exclusive modes.
8. Restores the previous process environment variables on every exit path. No routing changes, network scans, file recording, API calls, emergency dispatch or dashboard claims.

**Privacy:** Native FFmpeg/OpenCV can emit sensitive diagnostics; the launcher suppresses native stderr in the RTSP probes. Keep the terminal private. The local Python process will briefly hold camera credentials in its environment memory. This is not a secure secret manager and should only be used during supervised lab demos.

## Operator commands (do not paste secrets into chat)

Run these on the approved Windows machine:

```powershell
$cameraIp = Read-Host 'Authorized private camera IP'
powershell -NoProfile -File D:\VIIL-Sentinel\scripts\start-hikvision-staged.ps1 `
  -CameraIp $cameraIp -PreflightOnly
```

**Preflight-only does not open the camera**.

For one authorized RFC1918 camera, a credential-free **protocol-only** OPTIONS probe can distinguish a TCP handshake from an actual RTSP server response, without accessing a stream or frame:

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m sentinel_edge.rtsp_protocol_probe `
  --camera-ip 192.168.10.204 --port 554 --timeout-seconds 3
```

The output deliberately includes only an RTSP status code (e.g. 200 or 401) and safe booleans. **Any RTSP response only verifies that a server answered OPTIONS; it does not authenticate the camera, identify the physical device, validate credentials, grant privacy consent, negotiate a media stream, decode video or prove fall detection.** This sends one socket request, not a network scan. A status 401 means authentication was requested for OPTIONS only; a 200 does not mean protected video will play.

After the site operator has completed a genuine privacy review, signed the policy (see `docs/security/GLOBAL_PRIVACY_SECURITY_BASELINE.md` and `docs/security/SIGNED_CAMERA_APPROVAL_OPERATOR_WORKFLOW.md`) and placed it in a protected folder outside Git:

```powershell
$cameraIp = Read-Host 'Authorized private camera IP'
$approval = Read-Host 'Absolute path to approved signed policy'
$cameraId = Read-Host 'Pseudonymous camera ID authorized by that policy'
powershell -NoProfile -File D:\VIIL-Sentinel\scripts\start-hikvision-staged.ps1 `
  -CameraIp $cameraIp -PrivacyApproval $approval -SourceId $cameraId -RunEdge
```

Before connecting to any real camera, you can test **only the local GUI** (no RTSP credentials, camera capture or approval needed) from an **interactive** Windows desktop PowerShell session:

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m sentinel_edge.live_preview --self-test-gui --duration-seconds 5
```

The window must say **SYNTHETIC / NOT CAMERA VIDEO**, shows a changing frame counter and closes with **Q**, **Esc**, or the window **X**. It cannot prove that a real Hikvision stream is readable or that the current remote shell can display windows on the operator's desktop. It never opens a camera, stores frames or sends media. GUI errors stop the preview rather than needlessly opening an alternate camera stream.

To **show the live video in an actual local window** instead of running AI, execute from an **interactive Windows desktop PowerShell session** after the same genuine signed approval is installed:

```powershell
$approval = Read-Host 'Genuine signed approval file path'
$cameraId = Read-Host 'Approved pseudonymous camera ID'
powershell -NoProfile -File D:\VIIL-Sentinel\scripts\start-hikvision-staged.ps1 `
  -CameraIp 192.168.10.204 `
  -PrivacyApproval $approval -SourceId $cameraId `
  -ShowPreview -PreviewDecoder pyav -PreviewSeconds 30 -PreviewFrames 450
```

The `-PreviewDecoder pyav` option uses PyAV/FFmpeg to decode RTSP-over-TCP frames in memory, following the local POC's decoder approach. It also uses the same decoder for the required 12-frame Health Check; if channel 102 fails, channel 101 is checked before opening the GUI. Install this **optional** backend into the Edge virtual environment with `D:\VIIL-Sentinel\services\edge-vision\.venv\Scripts\python.exe -m pip install -e ".[pyav]"` from `D:\VIIL-Sentinel\services\edge-vision`. Omit `-PreviewDecoder` to use the original OpenCV path. Neither decoder bypasses the genuine signed policy. The supplied POC's direct credential-only capture and disk-based run logs have **not** been imported into the production preview.

The launcher asks for the existing policy signing key and read-only camera credentials **only on the local operator machine**. After its 12-frame health probe succeeds, OpenCV opens a local video window. Press **Q** or **Esc** in that window to stop, or allow the bounded trial to finish. A background terminal/service (including an unattended remote shell) may not have access to the logged-in user's Windows GUI, so start this command in the interactive desktop. This **does not provide a web/Dashboard video feed**: browser streaming would require a separate, authenticated and privacy-reviewed design. Neither the local preview nor its diagnostic JSON confirms AI fall detection.

The script prompts **locally**, with password masking. If direct Wi-Fi routing (rather than an existing authorized Tailscale/VPN route) is a hard requirement, add `-RequireDirectWifi`; it will **refuse to run** unless Windows selects the adapter named `Wi-Fi` for that destination, and it will not alter Windows routing. If your Wi-Fi adapter has been renamed, review the route manually before using this strict option. Route and TCP connectivity alone cannot verify RTSP authentication or decode.

## Necessary operator inputs

- Verified camera IP and read-only credentials, configured by the camera administrator (rotate any previously shared passwords).
- A signed privacy approval specifically listing the pseudonymous `SourceId`, valid dates, human-review requirements, zero frame retention and genuine reviewed notices/site authorization; never generate a fake approval merely to make the test pass.
- Signing secret matching that approval, stored or entered only on the approved local host.
- Local Pose Landmarker model file, from an appropriately licensed verified source.
- Actual authorized staged environment (no unauthorized filming of subjects).

## Interpretation

A successful TCP port 554 handshake is **transport only**, not a login. A successful 12/12 health probe requires 12 nonempty **HxWx3 uint8 BGR** frames; a placeholder, zero-sized image, unexpected channel count or wrong pixel type now causes an interrupted result. That is evidence of some usable frame decoding, **not** proof of recognizable people, stable FPS, pose coverage or fall accuracy. A synthetic model smoke is inference validation on synthetic inputs, not camera validation. The system does not authorize unattended surveillance, medical diagnosis or safety-critical alerts.
