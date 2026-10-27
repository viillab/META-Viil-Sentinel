# Member 1 — Development-Subject Cross-Validation Handoff (27 Oct 2026)

**Scope:** `services/edge-vision` research pipeline; no incident routing, alerts,
medical claims, production threshold change, weight export or cloud upload.

## Why this exists

Our fixed CAUCAFall pilot used **40 selected staged-activity clips** from ten
declared publisher subjects; five clips failed the 10/30-pose-observation gate.
Only **six pose-readable test clips** remained (four Fall, two ADL).
Previously V1 scored 2/4 held-out falls, while V2 scored 3/4; both correctly
classified the only 2 eligible test ADLs. However **validation was tied**,
so the predeclared simple-model tie-breaker retained V1. The diagnostic
held-out delta must NOT be reused to revise thresholds or model choice.

An extra **independent test cohort is still missing**. We must not confuse
repeated evaluation on the old held-out subjects with fresh evidence.

This feature introduces an **opt-in diagnostic on development people only**
to quantify how unstable V1/V2 may be when the participant changes.

## Four-fold nested subject-isolated protocol

- The v2 dataset manifest and 30 × 6 pose feature bundle are validated by
  existing `_validate_bundle` (dataset, subject, recording and hash split audit).
- Only clips declared as `train` or `val` enter CV. The original
  `test` split is NEVER pooled, optimized, classified or used for CV metrics.
- Require **8–64 unique development subjects**. Sort pseudonymous declared
  subjects, assign them cyclically into **four outer folds**. Every person
  belongs to exactly one outer fold.
- For outer fold `i`, inner validation uses fold `(i+1) % 4`, while the
  other **two folds** provide fitting data. Outer/inner/fitting people
  must be disjoint in that run. Each subset requires Fall and ADL;
  fail rather than silently dropping an invalid fold.
- Fit V1 (30 pooled descriptors) and V2 (40 masked dynamics descriptors)
  with each fold's **training subjects only**. Each candidate's threshold
  is tuned on inner validation people only (higher thresholds break ties).
  The exact existing margin **V2 balanced accuracy > V1 + 0.01** selects
  that fold's V2, otherwise V1.
- Outer-fold predictions are concatenated exactly once per development clip
  to aggregate TP, FN, FP, TN for `baseline_v1`, `dynamics_v2`,
  and `inner_selected`; report four-fold selection counts. Aggregate
  reports never include clip identifiers, subject IDs, model weights, or
  derived 30 × 6 windows.
- **Critically, CV never changes** the previously frozen V1/V2 choice or
  thresholds used by `compare_models`. It is an optional audit, NOT a
  justification to reselect using the old final test.

This is *not* repeated independent trials of people, nor nested search across
many architectures; participants can train other folds, the outer folds share
training samples, publisher labels are not independently verified and
pose-coverage selection can create severe bias. Do not present the aggregate
counts as deployable fall detection accuracy.

## Run locally

Use the isolated environment; Windows global Python has conflicting MediaPipe
and protobuf installs. From the checkout:

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
& $py -m pytest -q
& $py -m ruff check .
& $py -m sentinel_edge.model_quality --synthetic-demo --dev-crossval
```

The synthetic example uses **entirely invented numeric motion** and must
never be cited as fall-recognition accuracy.

For CAUCAFall publisher-labeled real staged video, existing **private**
extracted files and manifests must already exist; `--dev-crossval`
only adds in-memory NumPy calculations **after the same one-pass video
decoding**, without writing pose features or model artifacts:

```powershell
$root = "D:\VIIL-Sentinel\data\private\public-datasets\caucafall-omnifall\extracted\Cauca_fall"
& $py -m sentinel_edge.model_quality `
  --root "$root" `
  --groups "$root\caucafall-research-groups-v2.json" `
  --segments "$root\caucafall-review-proposals-v1.json" `
  --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --acknowledge-publisher-labels --acknowledge-pose-privacy `
  --dev-crossval
```

