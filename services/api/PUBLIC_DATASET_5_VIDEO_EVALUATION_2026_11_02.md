# VIIL-Sentinel — Five public fall-detection videos: local evaluation (2026-11-02)

**Executed with real, human-performed staged MP4 clips on Windows, actual MediaPipe PoseLandmarker and unchanged Member 1 TemporalFallDetector. Not a Meta inference. Not clinical validation.**

## Data rights and reproducibility

- Upstream repository: [samruddhi-2308/FallDetectionDataset](https://github.com/samruddhi-2308/FallDetectionDataset); 54 clips in 4 groups.
- Source labels: [metadata/clips_index.csv](https://github.com/samruddhi-2308/FallDetectionDataset/blob/main/metadata/clips_index.csv).
- License: [CC BY-NC 4.0](https://github.com/samruddhi-2308/FallDetectionDataset/blob/main/LICENSE), attribution required, noncommercial use only. The publisher warns identifiable humans appear. Do not re-publish media, snapshots, or derived poses.
- Upstream Git tree identifier: `2ea3acbb74db88a4c2d584b3b5a631f180b490f6`. Each selected MP4 was downloaded from the project's raw GitHub repository, its file size and exact Git blob SHA-1 and independently calculated SHA-256 validated.
- Method: selected the smallest video from standing-to-fall, sitting-to-fall and sleeping-to-fall, plus the two smallest ADL videos. **This is a nonrandom convenience sample, not an independent held-out or subject-wise benchmark.**
- Storage: `D:\VIIL-Sentinel\data\private\public_fall_video_probe_v1\` (Git ignored). Raw MP4, minimal torso landmark `*.pose.jsonl`, the local evaluation manifest and aggregate report remain private.
- No frame, pose or person was uploaded to Meta. **0 Meta calls** this round. No camera access, notifications or medical actions.

## Actual video / model inference

Environment: Windows, Python 3.12.13, MediaPipe 0.10.35, `cv2.__version__=5.0.0`. Note: the optional video installation yielded both opencv-python 4.14.0.94 and opencv-contrib-python 5.0.0.93; use an isolated, pinned Video venv before production. Existing `models/pose_landmarker_lite.task` was used (5,777,746 bytes), but that pre-existing asset's upstream origin/license was not independently verified. All video frames were decoded and processed; the Edge runner exited with code 0 for each clip. There was no `--max-frames` truncation.

| ID | Ground-truth dataset category | Frames | Valid torso poses | Candidate | Result |
| --- | --- | ---: | ---: | ---: | --- |
| FD0033 | standing_to_fall | 95 | 95 | 0 | **FN** |
| FD0012 | sitting_to_fall | 147 | 145 | 0 | **FN** |
| FD0032 | sleeping_to_fall | 231 | 231 | 0 | **FN** |
| FD0002 | adl_no_fall | 101 | 101 | 0 | **TN** |
| FD0003 | adl_no_fall | 93 | 88 | 0 | **TN** |
| **Total** | **3 positive / 2 negative** | **667** | **660** | **0** | **TP 0, FN 3, TN 2, FP 0** |

Metrics from actual `sentinel_edge.evaluation.evaluate_manifest()`: **recall 0/3 = 0%**, **F1 = 0**, evaluator precision = 0 by convention when no positive predictions, correctness 2/5 = 40%. These are NOT reliable performance estimates. Only 3.576 seconds of negative ADL clips were observed, so zero FP does not demonstrate a safe false-alert rate. No onset timestamp annotation was available for these selected clips; detection latency is unknown.

## Root-cause diagnostics from the extracted poses (aggregate counts only)

The MediaPipe Pose model yielded valid features for 660/667 frames (98.95%). The primary miss is in the **strict combined detector gates**, not whole-video pose extraction failure. Current Member 1 default conditions: upright angle ≤32°, horizontal angle ≥56°, hip descent ≥0.13 normalized frame, prior upright ≤1600 ms, and horizontal held ≥450 ms.

| ID | Upright frames | Horizontal frames | Horizontal after recent upright | Max post-upright hip descent | Diagnostic |
| --- | ---: | ---: | ---: | ---: | --- |
| FD0033 | 21 | 34 | **0** | 0.070 | No recent-upright-to-horizontal combination and drop below 0.13 |
| FD0012 | 79 | **0** | 0 | 0.489 | Maximum measured torso angle **52.2°**, below horizontal gate 56° |
| FD0032 | **0** | 231 | 0 | 0 | Already horizontal; never established prior upright pose |
| FD0002 | 101 | 0 | 0 | 0.010 | No fall candidate expected |
| FD0003 | 88 | 0 | 0 | 0.013 | No fall candidate expected |

The gate counts show what was **not satisfied**, not actual fall onset, activity intention or medical outcome; independently inspecting licensed temporal annotations is future work. **No thresholds were tuned on these evaluation clips.**

### SHA-256 of verified source MP4s

| ID | SHA-256 |
| --- | --- |
| FD0033 | `4a1f32db7c7133b7ed7248f31bd0429a399ceb1f6cd9e65fcb4ccc6779ab1353` |
| FD0012 | `fb644d44867a59abc05204867e1abb0df73394d6944092aa4610ec0919383421` |
| FD0032 | `9cf4570ecb13c7e6fdab781a3403e1911a4c69fb03f46fa63eb47c1c50fe87db` |
| FD0002 | `028a9e5c33939b2d13daafee1e26f763682edbf9fd33e2cff57e6ff1a3e8bbd1` |
| FD0003 | `16bba229904cd3bb423199520ba46494106e088ea1b465350a20116fb8445edc` |

## Reproduce with the same five licensed clips

In `D:\VIIL-Sentinel\services\api` with `.venv` and the optional Edge `.[video]` dependencies installed:

```powershell
# Downloads only preselected, pinned public videos to ignored private storage.
.\.venv\Scripts\python.exe -m app.public_video_eval --download --acknowledge-noncommercial-license

# First extraction only: real OpenCV/MediaPipe inference; refuses to overwrite existing private pose traces.
.\.venv\Scripts\python.exe -m app.public_video_eval --evaluate --acknowledge-noncommercial-license --timeout-per-video 600

# Rerun clip-level evaluation from the existing private traces (NO model call or network), with aggregated diagnostics.
.\.venv\Scripts\python.exe -m app.public_video_eval --summarize-existing --acknowledge-noncommercial-license

.\.venv\Scripts\python.exe -m pytest -q tests/test_public_video_eval.py
```

The `--summarize-existing` command produces `data/private/public_fall_video_probe_v1/evaluation-summary.json`; it contains **only aggregate counts and pseudonymous clip IDs**, no raw pose points. The extractor's five original MP4s, pose traces and existing model file stay ignored; do not force-add them to Git.

## Actionable handoff

1. **Member 1 model owner:** investigate camera orientation/temporal frame history and non-upright starting postures, especially sitting-to-fall and bed-to-floor falls. Reproduce with annotations; do not simply lower all thresholds on the held-out five clips.
2. On a *separate development split*, experiment with action-specific detectors, temporal pose velocity, state transitions, image rotation robustness, tracking and calibrated abstention; assess false positives using many more ADL videos.
3. Keep independent subject-wise test clips and measure per-event recall, false alarms per hour, latency (once onset annotations exist) and uncertainty. Do not claim clinical accuracy or deploy unattended emergency dispatch.
4. Meta may later assist authorized caregiver review, but **do not upload these videos/poses to Meta** without verified use rights and consent. The existing local paid Meta ledger is exhausted at **4/4**; it was untouched.
5. Existing Member 1 source code was **not edited**. New downloader/evaluator and CI tests are in Member 2's `services/api/`.

This report records the initial observed failure faithfully rather than masking it with synthetic fixtures or hyperparameter tuning.
