# VIIL-Sentinel: Local operator launcher for an authorized Hikvision camera

This launcher is a **bounded, non-clinical staged demo**. It cannot grant itself access to a camera and does not replace written consent, privacy notices, site permission or legal review.

## What is automated

`scripts/start-hikvision-staged.ps1` runs on the **Windows Edge host**, accepts one operator-approved RFC1918 camera IP, uses the local MediaPipe virtual environment and private pose asset, and:

1. Supports a camera-credential-free `-PreflightOnly` check: private IPv4, Windows route, model asset and signed policy readiness. If the policy file and verification key are already available in the local process environment, it also runs the real offline HMAC/date/camera-scope policy verifier (no camera/network access); otherwise it explicitly reports that verification was not attempted. The check prints booleans only, not approval contents or secrets.
2. Before capture, requires a private **signed** approval JSON matching `-SourceId`, verifies its HMAC and dates through the application privacy gate, and requires an operator-approved read-only camera account.
3. Prompts locally for the camera password and for the existing signing key if not already configured; neither value is passed on the command line nor intentionally written to disk.
4. Sets temporary `VIIL_HIK_LAN_SUB` (Hikvision channel 102) and `VIIL_HIK_LAN_MAIN` (channel 101) only in the launcher process environment.
5. Runs at most two separate 12-frame, no-recording RTSP health probes (substream, then mainstream if needed). The PowerShell 5.1 native-command helper intentionally preserves a failed decoder's exit status even if FFmpeg writes to stderr, so the alternate stream can be tried. If neither decodes, returns nonzero and never starts the AI. **If only the mainstream probe passes, Edge starts with that verified mainstream as primary**, keeping the substream as the bounded retry fallback; it does not needlessly reopen the already-failed substream first.
6. With `-RunEdge`, runs a bounded metadata-only Edge experiment with **at most 120 frames or 60 seconds per attempt** and at most two attempts (one retry), each with fresh model/capture state. These limits are not a single global 120-frame/60-second budget. The RTSP inference path rechecks frame metadata (nonempty HxWx3 BGR uint8) before MediaPipe; an unusable frame is treated as a camera interruption eligible for the same-camera bounded fallback, without emitting a candidate from the corrupt frame. The supervised launcher now shows only a strictly allowlisted, **numeric** `EDGE_SAFE_RTSP_METRICS` summary per reported Edge epoch: frames processed, unavailable Pose frames, unconfirmed candidate count, cycle throughput (FPS), cycle P95 (ms), sampled RSS (MiB), and interruption status. These are *research pipeline cycle measures*, not camera FPS, end-to-end network latency, or accuracy. **All raw native stderr and Edge stdout are suppressed** in this supervised mode, including event JSONL; use the underlying approved runner with explicitly reviewed metadata-output handling for Member 2 integration. Native error messages may contain credentials; the output filter parses the versioned profile and reconstructs only validated numeric/boolean fields. No media, URL, source ID, raw profile, or credential is displayed or stored.
7. With **`-ShowPreview`**, opens an explicit operator-only OpenCV window on the Windows desktop, shows live decoded BGR frames (max 960px), responds to `Q` / `Esc`, and falls back to the other verified same-camera channel if the stream breaks. The preview is bounded (default max 450 frames / 30 seconds, configurable 1–900 frames and 1–120 seconds), re-verifies the real signed policy before and after every read and before display, saves **no** frames and sends **no** video to a backend, browser, cloud or other machine. Preview and Edge inference are separate, mutually exclusive modes.
   The local preview now overlays an in-memory `LOCAL ONLY` status line with frame number, displayed frame dimensions and an approximate **preview display FPS** once warmed up. This count is measured from the on-screen presentation loop, **not** camera-configured FPS, RTSP transport latency or Edge AI inference speed. The overlay contains no source identifier, camera address, credential, face identifier, person trace or alert result. Failure to draw the optional status text does not interrupt a valid authorized camera preview.
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

### One-command camera readiness (no video or camera credentials)

Use the operator readiness command to combine one read-only credential-free RTSP
OPTIONS probe with an optional **existing, genuine** signed privacy approval
check. This tool never requests DESCRIBE/SETUP/PLAY, authenticates to the camera,
decodes frames, records footage, checks AI inference, or authorizes a site:

