# VIIL-Sentinel — ASSIST-IoT Frozen Fall-Miss Attribution

27 October 2026 · Member 1 · research-only, no automatic alerts

## Purpose

The last source-frozen ASSIST-IoT external stress run used **eleven** official
source-verified public MP4 reference videos: eight hard ADL negatives and
three publisher-labeled staged Fall reference videos. The frozen joint
CAUCAFall+GMDCSA V1 reported **zero fall-candidate videos out of three
publisher-labeled falls**, even though all eight hard negatives had zero
false candidates. The fall clips had 5/8 pose-eligible time windows;
three windows abstained (across two videos).

The key unsolved question was **where** the evidence disappeared:
raw MediaPipe torso detection, motion-geometry validation, 30-bin sampled
quality, or the frozen classifier versus the legacy heuristic.

This change adds **opt-in streaming aggregate diagnostics** to that exact
research benchmark. It does **not** change model parameters, threshold,
Live Edge detector, back-end alarm logic, Pose Landmarker asset,
event-onset labels or the video subset. All footage, poses and individual
model scores remain in memory; only integer counters and coarse
below/above-threshold bands are emitted into a private JSON report.

### Diagnostic stages

1. **MediaPipe adapter torso available**: nonempty PoseFrame landmarks from
   the existing strict pose adapter. Missing counts include no single
   unambiguous person, weak/off-image landmarks, or ambiguous multi-person
   frames. The counter **cannot identify which of those caused a miss**.
2. **Torso geometry eligible**: existing PoseFeatures.from_frame with the
   existing 0.55 visibility gate and 0.04 minimum torso geometry. A frame
   unavailable after the adapter might lack enough geometry, but counter
   values alone **cannot prove camera or model cause**.
3. **30-bin classifier sample available**: the existing frozen
   non-overlapping <=8s video window sampler. A window with fewer than
   10 valid sampled poses abstains. Missing samples are not treated as
   negative evidence. Model probabilities are deliberately **not written**.
4. **Frozen V1 score bands**: a descriptive count of eligible windows:
   `clearly_below` (p < 0.33), `near_below`
   (0.33 <= p < 0.53), and `candidate` (p >= 0.53).
   These are **uncalibrated research logistic scores**, not medical
   confidence. The 0.20 band width exists only for diagnosis; it is
   **NOT a proposed threshold adjustment**.
5. **Original temporal heuristic**: count its event candidates generated
   during the **same streamed video**. It uses a different fall/event
   contract than the per-window logistic model. The two counts are
   diagnostically comparable, **not interchangeable event-level
   sensitivity**.

No time series of pose locations, frame-level timestamps, identities,
recognized video frame pixels, reviewer details or private numerical
model weights are saved. Per-activity aggregations use the upstream
public activity name only. Unknown person/participant video identities
remain unknown.

## Exact repeatable local command

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$p = "D:\VIIL-Sentinel\data\private"

& $py -m sentinel_edge.assist_external --mode diagnose `
  --root "$p\public-datasets\assist-iot-external" `
  --model "$p\joint-cauca-gmdcsa-v1-publisher-research-20261027.json" `
  --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --report "$p\assist-fall-failure-attribution-20261027.json" `
  --acknowledge-publisher-labels --acknowledge-pose-privacy

