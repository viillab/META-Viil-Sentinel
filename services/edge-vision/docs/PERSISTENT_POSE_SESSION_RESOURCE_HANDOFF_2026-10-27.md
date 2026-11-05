# VIIL-Sentinel — Persistent MediaPipe Runtime Research Benchmark
27 October 2026 · Member 1 · Offline replay / NO real webcam or alarm authority

## Motivation

Previous resource profiling of the **eight already-exposed source-verified IKAR
public staged Fall clips** ran MediaPipe Lite with an independent model
instance per video. On the Windows development computer, the unmodified
native-resolution original heuristic pipeline processed 889 frames in
36.115 seconds, or **24.62 frames/second**, using approximately 248.24 MiB
maximum *sampled* own-process RSS. That includes video decoding, eight
model starts/shutdowns, strict multi-person torso processing and original
heuristic; not a live camera FPS value.

To measure per-video model start overhead and feasibility of keeping the
model in memory, the new experimental `persistent_pose_session` opens
**one** official MediaPipe Lite `PoseLandmarker` for exactly eight
original staged IKAR clips, decoding all videos sequentially through
one VIDEO-mode task. This is an **offline research experiment**, not a
webcam, safety alert server, or deployed Camera API.

## Exact safety and timing contract

- Exact public source attribution: IKAR 2026 AGH University of Krakow,
  https://doi.org/10.58032/AGH/A1NZPE, CC BY 4.0, source archive SHA-256
  `722ec563082373213fe43af94173b8ad1273a703b32acb262b6f3d21dd1f7809`.
  The earlier predeclared **two video IDs 0,1 per type**
  (trips, slips, faintings, blackouts) remain unchanged.
- BEFORE initializing MediaPipe: recompute each pinned video SHA-256,
  verify eight videos and their spatial annotation JSONs and validate
  the private immutable manifest. Video frame counts are independently
  read from OpenCV metadata and checked against every actual decoded frame.
  Frames over bounded 2,000-per-video budget or malformed metadata abort.
- MediaPipe `num_poses=2`, original unmodified fail-closed
  `extract_torso_landmarks` adapter, and default original
  `TemporalFallDetector` are used. **A new heuristic instance is
  explicitly created for each video**, ensuring temporal candidate
  evidence from one publisher clip cannot carry into the next.
- For MediaPipe VIDEO mode, timestamps are strictly increasing *across*
  the entire session: per-video source FPS times with **a synthetic
  1,000 ms inter-segment gap**. These are internal monotonic timing
  inputs, **not original publisher Fall onset annotations**.
- Because the MediaPipe task instance persists across artificial file
  cuts, **its internal tracker may carry temporal state over discontinuous
  staged scenes** even though the fall heuristic restarts. Therefore
  accepted Pose frames and event counts may differ from cold per-file
  tests; they must be treated as model continuity *risks*, not automatic
  quality improvements. A seamless true live camera would have different
  frame content and timestamp scheduling from this experiment.
- One streamed detection result at a time. No person association,
  candidate pose selection, raw video, landmark coordinates, images,
  source filesystem paths, per-event timestamps or private weights are
  written into the report or committed. The video/research report stays
  below ignored `data/private`. No model or production code is changed.
- `perf_counter()` includes MediaPipe model initialization **once**,
  all decoder starts, frame conversion and detector overhead.
  `process_time()` reports process CPU seconds, which may exceed
  wall seconds in multithreaded native inference.
  Process RSS is sampled at init, first frame and every 16 frames;
  **not a true instantaneous peak, not a device power measurement**.
- Result is a frame-weighted replay FPS and ratio to summed nominal
  source playback duration; **not** true persistent live-camera FPS,
  end-to-end event notification latency, False Alarms/hour,
  sensitivity/recall, or an evidence-based release benchmark.

## Run on authorized local Windows machine

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$root = "D:\VIIL-Sentinel\data\private\public-datasets\ikar-2026"

& $py -m sentinel_edge.persistent_pose_session `
  --root $root `
  --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --report "D:\VIIL-Sentinel\data\private\ikar-persistent-pose-session-20261027.json" `
  --acknowledge-media-rights --acknowledge-pose-privacy

& $py -m pytest -q
& $py -m ruff check .
```

