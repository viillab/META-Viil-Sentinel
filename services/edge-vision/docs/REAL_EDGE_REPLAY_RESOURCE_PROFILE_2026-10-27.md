# VIIL-Sentinel — Actual Edge Replay Performance & Memory Profiling
27 October 2026 · Member1 · Offline, research-only, no safety deployment

## Engineering question
After actually testing IKAR 2026 as an external new Fall video source
(and refuting promotion of the NumPy Tiny MLP due to worse declared
validation performance), what are the CPU/RAM/FPS costs of the REAL
video decode + MediaPipe Lite VIDEO-mode multi-pose 2 + strict torso
adapter + original temporal heuristic pipeline?

Prior published MLP/linear per-window microseconds are **NOT** the
latency of end-to-end video inference. This new module measures actual
wall-clock replay, CPU time and sampled process RSS on an authorized
local Windows workstation. All media are source-pinned and private.

## Data, safety, provenance

- Input: **exactly 8 prespecified original IKAR MP4s**: ids `0`
  and `1` in each publisher category, trips/slips/faintings/blackouts
  sourced from AGH University of Krakow, DOI
  https://doi.org/10.58032/AGH/A1NZPE ; publisher source CC BY 4.0.
- The downloaded official v1.0 archive
  `IKAR_dataset.tar.gz` has pinned SHA-256
  `722ec563082373213fe43af94173b8ad1273a703b32acb262b6f3d21dd1f7809`.
  The source-frozen per-video private manifest is rechecked with
  local SHA-256 for **every** source MP4 and its spatial bounding-box
  annotation JSON *before the first performance pass*. Unknown actor
  identities and fall onsets remain unknown.
- Processed strictly **one local video at a time**, using the
  exact same `collect_video_frames` code path as original frozen
  scientific evaluations, `PoseLandmarker` MediaPipe `num_poses=2`,
  and the existing `TemporalFallDetector` heuristic without
  threshold, person selection, or event policy change.
- Two fixed benchmark passes in this order: **native video
  resolution** `max_inference_side=0`, then explicitly **experimental**
  aspect-preserving side cap `512`. Both decode/score all the frames
  including cases with low confidence and multiple people. This is
  not retraining or safety threshold tuning.
- No webcam and no participant-specific data export. The frame
  consumer tallies only counts, never buffers pose/frame content.
  The event consumer counts events only, not event timestamps.
  Model and raw video data never leave ignored `data/private`;
  report includes only grouped aggregates by 4 publisher action
  categories, model SHA, timings and **own-process memory** metrics.

## Measurement contract

For each file, calls run:
1. `perf_counter()` around the **entire** existing collector call
   (including video open, MediaPipe model creation, decoding,
   inference, strict torso adapter and original heuristic; this is
   **not** frame-only inference).
2. `process_time()` around the same call to measure accumulated
   process CPU time. CPU seconds can exceed wall seconds on native
   multithreaded inference. No GPU wattage or power meter exists.
3. `psutil.Process().memory_info().rss` at the start, first frame,
   every 16th decoded frame and after returning. Peak displayed is
   **largest sampled resident-set value**, **NOT the provable true
   instantaneous RSS peak** and not total physical system RAM.
4. Observe original source FPS and declared total frame counts via
   OpenCV. Require **every** source frame to be decoded and received
   once, with pose-availability parity and event counts reconciled
   against the original collector. Incomplete decoder clips fail
   closed rather than show artificially high FPS.
5. Aggregate FPS = total decoded frames / sum complete
   collector wall seconds; playback-speed ratio = original
   source-video nominal duration / sum processing wall seconds.
   Per-clip median FPS is also reported, clearly distinct from
   global frame-weighted FPS.

The included model startup/teardown per video means the result is
**offline cold/repeated video file replay performance**, not a
persistent live-camera steady-state FPS or worst-case incident
latency. Second pass also runs after the first pass with warm file
caches and different input size. Differences in OS cache/thermal
state or scene selection can affect comparisons, so this is not a
validated resource optimization or deployment setting.
The 512 experiment can change multi-pose detection, candidate counts,
or temporal signals: report these as regressions and never silently
promote 512 to the live detector.

On these eight already-exposed, **staged Fall-only** clips, no ADL,
human onset or independently verified volunteer identities are
available. Do not report accuracy, recall, false alerts/hour,
sensitivity, event latency or generalization from this profiler.

## Commands

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$root = "D:\VIIL-Sentinel\data\private\public-datasets\ikar-2026"
$private = "D:\VIIL-Sentinel\data\private"