```powershell
cd D:\\VIIL-Sentinel\\services\\edge-vision
.\\.venv\\Scripts\\python.exe -m sentinel_edge.hikvision_operator_readiness `
  --camera-ip 192.168.10.204
```

It emits only allowlisted status and next-step codes, never the camera IP,
approval file path, key, URL, user or original headers. Without a signed
approval, it always marks `eligible_for_separate_supervised_decode_trial=false`,
even if RTSP OPTIONS responds 200. The tool deliberately exits 2 while blocked.
A signed approval can be checked **only after the authorized site/privacy review**
and without prompting for or generating the actual HMAC signing key:

```powershell
.\\.venv\\Scripts\\python.exe -m sentinel_edge.hikvision_operator_readiness `
  --camera-ip 192.168.10.204 `
  --privacy-approval 'C:\\PrivateConfig\\approved-privacy.json' `
  --source-id staged-camera-01
```

The second command requires the matching existing private
`VIIL_PRIVACY_APPROVAL_KEY` in the local process environment. A verified
policy plus OPTIONS 200/401 means only that an operator may attempt the
**separate, gated 12-frame decode health test** with local read-only camera
credentials. It does not prove those credentials, show live footage or establish
stable camera FPS, real-world fall accuracy or legal compliance. A site-specific
permission and relevant consent/notice procedures must be complete first.

### Verify Hikvision codec configuration without video (read-only ISAPI)

The authorized camera administrator can inspect exactly the **stream-configuration metadata** (not image/video data or camera settings writes) from channels **101** and **102**:

```powershell
powershell -NoProfile -File D:\VIIL-Sentinel\scripts\inspect-hikvision-streams.ps1 `
  -CameraIp 192.168.10.204
```

Enter the **authorized read-only Hikvision camera account** and masked password locally. The helper sends GET-only Hikvision ISAPI requests using HTTP Digest (which can require one 401 challenge/retry per endpoint), with redirects and external proxies disabled, a max 64-KiB XML response per channel, and a 3-second per-request timeout. Credentials are kept in temporary process environment variables and restored on exit; neither credentials, private camera IP, original XML, serial number nor person/video data are printed or saved. An authorized metadata inspection is **not video consent** and does **not** satisfy the Signed Privacy Approval required to view/process footage.

**Real camera configuration verified on 29 October 2026 (read-only ISAPI):** model `DS-2DE2C400MWG-4GUHK`, firmware `V5.8.34 build 260403`; Main `101` = H.264, 2560×1440, 15 configured FPS, about 3994 Kbps; Sub `102` = H.264, 768×432, 10 configured FPS, about 512 Kbps. Values are **configuration settings**, not observed decode rate or AI FPS. The command re-reads the current settings and emits only allowlisted codec/resolution/FPS/bitrate values. It prefers substream `102` for H.264/H.265 Edge experiments; with current H.264 configuration **HTTP-MJPEG cannot be presumed to work** and no codec change should be made automatically. RTSP OPTIONS 200 and ISAPI GET 200 still do not prove live frames decoded.

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

### Alternative transport: HTTP Digest / MJPEG (substream 102)

Some Hikvision IPC cameras can send a live MJPEG multipart stream over HTTP at `/ISAPI/Streaming/channels/102/httpPreview`. This feature is **model/firmware dependent**, and the camera must already have **Substream video encoding MJPEG** configured by an authorized camera administrator. **The launcher never changes camera settings.** A response of `401 Digest` confirms that HTTP authentication is requested; it does **not** establish that any MJPEG frames can be decoded.

To try the independent transport from an interactive Windows desktop after obtaining the genuine site-approved signed privacy policy:

```powershell
$approval = Read-Host "Genuine signed approval path"
$cameraId = Read-Host "Approved camera source ID"
powershell -NoProfile -File D:\VIIL-Sentinel\scripts\start-hikvision-staged.ps1 `
  -CameraIp 192.168.10.204 `
  -PrivacyApproval $approval -SourceId $cameraId `
  -ShowPreview -PreviewDecoder http-mjpeg -PreviewSeconds 30
```

