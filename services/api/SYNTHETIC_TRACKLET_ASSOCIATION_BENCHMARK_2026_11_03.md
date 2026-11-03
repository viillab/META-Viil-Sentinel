# VIIL-Sentinel — Ground-Truth Fictional Tracklet Association Benchmark

**2026-11-03 KST | Member 2 | Research-only | No real-person multi-person accuracy claim**

## Outcome

The earlier 8-point geometry matcher can silently exchange two people's
associations when the *sampled* scene swaps spatial positions between
adjacent frames. The eight torso/leg points alone cannot prove who is who.

A new deterministic synthetic benchmark with **eight fictional scenes**,
each replayed in **two modes** (16 experiments), was added in
`services/api/app/synthetic_tracklet_benchmark.py`. The reference actor
labels are **invented locally** and are used only during evaluation;
not saved in results. The benchmark measures adjacent reference
appearances, correct and wrong same-frame-index links, and deliberately
unlinked appearances. **It does not measure real tracking accuracy,
clinical fall metrics, calibrated confidence, IDF1/MOTA on real actors,
or any official benchmark dataset score.**

The default mode of
`services/api/app/anonymous_tracklet_research.py` is now
`multi_person_mode="abstain"`: it refuses association whenever **two
or more poses** are detected **or** two or more old anonymous local
tracklets remain. This is a strict, intentionally lossy default. The
previous behavior can only be enabled explicitly via
`TrackletPolicy(multi_person_mode="geometry_only")` for a fictional
research ablation. It is **not recommended for safety, alerts, medical
decisions or production deployment**.

When tracking only a single pose, the default matching behavior and
previous local five-clip retrospective were left unchanged.

### Results from the actual local synthetic benchmark

| Metric (8 original fictional scenarios) | Geometric ablation | Safe default: abstain |
|---|---:|---:|
| Reference adjacent actor appearances | 161 | 161 |
| Correct adjacent associations | 141 | 59 |
| **Wrong adjacent associations** | **2** | **0** |
| Reference appearances left unlinked | 20 | 102 |
| Frame-level abstention/gap resets | 9 | 56 |

Interpretation:
- The intentionally adversarial **indistinguishable spatial swap**
  makes the geometry-only matcher associate person A's previous
  position with synthetic B's next pose and vice versa. Its
  **2 wrong matches are directly established by fictional actor
  ground-truth labels**. They are not anecdotal and not a real-video
  observation.
- The default deliberately refuses all 2+ person association,
  so it avoids *these* false person matches at the cost of many
  fragmented/unlinked observations.
- The 161 denominator includes low-confidence frame appearances
  and timestamp discontinuities. Therefore "unlinked" includes
  deliberate safety abstentions and is **not a calibrated missed
  track or ID-switch rate**. An interrupted scene cannot be
  declared the same individual at the next observation.
- The zero wrong matches for the safe default is **only measured on
  these 8 scripted cases**, not proof that any real-world matching is
  safe or that the one-person stream cannot contain unnoticed
  identity switches.
- There is **NO GO** for actual multi-person linking; no video
  model was trained or calibrated and no person identity
  verification exists.

### Fictional scenarios

1. One silhouette moving gradually with full joint coverage.
2. Two well-separated fictional people whose detection order flips.
3. Two fictional actors exchange apparent spatial positions between
   adjacent timestamps — reveals an identity-switch vulnerability.
4. Approach, crowded overlap and separate — abstain near crossing.
5. Temporary disappearance and reappearance — start a new anonymous
   tracklet, no re-identification.
6. Lower-limb low-confidence occlusion — clear continuity.
7. Camera timestamp gap — do not interpolate through the gap.
8. One old silhouette becomes two matching candidates — ambiguous.

The tests verify fixed outcomes of both modes, privacy-safe aggregate
fields, bounds against malformed poses/policies, and the absence of
persistent track IDs. These fixtures are only **synthetic landmark
numbers** — no faces, identifiable human poses, downloaded multi-person
videos, camera feed or external provider connection.

## Existing five licensed single-person-maximum MP4s

The **original** local five videos from
[samruddhi-2308/FallDetectionDataset](https://github.com/samruddhi-2308/FallDetectionDataset),
licensed [CC BY-NC 4.0](https://github.com/samruddhi-2308/FallDetectionDataset/blob/main/LICENSE)
for noncommercial research with attribution, were already processed
with `num_poses=1` by MediaPipe. They are **not a real multi-person
validation set**. The local exact-source-hash and complete-frame
checks were rerun after changing the default policy:

| Retrospective local check | Result |
|---|---:|
| Existing private videos | 5 |
| Previously processed frames | 1,368 |
| Adjacent anonymous geometric links | 892 (unchanged) |
| Real multi-person frame-level data | **Not available** |
| Real person identity ground truth | **Not available** |

No raw person-derived joint trace, image, model weights or media was
uploaded, serialized in this Markdown, sent to Meta, or committed to Git.

## Reproduce offline

From `D:\VIIL-Sentinel\services\api`:

```powershell
# Requires no media, external services or paid APIs.
.\.venv\Scripts\python.exe -m app.synthetic_tracklet_benchmark --run

# Fictional-number unit tests only:
.\.venv\Scripts\python.exe -m pytest -q tests/test_anonymous_tracklet_research.py tests/test_synthetic_tracklet_benchmark.py

# Prior private single-pose replay (noncommercial and privacy acknowledged):
.\.venv\Scripts\python.exe -m app.anonymous_tracklet_report --evaluate-known --acknowledge-noncommercial-license --acknowledge-pose-privacy

.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

The synthetic report prints aggregate statistics only; the existing
real-video replay writes aggregate output exclusively to Git-ignored
`data/private/eight_joint_pose_research_v1`. Local Meta attempt
budget is already exhausted (4/4); this milestone makes **zero paid
Meta API calls**. Production Member 1 Edge detector and caregiver
notification paths remain unchanged.

## Next prerequisite

Acquire lawful/authorized **multi-person video**, independently
annotated persistent per-person identities and timestamps, diverse
camera angles, occlusion, full visibility and explicitly known
consent/license. Then validate an identity-aware matcher against
unseen actor-disjoint data, reporting identity switches, fragmentation,
recall, ambiguous scene fraction, latency and failure cases. No
auto-alert or safety claims until that validation passes. If
appearance features are ever considered, review their additional
privacy, retention and identification risks **before** implementation.
