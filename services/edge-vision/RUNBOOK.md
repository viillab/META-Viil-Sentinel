# Member 1 — Edge Vision verification and handoff

The local detector is a **non-clinical heuristic**, not an independently validated
safety system. No automatic rescue dispatch or medical conclusions are permitted.
All model and media handling in this module is local-only.

## Stage 1 — Reproducible code verification (no camera)

In PowerShell, run:

~~~powershell
cd D:\VIIL-Sentinel\services\edge-vision
python -m pytest -q
python -m ruff check .
python -m sentinel_edge.evaluation --manifest examples/synthetic/manifest.json
~~~

The example's synthetic F1 score is not a real-world performance claim.

**Onset-matching update:** For clips with an annotated onset_ms, a candidate
before onset is classified as premature and is NOT credited as a detected fall.
The report now includes pre_onset_candidate_count, first_matching_candidate_ms,
observed_pose_frames and false_candidates_before_onset. Ground-truth onset
must lie inside the recorded trace. Missing/occluded pose clears previous
upright evidence to prevent stale posture history from creating an event.
Clips without onset annotations retain coarse clip-level matching only.

## Stage 2 — Isolated local video dependencies

Using a local Python 3.11+ virtual environment (do not override system packages).
MediaPipe installs its compatible OpenCV contrib package; do not separately
install another OpenCV provider into the same environment:

~~~powershell
cd D:\VIIL-Sentinel\services\edge-vision
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[video,dev]"
.\.venv\Scripts\python.exe -m sentinel_edge.doctor
~~~

**A Pose Landmarker .task model is not shipped with this repo.**
Obtain a compatible model with appropriate usage rights via
[official MediaPipe documentation](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/python).
Store it in D:\VIIL-Sentinel\models\pose_landmarker_lite.task
(or another location ignored by Git).

Run the readiness check with the actual model path:

~~~powershell
.\.venv\Scripts\python.exe -m sentinel_edge.doctor --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task"
~~~

The probe checks package versions and file existence; it does **not**
load the model, open a camera or confirm model accuracy.

## Stage 3 — Webcam or consented staged video

Only analyze footage from people who explicitly consented.
Staged fall demonstrations must be performed safely, with supervision,
and without any actual uncontrolled fall.

~~~powershell
.\.venv\Scripts\python.exe -m sentinel_edge --source 0 --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --display --max-frames 300
~~~

For a specific authorized local video, replace --source 0 with its path.

The video runner outputs **FALL_CANDIDATE metadata only** to stdout,
and summary counts to stderr. No image, video or pose is sent to a network.
An absent pose, multiple detected people, occluded/out-of-frame joints,
or poor landmark confidence must not be converted into a fall claim.
The task is configured for up to two poses to detect obvious multi-person
ambiguity, but **does not perform persistent person tracking**. It can still
miss people or switch identities; never use it as a monitoring guarantee.

## Stage 4 — Explicit pose trace export and evaluation

Derived pose coordinates may still be identifying. Export only with
explicit authority and store files outside the repository:

~~~powershell
.\.venv\Scripts\python.exe -m sentinel_edge --source "D:\staged-private\fall1.mp4" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --trace-output "D:\staged-private\fall1.pose.jsonl" --acknowledge-pose-privacy
~~~

Create a version-1 ground-truth manifest alongside the local traces,
following examples/synthetic/manifest.json and annotating onset when known.
Evaluate it:

~~~powershell
.\.venv\Scripts\python.exe -m sentinel_edge.evaluation --manifest "D:\staged-private\manifest.json"
~~~

Report results only after independent held-out footage is evaluated.
Include non-falls such as sitting, bending, lying, partial occlusion,
camera-angle differences and changing illumination. Split training or
threshold tuning data from test data by subject where possible.

## Stage 5 — Real MediaPipe runtime smoke test (no camera)