Output report is exclusive-create under private, never overwritten;
use a new private filename on future repetitions. No user camera,
network inference, secrets, GPU, paid API or larger framework needed.
Tests inject fake MediaPipe/OpenCV only to validate timestamp arithmetic,
one-model/eight-detector isolation, exact full-decode parity,
privacy-safe report contracts and source tamper refusal.

## Actual measured results (verified real public MP4s)

The actual full eight-video replay **completed successfully** on the
authorized Windows machine. All original public source videos were
verified against source-pinned SHA-256, all expected **889/889** decoded
frames were consumed, and **only ONE** actual MediaPipe PoseLandmarker
instance was used across all eight original video files. A separate
`TemporalFallDetector` was constructed for EACH clip (eight instances).
The MediaPipe session timestamps were strictly increasing across video
boundaries with a 1,000 ms synthetic gap. No images or poses were saved.

| Measured metric | Previous independent-model-per-clip replay | Current single persistent model session |
|---|---:|---:|
| Source video frames | 889 | 889 |
| Full replay wall time | 36.115 seconds | **31.059 seconds** |
| Complete frame-weighted throughput | 24.62 FPS | **28.62 FPS** |
| Ratio to nominal video playback time | 0.821× | **0.954×** |
| Process CPU seconds | 42.407 | 39.344 |
| Maximum sampled own-process RSS | 248.24 MiB | 241.82 MiB |
| Strict accepted torso frames | 831 | **823** |
| Original heuristic candidate events | 1 | 1 |
| MediaPipe PoseLandmarker instances | 8 | **1** |
| Separate heuristic detector instances | 8 | **8** |

The persistent session's measured MediaPipe initialization step
was **0.105 seconds** on this particular run (included in 31.059s).
Some startup overhead occurs within native OS image caching and the
video decoder and is not attributable solely to this single value.

Category outcomes from the real one-model replay:

| Publisher staged category | MP4s | Complete frames | Strict accepted frames | Heuristic events |
|---|---:|---:|---:|---:|
| Trips | 2 | 241 | 213 | 0 |
| Slips | 2 | 158 | 152 | 1 |
| Faintings | 2 | 251 | 241 | 0 |
| Blackouts | 2 | 239 | 217 | 0 |
| **Total** | **8** | **889** | **823** | **1** |

**Descriptive speed difference:** 28.62 vs 24.62 FPS is about
**16.2% more throughput** versus the prior cold-per-video run.
This is *not* a controlled repeat-paired benchmark: experiments
were run at different times with potential disk cache, CPU, thread
pool warmup, temperature and OS scheduling effects. The only
directly proven engineering property is that the new research code
completed the specified test with one long-lived model and
unmodified per-segment heuristic state handling.

**Important pose continuity warning:** exact input videos and
original strict adapter produced **831** accepted torso frames with
per-clip task reset but **823** with the shared VIDEO-mode tracker.
This 8-frame difference may result from tracker state surviving
artificial scene cuts and/or runtime inference nondeterminism.
We cannot isolate a causal mechanism without controlled repeated
trials and per-cut diagnostics. A true camera stream has continuous
scene semantics and cannot be inferred from abrupt file cuts.

The private report with only category aggregate counts is:
`D:\VIIL-Sentinel\data\private\ikar-persistent-pose-session-20261027.json`.
No per-frame event times, pose arrays, original frames, names of
volunteers, or absolute source paths are in the report. Source
staged Fall labels are still not independently reviewed event onset
truth; none of these counts measures actual Fall recall or ADL
false alerts/hour. No change to the shipped fall detector was made.

## Interpretation and next steps

A continuous camera has no abrupt video cuts; it requires a persistent
model initialized once, **sustained operation**, real camera timestamps,
multi-person occlusion and realistic light conditions. Profiling
an offline set can reveal model initialization overhead but does not
validate steady-state production latency, field reliability or identity
tracking. Future validation needs independently reviewed extended
ADL negatives to estimate full-stream false alarm/hour, fall onsets
to measure event delay, identity-verified actor/camera splits, and
persistent capture on the target low-cost edge device under
realistic resource and thermal loads.

Do not modify the existing heuristic or high-stakes incidents based
on eight already-exposed, staged Fall-only publisher clips.
Member1 topic: `member1/feature/persistent-pose-replay-benchmark`;
authorized integration: `member/feature/preprod`; leave
protected `main` and shared `preprod` unchanged.
