# VIIL-Sentinel — Local Eight-Joint Pose Feasibility & Abstention

**2026-11-03 (KST) · Member 2 · Actual local MediaPipe extraction · research only**

## Outcome

Implemented and actually executed an **isolated 8-joint research pipeline**
without changing Member 1's four-joint Edge runtime. It adds landmarks
**11/12 shoulders, 23/24 hips, 25/26 knees and 27/28 ankles**, but **does not
claim to add multi-person tracking, determine floor contact, detect a fall,
train a model or improve clinical sensitivity**.

The new module `services/api/app/multi_joint_research.py` performs the
following in a *local research shell only*, not a FastAPI route:

1. Select exactly five **already known, previously inspected** real staged
   videos from the project's existing private research dataset copies.
2. Validate each source against the published/previously pinned Git blob and
   independent SHA-256, probe the container's expected frame count.
3. Run the existing MediaPipe PoseLandmarker model **offline** on every frame,
   with `num_poses=1`. Store only the eight named normalized joints
   `{x,y,visibility}` per frame under Git-ignored `data/private`;
   no RGB frames, names, faces or videos are copied to the research output.
4. Strictly reread the derived private JSONL: schema version, allowed joint
   IDs, monotonically increasing timestamps, JSON duplicate-key rejection,
   finite point values, bounded line/frame size and frame count agreement.
5. Publish **aggregate-only** joint visibility and knee-angle *geometry*
   coverage (not medical conclusions). Never expose per-frame landmarks in
   a Git-tracked report or send them to Meta.

The tool requires explicit
`--acknowledge-noncommercial-license --acknowledge-pose-privacy`
for both extraction and reading person-derived poses. It refuses to
overwrite an existing pose trace, refuses input beyond five frozen files,
and writes no image/person dataset under Git-tracked paths.

## Original source, scope and privacy

