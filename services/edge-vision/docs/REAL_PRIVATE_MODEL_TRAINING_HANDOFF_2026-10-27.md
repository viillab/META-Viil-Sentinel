# VIIL-Sentinel Member 1 — REAL Public-Video Training & Private Model Artifact
27 October 2026 · Publisher-labeled research only · **NOT deployable**

## Actual work (not synthetic training)

The original NumPy `TemporalLinearModel` V1 *already supports fitting*;
the previous experiments fitted it temporarily in RAM. This delivery
adds a **reproducible way to fit it on public Fall+ADL videos, serialize the
real numeric trained scaler/weights/threshold, strictly reload it,
and keep every artifact inside ignored `data/private`**.

Model architecture:
`pooled_temporal_logistic_v1_NOT_TCN_OR_GRU`.
MediaPipe Pose Landmarker Lite streams actual videos in memory; a
30-frame mask-aware window becomes a **30-dimensional descriptor**;
L2-regularized, class-balanced logistic regression is trained by 600
deterministic NumPy gradient steps. **All mean/scaler/weights use TRAIN
subjects only.** Balanced-accuracy threshold is selected on declared
Validation participants only, before the Test clips are scored. The
old unreviewed held-out subject metrics are reported for diagnostics
only and must not be used to reselect a threshold.

This is a truly **trained** statistical classifier, not a randomly
initialized model, synthetic-number benchmark, or TCN/GRU. It is not wired
into edge realtime inference, notification dispatch or the backend.

## Reproduction (isolated Windows environment)

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$pose = "D:\VIIL-Sentinel\models\pose_landmarker_lite.task"
$private = "D:\VIIL-Sentinel\data\private"
$gmdcsa = "$private\public-datasets\gmdcsa24-mini"

& $py -m sentinel_edge.private_model_training `
  --root $gmdcsa `
  --groups "$gmdcsa\gmdcsa-research-groups-v2.json" `
  --proposals "$gmdcsa\gmdcsa-publisher-proposals-v1.json" `
  --pose-model $pose `
  --output "$private\gmdcsa24-v1-publisher-research-20261027.json" `
  --acknowledge-publisher-labels --acknowledge-pose-privacy
