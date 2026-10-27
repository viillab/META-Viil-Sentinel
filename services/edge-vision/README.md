# Member 1 — Edge Vision and Model Evaluation

**Owner:** Member 1 (you)

**Member 1 branches:** `member1/feature/*`

**Integration:** `member/feature/preprod` (actual `preprod` and `main` promoted by human)

**Status:** Actual MediaPipe pose AI inference **works**; fall-candidate heuristics remain **unvalidated for reliable safety alerts**. NOT a clinical or production safety detector.

## Research-driven model preparation (27 Oct 2026)

New [research-to-engineering audit](docs/DEEP_RESEARCH_MOTION_AND_DATASET_PROTOCOL_2026-10-27.md)
provides an experimental **bounded temporal motion-feature window** and
`--motion-study` aggregate-only real-video diagnostics, plus a strict
subject-/recording-/media-disjoint research manifest audit:

```powershell
python -m sentinel_edge.split_audit --manifest examples/synthetic/subject_disjoint_v2.example.json
```

These are **research scaffolding, not a trained TCN/GRU model**. Fall
candidate production thresholds and outputs are unchanged; the original
8-clip positive-only IKAR evaluation remains 1/8. No additional person
images, models or subject metadata have been committed.

## Private Pose-to-Window Export (reviewed human video only)

A consent-gated [local reviewed-window exporter](docs/PRIVATE_WINDOW_EXPORT_2026-10-27.md)
now connects real MediaPipe video inference to **30×6 masked motion windows**
for the existing research trainer. Group IDs, media SHA-256 and human-reviewed
interval labels must be supplied, with Fall AND ADL among disjoint train/val/test
people. Exported derived features are sensitive: the CLI ONLY creates files
inside Git-ignored `data/private`, with explicit authorization and no overwrite.

A real **in-memory IKAR pilot** decoded 87 frames and produced a 30×6 window
without assigning a Fall/No-Fall label or saving the features. IKAR was **not**
used for supervised training. A separate publisher-labeled, unreviewed
CAUCAFall study (below) has since fitted a research-only classifier; neither
experiment validates a deployed fall detector.

## CAUCAFall real-video Fall/ADL research curation

The private [CAUCAFall research curation protocol](docs/CAUCAFALL_RESEARCH_DATASET_2026-10-27.md)
uses the downloaded Zenodo OmniFall CAUCAFall derivative, publisher MMAction2
and original CSV annotations to create a **fixed subject-disjoint 40-video
proposal** (20 fall-motion, 20 clean ADL) with verified media SHA-256.
It never infers ADL labels from the names of fall source recordings,
includes no `fallen` as a fall event, and sets `label_reviewed=false`
until manual review. Optional **publisher-labeled** in-memory baseline
training is *research-only* and reports pose-quality exclusions and held-out
subjects; it does **not** assert independent human label verification.

## Independent annotation review gate (requires real human verification)

The [two-reviewer label-verification protocol and developer handoff](docs/INDEPENDENT_ANNOTATION_REVIEW_HANDOFF_2026-10-27.md)
adds `python -m sentinel_edge.annotation_review` as a **private-only**
preprocessing gate. It can generate a template with **two blank, unapproved
review entries per clip**, then compile an exporter-compatible reviewed
manifest **only if two distinct reviewers attest matching Fall/ADL activity,
timing and SHA-256 source media** for every clip. Disagreement, ambiguity,
untouched templates, changed video and missing participants fail closed.
The tool cannot independently verify reviewer identities or consent.

**No CAUCAFall clip has been newly approved by this tool:** historical
publisher-labeled research scores remain unreviewed, and data must not be
presented as independently validated until humans complete real visual review.
Private review files and derived pose remain ignored under `data/private`.

## Lightweight V1/V2 model-quality comparison (Member 1 handoff)

