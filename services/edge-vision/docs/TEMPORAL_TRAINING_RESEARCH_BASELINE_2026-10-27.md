# Member 1 — Supervised Temporal Research Baseline (2026-10-27)

## Executive status

**Executable NumPy research classifier trained on invented feature vectors.**
This is *not* a clinically validated fall model, a TCN/GRU, or a model trained
on human Fall/ADL video. No model weights are saved or deployed. MediaPipe
PoseLandmarker plus the existing TemporalFallDetector continue to handle
normal operations without any behavioral changes.

The previous **8-clip IKAR filmed staged-fall baseline remains 1 detected /
7 missed**. Its source dataset supplies no ADL negatives, so it cannot be
used alone to train or validate a binary Fall/No-Fall classifier. No live
Meta AI endpoint was invoked.

## Why this small model first

The local Edge Vision environment has **NumPy installed**, while PyTorch,
scikit-learn and scipy are not installed. This deliberately adds *no* large
training runtime, and validates the supervised learning/data quality loop
before undertaking a potentially heavier TCN or GRU experiment.

Architecture `pooled_temporal_logistic_v1_NOT_TCN_OR_GRU`:

1. Input **30 ordered frames × 6 previously implemented motion channels**,
   with explicit binary pose-observation masks. The preprocessing requires
   a complete, finite fixed-size window with at least 10 valid poses.
2. Mask-aware means over **5 chronological time bins**, 6 features per bin,
   producing a small **30-dimensional** time-aware descriptor. It keeps only
   coarse order; it is *not* a convolutional or recurrent network.
3. Training-only per-channel mean/std; constant features use unit scaling.
   A simple class-balanced L2-regularized logistic fit using NumPy,
   deterministic and with bounded iterations.
4. **Validation-subject-only** selection of a classification threshold
   based on balanced accuracy, with higher thresholds winning ties.
5. **Held-out test** evaluated after all parameters and threshold are fixed.
   Reports clip-level precision, recall, specificity, false positive rate
   and TP/FP/TN/FN counts. Clip metrics cannot establish event latency or
   false alerts per actual surveillance hour.
6. Trained weight vector (approx. **736 bytes** for weights, scaler,
   bias/threshold) stays in RAM. **No model artifact is written**;
   production incident detection and emergency actions are untouched.

## Reproducible synthetic proof-of-execution

From `D:\VIIL-Sentinel\services\edge-vision`:

```powershell
# NumPy is optional to the main MediaPipe runner
python -m pip install -e ".[training,dev]"

python -m sentinel_edge.temporal_training --synthetic-demo
python -m pytest -q tests/test_temporal_training.py
```

The demo creates **invented numerical features**, not real people/videos:
8 fictional training subjects × two classes, 3 validation subjects × two
classes, and 3 different test subjects × two classes (28 clips total).
On the executed run: train 16, validation 6, held-out test 6. The
deliberately separable synthetic samples returned TP=3, TN=3, FP=0, FN=0
on held-out *synthetic* IDs. **100% on these invented samples is NOT
a real-world model result and must never be presented as such.**

The code explicitly marks `synthetic_data_only=true`,
`human_dataset_accuracy_claim=false`,
`real_world_accuracy_established=false`, and
`automated_fall_alerting_authorized=false`.

This smoke test verifies that actual supervised fitting, masked temporal
features, train-only transforms, validation threshold selection and test
scoring execute. It does **not** verify correct recognition of falls.

## Real dataset input protocol (not yet fulfilled)

To operate on properly consented/licensed *real* inputs, BOTH files must
be supplied using fully separate private, ignored local paths:

```powershell
python -m sentinel_edge.temporal_training --manifest "D:\VIIL-Sentinel\data\private\research\groups-v2.json" --features "D:\VIIL-Sentinel\data\private\research\derived-30frame-windows.json"
```

`groups-v2.json`: the exact `split_audit.py` v2 schema with
`permission_basis`, `clip_id`, `dataset_id`, stable pseudonymous
`subject_id`, `recording_id`, `split` (`train`, `val` or `test`)
and explicit `expected_fall`. The split auditor blocks overlapping
subjects, recordings and media hashes across splits and requires BOTH
Fall + ADL in each partition.

`derived-30frame-windows.json` example *schema only*:

```json
{
  "version": 1,
  "feature_set": "experimental_pose_motion_v1",
  "windows": [
    {"clip_id": "pseudonymous-id", "features": [[0.0,0.0,0.0,0.0,0.0,0.0]]}
  ]
}
```

The illustration above intentionally contains only **one row** and would
be rejected by the trainer; each real example must contain exactly **30
finite numeric rows × 6 channels** matching `FEATURE_NAMES` and the
observed-mask semantics of `TemporalFeatureEncoder`. Each label must
have an exactly corresponding feature window. File size is capped and
raw media paths, human names, extra fields, missing classes, and
cross-split recording overlap are rejected. **No real media/pose dataset
was collected, exported, or committed in this task.**

An approved, separate window extraction and event-onset labeling process
is still needed. Per-clip binary labels should only be assigned to
windows that actually contain the target activity, with contamination
rules documented. Do not label every pre-fall upright segment as a Fall
without annotation.

## Dataset research and license gating

- IKAR (Opyrchał et al. 2026, AGH; CC BY 4.0): staged fall-only videos,
  DOI https://doi.org/10.58032/AGH/A1NZPE ; no ADL negatives.
- CAUCAFall (2022): 10 people, five fall categories and five ADL categories,
  DOI https://doi.org/10.1016/j.dib.2022.108610 . The *article* is open
  access, but the rights to each video repository file and consent must be
  independently reviewed **before download and training**.
- Video-Based Fall Detection Dataset (Ursul, figshare, 2025, CC BY 4.0
  dataset page), 2017 labeled activities from 29 people:
  https://figshare.com/articles/dataset/28596332 . Approx. 2.36 GB
  download; verify package-level licensing, annotations and genuine
  subject IDs before selecting a smaller authorized subset.
- CAUCAFall and other public research datasets contain volunteer-staged
  falls; **not guaranteed generalization to unexpected falls or older
  adults in care settings**.

No new third-party media or pretrained weights were bundled or downloaded.

## Next gated deliverables

1. License and participant metadata verification for a dataset containing
   Fall + ADL. Preserve separate individuals and camera sessions in splits.
2. Authorized offline **pose-to-window exporter** with participant-
   independent extraction, annotation of event boundaries, no leakage of
   held-out subjects and no identifying media/pose outputs in Git.
3. Re-run research baseline on actual unseen people. Only *then* assess
   whether it warrants a lightweight TCN/GRU using optional, separately
   installed training dependencies. Compare all alternatives against the
   unchanged heuristic with a consistent data split.
4. Evaluate realistic recall, false positive rate and false alarms/hour,
   temporal latency, memory, CPU, model bytes, and multi-person/occlusion.
   Human verification remains mandatory throughout.

All model evaluation claims should identify **synthetic** vs **real-human**
data, video type, scope, version, and the number of independent subjects.