See [Model validation](docs/MODEL_VALIDATION.md) for an official downloadable
Pose Landmarker Lite task bundle and SHA-256/latency testing. The smoke test
uses **synthetic empty frames**, checks model load and inference, but does not
measure fall detection sensitivity, real-person accuracy or false alarms.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.model_smoke --model "D:\\VIIL-Sentinel\\models\\pose_landmarker_lite.task" --frames 30
```

## Stage 6 — Video-to-MediaPipe-to-ground-truth scoring (local only)

See [Video benchmark procedure](docs/VIDEO_BENCHMARK.md) for the
manifest schema, explicit consent step, per-clip frame limits and
reported metrics. Unlike the JSONL evaluator, this command decodes
consented local video with the **real on-device MediaPipe model** and
uses temporary in-memory PoseFrames; it neither saves captured frames
nor stores landmark traces.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.video_benchmark --manifest "D:\\staged-private\\manifest.json" --model "D:\\VIIL-Sentinel\\models\\pose_landmarker_lite.task" --confirm-consent
```

The benchmark now checks valid nominal FPS, declared frame count, decoded
frame count and remaining evaluation budget *before* reporting any metrics.
An interrupted/invalid decoder or inconsistent metadata fails closed.
VFR video timing cannot be validated from nominal FPS alone; use a known
constant-frame-rate video for meaningful event-onset latency comparisons.

The project also contains an automated **synthetic black-video**
integration test; it is not a fall/no-fall benchmark on humans.

## Stage 7 — Versioned, local-only candidate handoff for Member 2

See [Candidate handoff v1](docs/CANDIDATE_HANDOFF_V1.md) for strict
schema, synthetic test command, local MediaPipe runner `--candidate-format v1`,
provenance, relative timestamps, uncalibrated scoring and Member2's
future *authenticated* ingestion responsibilities. The existing
`/api/v1/incidents/demo` endpoint remains simulation-only and must not
receive actual Edge candidate events.

## Optional input-size performance experiments

Read [resolution experiment](docs/RESOLUTION_EXPERIMENT_2026-10-27.md)
for a complete real-video comparison and example commands. The offline
`sentinel_edge.video_benchmark --max-inference-side 640` option changes the
input to MediaPipe for **experimental measurements only**. The default 0
keeps original pixels, real-world person-count handling and temporal
thresholds unchanged. Reducing frame size has **not** proven a latency
improvement or improvement in fall detection quality.

## Optional performance and disk audit

See [Performance, RAM and disk audit](docs/PERFORMANCE_EFFICIENCY_2026-10-27.md).
The default benchmark streams aggregate detections with bounded in-memory
state. Use `--buffered-eval` only for reference comparisons and
`--signal-diagnostics` for detailed aggregate gate counts. For machine
measurement, install optional `psutil` into the **dev-only** virtual
environment and run `scripts/profile_edge.py`; it does not upload media.
Root `.dockerignore` prevents local datasets, model weights, `.venv`,
`node_modules` and `.git` entering Docker build contexts. No local files
are automatically deleted or compressed.

## Real-human staged fall video baseline (IKAR)

See [IKAR real video result](docs/IKAR_REAL_VIDEO_EVALUATION_2026-10-27.md)
for CC BY 4.0 attribution, verified archive MD5, reproducible private-only
sampling, 8 manually staged human fall clips, on-device MediaPipe evaluation,
and an observed 1/8 detection rate. This dataset contains no negative ADL
clips, so do not infer false-positive rate or meaningful deployment safety.
The optional `--signal-diagnostics` outputs only per-clip gate *counts* (no
images, no raw keypoints), to support failures analysis without threshold
fitting on the same held-out evaluation clips.

## Member 2 integration contract

Candidate events contain source identifier, timestamp, *heuristic*
uncalibrated score and uncertainty notes. Member 2 must not interpret a
candidate as a confirmed fall, medical severity or diagnosis. Evidence
selection, secure transmission and the human decision workflow are
separate integration tasks and are **not implemented in this branch**.

## Git ownership

The latest work belongs to member1/feature/event-robustness.
Validated Member 1 work is merged into the separate integration branch
member/feature/preprod on explicit user instruction. This is NOT the actual
preprod branch. Only the human promotes changes into preprod or main.
