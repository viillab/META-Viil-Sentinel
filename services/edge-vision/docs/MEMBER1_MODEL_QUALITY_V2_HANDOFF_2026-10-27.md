# VIIL-Sentinel Member 1 — Model Quality V2 & Next Developer Handoff
27 October 2026 · Research prototype only · Owner: Member 1 (Edge Vision)

## Status, ownership and scope

- Development: `member1/feature/subject-calibrated-model-v2`
- Member-only integration: `member/feature/preprod`
- Shared `preprod` and `main`: HUMAN promotion ONLY. No automation pushes there.
- Edge-vision project: `services/edge-vision/`.
- No downstream alert/dispatch, camera server, dashboard, or Meta API behavior is changed.
- AI **pose inference works** on the isolated `.venv`. An offline fall classifier research
  experiment is **not** a deployable or clinically validated fall detector.

## What V2 adds (and does NOT claim)

The unchanged `temporal_training.py` baseline takes 30 samples × 6 channels,
calculates five mask-aware time bins (30 descriptor numbers), and fits a tiny
balanced L2-regularized NumPy logistic classifier. V2 introduces a second
candidate in `sentinel_edge/model_quality.py` using:
- **Original 30 numbers**, unchanged, PLUS
- **5 signed trajectory deltas**: last 10 sample slots minus first 10, each
  mask-aware and with zeros for absent subwindows, PLUS
- **5 within-clip standard deviations** of the *observed* first five motion
  channels. The sixth observation-mask channel is not duplicated.
- **40 derived numbers** total; two logistic candidates are fitted on the
  same declared train subjects using identical bounded regularization and
  deterministic 600 optimization steps. Class weights balance Fall and ADL.
- The model and threshold choice uses **only validation people**, maximizing
  validation balanced accuracy. V2 must exceed V1 by >0.01 or V1 is preferred.
  The test people are not loaded by the candidate chooser until it freezes
  that choice. Both candidates are reported on the same held-out test only
  for side-by-side **diagnostics**, never for selecting the promoted candidate.
- No pose windows, model weights, personal imagery, or trained classifier
  are persisted. No automatic fall alert path was modified.

This is a *quality/experiment framework*, not evidence that V2 actually
outperforms V1 on real-world falls. Both are compact linear models, NOT a
TCN, Transformer, GRU, calibrated probability or medical system.

## Environment — avoid global Python

Use `D:\VIIL-Sentinel\services\edge-vision\.venv\Scripts\python.exe`
(known working: Python 3.11, MediaPipe 0.10.35) because the Windows global
Python has a conflicting old MediaPipe 0.10.9/protobuf stack.

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
& $py -m sentinel_edge.doctor --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task"
& $py -m pytest -q
& $py -m ruff check .
& $py -m sentinel_edge.model_quality --synthetic-demo
```

A non-Git MediaPipe PoseLandmarker `.task` must already be on disk.
Do not publish or re-distribute it without verifying asset terms.

## Repeat actual 40-clip CAUCAFall publisher-labeled pilot

The private media and the TWO existing private manifests are at
`D:\VIIL-Sentinel\data\private\public-datasets\caucafall-omnifall\extracted\Cauca_fall`.
No need to overwrite the manifests: the new runner **reads existing** files.
It checks that private paths stay within the Git-ignored `data/private` root,
verifies media SHA-256 against the manifest before decoding each video,
validates declared subject/recording/media-split disjointness and labels,
and processes 30×6 feature windows in RAM only.

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$root = "D:\VIIL-Sentinel\data\private\public-datasets\caucafall-omnifall\extracted\Cauca_fall"
& .\.venv\Scripts\python.exe -m sentinel_edge.model_quality `
  --root "$root" `
  --groups "$root\caucafall-research-groups-v2.json" `
  --segments "$root\caucafall-review-proposals-v1.json" `
  --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --acknowledge-publisher-labels --acknowledge-pose-privacy
```

**Permission/label caveat:** CAUCAFall/OmniFall publisher action annotations
are not independently human-reviewed. `label_reviewed=false` is intentional,
not a problem to silently fix. Re-check license attribution and rights in
Zenodo 17170592 and the original Mendeley CAUCAFall before public use.
Never commit `data/private`, features, raw videos or pose traces.

## Measured same-clips CAUCAFall pilot (isolated runtime, 27 Oct 2026)

Actual local MediaPipe pose inference processed 40 staged-action videos.
**35/40** passed the predeclared pose-quality gate. The held-out test had
4 readable Fall clips and **only 2/4 readable ADL clips**. Two ADLs were
**abstentions**, not true negatives. Both models used the same filtered
subjects/media, train-only scalers and validation-only threshold calibration.

