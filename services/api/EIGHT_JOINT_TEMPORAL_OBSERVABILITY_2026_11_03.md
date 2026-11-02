# VIIL-Sentinel — Eight-joint Temporal Observability, Local Research

**2026-11-03 (KST) · Member 2 · Real local research pose replay · no cloud AI**

## Outcome

Implemented and exercised **temporal feature extraction** using the five
previously extracted, licensed, private eight-joint MediaPipe pose traces.
This is NOT a trained classifier, multi-person tracker, fall confirmation,
person identification, physical speed measurement or production feature.

New files:

- `app/multi_joint_temporal.py`: pure bounded research function that
  calculates time-normalized **hip-center and ankle-center 2D image-plane
  velocity magnitudes** and absolute knee-angle change rate. Reports only
  the nearest-rank 95th percentile of each; no per-frame joint coordinates.
- `app/multi_joint_temporal_report.py`: exact five-clip research replay.
  Re-verifies the *original* human videos against pinned public Git blob
  and SHA-256, compares the prior 8-joint visibility baseline with the
  derived pose record count, and stores only aggregate quality statistics
  in ignored `data/private/eight_joint_pose_research_v1/`.
- `tests/test_multi_joint_temporal.py`: synthetic-only regression tests
  for continuity, occlusion, timestamp gaps, corrupted inputs, observability
  gates and non-effectful outputs.

No Member 1 Edge/RTSP runtime, model weights, caregiver API, Mobile,
Dashboard or Meta planning transport was changed.

## Continuity and privacy contract

A candidate temporal pair is calculated **only** when:

1. Both consecutive, strictly time-ordered frames contain all eight
   allowed shoulders, hips, knees and ankles (11,12,23,24,25,26,27,28).
2. All eight landmarks have `visibility >= 0.55`, and their 2D
   coordinates/visibility values are finite.
3. The frame interval is **≤200 ms**; a greater interval is omitted.
4. Both knee angles are geometrically computable (no collapsed joint
   vector). Missing joints break the chain, rather than being interpolated.

The observation window is **not continuous** if any of these fail.
A previously missing/low-visibility landmark cannot be connected to
a reappearing point in the next valid frame; this prevents artificial
velocity spikes across tracking outages.

**Conservative abstention policy**, all thresholds fixed before
executing the known-clip retrospective replay:

- At least **75%** of frames contain all eight joints.
- At least **50%** of adjacent frame intervals are eligible.
- At least **20** eligible consecutive-frame motion pairs.
- No run of more than **12 unusable frames** (from the prior
  Evidence Quality & Abstention engineering guardrail).

All of these are **uncalibrated engineering rules**, not clinical
thresholds, diagnostic confidence values or trained weights.

States are `abstain_missing_lower_body`,
`abstain_temporal_discontinuity` and
`exploratory_temporal_geometry_available`. Even the third state
means **geometry available to study**, not "no fall" or "fall".

Every record also explicitly states:
`person_identity_verified=false`, `confirms_fall=false`,
`confirms_no_fall=false`, `alert_permitted=false`,
`meta_upload_permitted=false` and
`raw_pose_coordinates_exported=false`.

**Very important:** The local MediaPipe extractor uses `num_poses=1`
and does **not** implement actual person association or cross-occlusion
tracking. It could switch persons if multiple appear; even two aligned
kinematic samples do not prove identity persistence. Camera movement,
perspective, zoom and occlusion can distort these quantities; the
velocity is **normalized image coordinates/second**, *not m/s*.

## Actual results — 5 previously inspected human clips

