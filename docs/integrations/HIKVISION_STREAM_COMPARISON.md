# Hikvision Mainstream vs Substream — Local Aggregate Comparison

**Status: code and synthetic tests only. No physical camera evidence is available.**
This is a Member 1 research-side comparison, NOT a deployment or fall-detection
certification. Do not present a successful synthetic test as a real measured FPS.

## Goal

Compare /Streaming/Channels/101 (main) and /Streaming/Channels/102 (sub),
only when supported by the specific Hikvision model, using the same authorized
staged scenario, PC, lighting, camera angle, device firmware, model weights,
and configured trial length. Record the scene and hardware in a private
operator notebook, not in CI or the aggregate output. No password or RTSP
URL should be stored in the Git repository.

## Capture and input preparation

1. Obtain camera owner/participant permission and use a trusted LAN with
   read-only camera credentials. Run the RTSP preflight, then the bounded
   300-frame test with `--profile-rtsp` as described in
   `HIKVISION_LIVE_PERFORMANCE.md`.
2. From a *private* console, extract one JSON object **after** the exact
   `RESEARCH_RTSP_PROFILE ` prefix and one after the exact
   `EDGE_POSE_COVERAGE_SUMMARY ` prefix for the *same* camera session.
   Do NOT use the whole terminal output (native FFmpeg logs may reveal
   hostnames and credentials); never copy stdout with candidate source IDs.
   Save exactly four restricted-access `.json` files **outside Git**.
3. Use one profile+coverage pair for main channel and one for sub channel.
   Reconnects create new sessions, so never combine aggregates from
   separate epochs. Ensure session totals agree, and check manual notes for
   comparable staged conditions.
4. From `services/edge-vision`, run:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.rtsp_compare --main-profile "C:\PrivateTests\main-profile.json" --main-coverage "C:\PrivateTests\main-coverage.json" --sub-profile "C:\PrivateTests\sub-profile.json" --sub-coverage "C:\PrivateTests\sub-coverage.json"
```

The module also provides installed CLI `viil-edge-compare-rtsp`.
This is entirely local: it doesn't connect to a camera, backend or Meta API,
and produces only whitelisted numeric/boolean aggregated fields. It refuses
unexpected fields, inconsistent pose/frame totals, invalid units, missing
cycle timings, non-finite values and files larger than 16 KiB. Parsing errors
do not echo the path or source content in the application error. Keep
terminal/camera logs private regardless.

## Reading the comparison

The report contains mainstream and substream summaries plus four independent
comparisons: pose coverage, throughput FPS, local cycle p95 (milliseconds)
and *sampled* process RSS (MiB). 'Higher' or 'lower' is **descriptive**.
There is no automatic winning stream: a low-latency stream that loses
landmarks may be worse for the task. Pose coverage is not ground-truth
fall detection accuracy. Frame-cycle latency excludes camera acquisition,
cloud analysis and caregiver alerts.

The optional `provisional_technical_screen_passed` uses **illustrative,
unvalidated research thresholds**; it only shows which engineering checks
merit closer inspection:

- At least 300 processed frames and 30 recent cycle samples;
- No observed stream interruption during the chosen session;
- At least 8 FPS observed cycle throughput;
- Local frame-cycle p95 no more than 250 ms;
- At least 60% strict pose availability in a suitable staged scene;
- Sampled process RSS at most 1024 MiB (missing RSS = screen incomplete).

These values are *not* competition requirements, medical criteria, calibrated
safety thresholds, or standards. Do not cite 'passed' as real readiness without
actual recorded evidence. In particular the reports do **not** prove a
30-minute endurance window (session elapsed wall time is not exported) or
matched conditions, and they cannot measure sensitivity, specificity,
false alarms/hour, fall-onset delay, end-to-end Meta latency or caregiver
response. Every output explicitly sets
`eligible_for_real_world_safety_deployment: false` regardless of scores.

## Acceptance work still pending

Run two rights-cleared comparable scenes with a real device, then
perform a separate 30-minute staged endurance trial under explicit operator
supervision. Collect hardware, temperature, network conditions, CPU/RAM
and dropout notes. Evaluate independently annotated activities of daily
living and staged falls for false alarms/hour and detection latency.
Coordinate authenticated backend/evidence processing with Member 2;
do not send private footage or credentials to third-party systems
without authorization.
