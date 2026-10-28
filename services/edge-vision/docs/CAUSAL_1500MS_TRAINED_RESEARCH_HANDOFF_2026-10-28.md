# Member 1 — independently fitted causal 1.5-second research baseline

28 October 2026 · VIIL-Sentinel · **Research ONLY, not an incident detector**

## Design decision BEFORE running the new model

The previously exposed 40 publisher-staged CAUCAFall clips have variable
durations from **1,100 to 6,400 milliseconds**. Fifteen original clips
are shorter than 2,000ms; fixed 2s sampling would exclude many fall
motions before a model even sees their poses. On **duration metadata
and known publisher action labels only**, the Member1 pilot was
predefined to use a **1,500ms trailing window** (within the desired
1–2 second research range). This choice itself inspected the old
cohort's clip length/label distribution. Neither the original final
test subjects nor this new pilot are untouched independent evaluation
data. Do not use the observed test confusion matrix to revise this
window, fit thresholds or select architectures.

The original 8s SHA-pinned Linear V1 shadow is not usable with a 1.5s
feature window. We have therefore **trained an entirely separate
in-memory 30D NumPy logistic model** from real original local pose
frames in each qualifying clip's final exactly 1500ms:

1. Load only SHA256-pinned, path-confined CAUCAFall publisher source AVI
   files and accompanying frozen group/segment manifests.
2. Preflight all original clips, video FPS/frame counts, publisher
   unreviewed labels, segment bounds and declared disjoint subjects.
   Short labeled intervals must **abstain**, not be padded, silently
   fabricated or scored as ADLs.
3. Decode the full original video with existing MediaPipe Pose
   Landmarker and strict multi-person-safe torso adapter. Require
   original declared frame count to match **collector stats AND the
   sampling callback**, reject partial decodes, and check source SHA256
   again after processing.
4. Use existing NearestFrameSampler to select **30 uniform timestamps
   across the 1500ms before the publisher clip's end** (all selected
   frames are at or before the end). Missing/ambiguous poses are
   zero-masked, not invented. A minimum 10/30 visible slots is required.
5. Use unchanged TemporalFeatureEncoder, 5 contiguous masked pooled
   bins, and a new 30D train-only standardizer clamped to [-12,+12].
   The in-memory linear parameters are fitted on declared TRAIN
   participants; the decision threshold comes from declared VAL
   participants. Repeatedly exposed TEST publisher labels are scored
   **only after** fitting and validation selection.
6. Return aggregate counts and explicit limitations only. New weights
   are **not serialized** to the existing 8-second Linear V1/V2
   artifact schema: that would silently mix incompatible model
   window contracts. No live camera prediction, event, emergency
   dispatch, network request, image or landmark export.

**Important meaning of causal:** all features are from samples at
or before a fixed *clip-end time* with exactly 1500ms of history.
We are NOT claiming fall onset timing, a continuous sliding inference
implementation, 1.5s wall-clock inference latency, or verified early
fall detection. An action's clip-end may occur *after* the actual fall
motion. A late classifier success may be recognizing an already fallen
pose. This is only a necessary training/feasibility experiment.

## Actual original-video replay

Command run from the Edge Vision checkout:

```powershell
$root = "D:\VIIL-Sentinel\data\private\public-datasets\caucafall-omnifall\extracted\Cauca_fall"
.\.venv\Scripts\python.exe -m sentinel_edge.causal_1500ms_research `
  --root "$root" `
  --groups "$root\caucafall-research-groups-v2.json" `
  --proposals "$root\caucafall-review-proposals-v1.json" `
  --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --acknowledge-publisher-labels --acknowledge-pose-privacy
```

Validated real input: **40 original source-pinned staged activity
clips**. **31 clips pose/context-eligible**, **9 abstained**. For
the 38 clips long enough to be processed, **1,956 original frames
were fully decoded**. Two short clips were excluded before MediaPipe
inference; seven additional eligible-duration clips failed the
pose coverage gate. No raw footage or features were exported.

| Source split and label | Selected | Too short | Pose abstained | Scored |
|---|---:|---:|---:|---:|
| TRAIN Fall | 12 | 0 | 2 | 10 |
| TRAIN ADL | 12 | 1 | 0 | 11 |
| VAL Fall | 4 | 0 | 1 | 3 |
| VAL ADL | 4 | 1 | 1 | 2 |
| Previously exposed TEST Fall | 4 | 0 | 1 | 3 |
| Previously exposed TEST ADL | 4 | 0 | 2 | 2 |
| **Total** | **40** | **2** | **7** | **31** |

Trained independent linear classifier state **736 bytes in RAM**;
validation-selected threshold **0.95**. No model file was written.
Publisher-clip categorical results:

| Old, tiny, publisher-labeled diagnostic | Validation | Previously exposed TEST |
|---|---:|---:|
| True Positive (staged Fall) | 2 | 1 |
| False Negative (staged Fall) | 1 | 2 |
| False Positive (ADL) | 0 | 0 |
| True Negative (ADL) | 2 | 2 |

**Finding:** The independent 1.5s trained model exists and scores
new short historical pose windows. But the old publisher-labeled test
has just **one staged Fall clip predicted positive out of three
eligible Fall clips**. Both eligible ADLs were classified negative,
while the other **two test ADL clips abstained**. Therefore this
prototype cannot establish clinical effectiveness, prospective
false alarms/hour, real-world event recall, precision or detection
latency. It should NOT be promoted into alerts. In fact, on these
already-examined inputs, the observed missed staged Fall clips are
a significant research concern.

The 8s versioned private research model, 2s untrained probe,
original heuristic, incident outputs, human review gate and
other team members' APIs remain unchanged.

## Regression and CI

Tests in `tests/test_causal_1500ms_research.py` are invented numerical
poses only. They include samples **after** the annotation end changed
without affecting training/report, incomplete decoder rejection even
when the decoder's own count agrees with its callbacks, insufficient
pose abstention, short/invalid annotations, source hash drift, unsafe
paths, malformed metadata and group leakage before any model opens.

Edge Vision **573 pytest cases passed**, full Ruff passed; Backend
**6 pytest cases passed** and Ruff passed; Dashboard production
TypeScript/Vite build passed. Final GitHub exact-SHA CI verification
is required on the feature and team merge commits before calling
the branch integration complete.

## Next developer gates

1. Get two genuine independent human reviews on fall onset/offset,
   non-fall intervals, and actual rights to use/redistribute source
   material. Publisher-level action class is not event-onset ground
   truth.
2. Freeze completely new actor/camera-disjoint source/test cohorts
   and long ADL negatives, including sit/lie/kneel/occlusion.
3. Develop a separately versioned **1.5s streaming research
   shadow** with strict pose coverage and per-hop abstention,
   compare on newly reviewed event onset latency and negatives/hour.
   Never reuse pinned 8s weights, model file format or SHA as 1.5s.
4. Only consider model promotion if prospective metrics are robust
   with confidence intervals, real CPU/RAM/edge latency, alert
   safeguards and human review. No automated emergency use.
