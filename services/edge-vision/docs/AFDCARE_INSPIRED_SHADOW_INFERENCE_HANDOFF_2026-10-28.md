# VIIL-Sentinel: AFDCare-inspired frozen Linear V1 Shadow Mode

28 October 2026 · Member 1 · **Research-only, no incident dispatch**

## What we learned by inspecting the REAL local AFDCare source

Read-only inspected local `D:\AI-Fall-Detect\AFD-edge`:
`README.md`, `inference/hybrid_classifier.py`, `pipeline.py`,
`config.yaml`, `tools/train_temporal_model.py`.

AFDCare's planned appliance pipeline is YOLO Pose ONNX -> bounded
person tracking -> temporal GRU/ONNX -> smoothing / candidate vs
confirmed incident -> offline outbox and supervised operator
notifications. Its temporal classifier can give a model-driven
positive even when pose geometry alone does not meet the original
heuristic gate. Its local model baseline config reports an OmniFall
held-out 367-clip diagnostic (fall recall 67.4%, false-positive
percentage 15.1% at a stated threshold) with the original caveats
about ADL lying-down confusion. Those numbers apply to **AFDCare's
own data and rules only** and do NOT transfer to VIIL-Sentinel.

We did NOT copy AFDCare source, weights, datasets, ONNX files,
thresholds, private infrastructure or enrollment logic. Per project
`AGENTS.md`, shared work here is an independently implemented,
small, auditable safety-isolated experiment.

## New VIIL architecture

```text
Local consented Camera/Video
        |
  MediaPipe PoseLandmarker Lite (original num_poses=2)
        |
  Strict original pose adapter (multi-person ambiguous => no pose)
        |
        +--> Original TemporalFallDetector ------> Original event JSONL
        |
        +--> Optional frozen Linear V1 SHADOW    -> stderr counters only
             (trained V1 SHA256 required, 0.53 fixed threshold)
             |
             8-second trailing local PoseFrame ring buffer
             30 evenly spaced sample slots via NearestFrameSampler
             zero-mask on lost / ambiguous frames
             5 contiguous bins x 6 features = trained 30D contract
             one private local inference per 1-second hop
             NO API / no backend / no alert / no video or pose export
```

The camera runner `--shadow-model` switch is **opt-in** and
requires `--confirm-consent` and `--acknowledge-pose-privacy`.
It checks the private baseline artifact against the exact
source-linked model hash
`2e55abd9657148a5fb17c3291c96841c31d030695c18116e0da70d6489aec3ab`.
The threshold `0.53` stays unchanged.

**Crucial issue the old AFDCare-like proposal might miss:** the
present VIIL model was trained on **30 sparse samples across eight
seconds**, NOT 30 consecutive live frames. This code uses the exact
existing training sampler and 30D pooling, and will **abstain until
eight seconds of continuous source context** have elapsed. This
current V1 cannot honestly be advertised as "immediate detection".
After each timestamp gap above 700 ms or source switch, it restarts
its evidence window; low pose coverage causes abstention. Bounded
in-memory source PoseFrame history remains inside this local process.

The shadow result deliberately emits **no event** and does not
modify the legacy detector's candidate path or threshold.
It returns only totals: frame count, shadow windows eligible,
positive/negative, pose-abstained, missing-time resets and
source resets. No probabilities, pose arrays, source IDs, absolute
video file paths, or per-event timestamps go to stderr or saved JSON.

## Command on authorized Windows workstation

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$p = "D:\VIIL-Sentinel\data\private"

# Opt-in local video/camera research, with human permission.
& $py -m sentinel_edge.runner `
  --source "D:\path\to\authorized_staged_video.mp4" `
  --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --shadow-model "$p\joint-cauca-gmdcsa-v1-publisher-research-20261027.json" `
  --confirm-consent --acknowledge-pose-privacy
# Machine-readable heuristic event JSONL alone on stdout;
# aggregated 'RESEARCH_MODEL_SHADOW' diagnostic alone on stderr.

# Offline source-hash-verified diagnostic on all 11 original public
# ASSIST-IoT reference clips; already exposed, research-only.
& $py -m sentinel_edge.shadow_external `
  --root "$p\public-datasets\assist-iot-external" `
  --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --linear-model "$p\joint-cauca-gmdcsa-v1-publisher-research-20261027.json" `
  --report "$p\assist-linear-v1-shadow-8s-diagnostics-20261028.json" `
  --acknowledge-publisher-labels --acknowledge-pose-privacy

& $py -m pytest -q
& $py -m ruff check .
```