```

For the already-local CAUCAFall data, use the exact same CLI with root
`$private\public-datasets\caucafall-omnifall\extracted\Cauca_fall`,
`caucafall-research-groups-v2.json`,
`caucafall-review-proposals-v1.json`, and a new private output
`$private\caucafall-v1-publisher-research-20261027.json`.

**No overwrite** is permitted. To train another version, choose another
output filename; never silently edit an existing model. The same video
sources are verified by SHA-256 on every run. Read outputs in the source
checkout only: no model file is pushed or uploaded.

## Actual completed runs (27 Oct 2026)

Both commands were run **on real local videos** and both 30-dimensional
weight artifacts were saved and reloaded successfully:

| Dataset | Selected / eligible | Fit clips (train people) | Val clips | Frozen threshold | Held-out diagnostic |
|---|---|---|---|---|---|
| GMDCSA-24 | 16 / 16 | 8 (2 people) | 4 (1 person) | **0.79** | TP 0, FN 2, FP 0, TN 2 (Subject 4) |
| CAUCAFall | 40 / 35 | 23 (6 people) | 6 (2 people) | **0.95** | TP 2, FN 2, FP 0, TN 2 (Subjects 9–10, eligible only) |

Two files created in the **original checkout's ignored private root**:

- `D:\\VIIL-Sentinel\\data\\private\\gmdcsa24-v1-publisher-research-20261027.json`
- `D:\\VIIL-Sentinel\\data\\private\\caucafall-v1-publisher-research-20261027.json`

GMDCSA coverage: **16/16** (8 Fall / 8 ADL).
CAUCA coverage: **35/40**; five unreadable windows abstained,
including two ADL clips in its old Test set.

These are independent research models; **do not combine** their two
held-out confusion matrices or claim one model was jointly trained.
Neither includes human-reviewed event-onset intervals and neither
has a fresh untouched test cohort. In particular, GMDCSA's zero of
two staged Falls from the test person is an observed generalization
failure, NOT evidence that a deployed product can detect real falls.

## Private artifact contract

Format: strict JSON with `version=1`, architecture name,
`dimension=30`, three arrays `mean`, `scale`, `weights` (30
float64 values each), scalar `bias` and `threshold`, plus SHA-256 of
each source manifest, dataset ID, and explicit publisher/unreviewed and
no-deployment flags. No full 30x6 motion windows, clip IDs, frames,
video, identifiable reviewer IDs or fitted per-person traces are
persisted. Each model has ~**736 bytes** of numeric NumPy
parameters in memory (strict JSON takes slightly more disk space).

Use `sentinel_edge.private_model_training.read_private_artifact(path)`
to validate architecture, provenance shape and finite numeric values
and load a `TemporalLinearModel`; accept it for *offline research
predictions only*. The full live edge candidate/alert path **does not load
or dispatch based on this model**. Export is always opt-in and requires
acknowledgement that publisher action labels are **not independently
human-reviewed**. The rights and privacy assumptions remain for
review by project maintainers before publication or distribution.

## Dataset, splitting and model-readiness caveats

**GMDCSA-24**: Ekram Alam (2024), public source repository MIT license,
https://github.com/ekramalam/GMDCSA24-A-Dataset-for-Human-Fall-Detection-in-Videos,
pinned upstream commit `5abac7693229900cf80f722e878fbb119211fc1c`.
16 chosen local videos (Fall 8, ADL 8) from four distinct subjects:
train S1–S2 (8), validation S3 (4), old held-out S4 (4).
All 16 clips passed the preset 10/30-pose quality gate.
Existing test subject S4 had only 2 Fall clips and previously **0/2
detected** by both V1/V2; this outcome is not useful for future
hyperparameter changes because it has been observed repeatedly.

**CAUCAFall (OmniFall publisher derivative, CC BY 4.0)**:
40 publisher-action clips from ten declared people; five failed
pose quality. Train subjects 1–6, validation 7–8 and old Test 9–10.
These models are independent research fits and MUST NOT be presented as
a jointly trained ensemble, verified clinical model or reliable safety
classifier. Dataset copyrights, likeness rights and participant-consent
conditions may need additional review even if a repository declares a
permissive license.

**Known limitations:**
- Sources use publisher class labels, not independently reviewed fall
  onsets; actual dynamic windows may mix pre-fall and post-fall posture.
- Very few individuals; biased staged scenes and changing camera layouts.
- Test sets have been inspected in past research, so a genuinely new
  untouched subject/domain test cohort is required before model promotion.
- No measurement of false alarms per hour, time-to-alert, multi-person
  tracking or resource usage on production edge hardware.
- A private model file does not mean the model is deployed, validated,
  or safe for autonomous incident response.

## Immediate next developer tasks

1. Inspect the **actual private artifacts** with strict loader, source
   digests, model dimension and threshold; do not commit their contents.
2. Use more licensed diverse videos with genuine subject identity and
   independently validated action labels; retain immutable source URLs,
   expected hashes, splits and local private files.
3. Build a separate, larger totally untouched test cohort (new people,
   independent camera scenes) *before* any new hyperparameter or architecture
   search. The exposed GMDCSA subject 4 and CAUCA subjects 9–10 should
   be treated as development diagnostics going forward.
4. Re-run actual in-memory MediaPipe and candidate comparisons on frozen
   train/validation sets; measure event-level recall and operational
   false positives per negative-video hour, plus uncertainty and abstention.
5. Only consider a production inference adapter after passing the
   preceding evidence, latency/RAM and safe-human-confirmation gates.
6. Commit the next small change in `member1/feature/*`, validate all
   tests and Ruff, merge only into `member/feature/preprod`.
   **Never modify human-only `main` or shared `preprod`.**

**Quick checks:**
`& $py -m pytest -q`; `& $py -m ruff check .`.

The user may retrain using new publisher-licensed clips, but these
research weights must not be deployed as automatic emergency alerts.
