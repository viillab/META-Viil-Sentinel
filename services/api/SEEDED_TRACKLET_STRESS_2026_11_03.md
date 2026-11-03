# VIIL-Sentinel — Seeded Association Stress & Fail-Closed Input Recovery

**2026-11-03 (KST) · Member 2 · Research-only · Executed offline on fictional poses**

## Outcome

Implemented and executed a **deterministic 32-seed, eight-family** stress
corpus, giving **256 original fictional scenes** and **512 policy replays**
(`abstain` vs the explicitly opt-in `geometry_only` comparison).
This is NOT real-person multi-person testing, clinical validation, fall
inference, tracking model training, IDF1/MOTA, or deployment.

The key new failure mode is **single-detection actor substitution**:
even when the detector outputs *only one pose per frame*, person A can
disappear and person B occupy A's previous position in the **next**
sampled frame. Without a missing-frame marker, appearance, externally
verified occupancy or per-person ground truth, the pose stream does not
provide a way to tell that identity has switched. **The current default
multi-person-abstain mode still makes an incorrect fictional link.**
Do NOT claim zero identity switches or trustworthy person continuity
from the earlier 8-case benchmark.

All 32 seeded invisible-handoff scenes produced **one false association
each** under the default. This is a constructed counterexample,
not an estimated real-world rate.

## Exact locally executed synthetic results

Eight scenario families × 32 fixed pseudorandom geometry seeds:

| Fictional association metric | Opt-in geometry-only ablation | Current multi-person-abstain default |
|---|---:|---:|
| Ground-truth adjacent actor appearances | 7,808 | 7,808 |
| Correct adjacent fictional links | 7,328 | 2,240 |
| **Incorrect fictional links** | **96** | **32** |
| Reference adjacent appearances left unlinked | 480 | 5,568 |
| Frame-level abstentions or time resets | 224 | 2,656 |
| Fictional examples with incorrect links | 64 | 32 |

Error attribution:
- **32 wrong links in both modes**: 32 single-pose same-position
  actor-handoff scenes. The conservative crowd guard cannot detect the
  swap because no frame has more than one person.
- **64 additional wrong links in `geometry_only`**: two fictional
  people fully exchange spatial positions between sampled frames,
  causing two wrong links × 32 seeds. The default deliberately refuses
  this entire multi-person association.
- In all other six scripted families the conservative default did not
  make an incorrect link **in this mathematical corpus**. That is NOT
  evidence of field identity accuracy or a zero-real-world-error rate.
- Ground-truth reference transitions count same fake actor IDs in
  adjacent frames, including deliberately withheld observations.
  An actor-handoff false link is an extra incorrect edge and is
  **not a genuine reference transition**. Consequently
  `incorrect_links` should NOT be treated as ordinary misses,
  and these totals are not tracking-accuracy benchmarks.

The families are:
`single_subject_jitter`, `invisible_single_pose_handoff`,
`two_people_pose_order_shuffle`, `two_people_full_position_swap`,
`two_people_near_crossing`, `single_pose_occlusion`,
`camera_time_discontinuity`, and `three_people_shuffled`.
Each seeded scene has 20 frames of original fictitious numeric skeletons.

Determinism: Python standard-library `random.Random(0x5A172026 + seed)`
with integer seeds 0 through 31, no live services or downloaded data.
The CLI and tests reject unbounded/invalid seed counts and unexpected
scenario families.

The generated fake actor labels are used as a temporary in-memory
reference for scoring only, not included in machine-readable output.
Only per-family/mode **aggregate** counts appear in reports;
no frame-level person coordinates, actor IDs or stable tracks are saved.

## Practical code correction

`services/api/app/anonymous_tracklet_research.py` had a genuine
fail-closed problem: previously a frame containing invalid coordinates
could raise an error **after mutating its timestamp**, leaving an
earlier active anonymous tracklet in memory. A later valid frame
might then be linked across an **untrusted frame**.

The updated `process()`:
1. Clears previous benchmark-only instantaneous association edges
   before validating any new input.
2. Validates frame type, bounded source ID/capacity, monotonic
   timestamp, permitted joint IDs, finite normalized points, and
   frame limit **before committing accepted-frame counters/time/source**.
3. On invalid input, clears all active tracklets and raises; a
   subsequent valid frame **starts new anonymous geometry** and cannot
   silently continue over the corrupt frame.
4. Rejects invalid initial poses **without latching** a bogus source ID.
5. Never creates an incident, authorized notification or confirmed
   person identity.

Fixed synthetic regression tests cover bad coordinates, invalid
initial pose, a cross-camera attempt, reversed/replayed timestamps,
and excessive detection capacity. This is a conservative integrity
hardening, not person re-identification or fall recognition.

## Regression on previously inspected human footage

The earlier **five real staged public MP4s** from
[samruddhi-2308/FallDetectionDataset](https://github.com/samruddhi-2308/FallDetectionDataset)
([CC BY-NC 4.0](https://github.com/samruddhi-2308/FallDetectionDataset/blob/main/LICENSE),
noncommercial with attribution) are available only on the authorized
local research workstation. They were extracted in a previous milestone
with MediaPipe `num_poses=1`; no real multi-person identity annotations
exist. Replaying those five previously inspected private traces still
produces **892 anonymous neighboring geometry links across 1,368
frames**. This regression demonstrates no change to previous
single-pose research outputs but **does not prove correct actor identity**.

Real source MP4s, private eight-joint pose traces and local aggregate
JSONs remain Git-ignored. No person data was fetched anew, no
Meta calls made, no automated alerts dispatched, and no change was
made to Member 1's production Edge, Mobile or Dashboard.

## Local reproduction

From `D:\VIIL-Sentinel\services\api`:

```powershell
# Full synthetic deterministic counterexample suite (offline):
.\.venv\Scripts\python.exe -m app.seeded_tracklet_stress --run

# Regression tests with only mathematical fake skeletons:
.\.venv\Scripts\python.exe -m pytest -q tests/test_seeded_tracklet_stress.py tests/test_synthetic_tracklet_benchmark.py tests/test_anonymous_tracklet_research.py

# Already inspected licensed private source regression only:
.\.venv\Scripts\python.exe -m app.anonymous_tracklet_report --evaluate-known --acknowledge-noncommercial-license --acknowledge-pose-privacy

# Whole repository's backend tests and lint:
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

## Safety / next engineering prerequisite

**NO-GO** for identity verification, real multi-person tracking,
unattended fall alarms, safety assurance, emergency dispatch and any
person-data upload to Meta. All anonymous links are **correlated
geometric samples, not proof of the same human**.

True identity continuity requires a separately authorized, documented
multi-pose video dataset with human-labeled per-person continuity,
occlusions, person replacements, entering/exiting camera view and
independently annotated actor-disjoint evaluation. Camera motion,
detector omissions, temporal sampling and privacy boundaries must
also be validated. Provenance and consent checks should be defined
before changing the single-pose MediaPipe extractor, model weights,
or production notification systems.