The private offline audit uses the original pinned Git reference
video blobs and local SHA-256 verification; reports are
exclusive-create under ignored `data/private`. It groups results
into publisher `fall` / `adl` counts, **never human event-level
ground truth**. Public IKAR reference clips are all 2.37–4.53
seconds long and therefore CANNOT exercise an eight-second
trained model without artificially repeating/concatenating them.
Do **not** pad fake history or choose thresholds from prior IKAR or
ASSIST external videos.

## Real replay status

**Completed actual source-verified MediaPipe replay** of 11 original
ASSIST-IoT public MP4s, totaling **3,396 decoded frames**. This is the
same previously exposed reference source, NOT a newly untouched
generalization test.

| Research-only measurement | Publisher ADL | Publisher staged Fall |
|---|---:|---:|
| Public MP4s source-verified and decoded | 8 | 3 |
| Real decoded frames | 1,838 | 1,558 |
| Clips shorter than model's 8s context | 4 | 0 |
| Videos with at least one eligible shadow window | 4 | 3 |
| Eligible model-score windows (1s hops) | 12 | 10 |
| Frozen model score >= 0.53 windows | **0** | **0** |
| Scored windows below original threshold | 12 | 10 |
| Explicitly abstained windows due to insufficient pose | 0 | **20** |
| Original unchanged heuristic candidate events | 0 | 0 |
| Pose frames unavailable to strict adapter | 318 | 860 |
| Frame-gap resets | 0 | 0 |

**Negative research outcome**: installing the *real* trained frozen
V1 side-by-side with the original detector did NOT produce a
positive candidate on any of the eligible staged Fall video windows.
The 20 Fall pose-abstained windows also matter: this is
not evidence of correctly classifying them as normal.

**Do not call this "0% event recall", "0% Fall accuracy" or a
validated comparative test**: the source publisher action names
do not enumerate onset events, participant identity is unknown,
the dataset has already been repeatedly used for diagnostics,
and many short ADL clips have no valid eight-second sample window.
The observation does establish a concrete **missing capability**:
the present pooled linear model does NOT solve detection merely by
being called from the camera runner. The original frozen model
weights, threshold and incident code were NOT changed.

Private aggregate report:
`D:\VIIL-Sentinel\data\private\assist-linear-v1-shadow-8s-diagnostics-20261028.json`.
The report stores NO video file path, raw pixels, pose, score values,
participant identity or event timestamps.







## Remaining limitations / next acceptance gate

1. Original trained 30D V1 validation balanced accuracy 90%,
   old exposed TEST 70% / fall recall 50% and 0/3 video-level
   candidate coverage on ASSIST from earlier evaluations do
   **not** justify emergency monitoring.
2. A truly faster temporal model requires NEW human-reviewed fall
   onset intervals, subject+camera disjoint splits and new ADL
   negatives, with an explicitly defined causal low-latency
   feature window and appropriate validation before selection.
3. The original heuristic can miss falls if it requires a
   distinctive sudden descent into horizontal posture. Shadow
   model output should be compared offline and audited first;
   never auto-promote a previously exposed model's positive as
   a dispatchable incident.
4. Maintain strict multi-person abstention. AFDCare tracking
   is a separate engineered component; don't quietly assign
   identity to unreviewed poses. Prevent old tracker state,
   duplicates, camera reconnection and temporal context gaps.
5. Before promoting any AI-driven event, confirm event-level
   recall and detection delay against **two human-reviewed
   onset observers**, real false alerts per long ADL hour,
   resource stability on target hardware, privacy, and
   explicit operator confirmation.

Member1 branch: `member1/feature/afdcare-inspired-model-shadow`.
Authorized integration only `member/feature/preprod`.
Protected `preprod` and `main` untouched.
