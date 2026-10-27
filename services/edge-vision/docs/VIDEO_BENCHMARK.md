# Member 1 — Local video-to-model-to-evaluation benchmark

**Feature:** On-device video → MediaPipe Pose Landmarker → in-memory torso poses →
time-aware candidate detector → per-clip ground-truth scoring.

This directly closes the gap between the existing video runner and its
JSONL-only evaluation CLI. Neither raw frames nor torso coordinates are
written to files by this evaluation command.

**Not a medical device and not proof of fall detection accuracy.**
Only test with staged, consented, appropriately licensed clips.
Never use private CCTV or patient imagery without valid authorization.

## Required inputs

- Local MediaPipe Pose Landmarker `.task`, previously installed in ignored `models/`.
- Video manifest JSON stored **in the same private directory as the video files**.
- Named clips with clearly annotated `expected_fall`; `onset_ms` optional
  for fall clips, measured from the beginning of the video (milliseconds).
- A real `permission_basis` stating the consent/license basis. Simply filling
  this field is not itself proof that consent exists.
- An explicit CLI `--confirm-consent` flag to acknowledge responsibility.

Example `D:\staged-private\manifest.json` (this is only a template):

```json
{
  "version": 1,
  "permission_basis": "Team-staged footage with documented written informed consent",
  "clips": [
    {"id": "person01_stagedfall01", "video": "fall01.mp4", "expected_fall": true, "onset_ms": 1800},
    {"id": "person02_sit01", "video": "sitting01.mp4", "expected_fall": false}
  ]
}
```

Only use pseudonymous IDs; do not put names, identifying titles, personal
health details or URLs in the manifest or filenames. A video file must be
**inside the manifest directory**, have a supported extension
(`.mp4`, `.avi`, `.mov`, `.mkv` or `.webm`) and be no larger than 512 MiB.
The tool rejects absolute files, parent traversal, remote URLs and
symlink escape paths. It does not accept webcam sources.

## Command (PowerShell)

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m sentinel_edge.video_benchmark --manifest "D:\staged-private\manifest.json" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --confirm-consent
```

Optional `--max-frames 3000` (defaults to 6000 per clip); `--min-hip-descent`,
`--horizontal-min-angle-deg` and `--horizontal-hold-ms` control
heuristic thresholds. Inputs are capped at 100 clips, 6000 frames per
clip and 30,000 total frames. Oversized clips are **rejected**, never
silently treated as fully evaluated.

## Output fields

- `metrics`: clip-level TP, FP, TN, FN, Precision/Recall/F1 on this dataset
- `false_candidates_before_onset`: premature alerts, not credited as detections
- `false_candidates_per_negative_hour`: event count normalized to exposure
  in negative clips, only meaningful on substantial real footage
- `clips[].latency_ms`: time between annotated fall onset and first later
  candidate, when annotated and detected
- `pose_frame_availability_rate`: ratio of frames with valid, unambiguous torso pose
- `model_sha256`: hash for reproducibility, not a license or security guarantee
- `raw_frames_written_to_disk=false`, `pose_frames_written_to_disk=false`,
  `media_or_pose_uploaded=false`: behavior of this local benchmark, excluding
  existing source files on disk

All report statistics are descriptive **of the explicitly supplied files**
only. This is not an out-of-sample score unless the team uses a held-out
participant-based test set. It does not validate real emergency recognition.

## What was verified without any human video

The automated real-runtime integration test creates a temporary 12-frame,
160×160, all-black MJPG AVI in a test directory, then **decodes it with
OpenCV, runs the actual MediaPipe Pose Landmarker Lite `.task`, and computes
a one-clip negative ground-truth report**. Temporary video is removed with
pytest's temp directory cleanup. The test is skipped on CI when the
external model/MediaPipe is absent.

Expected negative-control behavior: 12 decoded frames, zero valid person
poses, zero fall candidates and one true-negative clip. This test cannot
measure sensitivity, real-world false alarms or scene robustness.

## Remaining evidence needed

To claim real detection quality: collect consented staged fall/non-fall
recordings, keep subject-level development/test splits separate, document
viewpoint, fps and environment, then run the same CLI and report actual
confusion-matrix counts, non-fall exposure, fall onset latency and observed
pose coverage. Preserve original licensing and consent off Git.