The [V2 implementation and next-developer handoff](docs/MEMBER1_MODEL_QUALITY_V2_HANDOFF_2026-10-27.md)
adds a 40-dimensional mask-aware motion descriptor alongside the unchanged
30-dimensional V1 baseline. It uses train subjects for weights, validation
subjects to select candidate/threshold, and held-out test subjects for
diagnostic comparison only. The real publisher-labeled CAUCAFall pilot can
be rerun in memory without overwriting the private manifests:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.model_quality --synthetic-demo
```

**This is research model selection, not a production fall-alert model.**
Model improvements must be supported by held-out results and pose coverage,
never claimed from synthetic fixtures or validation-set optimization alone.

## Development-subject Cross-Validation (optional research gate)

The [4-fold cross-subject research protocol and next-developer instructions](docs/DEVELOPMENT_SUBJECT_CV_HANDOFF_2026-10-27.md)
add an opt-in `--dev-crossval` to the in-memory V1/V2 CLI. It rotates
train/inner-validation/outer-scoring groups over **development subjects only**.
No final test labels or features influence the CV. The same 40 real CAUCAFall
clips yielded 29 eligible *development* clips from 8 declared participants:
V1 outer-fold fall recall **9/15**, V2 **4/15**; both flagged 3 of 14 ADL
clips as fall. Inner validation chose V1 in all four folds. These clips
are staged publisher-labeled activities, not deployment evidence. The
predeclared V1 selection remains unchanged.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.model_quality --synthetic-demo --dev-crossval
```

## Research-only trained Temporal Logistic baseline

A lightweight **NumPy-supervised model** can now be fitted on masked temporal
pose features in an **offline experiment**. It applies the v2 subject-disjoint
audit, trains and normalizes using train subjects only, selects threshold on
validation subjects, and scores a separate held-out test. Both fictional
synthetic demonstrations and a tiny real **publisher-labeled staged** CAUCAFall
pilot have been trained and evaluated in memory. Neither has independently
verified action labels or robust real-world evidence. This is NOT a TCN/GRU,
NOT a validated Fall Detection AI replacement and never connects to live alerts.

See [temporal baseline training and dataset gates](docs/TEMPORAL_TRAINING_RESEARCH_BASELINE_2026-10-27.md).

```powershell
python -m pip install -e ".[training,dev]"
python -m sentinel_edge.temporal_training --synthetic-demo
```

## AI model readiness — verified

See the [latest real runtime and model readiness audit](docs/MODEL_READINESS_AUDIT_2026-10-27.md):
Pose Landmarker Lite loads and infers locally, but the fall event classifier is
a heuristic with 1/8 detected staged falls in a tiny positive-only IKAR test.
The latest video report adds a conservative `readiness_gate`, never granting
automated alert/dispatch authorization. **Meta multimodal live inference is
not implemented** (Backend `meta.py` uses an explicitly labeled mock).

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

The first [real-human staged fall video evaluation](docs/IKAR_REAL_VIDEO_EVALUATION_2026-10-27.md)
used licensed IKAR CC BY 4.0 recordings and detected only **1/8** positive clips
with the original thresholds. This is an exploratory positive-only subset,
NOT a generalizable fall accuracy estimate. Diagnostic gate counts now help
investigate missed events without storing image or pose data.

The new [Local Video Benchmark](docs/VIDEO_BENCHMARK.md) evaluates
consented videos directly using local MediaPipe inference and clip-level
labels without writing derived pose traces. It is distinct from the
synthetic negative-control smoke test and cannot establish clinical accuracy.

For the exact readiness checklist and dependency-isolated camera commands, see
[Member 1 verification runbook](RUNBOOK.md). The latest MediaPipe optional
video dependency installs its own compatible OpenCV package; avoid mixing
multiple OpenCV wheels in the same Python environment.

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

## Optional resolution experiment (NOT production)

Read the [real IKAR frame-size comparison](docs/RESOLUTION_EXPERIMENT_2026-10-27.md):
original-resolution inference remained faster end-to-end than experimental
640/480 px input caps in one local trial. The default is unchanged; the
`--max-inference-side` flag is benchmark-only and must not be promoted without
representative positive/negative validation on target devices.

