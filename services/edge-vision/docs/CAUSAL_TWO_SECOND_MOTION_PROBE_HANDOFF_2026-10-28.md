# VIIL-Sentinel: causal 2-second motion-cue probe (research-only)

28 October 2026 · Member 1 · No model tuning, incident dispatch or automated alerts

## Why we built this

Frozen pooled Linear V1 requires **30 samples across 8 seconds** and its
prior ASSIST-IoT diagnostic scored zero positive fall windows out of
10 eligible publisher-Fall windows (20 other windows abstained).
Changing the original trained model's thresholds, pretending 30
adjacent camera frames equal the trained 8-second window, or
automatically dispatching emergency alerts would be misleading.

This milestone instead creates a **separate, deterministic, causal,
maximum-two-second motion proposal probe**. It asks whether a very
short physical motion cue is measurable at all from the original strict
MediaPipe torso stream, not whether a trained model can accurately
recognize an actual fall. Unlike AFDCare's actual trained GRU, this
probe is a **hand-designed, untrained kinematic rule** and must
not be described as AI classification, Fall Recall, accuracy,
or clinical/remote safety readiness.

## Freeze before external clips

All thresholds were fixed from basic normalized motion assumptions
and the original strict heuristic's reference values BEFORE reading
the real source video outcome; they are not optimized on exposed
ASSIST-IoT clips.

- Video pose: exactly one accepted strict torso pose at a time;
  original multi-person abstention is unchanged; visibility >=.55,
  geometrically collapsed torso is excluded.
- Local maximum history **2,000 ms**, at most **240** sanitized
  pose-feature readings, reset on missing/collapsed pose, source
  change or a timestamp gap above 700 ms. Source monotonicity
  enforced for one source; no identity tracking added.
- Requires recent upright torso (angle <=32°) within 1,500 ms.
  A downward hip displacement of at least **0.13** normalized
  image heights relative to recent upright baseline, downward
  instantaneous hip speed >= **0.20** normalized image heights/s,
  and the same cue sustained for at least **40ms and two observed
  frames**. Minimum 200ms of motion context must exist.
- Research proposal repeated cooldown 2,500 ms. No confidence
  or probability; no checked fall-onset matching, no medical
  severity, no rescue actions. Ordinary sitting, close camera
  motion or partial body occlusion can mimic movement.
- Never push proposal objects to original `TemporalFallDetector`,
  incident JSONL, APIs or backend. The `runner`
  `--early-motion-probe` flag writes only categorical totals to
  stderr under `RESEARCH_EARLY_MOTION_PROBE`, and requires both
  `--confirm-consent` and `--acknowledge-pose-privacy`.
  It may be combined with frozen `--shadow-model`:
  the original detector and its event output remain unchanged.

## Commands

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$private = "D:\VIIL-Sentinel\data\private"

# Opt-in local demonstration of independent motion-only counters.
& $py -m sentinel_edge.runner `
    --source "$private\public-datasets\assist-iot-external\clips\fall\01_forward_fall_walking.mp4" `
    --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
    --early-motion-probe --confirm-consent --acknowledge-pose-privacy

# All 11 source-verified ORIGINAL ASSIST-IoT MP4s, never padded.
& $py -m sentinel_edge.early_motion_external `
    --root "$private\public-datasets\assist-iot-external" `
    --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
    --report "$private\assist-early-motion-probe-frozen-20261028.json" `
    --acknowledge-publisher-labels --acknowledge-pose-privacy

& $py -m pytest -q
& $py -m ruff check .
```

The direct runner is a research diagnostic with no video or pose
recording. Only categorical totals are printed, not subject IDs,
coordinates, timestamps, probabilities or image/video paths.
The offline audit requires the existing signed-off exact original
source manifest and source clip SHA-256 and checks full frame-count
parity with the unchanged original video collector; output is
exclusive-create in Git-ignored `data/private`.

## Important coverage difference discovered during actual replay

The strict MediaPipe torso adapter can accept some landmark sets
which `PoseFeatures.from_frame` subsequently rejects because the
torso has collapsed or become geometrically too small to estimate
direction. These are legitimately **two distinct stages** of
abstention, not a bad frame count. The research audit counts
`strict_adapter_unavailable_frames` and
`pose_abstained_frames` independently, verifying the latter is
never smaller than the former. It does NOT silently reclassify
such frames as normal movement or add false model evidence.



## Actual complete original publisher video replay

Real source-verified 11 original ASSIST-IoT MP4s all decoded:
**3,396/3,396 frames**, MediaPipe Lite num_poses=2, original
strict pose adapter and unchanged original heuristic.

| Categorical aggregate | ADL (8 videos) | Publisher staged Fall (3 videos) |
|---|---:|---:|
| Frames processed | 1,838 | 1,558 |
| Strict torso adapter unavailable frames | 318 | 860 |
| Kinematic feature abstained frames | 367 | 860 |
| Usable motion feature frames | 1,471 | 698 |
| Frames with downward cue | 0 | 24 |
| Provisional *untrained* motion proposals | **0** | **3** |
| Videos with at least one such proposal | **0/8** | **3/3** |
| Original heuristic events | 0 | 0 |

**Limited technical finding:** early physical-motion proposals
appeared in each publisher staged-Fall video while the original
heuristic emitted none. This is NOT Fall event recall or accuracy:
publisher clip names and actual event onsets have not been
independently reviewed; data have been exposed to previous
diagnostics; sitting and camera motion can mimic these cues.
Fixed thresholds were NOT adjusted to obtain these results.
49 ADL frames passed the strict torso adapter but were
geometrically unusable for the motion probe; they remain
abstentions, not inferred normal ADL behavior.

Source: full source-hash-rechecked, category-only private JSON
`D:\VIIL-Sentinel\data\private\assist-early-motion-probe-frozen-20261028.json`.
No raw frames, source paths, landmarks, probabilities or
individual event times are stored.

## Interpretation limits

- The videos' fall onset timestamps and actor identities are
  **not independently human reviewed**. A publisher's `fall`
  clip label may encompass multiple actions or staged behavior;
  one clip may have long non-fall periods. Thus a cue proposal
  is neither a true Fall hit nor a clinical detection.
- ASSIST-IoT reference videos have already been examined in
  previous rounds: they CANNOT be an untouched cross-subject
  model test. This probe is a **new diagnostic, not trained
  model improvement**. Do not tune `.13` or `.20` using its results.
- Conservative 2-second physical cues are sensitive to seated
  transitions, camera movement, target scale, and blurred video;
  even if publisher Fall clips show cues and ADL clips do not,
  one cannot infer precision, recall, or false alerts/hour.
- A true low-latency AI fall detector next needs newly reviewed
  event-onset windows, strict subject/camera disjoint splits and
  unseen long ADL negatives, training a causal 1–2s model
  separately from V1, prospective evaluation and human confirm.
- Never enable new cues as production emergency notifications.

Source code remains in the Member 1 topic branch and is integrated
only into `member/feature/preprod` after tests and GitHub CI.
Main and shared `preprod` remain controlled by a human operator.