| Metric | Frozen baseline V1 | Experimental dynamics V2 |
|---|---:|---:|
| Trainable numeric state (approx.) | 736 bytes | 976 bytes |
| Validation TP / FN / FP / TN | 2 / 1 / 0 / 3 | 2 / 1 / 0 / 3 |
| Validation-selected threshold | 0.95 | 0.63 |
| Held-out TP / FN / FP / TN | 2 / 2 / 0 / 2 | 3 / 1 / 0 / 2 |
| Held-out Fall recall | 2/4 (50%) | 3/4 (75%) |
| Held-out ADL specificity | 2/2 (100%) | 2/2 (100%) |
| Held-out scored / selected clips | 6 / 8 | 6 / 8 |

**Selection result:** Validation balanced accuracies **tie**. By the
predeclared complexity rule, the selected model remains **V1**. V2's
+1 held-out correctly detected staged fall is diagnostic only, and
**MUST NOT be used retroactively** to change the selection rule or tune
the model on these same test people. The old temporal heuristic has
0/4 recall on these same 6 pose-readable test videos.

These results are *extremely uncertain*, reflect pose-quality selection
and publisher—not independently reviewed—labels, and cannot establish
real-world reliability. Any next training/tuning cycle needs a **new,
predeclared, untouched set** of real participant/ADL recordings.
Do not advertise the V2 diagnostic +25 percentage points as a certified
generalization improvement or deploy it to emergency alerting.

## Data and evaluation protocol

`groups-v2.json` is required to include:
`version=2`, bounded `permission_basis`, exact clip keys
`clip_id, dataset_id, subject_id, recording_id, split, expected_fall,
media_sha256` (digest optional in generic parser but **required by real
publisher pilot**). Split membership must be disjoint by declared subject,
recording and SHA-256 across train/val/test. All three splits need positive
and negative examples. Declared IDs are not independently identity-verified.

`segments-v1.json` includes video-relative `video`, `start_ms`,
`end_ms`, explicit `expected_fall`, publisher annotation provenance and
`label_reviewed=false`. `window_export.py` intentionally REJECTS this
unreviewed input: the research-only pilot can fit from publisher labels
without ever asserting human independent review.

A pose frame contains exactly 6 channels in `motion_features.FEATURE_NAMES`,
mask = 0 or 1, missing-frame channels all zero, and a clip is eligible only
with at least 10 valid pose slots out of 30. Report both **eligible clip**
and **abstention** counts and **condition** all headline metrics on eligibility.

## Promotion rules for future ML work

1. Freeze dataset revision/split IDs and licenses **before** experimentation.
2. Train feature scalers on *train people only*; tune hyperparams/decision
   threshold on *validation people only*. Never inspect held-out test scores
   to select/alter the classifier (if you do, freeze a new untouched test set).
3. Prioritize additional ADL negatives across lighting, clothing, camera
   angles, sit/lie/kneel and occlusion, **with actual annotation review**.
4. Evaluate fall recall, specificity, abstention rates, exact TP/FN/FP/TN,
   Wilson intervals, false alerts per observed negative-video hour, event
   onset latency, CPU, RAM, model bytes, FPS and multi-person association.
   A 6-clip pose-eligible test with just 2 ADLs **cannot** show real-world
   robustness; 2/2 TN is not a deployment-grade specificity estimate.
5. Consider group-aware repeated outer folds *for research only*, while
   keeping a never-touched final evaluation cohort.
6. Only after larger independent validation should the next developer
   consider ONNX/TFLite, an actual TCN/GRU, or shadow inference. Never wire
   an unvalidated experiment into live care/emergency paths.

## Key files for handoff

| File | Responsibility |
|---|---|
| `sentinel_edge/model_quality.py` | New V1/V2 comparison, CLI, no disk artifacts |
| `sentinel_edge/temporal_training.py` | Original V1 unchanged (reference) |
| `sentinel_edge/caucafall_curator.py` | Private publisher-labeled pilot and pose-quality exclusions; injectable research trainer |
| `sentinel_edge/window_export.py` | Separate reviewed private window export (requires human review) |
| `sentinel_edge/split_audit.py` | Subject/recording/media digest leakage checks |
| `tests/test_model_quality.py` | Mask contract, baseline parity, test-label/feature anti-leakage, CLI gate |
| `tests/test_caucafall_pilot.py` | Fake-video numerical integration and tamper guards |

## Next developer's first PR

Create a NEW `member1/feature/*` branch, add a clearly separated
independently labeled ADL set and ground-truth fall timing; write new
evaluation tests **before** changing model hyperparameters. Re-run the
commands above, include confusion matrix and abstentions with denominators,
document model bytes and runtime. Commit/push your topic branch; only after
checks merge to `member/feature/preprod`. Never push shared `preprod` or `main`.

Rollback: revert only the next Member1 topic/merge commit(s) via reviewed
Git revert if needed; `temporal_training.py` and all production alert
routes remain unchanged.
