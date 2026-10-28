# Member 1 — Temporal V1/V2 train-to-inference scaler parity

28 October 2026 · VIIL-Sentinel · **Research-only; NOT production alerting**

## Confirmed bug before patch

The fitted NumPy V1 and V2 logistic regression models both learned weights
using **train-subject-only** `mean` and `scale`, followed by a *z-score
clamp to [-12,+12]*. Two corresponding prediction functions inadvertently
used the unbounded standardized input instead:

- `TemporalLinearModel.predict_probability` in `temporal_training.py`
  (used by private V1 research weights and opt-in shadow inference).
- The internal V1/V2 `predict` closure in `model_quality._fit_candidate`
  (used for validation/held-out predictions, cross-subject research CV and
  the Tiny MLP V1 comparator).

This was not a training/validation split leak, but it **was a material
mathematical mismatch** for outlier features. On fully fictional unit inputs
with trained mean=0, scale=1, weight on one feature=1 and bias=-2,
outlier z=+1e9 returned 1.0 rather than the trained
[-12,+12]-bounded result of **0.9999546021**; z=-1e9 returned approximately
2.86e-20 rather than **8.31528e-7**.

## Narrow fix

A single `_normalize_for_fit_and_inference` function now handles both
fitting and prediction, accepting a 1D descriptor or nonempty 2D descriptor
batch. It checks finite features and finite, positive model normalizer
parameters; rejects wrong feature dimensions and invalid values before
computing a probability; and bounds normalized values to [-12,+12] for both
paths.

This fix preserves:
- The already-declared 30-D V1 and 40-D V2 architecture, train-only fitting
  subjects, validation threshold policy, held-out split semantics and
  original class balancing/optimizer hyperparameters.
- Original `TemporalFallDetector`, MediaPipe pose adapter, existing
  trained weight file format, camera incident reporting, backend/dashboard
  and auto-alert boundaries.
- Private research artifact hashes, human-review gates, publisher-label
  limitations and no remote media uploads.

**Important reproducibility note:** scoring semantics of extreme normalized
features have changed while old private research weights remain numerically
unchanged. Reports produced by older source commits are **not directly
interchangeable** with reports from this commit. Annotate the commit hash
when citing any diagnostic and regenerate comparisons reproducibly; do not
interpret historical deltas as an independent accuracy gain.

## Synthetic regression proof

Before the patch: **9 of 14 targeted synthetic tests failed**, including
V1 outlier disagreement, malformed/nonfinite inputs being scored rather
than rejected, and the missing V2 input checks. A deliberately
weak-signal 4-sample V2 fixture exposed the same outlier mismatch
(uncapped vs capped probability 1.0 vs approximately 0.999322;
similarly low-side ~0 vs 0.000678).

After the patch, focused tests, V1/V2 research comparison, full Edge,
Backend, lint and Dashboard builds must pass. No synthetic test result
is an estimate of recognizing a real person's fall.

## Rerun instructions

From `D:\\VIIL-Sentinel\\services\\edge-vision`:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest -q
.\\.venv\\Scripts\\python.exe -m ruff check .
.\\.venv\\Scripts\\python.exe -m sentinel_edge.model_quality --synthetic-demo --dev-crossval
```

Optional **previously exposed** CAUCAFall publisher-labeled dataset,
if present in ignored `data/private` (no new source download,
labels remain unreviewed):

```powershell
$root = "D:\\VIIL-Sentinel\\data\\private\\public-datasets\\caucafall-omnifall\\extracted\\Cauca_fall"
.\\.venv\\Scripts\\python.exe -m sentinel_edge.model_quality `
  --root "$root" `
  --groups "$root\\caucafall-research-groups-v2.json" `
  --segments "$root\\caucafall-review-proposals-v1.json" `
  --model "D:\\VIIL-Sentinel\\models\\pose_landmarker_lite.task" `
  --acknowledge-publisher-labels --acknowledge-pose-privacy `
  --dev-crossval
```

Treat all reported held-out counts as **previously examined,
pose-eligible, staged publisher-label diagnostics** — not independently
reviewed fall onset recall, prospective accuracy, real-world false alarm
rate, or permission to deploy. Do not reselect V1/V2 or retune thresholds
using those held-out outcomes.

## Verified run on this development iteration

**Local software validation:** **538 Edge pytest cases passed**, full Edge
Ruff passed, **6 Backend pytest cases passed**, Backend Ruff passed,
and Dashboard production build passed. The additional V2 outlier test
covers both 30-D and 40-D descriptors.

**Executed real, existing private publisher-label CAUCAFall pilot:** 40
source-action clips were processed by the already-existing local
MediaPipe pipeline, **35 passed** the predeclared pose-coverage gate.
Only **6 pose-readable old held-out clips** remained (4 staged Fall and
2 ADL); the other two test ADLs were abstentions, not negatives.

| Pre-existing, repeatedly exposed publisher-label research cohort | V1 | V2 |
|---|---:|---:|
| Validation TP / FN / FP / TN | 2 / 1 / 0 / 3 | 2 / 1 / 0 / 3 |
| Validation threshold | 0.95 | 0.63 |
| Old held-out TP / FN / FP / TN | 2 / 2 / 0 / 2 | 3 / 1 / 0 / 2 |
| Four-fold development CV TP / FN / FP / TN | **8 / 7 / 2 / 12** | **3 / 12 / 2 / 12** |

Four-fold **development-only** CV selected V1 in all 4 folds,
with 29 eligible development clips from 8 declared participants;
it did not train, select or validate on old held-out test people.
The frozen validation tie-break selection still selects **V1**.

The historical, same-clip, **pre-fix** development CV was
V1: **9 / 6 / 3 / 11** and V2: **4 / 11 / 3 / 11**.
The changed counts are a **preprocessing/scorer-version effect**
on already-examined data, not an accuracy gain; note also the old
held-out predictions remain numerically the same in this run.
This pilot did not reselect thresholds based on the test cohort.
Neither small staged publisher-labeled clip classification nor
subject-fold CV proves fall-event detection, operational false-alarm
rate, real-world performance or participant consent.

**Source/provenance:** 28 Oct 2026 local CLI with `--dev-crossval`,
private original `caucafall-research-groups-v2.json`,
`caucafall-review-proposals-v1.json` and locally installed official
PoseLandmarker Lite `.task`. No raw images, per-person predictions,
pose windows or model weights were committed.

**GitHub exact-commit CI:** Prior to promoting this research-only change,
verify the exact topic commit and team integration commit each pass backend,
edge-vision and dashboard checks. Record hashes and URLs in the handoff.
Do not push or merge into protected shared `preprod` or `main`.


## Next developer

First reproduce outlier numeric parity and the private-artifact V1 read-back
under the pinned Git SHA. For true model improvements obtain additional
independently reviewed Fall+ADL data and untouched actor/camera-separated
holdouts. Freeze pre-processing and its version together with any future
model artifact before rerunning new validation. Publish only aggregate
metrics when rights and independent review permit it.