& $py -m pytest -q
& $py -m ruff check .
```

This mode validates all source MP4 hashes before running inference,
requires the **exact frozen SHA-256** of the joint V1 model:
`2e55abd9657148a5fb17c3291c96841c31d030695c18116e0da70d6489aec3ab`,
and checks its original validation-selected threshold remains `0.53`.
The output report is exclusive-create only and remains inside
Git-ignored `data/private`; use a different filename to rerun.
The original `--mode evaluate` output remains backwards compatible
and does **not** include opt-in diagnostic fields.

## Actual real-video attribution — measured on the frozen external set

The command above was executed **successfully on all 11 public MP4
reference videos**, with the identical pinned video blobs, private
model SHA-256, and frozen threshold `0.53`. No model training was
performed. The resulting aggregate counters were:

| Strict diagnostic | 8 ADL references | 3 staged Fall references |
|---|---:|---:|
| Video frames processed | **1,838** | **1,558** |
| Torso adapter returned landmarks | 1,520 | **698** |
| Eligible motion geometry | 1,471 | **698** |
| Adapter output missing | 318 | **860** |
| Pose rejected between adapter and geometry | 49 | 0 |
| Non-overlapping video windows | 11 | 8 |
| Pose-eligible windows | **11** | **5** |
| Abstained windows | 0 | **3** |
| Frozen V1 candidate windows | 0 | **0** |
| Original heuristic event candidates | 0 | **0** |
| Frozen below-threshold windows: clearly / near | 11 / 0 | 4 / 1 |

Individual publisher-activity observations explain *where* the data
disappears, not why a real-world fall occurred:

- **Forward fall while walking**: 516 decoded frames, 121 adapter
  torso frames, **395 without adapter output**; two eligible windows,
  one abstained. Original heuristic and frozen V1: no candidates.
- **Backward fall**: 589 frames, 124 adapter torso frames,
  **465 without adapter output**; one eligible window, two
  abstained. Its sole eligible V1 score was **below** the unchanged
  0.53 decision threshold (near-below band). This is not permission
  to change the threshold.
- **Vertical fall / faint**: 453 decoded frames and
  **453/453 valid adapter torso and motion geometry frames**;
  two fully pose-eligible windows. Yet BOTH legacy heuristic and
  frozen V1 emitted zero candidates. Thus missing pose alone
  **cannot explain all failures**. It may be insufficient temporal
  motion/posture evidence, unfavorable segmentation or mismatch
  to the training domain; event-onset timestamps require human
  review before attributing a particular cause.
- All eight hard-negative ADL videos returned **zero** candidates
  from either classifier or heuristic. These small descriptive
  counts are not false alarms/hour.

At this point we have two distinct engineering priorities: improve
torso adapter coverage under falls (possible person ambiguity,
ground occlusion, out-of-frame keypoints or visibility failures;
specific reasons are not yet proven), AND develop better
event-localized temporal training data from **new, independently
reviewed clips**. Changing threshold to fit this already seen
external source would invalidate fresh-holdout claims.

The private diagnostic report, which is **not committed**, is
`D:\VIIL-Sentinel\data\private\assist-fall-failure-attribution-20261027.json`.
It contains aggregate counts plus public activity names but no
full per-frame pose stream, individual model probabilities, raw
images or trained weights.

## Limitations and next developer actions

- This repeated external set has been **exposed** and cannot be used for
  any new honest, untouched generalization estimate. No threshold or
  model selection based on its results.
- Source video activities lack independently reviewed event-onset
  annotations; one MP4 can contain multiple falls by the same people.
  Do not turn a video-level any-positive flag into event recall.
- ASSIST reference clips have unknown per-video participant IDs. No
  proof of cross-dataset person disjointness. CC BY 4.0 provenance is
  attributed but privacy/likeness rights may require further review.
- If both frozen V1 and the heuristic detect no events in a fully
  geometry-covered Fall video, additional temporal/event labels and
  an entirely new training cohort are required. If heuristic detects
  events and V1 does not, inspect the predeclared V1 motion descriptors
  on fresh, separately labeled development data; do not hand-tune
  against this exposed report.
- Quantify event-level false positives per monitoring hour and actual
  fall detection latency on long and independently annotated videos.
  Prioritize camera angle, multi-person ambiguity, occlusion, lighting,
  fall motion boundaries and memory/latency on the intended edge device.
  Keep human confirmation for any possible alert.

## Code ownership

`services/edge-vision/sentinel_edge/assist_external.py` contains the
opt-in diagnostic aggregation, with fictional-data checks in
`services/edge-vision/tests/test_assist_failure_diagnostics.py`.
Member 1 topic branch only; merge into
`member/feature/preprod` after tests. The human-only `main`
and shared `preprod` branches must remain unchanged.