# Already prepared with verified official source archive and 8 selected MP4s.
& $py -m sentinel_edge.edge_resource_profile `
  --root $root `
  --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --report "$private\ikar-frozen-edge-replay-resource-profile-20261027.json" `
  --acknowledge-media-rights --acknowledge-pose-privacy

& $py -m pytest -q
& $py -m ruff check .
```

The private aggregate report uses exclusive-create mode to prevent
accidental overwrites. For repeat benchmarking choose a **new
private filename**, preserve external source immutability and
document test order. The 8 video source manifest and media, official
pose `.task` and any trained joint weight JSON all remain in
`data/private` or ignored model directories. The profiler does
not load the 30D joint weights: it evaluates the **original
heuristic** and actual MediaPipe resource use only.

## Measured results from actual local Windows replay, 27 October 2026

**Successfully completed TWO passes over all 8 SHA-pinned original IKAR
clips**, in fixed order (native resolution first, then experimental
512px cap), on the authorized Windows 12-logical-CPU workstation.
Every expected frame was decoded in each pass (889/889), and the
original `collect_video_frames` callback/parity invariants passed.
These are real CPU/video/MediaPipe measurements, **not synthetic test
outcomes**.

| Actual metric | Native input | Experimental 512px cap |
|---|---:|---:|
| Clips fully decoded | 8/8 | 8/8 |
| Video frames processed | 889 | 889 |
| Original video nominal duration | 29.634 s | 29.634 s |
| Complete wall processing time including per-clip model init | **36.115 s** | **35.577 s** |
| Original process CPU time | 42.407 s | 37.547 s |
| **Frame-weighted full replay throughput** | **24.62 FPS** | **24.99 FPS** |
| Speed vs original 30FPS source video | 0.821× | 0.833× |
| Strict multi-person-safe Pose adapter accepted | 831/889 | 865/889 |
| Original temporal heuristic candidate events | 1 | **2** |
| Maximum *sampled* own-process RSS | 248.24 MiB | 245.20 MiB |

Native category-specific full-pipeline throughput:

- Trips (2 videos, 241 frames): **22.33 FPS**
- Slips (2 videos, 158 frames): **24.41 FPS**
- Faintings (2 videos, 251 frames): **26.33 FPS**
- Blackouts (2 videos, 239 frames): **25.65 FPS**

512px experimental category-specific throughput:

- Trips **23.94 FPS**
- Slips **24.43 FPS**
- Faintings **25.33 FPS**
- Blackouts **26.17 FPS**

**Engineering decision: DO NOT promote 512px to the live pipeline.**
Observed 512px full replay throughput is just **0.37 FPS greater**
(approximately **1.5% faster** in this one limited two-pass test).
Sampled process RSS was about 3.04 MiB lower, but these values
were not simultaneous exact memory peaks. Crucially the experimental
resize changed which strict Pose frames were accepted (**831 → 865**)
and doubled the original heuristic's observed candidate count
(**1 → 2**). Neither candidate is independently reviewed, so
the added event may be a true event or false event; **it is not
an accuracy improvement**. The second pass used warm file caches
and possibly changed CPU load; this is not a controlled throughput
comparison. Neither setting reached the nominal 30 FPS source speed
as a full per-file replay pipeline with repeated model loading.

All eight IKAR sources have publisher staged Fall classifications
only; there are **zero reviewed ADL negatives** and no reviewed
fall-event onsets. Therefore this profiler cannot estimate false
alarms/hour, fall event recall, true alert delay, operator reliability,
or a verified 30 FPS persistent-camera service.

Local aggregate private report:
`D:\VIIL-Sentinel\data\private\ikar-frozen-edge-replay-resource-profile-20261027.json`.

## Future work and acceptance for a genuine deployment

- Measure **persistent camera** latency/fps/RSS after warmup on the
  actual intended low-cost edge hardware, under realistically
  concurrent workloads, 2+ people, camera motion, dim lighting.
- Use new independently consented/reviewed ADL video or live
  recordings of enough duration to measure false candidates per
  **real reviewed negative hour**. Use event-onset ground truth for
  alert detection delay (not this publisher-stage-only video).
- Verify exact system/application-level alert propagation,
  offline recovery and privacy controls; clinical/safety
  readiness is NOT established by an 8-video resource experiment.
- Keep original multi-person abstention and operator/human-review
  gates unchanged until robust independent validation.

Member1 feature branch `member1/feature/replay-edge-resource-profile`
integrates **only** into `member/feature/preprod`;
do not push `main` or shared `preprod`.
