# VIIL-Sentinel — Cross-Dataset V1 Offline Research Training
27 October 2026 · Member 1 · Research / publisher labels only

## Purpose

Train **one** real V1 NumPy temporal logistic classifier using both local
public CAUCAFall (publisher CC BY 4.0 derivative) and GMDCSA-24 (GitHub
MIT repository, pinned public revision) at once, rather than two separate
tiny source-specific models. This is a **new experiment, NOT a validated
production improvement or a deployed fall-alert model**. Neither source
contains independent human-reviewed fall-onset ground truth in the current
private research data.

Both media sources have previously been used in candidate evaluation; their
existing Test individuals' results have been examined. **The same TEST
cohorts are NOT new unbiased heldout tests.** The report marks them
`old_exposed_test_diagnostic`; no promotion decision can use them.

## Training method and guardrails

1. Reuse `publisher_label_pilot(..., collect_only=True)` so the existing
   MediaPipe Lite streaming decoder, 30-frame 6-channel masked pose window,
   per-file SHA-256 validation, label_reviewed=false enforcement and
   10/30 observed-frame filter stay the same. `collect_only` does not train
   or score the test per source.
2. Combine **only after** both original manifest audits; then run a fresh
   audit on all subjects, recording IDs and media digests across datasets.
   Exact source identities must be `caucafall-omnifall` and `gmdcsa24`.
   If any source/recording/subject/hash overlaps incompatible splits,
   abort rather than silently dropping data.
3. Train the **original frozen V1** on *TRAIN* individuals only with
   train-only normalization and balanced, regularized logistic gradients.
   Choose ONE threshold from *VALIDATION* individuals only. Do not add
   hyperparameter tuning from previous exposed TEST clips.
4. Record old held-out per-dataset confusion counts strictly as diagnostics,
   with true positive, false negative, false positive, true negative and
   denominator. Do NOT use their scores to select V1/V2, to change
   threshold, to market reliability or to enable autonomous alerts.
5. Save only 30D numeric mean, scale, weights, bias and threshold as a strict
   private JSON research artifact, with provenance hashes aggregating both
   source manifests and both publisher-proposal manifests in source order.
   Never write 30x6 motion windows, raw frames, full pose landmarks, clips
   or human identifiers to Git or any external service.
6. Verify the private JSON artifact via the existing safe loader and
   numerical array equality. The file cannot overwrite an earlier fit.

## Run on the authorized Windows workspace

Use Python from the **isolated** `services/edge-vision/.venv`:

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$p = "D:\VIIL-Sentinel\data\private"

& $py -m sentinel_edge.joint_dataset_training `
  --cauca-root "$p\public-datasets\caucafall-omnifall\extracted\Cauca_fall" `
  --gmdcsa-root "$p\public-datasets\gmdcsa24-mini" `
  --pose-model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --output "$p\joint-cauca-gmdcsa-v1-publisher-research-20261027.json" `
  --acknowledge-publisher-labels `
  --acknowledge-pose-privacy

& $py -m pytest -q
& $py -m ruff check .
```

`--acknowledge-publisher-labels` means that only source/publisher activity
labels are being used, **not** that they are independently reviewed.
`--acknowledge-pose-privacy` means raw image/derived person poses must
remain private. Neither flag proves consent. Confirm license conditions and
participant rights before any distribution or commercial reuse.

**Output:** Original local workspace
`D:\VIIL-Sentinel\data\private\joint-cauca-gmdcsa-v1-publisher-research-20261027.json`.
Expected: research-only 30D strict-loadable JSON; never add to git.

## Interpretation / acceptance

- Assess eligibility on ALL input videos; report selected, pose-eligible and
  abstained counts per source (and aggregate Train/Val/Test).
- Distinguish training clips from clips merely decoded for diagnostics.
- Cross-dataset subject and file identity audits apply to the **combined**
  manifest, not just each source.
- Real reliability is NOT established by scoring previously exposed Test
  subjects; avoid claimed improvement based on these numbers.
- This lightweight fit does NOT train an actual GRU/TCN and does NOT
  change backend/dashboard alarm behavior.
- Before trying candidate architectures or model promotion, freeze a **fresh
  subject/camera-disjoint external cohort**, verify publisher/human action
  labels and evaluate false alerts/hour on long ADL videos.
- Extend with additional licensed hard-negative ADL actions (fast sitting,
  bending, reaching, sudden lying, stumbling), keeping recording groups and
  split identities correct. Revisit temporal event-onset annotations.

## Actual local joint training run (27 October 2026)

The command above **ran successfully on genuine public staged videos**,
and the combined fitted V1 model was written and reloaded under ignored
`data/private`. The same subject-disjoint rule held across both datasets.

| Stage | CAUCAFall | GMDCSA-24 | Combined |
|---|---:|---:|---:|
| Publisher-labeled videos selected | 40 | 16 | **56** |
| Pose-eligible | 35 | 16 | **51** |
| Low-pose abstentions | 5 | 0 | **5** |
| TRAIN clips used for model fitting | 23 | 8 | **31** |
| VALIDATION clips used for threshold selection | 6 | 4 | **10** |
| Previously exposed TEST clips, scored diagnostically | 6 | 4 | **10** |

- Joint threshold selected from VAL subjects **0.53**.
- Joint model: 30-dimensional pooled temporal logistic V1; **736 bytes**
  of float64 mean/scaler/weights and numeric bias/threshold in memory.
- Validation: TP 5, FN 0, FP 1, TN 4 (Fall recall 5/5, ADL
  specificity 4/5). These are **validation-selection numbers**, not
  independent field accuracy.
- Existing exposed Test across both sources: TP 3, FN 3, FP 0, TN 4.
  CAUCAFall subset TP 2/FN 2/FP 0/TN 2; GMDCSA subset
  TP 1/FN 1/FP 0/TN 2. These **cannot support model promotion**
  because previous work has repeatedly inspected these clips/labels.
- The old source-specific GMDCSA V1 had TP 0/FN 2; joint V1 has
  TP 1/FN 1 on the same prior-exposed tiny pair. That difference is
  an exploratory diagnostic, **not** a statistically valid improvement.
- Both sources' publisher labels are still **NOT independently
  human-reviewed**, and test coverage is too small to measure real-world
  false alerts/hour.

This run created just one new local model JSON file, which stays private.
The new code, synthetic regression tests and documentation can be committed
and publicly reviewed; the actual weight file and derived pose data cannot.

## Branch policy / developer handoff

Commit source and synthetic tests only on `member1/feature/*`, then merge
to `member/feature/preprod` after the full Edge suite and Ruff pass. Never
merge into shared `preprod` or human-only `main`.

The next Developer can use `sentinel_edge.private_model_training.read_private_artifact`
for **offline evaluation only**; it will not autonomously alert or call
emergency services.