Source: [FallDetectionDataset](https://github.com/samruddhi-2308/FallDetectionDataset)
by `samruddhi-2308`, [CC BY-NC 4.0 noncommercial](https://github.com/samruddhi-2308/FallDetectionDataset/blob/main/LICENSE)
with attribution. Videos are staged real-person footage; they may contain
identifiable individuals. The same 12 clips were previously analyzed by
this team. We are now repeating a *subset of five* locally with an added
joint mask, not obtaining new blind or actor-disjoint examples. Original
video publisher class labels are not per-frame fall onset annotations.

The previously deployed `models/pose_landmarker_lite.task` is used but
its original provider, model rights and suitability for commercial use
were **not independently verified** in this step. The workstation has
MediaPipe and OpenCV installed, but optional Python extras installed two
OpenCV distribution variants earlier; isolate/lock package versions
before any production deployment.

All five original MP4s remain in their existing
`data/private/public_fall_video_probe_v1`,
`data/private/public_fall_devset_v1` or
`data/private/adl_negative_challenge_v1` folders.

The **new** potentially identifiable eight-joint time series are in:
`data/private/eight_joint_pose_research_v1/FD*.eight.pose.jsonl` and must
never be committed, publicly linked or sent to any model provider. The
aggregate-only local report is
`data/private/eight_joint_pose_research_v1/aggregate-8joint-coverage.json`.

## Actual five-video extraction

All 5 local MP4s were checked against their prior content hashes, decoded
and processed by MediaPipe; all source container frame counts matched.

| Public clip ID | Publisher label | Frames analyzed | Frames with all 8 joints visible at ≥0.55 confidence | 8-joint coverage | Lower-body evidence status |
|---|---|---:|---:|---:|---|
| FD0012 | sitting_to_fall | 147 | 62 | **42.18%** | **Abstain** |
| FD0032 | sleeping_to_fall | 231 | 102 | **44.16%** | **Abstain** |
| FD0011 | sitting_to_fall | 216 | 147 | **68.06%** | **Abstain** |
| FD0001 | adl_no_fall | 326 | 250 | 76.69% | Exploratory geometry available |
| FD0005 | adl_no_fall | 448 | 339 | 75.67% | Exploratory geometry available |
| **Total** | **3 Fall-labeled, 2 ADL-labeled** | **1,368** | **900** | **65.79% pooled** | Research only |

The evidence gate uses **75% of frames with all eight joints at
visibility ≥0.55** as a *pre-established engineering coverage check*,
borrowed from the previous torso evidence-quality policy. It has not
been statistically calibrated. It **abstains on all three Fall-labeled
clips**, even though MediaPipe found valid *torso* points in nearly all
their frames. This exposes lower-body occlusion/limited framing;
it does NOT prove either whether a fall happened or whether a multi-joint
algorithm would detect one. An absence of visible ankle/knee points
must never become a negative fall label.

Across these five clips the **two-joint knee angle cannot always be
computed**. Where it is available, angle ranges are purely 2D joint
geometry subject to perspective, occlusion, and segmentation errors. We
did **not** fit knee thresholds, implement event-level V3 detection, or
derive a Fall-vs-ADL accuracy from these observations.

### Data access & effect boundaries

```text
5 already downloaded CC BY-NC MP4s (Git ignored, locally hash verified)
   → Existing local MediaPipe PoseLandmarker (8 selected indices only)
   → Private *.eight.pose.jsonl (Git ignored, potentially identifying)
   → Schema/finite/ordering/clip completeness checks
   → Aggregate joint visibility + knee geometry quality
   → Explicit insufficient lower-body evidence / exploratory only
      NO event, NO alert, NO inference call to Meta, NO image upload
```

These are **source-specific feasibility findings** from existing
convenience samples, not clinical validation, real-time camera
monitoring, multi-person association or emergency triage.

## Reproduce

From `D:\VIIL-Sentinel\services\api` after installing local research
dependencies and obtaining permission to process the staged dataset:

```powershell
# ONE-TIME: extracts 8-point time series into ignored private storage.
# Refuses to overwrite existing person-derived traces.
.\.venv\Scripts\python.exe -m app.multi_joint_research --extract --acknowledge-noncommercial-license --acknowledge-pose-privacy

# OFFLINE REPLAY: rechecks exact input MP4 hashes and private trace
# frame count, then writes an aggregate-only private JSON report.
.\.venv\Scripts\python.exe -m app.multi_joint_research --analyze --acknowledge-noncommercial-license --acknowledge-pose-privacy

# Unit and safety tests use fictional numeric points, not any human video.
.\.venv\Scripts\python.exe -m pytest -q tests/test_multi_joint_research.py

# Full tests:
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

The first command cannot be rerun into the same output folder without an
explicit private retention/delete decision; do not delete identifiable
traces casually just to regenerate nicer metrics.

## Follow-on: temporal continuity audit

The subsequent [Eight-joint Temporal Observability report](EIGHT_JOINT_TEMPORAL_OBSERVABILITY_2026_11_03.md)
computes research-only 2D image-plane hip and ankle velocities, knee-angle
change rates, and contiguous pose availability from the **existing**
private eight-joint traces. It discards pairs that cross missing joints
or gaps and adds a conservative 12-consecutive-unusable-frame
abstention rule. Across the same five previously inspected clips,
**all five abstained**: three because total lower-body coverage
was below 75%, and two because long lower-body tracking gaps occurred
despite greater-than-75% overall point coverage. This is not new
person tracking or fall prediction, and does not authorize alerts.

## Technical next steps and release decision

**NO-GO** for autonomous fall alerts or commercial pilots.
An 8-joint data mask alone did **not** repair the previously missed
FD0012/FD0032 falls, did not reduce ADL false-review risk, and did not
establish robust lower-body tracking.

For future work, first obtain a larger **licensed, actor-disjoint,
independently annotated** source with high lower-body visibility,
different camera placements and realistic long ADL episodes; explicitly
label fall onset, bed-to-floor transitions, voluntary fast sitting,
occlusion and near-fall. Introduce per-person tracking, reliable
visibility/occlusion handling, 2D camera orientation calibration,
potentially 3D/world coordinates if permitted, and explicit abstention.
Keep review outcomes human-confirmed, measure actual false review
candidates per video-hour and onset latency on a sealed evaluation split.

This branch **does not alter** Member 1 Edge code, the caregiver API,
Mobile/Dashboard code, or Meta spending. The Meta local attempt
ledger remains 4/4; no billable calls occurred.
