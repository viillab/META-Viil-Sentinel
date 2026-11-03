# VIIL-Sentinel — Anonymous Tracklet / Occlusion Abstention Research

**2026-11-03 (KST) · Member 2 · Local-only · Research, NOT production Person Tracking**

## What was implemented

Two independent new modules in `services/api/app/`:

1. `anonymous_tracklet_research.py`: bounded anonymous geometry matching
   for frames with **0–4 simultaneous eight-point poses**, including
   **unambiguous one-to-one assignment**, close-person/crossing abstention,
   short-timestamp speed guardrails, lost-pose resets, camera/source
   boundaries, and no identity linking across occlusion.
2. `anonymous_tracklet_report.py`: replays the already known five
   CC BY-NC 4.0 public research MP4s **from private, already extracted
   eight-joint pose traces only**. It validates the pinned original public
   video SHA-256 and Git object, verifies full frame counts against the
   previous temporal evidence audit, and stores only aggregate counters
   in ignored `data/private`.

The new test file `tests/test_anonymous_tracklet_research.py` contains
entirely **fictional, numerically generated poses**, including two
approaching/crossing people, a competing association graph, missing
legs, absence of detections, jumpy timestamps, source changes and
impossible motion speeds. No real people are loaded into CI.

### How the research matcher behaves

For each local frame:
- Require **one source ID**, increasing timestamps, 0–4 detections and
  **exactly eight allowed joint indices** (11,12,23,24,25,26,27,28)
  with visibility ≥0.55, finite normalized 2D coordinates and a
  measurable torso length. Refuse unbounded/unrecognized inputs.
- Track one **ephemeral in-process pelvis-center/torso-scale tracklet**
  per valid pose. Use a maximum **0.14 normalized distance** AND
  **2.0 normalized image units/second** movement bound and torso
  size ratio ≤1.8. These are *uncalibrated engineering safeguards*,
  not learned physical or person-ID thresholds.
- Match across adjacent frames only when no other old/new pose
  is compatible with the same match; if multiple candidates compete
  or two people are within 0.13 normalized distance, **abstain and
  drop all tracklets for the ambiguous frame**.
- Missing pose, low visibility, source change or a >200 ms timestamp
  gap is **not occlusion recovery**: terminate old continuity.
  Reappearance starts a **new anonymous tracklet**, never the same
  person ID, and no points are interpolated.
- Refuse replayed/reversed timestamps, cross-camera inputs and more
  than 12,000 frames/4 pose detections per frame (with smaller
  configurable bounded policies permitted for tests).
- Only export aggregate counts. No stable tracklet identifiers,
  camera images, raw 8-point coordinates, facial characteristics,
  clothing embeddings, location, personal identity or biometrics
  are added to Git or transmitted to a model.

**Limitations:** Geometric proximity does not prove identity. Even
apparently unambiguous matches can switch individuals due to camera
motion, occlusion, similar body shape, crossings between observed
frames or low frame rates. This is **NOT** production person tracking
and must not be used for identifying, monitoring, notifying or
diagnosing anyone. Because the original MediaPipe extraction had
`num_poses=1`, real multi-person precision/recall is entirely
**unmeasured**. Only fictional test fixtures exercise 2+ people.

No fall classification, clinical confidence, inference service call,
actual caregiver workflow, event state, face recognition, real-person
identity, notification or emergency dispatch is created.

## Real local data replay (existing five videos)

Public source:
[FallDetectionDataset](https://github.com/samruddhi-2308/FallDetectionDataset)
under [CC BY-NC 4.0](https://github.com/samruddhi-2308/FallDetectionDataset/blob/main/LICENSE)
(noncommercial research and attribution). These are previously
inspected staged videos of potentially identifiable people, not new,
actor-disjoint or held-out data.

| Public clip ID | Published category | Frame count | Anonymous geometric links | No pose | Incomplete 8-joint frames | Longest uninterrupted local tracklet |
|---|---|---:|---:|---:|---:|---:|
| FD0012 | sitting_to_fall | 147 | 61 | 2 | 83 | 62 frames |
| FD0032 | sleeping_to_fall | 231 | 101 | 0 | 129 | 102 frames |
| FD0011 | sitting_to_fall | 216 | 146 | 0 | 69 | 147 frames |
| FD0001 | adl_no_fall | 326 | 249 | 16 | 60 | 250 frames |
| FD0005 | adl_no_fall | 448 | 335 | 2 | 107 | 206 frames |
| **Total** | 3 Fall + 2 ADL | **1,368** | **892** | **20** | **448** | — |

A geometric link is **NOT proof of identity persistence**, fall
recognition or safe ADL classification. The prior unconstrained
eight-joint motion study had 894 eligible pairs; the two fewer
links reflect this research tracklet's additional implausible
image-plane speed rejection. No preexisting detector was retuned
or replaced. The source contains at most ONE extracted pose each
frame, so *zero observed ambiguous people* does not prove that
crowded scenes are handled accurately.

Private aggregate report:
`data/private/eight_joint_pose_research_v1/aggregate-anonymous-continuity.json`.
Raw human videos and pose traces stay under already ignored
`data/private/...`; **never force-add them to Git or upload them
to Meta**. License/retention and data subjects' right to control
person-derived traces require a separate review before broader use.

## Run on the authorized local workstation

From `D:\VIIL-Sentinel\services\api`:

```powershell
# Replay and validate ONLY the previously authorized five private traces.
# No new recording, image download or Meta API request.
.\.venv\Scripts\python.exe -m app.anonymous_tracklet_report --evaluate-known --acknowledge-noncommercial-license --acknowledge-pose-privacy

# No real media / person pose is needed for CI:
.\.venv\Scripts\python.exe -m pytest -q tests/test_anonymous_tracklet_research.py

# Full regression and lint:
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

**Safety decision:** The main Member 1 Edge runtime is unchanged, and
the experimental V2 remains review-only. This increment is **NO-GO**
for real-world person tracking, automatic fall/absence assurance,
caregiver alerts, emergency dispatch or sharing person video/pose
with Meta. The local paid Meta ledger remains at **4/4** approved
attempts; no new API calls were made.

## Next substantive prerequisite

True person association requires a **separately authorized multi-person
pose extractor**, annotated identity continuity ground truth, a license/
consent/retention audit, occlusion-heavy and crowded *actor-disjoint*
clips, and evaluation of **ID switches, fragmentation, recall,
ambiguous/abstention rate and tracking latency**. Never infer
persistent identity merely because the same coordinates reappear
after a pose gap.
