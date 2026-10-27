# Member 1 — Edge Vision and Model Evaluation

**Owner:** Member 1 (you)

**Branch:** `member1/feature/edge-vision`

**Integration:** `preprod` (human-only `main`)

**Status:** New, **unvalidated** pose-based fall-candidate heuristic. NOT a clinical or production safety detector.

## What has been implemented

- Typed 2D normalized pose landmark contracts, with visibility validation.
- Temporal fall-candidate state machine requiring ALL of:
  1. a recent upright shoulder–hip torso orientation,
  2. downward hip movement relative to the same-camera recent baseline,
  3. a horizontal torso posture sustained for at least 450 ms,
  4. minimum landmark confidence and a cooldown for duplicate events.
- Explicit reset on a camera switch, missing/poor landmarks, or discontinuous timestamps.
- Candidate output with event UUID, timestamp, source_id and **uncalibrated heuristic score**.
- Optional local MediaPipe PoseLandmarker + OpenCV runner for webcam or authorized video.
- Synthetic unit tests for fall-like transition, no-fall sitting, pre-existing lying posture, occlusion/gaps and metrics.

This is a heuristic demonstration; it does not establish clinical reliability. **Do not call the heuristic score a validated probability**. It cannot infer injuries, consciousness, severity, or whether emergency help is required.

## Setup and test

From `D:\VIIL-Sentinel\services\edge-vision` with Python 3.11+:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
```

Optional video runner dependencies:

```powershell
python -m pip install -e ".[video,dev]"
```

To use a webcam or local video, obtain a **compatible MediaPipe Pose Landmarker .task model** yourself from the official documentation, verify the asset's terms, and save it outside Git (e.g. `D:\VIIL-Sentinel\models\pose_landmarker_lite.task`). The project does not bundle or download any model weights.

```powershell
# Explicitly authorized staged recording
python -m sentinel_edge --source "D:\staged-data\example.mp4" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --max-frames 1000

# Local webcam, no recording and no network uploads
python -m sentinel_edge --source 0 --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --display
```

Default mode never opens a display window, saves frames, sends notifications or calls Meta AI. Only event metadata is printed as JSON to stdout.

Official task reference: https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python

## Handoff contract to Member 2

A candidate event has this shape (the numeric values are **illustrative only**, not measured):

```json
{
  "type": "FALL_CANDIDATE",
  "id": "a-uuid",
  "timestamp_ms": 880,
  "source_id": "staged-camera-01",
  "confidence": 0.8,
  "evidence_refs": [],
  "detector": "temporal-pose-heuristic-v0.1",
  "simulated": false,
  "evidence_notes": ["Human review is required"]
}
```

`confidence` is a heuristic score, NOT calibrated. No raw frames are attached. Member 2 will need to add evidence selection and an authenticated, provenance-preserving API integration before any real event can reach the caregiver workflow; **do not send candidate events through the existing `/incidents/demo` route as though they are staged events**.

## Remaining Member 1 work

- Run authorized fall-like and no-fall recordings; record ground truth at **event/clip level**, not individual frames.
- Verify subject-level train/test split, licensing and consent of any dataset.
- Calibrate thresholds and measure precision, recall, F1 and false-alert rate from real labeled evaluation sets.
- Implement real multi-person tracking (current PoseLandmarker runner tracks one pose only).
- Handle camera perspective, occlusions and sitting/lying false positives robustly.
- Add selected keyframes with local-only retention rules and user consent.
- Add confidence and uncertainty reporting independent of clinical implications.
- Test under realistic light, clothes, camera heights, frame rates and hardware conditions.
- Integrate the validated detection contract with Member 2/3 through an explicitly authorized authenticated service.

## Privacy and licensing

MediaPipe is an external third-party dependency; check the Pose Landmarker model asset license and permitted redistribution before making the GitHub repository Public. Do not commit raw footage, `.task` binaries, research models or personal data.

Use the official task documentation. No capability or performance has been tested against actual video or real-world falls in the synthetic unit tests.
