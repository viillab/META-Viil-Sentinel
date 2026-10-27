# Local inference proof — Member 1 / 27 October 2026

This is an operational readiness check on one Windows development workstation,
**not** proof of fall-detection accuracy or a controlled speed benchmark.

## What was executed

- MediaPipe `0.10.35`, OpenCV contrib `5.0.0.93`, Python 3.11 virtual environment.
- Real on-device Pose Landmarker Lite (`.task`) loaded successfully in VIDEO mode.
- `python -m sentinel_edge.model_smoke --model D:\VIIL-Sentinel\models\pose_landmarker_lite.task --frames 30`
- 30 generated solid-black RGB frames, each 256 × 256. No webcam, external person,
  real-world dataset, real videos, remote model calls or Meta AI calls.
- Task bundle SHA-256: `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`.
  Bundle is stored outside Git and must not be committed.

## Observed *single-run* result

| Measurement | Result |
|---|---:|
| Successful API/model initialization | Yes |
| Generated empty frames | 30 |
| Poses found on empty negative control | 0 |
| Fall candidates found on empty negative control | 0 |
| Inference latency mean | 19.195 ms |
| Inference latency p50 (nearest-rank) | 17.103 ms |
| Inference latency p95 (nearest-rank) | 33.044 ms |
| Inference latency maximum | 35.036 ms |
| End-to-end throughput including model startup/cleanup | 21.46 frames/s |

These measurements are environment- and sample-specific. The blank negative
control checks only obvious spurious detections and data-contract wiring.
It does not measure true-positive detection, robustness to a person moving,
false-positive rate in realistic no-fall video, image-to-decision latency,
confidence calibration, or clinical performance.

## Reproduce locally

Run from `D:\VIIL-Sentinel\services\edge-vision`:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.doctor --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task"
.\.venv\Scripts\python.exe -m sentinel_edge.model_smoke --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --frames 30
.\.venv\Scripts\python.exe -m pytest -q
```

## Remaining before asserting video fall detection

1. Obtain authorization/consent for safe staged video and record license provenance.
2. Label fall onset and non-fall clips, including sitting/lying/bending and occlusion.
3. Run video-to-pose pipeline on held-out subjects, measure F1 and alert latency.
4. Check false positives by camera viewpoint, lighting and occlusion.
5. Document calibrated model outputs and clearly preserve uncertainty.
