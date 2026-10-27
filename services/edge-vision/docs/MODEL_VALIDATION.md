# Member 1 — Real MediaPipe task initialization & blank-frame negative control

**Scope:** Confirm official Pose Landmarker Lite can load, process 30 generated empty frames,
and supply stable response contracts for the fall-candidate pipeline. This is **not**
a real-human fall-detection, false-alert, sensitivity or clinical benchmark.

## Model provenance

- Official MediaPipe Pose Landmarker documentation:
  https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python
- Example official Pose Landmarker Lite bundle URL (verified in Google AI Edge maintained repository):
  https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task
- Download the asset to `D:\VIIL-Sentinel\models\pose_landmarker_lite.task` for **local use only**.
- Do not commit, bundle, redistribute or upload .task assets until licensing terms are checked.
- The `models/` directory and `*.task` files are Git ignored.

## Offline smoke command

From `D:\VIIL-Sentinel\services\edge-vision` (PowerShell):

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.doctor --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task"
.\.venv\Scripts\python.exe -m sentinel_edge.model_smoke --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --frames 30
```

Output is JSON with: SHA-256 (no raw model bytes), frame count,
model initialization status, pose counts on generated empty images,
heuristic fall-candidate count, p50 and p95 inference latency,
and rough overall throughput. Real inference runs in `VIDEO` mode
against generated black RGB frames. The program **never opens cameras,
records humans, sends frames to Meta AI, or uploads data**.

If you later evaluate on consented real clips, use the existing video runner,
save optional torso-only JSONL traces outside the repository, annotate
truth in a manifest, and run `sentinel_edge.evaluation`.
A successful smoke test is only prerequisite readiness evidence; it is
not evidence that the heuristic detects actual falls.