The script verifies the signed policy **before asking for camera credentials**, then prompts locally for a read-only camera account. It uses HTTP Digest authentication and a strictly private camera URL on HTTP port 80 (or explicitly `-HttpPort 8080`). It performs a **12 decoded-frame in-memory health check** before showing a bounded local video window. HTTP redirects are disabled, the system proxy is bypassed, JPEG buffer size is capped at 2 MiB per frame and the response is closed on all outcomes. No video or credentials are written to files, printed or sent to a dashboard. Because HTTP without TLS is unencrypted, use only a trusted private segment or secure overlay (for example, the existing Tailscale route), and restrict access to read-only accounts. If unsupported, leave existing RTSP/PyAV path in place; **do not automatically change the camera codec**, as other camera viewers may depend on H.264/H.265.

HTTP-MJPEG also supports **bounded Edge AI experiments** via the same signed-policy workflow. Use a genuine reviewed approval and run:

```powershell
$approval = Read-Host 'Genuine signed approval path'
$cameraId = Read-Host 'Approved camera source ID'
powershell -NoProfile -File D:\VIIL-Sentinel\scripts\start-hikvision-staged.ps1 `
  -CameraIp 192.168.10.204 `
  -PrivacyApproval $approval -SourceId $cameraId `
  -RunEdge -EdgeDecoder http-mjpeg
```

This first probes **12/12 BGR decoded frames** through HTTP Digest MJPEG, then runs no more than **120 AI frames or 60 seconds**, whichever occurs first. All acquisition, every frame and the output path remain protected by the existing signed-policy gate. It is a **separate HTTP fallback input**, not a mixed automatic RTSP-to-HTTP retry; there is no automatic restart, no saved raw video/pose trace and no browser/dashboard stream. The launcher suppresses raw Edge/stdout/stderr for credential safety and reports only the bounded experiment result; it does not claim accuracy or latency without measurements. The standalone Edge runner supports `--source http-mjpeg --http-mjpeg-env VIIL_HIK_HTTP_URL --max-frames 120` with dedicated read-only HTTP Digest credentials in process-only environment variables, plus `--privacy-approval`, `--candidate-format v1` and `--confirm-consent`.

Do not claim a successful real-camera decode without 12/12 readable frames. This follows Hikvision's documented HTTP MJPEG stream constraints: https://www.hikvision.com/content/dam/hikvision/en/support/how-to/how-to-document/network-cameras/How-to-Get-IPC-MJPEG-Stream-via-HTTP-Commands.pdf

To **show the live video in an actual local window** instead of running AI, execute from an **interactive Windows desktop PowerShell session** after the same genuine signed approval is installed:

```powershell
$approval = Read-Host 'Genuine signed approval file path'
$cameraId = Read-Host 'Approved pseudonymous camera ID'
powershell -NoProfile -File D:\VIIL-Sentinel\scripts\start-hikvision-staged.ps1 `
  -CameraIp 192.168.10.204 `
  -PrivacyApproval $approval -SourceId $cameraId `
  -ShowPreview -PreviewDecoder pyav -PreviewSeconds 30 -PreviewFrames 450
```

For **authorized Edge AI inference using PyAV**, the operator can now select a decoder explicitly:

```powershell
$approval = Read-Host 'Genuine signed approval file path'
$cameraId = Read-Host 'Approved pseudonymous camera ID'
powershell -NoProfile -File D:\VIIL-Sentinel\scripts\start-hikvision-staged.ps1 `
  -CameraIp 192.168.10.204 `
  -PrivacyApproval $approval -SourceId $cameraId `
  -RunEdge -EdgeDecoder pyav
```

The launcher probes up to 12 decoded frames with **the selected Edge decoder**, first channel 102 then channel 101 if necessary. Only after the verified signed policy, real camera credentials, and successful decoder health does it start **bounded metadata-only Edge inference** with `--rtsp-decoder pyav`. The retry/fallback remains the same-camera, per-epoch fresh model/temporal state workflow, and cannot run without valid authorization. `-EdgeDecoder opencv` (default) preserves the original behavior. The Edge inference process emits only unconfirmed fall-candidate metadata and diagnostic counters, **not** frames or a browser preview; run `-ShowPreview` separately for video. The operator's password must be entered only in the local masked prompt and never pasted into scripts, logs, Git, or the terminal command line.

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