Upstream source:
[FallDetectionDataset](https://github.com/samruddhi-2308/FallDetectionDataset)
(CC BY-NC 4.0, noncommercial only, attribution required;
[license](https://github.com/samruddhi-2308/FallDetectionDataset/blob/main/LICENSE)).
All five clips were **seen during prior research** and may share subjects
and camera settings. This is a **retrospective observability diagnostic**,
not held-out evaluation or new fall-prediction evidence.

| Clip | Publisher class | Full video frames | Eligible temporal pairs | Longest missing 8-joint run | New status |
|---|---|---:|---:|---:|---|
| FD0012 | sitting_to_fall | 147 | 61 | 85 frames | **Abstain — missing lower-body coverage** |
| FD0032 | sleeping_to_fall | 231 | 101 | 120 frames | **Abstain — missing lower-body coverage** |
| FD0011 | sitting_to_fall | 216 | 146 | 69 frames | **Abstain — missing lower-body coverage** |
| FD0001 | adl_no_fall | 326 | 249 | 76 frames | **Abstain — long tracking gap** |
| FD0005 | adl_no_fall | 448 | 337 | 107 frames | **Abstain — long tracking gap** |
| **Total** | 3 Fall + 2 ADL | **1,368** | **894** | — | **5/5 abstained** |

Original 8-joint visibility coverages remain unchanged:
FD0012 **42.18%**, FD0032 **44.16%**, FD0011 **68.06%**,
FD0001 **76.69%**, FD0005 **75.67%**.
These are not clinically calibrated coverage or accuracy percentages.

Crucial additional finding: even the two ADL clips exceeding
75% all-point coverage contain **76 and 107 successive unusable
frames**. A simple "75%-covered" test would have *misleadingly*
marked those sequences suitable for continuous temporal analysis.
The bounded occlusion gate correctly abstains. This does **not**
mean either ADL clip is a fall; no event classification was attempted.

Approximate median/percentile movement statistics are computed locally
from the valid segments, but the p95 values cannot distinguish intent,
injury, floor contact, fall onset, stable person identity or physical
speed. They remain diagnostic observations only. No new model was
trained or fitted, no thresholds were tuned from these five clips,
and no Fall/No Fall confusion matrix was created for this milestone.

## Data controls

- Source MP4s are the existing noncommercial staged human recordings.
  No new media downloaded in this increment.
- Existing derived eight-joint JSONL contains potentially
  identifying motion time-series data and stays only in
  `D:\VIIL-Sentinel\data\private\eight_joint_pose_research_v1\`.
- Aggregate output:
  `data/private/eight_joint_pose_research_v1/aggregate-temporal-observability.json`.
- The CLI requires both
  `--acknowledge-noncommercial-license` and
  `--acknowledge-pose-privacy`.
- No images, source videos, raw coordinates or secret values were
  staged/committed, logged in the report, or transmitted to Meta.
- No paid calls were made and the existing 4/4 Meta local spend
  ledger was not reserved/reset.
- No person tracking across frames or re-identification is attempted;
  no incident/caregiver workflow is mutated.

## Reproduction

```powershell
cd D:\VIIL-Sentinel\services\api

# Offline, local, private-trace reanalysis. Requires the previous
# eight-joint extraction to exist already; does NOT re-extract media.
.\.venv\Scripts\python.exe -m app.multi_joint_temporal_report --evaluate-known --acknowledge-noncommercial-license --acknowledge-pose-privacy

# Fictional points only, no private media required:
.\.venv\Scripts\python.exe -m pytest -q tests/test_multi_joint_temporal.py

# Full regression:
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
cd ..\edge-vision
..\api\.venv\Scripts\python.exe -m pytest -q
```

## Next prerequisites and decision

**NO-GO** for autonomous alarms, triage, fall assurance or real-world
continuous safety monitoring.

The next worthwhile step is a **person-specific temporal association
research design** with explicit provenance/permission, an independent
actor-disjoint dataset, camera-movement handling, multiple poses
(`num_poses > 1`) with careful privacy/RBAC, and robust
occlusion/identity state. Only then consider training an incident
classifier or testing V2/V3 recognition against truly unseen
annotated falls and long-form ADL (reporting false reviews/hour,
onset-aligned latency, recall and abstention rate).

Do not treat the present four- or eight-joint features as a clinically
reliable Fall Detector. Human review is mandatory for any actual use.
