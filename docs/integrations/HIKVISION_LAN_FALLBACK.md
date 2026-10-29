# VIIL-Sentinel — Hikvision Local Wi-Fi RTSP stream fallback (Member 1)

## Scope and safety

**Non-clinical demo only.** This feature alternates *two streams of one approved private Hikvision camera*, not two cameras or Windows network interfaces.

- Preferred low-bandwidth substream: `/Streaming/Channels/102`.
- Alternate mainstream: `/Streaming/Channels/101` of the **same authority, credentials, port and NVR camera channel**.
- Both URLs are read from `VIIL_` environment variables, never passed on the CLI or checked into Git.
- Fallback is enabled only with `--rtsp-retries 1..3`. A failure starts a **new capture, MediaPipe task, pose detector and session-relative clock namespace**. Maximum four attempts; delay 250–5000 ms.
- Privacy denial stops all retries. No display, pose trace, frame recording, artificial fall alert, clinical verdict, or automatic incident dispatch.
- Exhausted fallback returns exit status 2; lack of fall events must **not** be interpreted as safe monitoring.
- If mainstream costs too much bandwidth/CPU, omit `--rtsp-fallback-env` and use bounded same-stream retries instead.

## LAN versus Tailscale (verified 29 Oct 2026)

Workstation Wi-Fi: `192.168.10.248`; camera target: `192.168.10.204`. Windows currently has a `192.168.10.204/32` Tailscale route, so TCP port 554 **succeeded via Tailscale**, with source address `100.114.63.20`. This is NOT proof of direct LAN routing or RTSP decoding.

No automatic route edit, adapter shutdown, Tailscale configuration changes, blanket subnet scan or public RTSP exposure is permitted by this feature. A network operator can independently review interface metrics and selectively remove/adjust the redundant route with a rollback plan, then verify `Test-NetConnection` reports `InterfaceAlias: Wi-Fi`. Merely switching RTSP URLs on the same IP does not change routing.

Run safe targeted diagnostic from repository root:

```powershell
powershell -NoProfile -File .\scripts\check-camera-lan.ps1 -CameraIp 192.168.10.204 -RtspPort 554
```

## Before any real camera decoding

Obtain explicit authorization of people who may appear, a dedicated read-only camera account, and the valid **signed privacy approval** for the `--source-id`. Do not add actual camera URLs, credentials, private frames or approvals to Git. Configure *both* local secrets so only `102` versus `101` differs:

- `VIIL_HIK_LAN_SUB`: substream URL.
- `VIIL_HIK_LAN_MAIN`: same camera's mainstream URL.

Confirm H.264 and RTSP rights on the camera. The validator accepts only literal private IPs, authorized ports and exact same-camera pair. Native FFmpeg/OpenCV may still emit sensitive diagnostics: keep supervised console output private.

## Bounded authorized probes

From `services/edge-vision`, first run a health probe (12 frames, no model) once credentials and approval are present:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.camera_health `
  --rtsp-env VIIL_HIK_LAN_SUB `
  --source-id <approved-pseudonymous-id> `
  --privacy-approval <signed-policy-path> `
  --confirm-authorized-camera --frames 12
```

If the substream is unreadable, try the main env separately. **Never** pass RTSP URL as `--source`.

Bounded Edge experiment (metadata-only; no unreviewed alerts):

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge `
  --source rtsp --rtsp-env VIIL_HIK_LAN_SUB `
  --rtsp-fallback-env VIIL_HIK_LAN_MAIN `
  --source-id <approved-pseudonymous-id> `
  --privacy-approval <signed-policy-path> `
  --model <local-valid-pose-task-path> `
  --candidate-format v1 --confirm-consent `
  --rtsp-retries 1 --rtsp-retry-delay-ms 500 `
  --rtsp-session-seconds 60 --max-frames 120 --profile-rtsp
```

Neither a TCP handshake nor mock tests constitute real decode, latency, retention, safety, or fall-detection accuracy evidence.

## Regression and delivery

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
cd ..\..
git diff --check
```

Push only the reviewed `member1/feature/*` topic branch; merge to `member/feature/preprod` only after validation and green CI. Never auto-promote to shared `preprod` or `main`.
