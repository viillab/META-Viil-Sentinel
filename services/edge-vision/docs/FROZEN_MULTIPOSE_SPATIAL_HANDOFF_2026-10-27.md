# VIIL-Sentinel — Offline Multi-Pose Spatial Geometry Study
27 October 2026 · Member 1 · Research only, no safety claims

## Why this exists

The previous opt-in rejection-reason audit counted **860** MediaPipe
multi-pose rejections in three ASSIST-IoT staged Fall reference videos,
while all eight ADL references had **51** multi-pose rejections.
"Multiple people" is the existing adapter's reason when MediaPipe returns
more than one pose. It does **NOT** establish that two real people
are present (some poses might overlap or be duplicate detections).

This task deliberately does **not** select, merge, or track any
pose. It classifies the geometry of exactly two MediaPipe torso
detections into *non-identifying spatial categories* for research
only, and leaves the original production fail-closed detector untouched.

## Fixed, auditable method

The opt-in callback `multipose_category_consumer` runs ONLY when
`assist_external --mode spatial-audit` requests it. The base
`extract_torso_landmarks` adapter, no-pose handling and live
events are exactly unchanged. Each decoded frame receives one
category. `not_multiple` means less than two returned poses or an
invalid non-list result. The other categories require at least
two poses; with more than two we classify as `unsupported_pose_count`.

For exactly two detections, inspect **only** four torso keypoints
(two shoulders and two hips) **in RAM** with finite in-frame
coordinates and the preexisting visibility/presence floor of 0.55.
If either torso is incomplete, out of frame or low quality:
`unusable_torso_geometry`. Otherwise compute a centroid,
torso length and the largest corresponding keypoint distance.
Predeclared rules (NOT tuned from these external clips):

- `overlapping_torso_geometry`: centroid distance no more
  than max(0.03, 0.20 times shorter torso length) AND
  max matched torso-joint separation no more than
  max(0.04, 0.30 times shorter torso length)
- `spatially_separated_geometry`: centroid distance at least
  max(0.24, 0.75 times the longer torso length)
- `ambiguous_geometry`: both torsos appear usable, but
  neither strict comparison above is met
- `unsupported_pose_count`: more than two returned poses
- `not_multiple`: a frame without multiple returned poses

These thresholds produce **exploratory geometry buckets**, not
probabilistic identities or a person-count classifier. Overlap
does not prove one person was detected twice; separation does not
prove two distinct participants. The adapter still **ABSTAINS on
all multiple-pose frames regardless of category**. No remote
inference, recording or upload is added. Frame coordinates,
images, IDs, per-frame timestamps and numerical confidence values
are NEVER exported or saved.

Every category is an integer count, and the combined report refuses
to succeed unless each source-video sum matches decoded frames and
the count of all categories other than `not_multiple` matches
the existing `multiple_people` adapter reason. Privacy-sensitive
source MP4s and model weights stay in ignored `data/private`.

## Frozen sources, frozen model

- ASSIST-IoT multimodal fall reference video collection, CC BY 4.0,
  https://github.com/ASSIST-IoT-SRIPAS/multimodal-fall-detection-dataset
  pinned to revision `7a11c96b9a3576cef92f0795a19b3786c69a3335`
- **11 existing MP4s** pinned to source Git blob hashes,
  8 challenging ADL and 3 staged Fall reference clips
- Private 30D joint CAUCAFall+GMDCSA-24 baseline V1 with SHA256
  `2e55abd9657148a5fb17c3291c96841c31d030695c18116e0da70d6489aec3ab`
  and validation-selected threshold 0.53; strictly unchanged

The reference clips are already-exposed diagnostics, and their
individual participants are not identified sufficiently to
certify subject disjointness. Source labels are not independently
human-reviewed and per-fall onset annotations are not provided.
Do not use any results to choose a different model, threshold,
pose-selection strategy or safety deployment policy.

