# Hikvision -> VIIL Sentinel: Member 1 local-only integration (28 Oct 2026)

## Scope and hard limits
This is an **authorized local research camera input**, not a production safety system.
No auto upload, Meta calls, image storage, backend POST, medical inference or real alarms.
Never reuse a private camera feed without the site owner's permission and informed
notice to people recorded. The camera operator controls retention and access.

## Camera requirements
- Hikvision IP camera or NVR with RTSP enabled, on a trusted isolated LAN.
- Dedicated read-only/least-privilege camera user, strong secret, current firmware.
- Prefer H.264 substream (channel 102 for first camera) at a moderate FPS/resolution;
  compare quality and missing poses against main stream 101 before making claims.
- RTSP URL path usually /Streaming/Channels/102. Confirm with the device documentation.
- Do **not** expose RTSP port 554 to the public Internet. Use a trusted LAN/VPN.
- ONVIF is optional for discovery/control, **not needed** for direct RTSP capture.

## Local operator example (PowerShell on authorized test machine)
Do not paste passwords into chat, shell history, Git, screenshots or bug reports.
Set the variable interactively in a secure local terminal or use a secrets manager.
This illustrative example is deliberately credential-free.

```powershell
# Locally assign VIIL_CAMERA_RTSP from a secure secret source.
# Example URL shape only: rtsp://camera-lan-ip:554/Streaming/Channels/102
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m sentinel_edge.runner --source rtsp --rtsp-env VIIL_CAMERA_RTSP --model ..\..\models\pose_landmarker_lite.task --source-id hikvision-test-01 --candidate-format v1 --confirm-consent --max-frames 300
```

Do not enable `--display` in a public or screen-shared session.
stdout contains versioned **unconfirmed candidate metadata** only.
Normal offline lab import remains manual. RTSP network/device failures end the
local run with a nonzero status on interruption; there is **no automatic reconnection or continuous camera health monitor** yet. RTSP uses FFmpeg with 8s open and 4s per-read timeouts where supported. A manual restart creates a new detector/model session. Never use stream silence as evidence that nobody fell.
Even with `--confirm-consent`, this flag is an operator attestation, **not
independent verification of people's consent**. Camera access and site permission
must be checked before operation.

## Test sequence
1. Offline unit test: `python -m pytest -q tests/test_hikvision_source.py`.
2. Run a 300-frame capture with a **non-person** authorized test scene; ensure
   video decoding and pose abstention, verify no images persisted or backend calls.
3. Stage authorized safe movement scenarios: walk, sit, bend, lie and simulated
   safe fall; obtain independently reviewed onset labels.
4. Track network outages / wrong credentials / H.265 decoder mismatch;
   never infer that silence proves nobody fell.
5. Compare substream vs main stream and benchmark end-to-end wall FPS,
   pose availability, candidate counts, RSS and verified false alarms/hour.
6. Only after privacy + accuracy gates, ask Member 2 for authenticated
   ingestion and narrowly authorized Meta evidence integration.

## Responsibility
Member 1: Edge RTSP decoding, local pose/detector, dashboard and metrics.
Member 2: authenticated backend, image permissions, real Meta provider,
notification policy and persistent incident workflow. No direct client keys.

References:
- https://supportusa.hikvision.com/support/solutions/articles/17000129064-how-do-i-get-my-rtsp-stream-
- https://supportusa.hikvision.com/support/solutions/articles/17000128730-how-do-i-enable-onvif-on-a-hikvision-camera-
