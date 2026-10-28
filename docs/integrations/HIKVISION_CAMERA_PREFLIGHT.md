# Hikvision Camera Acceptance Preflight — VIIL-Sentinel (Member 1)

**Prepared without a physical camera.** No stream, person, IP address, camera model, camera credentials, Meta provider or backend has been verified by this document.

## Purpose
Prove the Hikvision RTSP substream is readable *before* involving MediaPipe and fall-candidate heuristics.
One successful short read **is not** proof of continuous connectivity, accuracy, fall detection or emergency readiness.

## Minimal runbook (authorized Windows machine)
1. Confirm the exact Hikvision/NVR model and firmware, right to process footage, people notified, and protected LAN/VPN connectivity. Create a dedicated camera viewer credential. Do not use admin credentials.
2. Turn on RTSP for that device; choose H.264 stream if available and consider /Streaming/Channels/102 for the first channel substream (confirm model-specific syntax). Never port-forward RTSP.
3. Set `VIIL_CAMERA_RTSP` on the local machine using an approved secrets manager. Never paste it into commits/chat/logs. Native OpenCV/FFmpeg diagnostic output **might expose camera details**: keep the process and logs private; suppress vendor debug logging.
4. Run from `D:\VIIL-Sentinel\services\edge-vision`:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.camera_health --rtsp-env VIIL_CAMERA_RTSP --confirm-authorized-camera --frames 30
```

The only application-level printed fields are `type`, `status`, `frames_read` and `frames_requested`.
`readable` means all sampled frames decoded; `interrupted` means a read stopped; `offline` means capture never opened; `error` means the local decoder failed. Non-readable results exit 2.
The probe discards decoded image objects immediately; no model inference, screenshot, video, upload or event delivery.

5. Only if the camera is readable, run the local Edge candidate runner (details in `HIKVISION_RTSP_MEMBER1.md`). Do not interpret zero emitted candidates as proof that no falls occurred.
6. Review source changes after switch of camera/NVR, network interruption, codec and resolution. With the default settings, failure ends nonzero. An opt-in bounded retry mode (`--rtsp-retries 1..3`) now creates new MediaPipe and detector sessions with unique source-relative clock IDs. FFmpeg RTSP open is bounded at 8 seconds and each read at 4 seconds (where supported by the local OpenCV backend). Reconnect exhaustion exits nonzero and is not proof of safety.

## Acceptance gates still required
- Real camera video test on a permitted staged scene, compare H.264 main and substream for pose visibility.
- Validate 8s open / 4s read timeouts, unique reconnect session IDs, camera release and native-model recreation with actual Hikvision firmware. The bounded retry implementation is tested offline only; continuous camera health monitoring and delivery are not implemented.
- Inspect network/decoder stderr for credential leakage before deployment; library-native logs are **not** guaranteed sanitized.
- Test at least 30 minutes on the target PC, with dropped packets and disconnects, record p50/p95 throughput and memory.
- Independently annotated falls and ADLs, actor-disjoint evaluation, false-alarm/hour and onset latency.
- Member 2 backend-authenticated evidence permissions and Meta integration remains separate.

This probe is not a continuously running camera-monitoring service. No real alarms are authorized.