The output includes `development_crossvalidation` with aggregate results,
fold counts, the number of development subjects, and an explicit
`independent_final_test_subjects_used=0` marker for this *new CV only*.
It also includes the original `heldout_test` and
`pose_quality_filter` sections from prior research for backward
compatibility. The presence of a `heldout_test` section does **not** mean
the CV uses those subjects; the separate fixed-model comparison still
reports the same old held-out test.

## Actual CAUCAFall development-CV observations (27 Oct 2026)

Executed the exact command above in the isolated local MediaPipe environment
on the existing **40 published staged-action videos**, without writing raw
images, feature files or weights. After pose filtering, 35 clips remained:
**29 development clips across 8 declared people** and **6 held-out test
clips across 2 declared people**. Only the 29 development clips were
evaluated by this new four-fold CV.

| Aggregated OUTER development folds | V1 (30D) | V2 (40D) | Inner-selected |
|---|---:|---:|---:|
| True Positive / False Negative | 9 / 6 | 4 / 11 | 9 / 6 |
| False Positive / True Negative | 3 / 11 | 3 / 11 | 3 / 11 |
| Fall recall | 9/15 = **60%** | 4/15 = **26.67%** | 60% |
| ADL specificity | 11/14 = **78.57%** | 11/14 = **78.57%** | 78.57% |
| Inner-validation selected folds | 4/4 V1 | 0/4 V2 | V1 all folds |

**Interpretation:** The more complex V2 behaves markedly worse on this
development-person rotation. The existing V1 preference is supported by
these results. In the **old, repeatedly examined** fixed held-out set, V2
still scored 3/4 Fall vs V1 2/4; that single-clip difference is not sound
grounds to override the development-CV trend or promote V2. No new independent
test people were added here.

**No production claims:** Outer CV folds share training participants across
runs; the data remain staged and publisher-labeled, and only pose-readable
clips are scored. Further safety claims require new human-reviewed subjects,
more normal activities, pose-failure-aware evaluation and operational-time
false-positive measurement.

## Source layout for next Developer

| File | Contract / responsibility |
|---|---|
| `sentinel_edge/dev_crossval.py` | Four-fold development-subject diagnostic; no disk writes |
| `sentinel_edge/model_quality.py` | Optional `--dev-crossval` CLI, unchanged default candidate selection |
| `sentinel_edge/caucafall_curator.py` | One-pass MediaPipe collector and pose abstention reporting; duplicate dead reporting removed |
| `sentinel_edge/split_audit.py` | Prevent declared people/recordings/media leakage |
| `tests/test_dev_crossval.py` | Tests on wholly invented data, including perturbing held-out test labels/feature vectors |
| `tests/test_model_quality.py` | Frozen V1/V2 behavior and no test-set influence on selection |

## Remaining gating work / acceptance for future model promotion

1. Independently review the publisher interval labels and source/derivative
   redistribution terms before any dataset/model publication.
2. Enlarge **daily-living negatives**, especially lying, sitting, bending,
   kneeling, occluded actions and camera-height variations, under an
   explicit source/provenance policy.
3. Freeze a **new untouched final cohort** with independent people/sessions;
   never use the old test subjects to choose a new model because their
   metrics were already inspected repeatedly during development.
4. Quantify fall onset latency, false alerts per negative surveillance
   hour, recall, specificity and **pose abstention rates**, with person-level
   intervals and uncertainty across relevant hardware and lighting.
5. Benchmark cold start, decode FPS, RAM/CPU, model size, battery and
   multi-person tracking on target edge devices.
6. Create the next `member1/feature/*` from the latest integration base.
   Add tests first and push it, merge after successful checks to
   `member/feature/preprod`. Do not directly change `preprod` or `main`.

**Rollback:** revert the integration merge through Git's reviewed process,
or disable the CLI's optional `--dev-crossval`; the original
`compare_models` and incident pathways still work without it.