## Reproduce on authorized Windows machine

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$p = "D:\VIIL-Sentinel\data\private"
& $py -m sentinel_edge.assist_external --mode spatial-audit `
    --root "$p\public-datasets\assist-iot-external" `
    --model "$p\joint-cauca-gmdcsa-v1-publisher-research-20261027.json" `
    --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
    --report "$p\assist-frozen-multipose-spatial-audit-20261027.json" `
    --acknowledge-publisher-labels --acknowledge-pose-privacy

& $py -m pytest -q
& $py -m ruff check .
```

An existing output file is never overwritten; use a new private
filename to repeat. A completed report is stored under
`data/private` locally and contains counts per source activity,
not full pose tracks.

## Actual executed 11-video research observations (27 October 2026)

The source-verified **11 original public MP4s** were decoded with the
unchanged MediaPipe Lite task and identical frozen joint V1 weights and
threshold `0.53`. The opt-in spatial diagnostic ran successfully. Its
integer-only private JSON report is
`D:\VIIL-Sentinel\data\private\assist-frozen-multipose-spatial-audit-20261027.json`.

| Prespecified geometric category | 8 ADL reference videos | 3 staged Fall reference videos |
|---|---:|---:|
| Decoded video frames | 1,838 | 1,558 |
| `not_multiple` | 1,787 | 698 |
| `overlapping_torso_geometry` | 7 | **0** |
| `spatially_separated_geometry` | 3 | **820** |
| `ambiguous_geometry` | 24 | **0** |
| `unusable_torso_geometry` | 17 | **40** |
| `unsupported_pose_count` | 0 | 0 |
| **All multi-pose frames** | **51** | **860** |

Both sums reconcile exactly with decoded frames and with
the previous independent adapter reason audit's
`multiple_people` counts (51 ADL and 860 Fall).

Among Fall reference clips, **363/395** multi-pose frames in
*forward fall while walking* and **457/465** in *backward fall*
were geometrically separated; the remaining 32 and 8 had unusable
torso keypoints. The *vertical fainting fall* had no multi-pose
frames at all (453/453 strict accepted torso frames), but still
was missed by the frozen V1 and original heuristic. No new model
candidate results or weights were changed by this tool.

**Interpretation:** In this exposed, tiny external reference set,
almost all usable multiple-pose Fall frames were *spatially separated*,
not in the very close torso-overlap bucket. This makes a simplistic
"always collapse duplicate poses" fix especially unjustified.
Separation is still **not proof of two true humans** without
independent frame review. The 40 geometry-unusable frames remain
uncertain. Maintaining multi-pose abstention in production is the
safety-preserving decision. Improving real Fall recall additionally
requires event-annotated new training footage because one fully
observed Fall reference was still missed.

There is **no independently reviewed fall-onset ground truth** here,
no unique per-video subject identity, no validated real-world
performance or false alert/hour inference. These exposed test videos
must not be used to tune thresholds/association decisions and then
called untouched test data.

## Next steps for the developer

1. **Independent real scene annotation**: on fresh consented videos
   classify true extra persons, duplicated pose hypotheses and
   reflections/background people. This study alone cannot do so.
2. Develop a bounded **research-only association** experiment
   with unique identity uncertainty, explicit ambiguous/multi-person
   abstention; keep original production adapter unchanged.
3. Solve the second missed-Fall issue separately: one staged fainting
   clip had 453/453 valid torso frames yet both frozen V1 and
   original heuristic issued no fall candidate. Gather new annotated
   fall onset labels, subject/camera-disjoint training/validation,
   and a fresh untouched test set.
4. Measure long ADL false alarms/hour, fall-event recall/delay,
   edge CPU/RAM and FPS before any live alarm promotion.

Branch: `member1/feature/frozen-multipose-geometry-audit`,
integrate only `member/feature/preprod` after passing tests.
Human-controlled `main` and shared `preprod` MUST stay unchanged.