## Performance and disk footprint

The default local video benchmark now evaluates detected events **as frames
arrive** without retaining per-frame landmark dictionaries or running the
fall detector a second time. A `--buffered-eval` reference mode remains
for bit-for-bit report comparisons, and `--signal-diagnostics` keeps its
specialized buffered path. See the [real IKAR performance audit](docs/PERFORMANCE_EFFICIENCY_2026-10-27.md)
for reproducible wall time/CPU/RAM measurements and local disk inventory.
No threshold or safety behavior was relaxed.

## Member 1 → Member 2 Candidate Handoff v1

The new [versioned metadata-only candidate contract](docs/CANDIDATE_HANDOFF_V1.md)
exposes strictly labeled unverified fall candidates via local stdout JSONL.
It forbids raw frames, private landmarks and unreviewed evidence references,
and marks heuristic scores as uncalibrated. A standalone synthetic trace
exporter and opt-in `--candidate-format v1 --confirm-consent` video runner
mode can generate it. **No live Meta/Backend ingestion is implemented.**

## Legacy Handoff contract to Member 2

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

## New — Clip-level evaluation workflow

The Member 1 evaluator runs locally using **authorized, human-annotated clips**
represented by JSONL pose traces, then outputs clip-level confusion-matrix
counts, precision, recall, F1, false candidates per negative-video hour and
(optional) post-onset detection latency. These metrics are meaningful **only
for the clips you actually label and evaluate**. The included two-clip
synthetic demonstration is only a parser/logic smoke test.

You can run the synthetic smoke test immediately:

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
python -m sentinel_edge.evaluation --manifest examples/synthetic/manifest.json
```

### Collect local pose traces from an authorized video

After installing the optional video extras and obtaining a licensed local
Pose Landmarker model, this command exports only four normalized torso
landmarks per frame. Pose traces can still be identifying and may be
sensitive. **Use exclusively with consented staged media.** Store them in a
local ignored folder and never publish them.

```powershell
# From services/edge-vision, use a local video you are authorized to analyze.
# Create the private output folder yourself (e.g. D:\staged-private\).
python -m sentinel_edge --source "D:\staged-private\fall1.mp4" `
  --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --trace-output "D:\staged-private\fall1.pose.jsonl" `
  --acknowledge-pose-privacy
```

The output path must end in `.pose.jsonl` and must not already exist. The
export is **opt-in and local**; neither video nor poses are sent to Meta.
The tool does not export screenshots or raw frames.

### Annotate ground truth and evaluate

Create a manifest alongside the exported clips (see
`examples/synthetic/manifest.json`). Each clip requires a pseudonymous
ID, a relative trace path, an explicit `expected_fall` boolean and a
nonempty `permission_basis` documenting consent or licensing. For positive
clips you may specify `onset_ms` for detection latency measurements.
Run from the folder above:

```powershell
python -m sentinel_edge.evaluation --manifest "D:\staged-private\manifest.json"
```

Options: `--min-hip-descent`, `--horizontal-min-angle-deg` and
`--horizontal-hold-ms` enable controlled sensitivity experiments.
Do not tune thresholds on the held-out evaluation set. Use distinct
participants for development and evaluation clips, and document camera
angle, fps and consent.

**Interpretation limits:** This is *clip-level* fall/no-fall scoring, not
frame or event boundary localization. It cannot validate emergencies,
patient outcomes, or clinical sensitivity. Falling subjects may be missed
if pose is occluded, stationary, or the visual perspective hides descent.
Perfect scores on the tiny synthetic fixtures are not evidence of accuracy.

## Privacy and licensing

MediaPipe is an external third-party dependency; check the Pose Landmarker model asset license and permitted redistribution before making the GitHub repository Public. Do not commit raw footage, `.task` binaries, research models or personal data.

Use the official task documentation. No capability or performance has been tested against actual video or real-world falls in the synthetic unit tests.
