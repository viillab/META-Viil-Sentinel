# VIIL Sentinel — Hikvision Local Live Throughput Study (Member 1)

Updated: 28 Oct 2026. **The feature is implemented and unit-tested using fake
captures; NO physical Hikvision was benchmarked.** No field readiness claim.

## Motivation
Earlier `edge_resource_profile.py` evaluates **offline prerecorded video
replays**. That result cannot be called real live-stream latency. This
RTSP-specific profiler instead measures the wall cycle from just before
`cap.read()` until after local pose/temporal detection/metadata emission.
It can include network blocking/pacing; it excludes camera sensor exposure,
on-camera encoding, network transmission *prior to the read*, backend, Meta
API and caregiver action. **It does not measure fall accuracy or reaction
time.**

## Safely run with an authorized test setup
- Ask the site owner and all people appearing for permission; avoid patient
  data, real incidents and public network exposure.
- Keep camera RTSP credentials in a private `VIIL_CAMERA_RTSP` environment
  variable, never CLI arguments, screenshots or Git. No remote web/API call
  is made by this command.
- First run `python -m sentinel_edge.camera_health` per
  `HIKVISION_CAMERA_PREFLIGHT.md` on a test scene.
- Only then from `services/edge-vision` with the correct private model path:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.runner --source rtsp --rtsp-env VIIL_CAMERA_RTSP --model ..\..\models\pose_landmarker_lite.task --source-id stage-cam-01 --candidate-format v1 --confirm-consent --privacy-approval C:\PrivateConfig\approved-privacy.json --rtsp-retries 1 --max-frames 300 --profile-rtsp
```

The opt-in `--profile-rtsp` is available only with
`--rtsp-retries 1..3`; retry mode already prevents research traces,
display and experimental shadow model from crossing stream sessions.

**Bounded 30-minute endurance trial (authorized staged scene only):**

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.runner --source rtsp --rtsp-env VIIL_CAMERA_RTSP --model ..\..\models\pose_landmarker_lite.task --source-id stage-cam-01 --candidate-format v1 --confirm-consent --privacy-approval C:\PrivateConfig\approved-privacy.json --rtsp-retries 1 --rtsp-session-seconds 1800 --max-frames 0 --profile-rtsp
```

`--rtsp-session-seconds` allows 0 (disabled) or 1..3600 seconds and is
per RTSP session, not a global wall-clock deadline across reconnections.
If the stream fails, a fresh session can run up to the full budget again.
The bound is checked before each read and after each successful blocking
read, so processing stops without emitting a frame after the deadline,
subject to the time OpenCV spends inside one read (nominal 4s timeout).
The stream is never certified healthy because a test ends at its budget.
A zero-frame attempt is a failure and may retry; failure after the bounded
retry count returns exit code 2. Pose observations, candidate counts and
the per-session profile are kept separate across reconnections. Avoid
storing the raw terminal transcript because native decoder logs can be
sensitive.

**Output separation:**
- stdout: unconfirmed candidate v1 metadata only (may contain source IDs).
- stderr: one `RESEARCH_RTSP_PROFILE` JSON line per *processing* attempt
  (on successful frame-bound completion or capture interruption).
- stderr: an `EDGE_POSE_COVERAGE_SUMMARY` per processed retry-mode session,
  whether profiling was enabled or not. A transition line
  `EDGE_POSE_COVERAGE` is emitted when **both 45 consecutive processed
  frames AND 3,000 ms** have passed without usable torso landmarks (based on
  the stream-session relative timestamps), and again when pose is observed.
  Frame-only offline callers retain the legacy 45-frame diagnostic threshold.
  The combined threshold avoids prematurely flagging 45 frames at 30 FPS
  (roughly 1.5 seconds); at 5 FPS, 45 frames still take roughly 9 seconds.
  It is an observation gate, not a calibrated camera quality or safety threshold.
  Transition counts reset with each new camera/model session. These are
  **operator diagnostics**, not camera failure diagnoses or alarms.
  An empty room, darkness, occlusion, long distance, other people or model
  errors may each cause the same lack of usable pose. There is no assurance
  that a person is absent, safe or that no fall occurred. A stream can be
  decodable yet fail to provide usable pose; `stream_interrupted` separately
  describes RTSP read failure.
- Some native FFmpeg/OpenCV logs may still disclose connection details.
  Treat the **entire raw terminal output as private** and only publish
  manually checked, aggregate metrics with permission.

## Metrics and interpretation

| Field | Meaning / limitation |
|---|---|
| frames_processed | Successful decoded/processed frames in this particular session |
| pose_unavailable_frames | No usable strict torso landmarks, not a detected absence of a person |
| candidate_events_unconfirmed | Heuristic candidates, **not** confirmed falls |
| cycle_p50_ms / cycle_p95_ms | Recent up to 2,048 wall-frame cycle samples (not acquisition-to-alert) |
| cycle_mean_ms_all_frames | Mean blocking-read + infer + emit cycle across all processed frames |
| observed_cycle_throughput_fps | Processed frames divided by total measured cycle duration (includes stream pacing; excludes model and capture opening) |
| sampled_process_rss_max_mib | Process RSS sampled on startup, every 32 frames and end; may be null and is **not** a true instantaneous peak |
| stream_interrupted | True if the processing session ended due to an RTSP read failure |

Do not calculate or present **accuracy, sensitivity, fall warning delay,
false alerts per hour, clinical reliability or Meta AI latency** using these
measurements. Those require independently reviewed ground-truth events,
calibrated onset labels and an authenticated end-to-end integration.

## Staged camera acceptance matrix
1. Capture a rights-cleared 300-frame H.264 substream (/102, if available),
   record environment/hardware and summarized metrics privately.
2. Repeat with main stream (/101) under comparable scene and lighting.
3. Stage a deliberate unplug, disconnection or invalid account: interruption
   must be visible, retries bounded and stale model tracking not reused.
4. Run a consented 30-minute continuous session, check temperature/CPU/RAM,
   loss rates and whether the decoders meet the expected FPS.
5. Compare p50/p95, pose availability and sampled RSS side by side; prioritize
   reliable pose and fail-safe behavior, not maximum nominal FPS alone.
6. Validate Member 2's separate Meta/Backend loop and user-facing incident
   timelines before an end-to-end demonstration.

All numeric camera performance results remain **unverified until the actual
device and target PC are available**. No cloud inference or alarms are
enabled by this profiling feature.
