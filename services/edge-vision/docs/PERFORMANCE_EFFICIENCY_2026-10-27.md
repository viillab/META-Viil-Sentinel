# Member 1 — Performance, RAM, disk and footprint audit (2026-10-27)

## Goal and outcome

Speed up local fall-candidate evaluation and reduce data buffering **without
changing the actual MediaPipe pose model, inference resolution, multiple-person
abstention behavior, event thresholds, output semantics, consent or accuracy**.

Implemented a default **streamed pose evaluation** path: the video runner calls
a bounded-memory accumulator with each frame and each event it already detected.
It no longer collects full landmark dictionaries in a list *or runs a second
TemporalFallDetector* over them. Only aggregate counts and event timestamps
are retained per clip, plus the final clip-level report.

`--buffered-eval` remains as a correctness/performance reference.
`--signal-diagnostics` still follows the full-frame buffered path because it
produces extra aggregate gate analysis. Neither mode persists private pose data.

## Measured local benchmark — 8 IKAR volunteer-staged fall clips

Source/licensing: IKAR (Opyrchał et al., 2026), CC BY 4.0,
https://doi.org/10.58032/AGH/A1NZPE.
These are **recordings of real volunteers staging falls safely**, not accidents.
All eight videos and the manifest were processed entirely on the Windows host,
with the same local Pose Landmarker Lite model file SHA-256
`59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`.

Measurements are **one run per mode**, on the same machine, including Python
startup, model initialization, OpenCV decode and JSON serialization.
The optional `psutil` probe measures peak Windows working set and CPU seconds
from **inside the inference process**. Earlier external profiler polling
returned misleading 4 MB values, which are excluded from this report.

| Measurement | Buffered reference | Streamed default |
|---|---:|---:|
| Real human staged clips | 8 | 8 |
| Total frames | 889 | 889 |
| Valid pose frames | 831 | 831 |
| Wall time | 34.651 s | 33.505 s |
| Effective end-to-end throughput | 25.66 fps | 26.53 fps |
| CPU seconds including native runtime | 39.656 s | 38.906 s |
| Peak working set (native + Python) | 247.77 MiB | 247.91 MiB |
| Detected positive clips | 1/8 | 1/8 |
| Missed fall clips | 7/8 | 7/8 |

Single-run time reduction: **1.146 seconds, 3.3%** versus buffered; CPU
seconds are 0.750 lower (1.9%). Both may fall within machine/load variance:
repeat multiple times before asserting performance improvements.
**Peak RAM did not measurably decrease** (difference +0.14 MiB); native
MediaPipe allocations dominate in this small sample. The *algorithmic*
pose-storage complexity in the default evaluator changed from O(frames)
to O(candidate events), but that is **not proof of lower process RSS**.
No throughput or CPU value above should be projected to another device.

**Detection semantics did not change:** event count/time on each clip
matched exactly, including one event at 2,000 ms in `ikar-slips-01`.
The existing dataset is positive-only; recall remains 12.5% and there is
no valid estimate of false alarms or medical suitability. Optimization
must not be confused with detection quality.

## Local disk footprint (read-only inspection)

Values are binary MiB (1 MiB = 2²⁰ bytes), not production build artifact sizes.

| Local component | Observed size |
|---|---:|
| Ignored MediaPipe Lite `.task` model | 5.51 MiB |
| Edge Python `.venv` after installing optional profiler library | 354.85 MiB |
| Eight privately extracted IKAR clips and manifest | 3.71 MiB |
| Downloaded full IKAR archive | 121.41 MiB |

Most local disk consumption is **dev environment and an optional archive**,
not the deployed algorithm. The `.dockerignore` newly excludes `.venv`,
`node_modules`, `.git`, private datasets, models, weights and videos from
a root Docker build context. This also reduces the risk of accidental
distribution; it does not delete existing local data.

**No data was deleted.** If storage is scarce, after validating that source
files can be reacquired from the publisher, the human operator may decide
whether the full `data/private/ikar/IKAR_dataset.tar.gz` archive needs
to remain locally stored. Do NOT automatically delete the private sample,
annotations, environment or models, and never upload them to public Git.

## Reproduce time and resource measurements

PowerShell, from `D:\VIIL-Sentinel\services\edge-vision`:

```powershell
# Optional development-only profiling package; not a runtime dependency
.\.venv\Scripts\python.exe -m pip install psutil

# Streaming default
.\.venv\Scripts\python.exe scripts/profile_edge.py --manifest "D:\VIIL-Sentinel\data\private\ikar\IKAR_dataset\ikar_sample_manifest.json" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --confirm-consent --disk-summary

# Buffered reference under the same conditions
.\.venv\Scripts\python.exe scripts/profile_edge.py --manifest "D:\VIIL-Sentinel\data\private\ikar\IKAR_dataset\ikar_sample_manifest.json" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --confirm-consent --buffered-reference
```

The script emits aggregate JSON only. It does not write metrics or derived
landmarks to disk, use the camera or access external services. Run without
concurrent heavy jobs for better repeatability, alternate run order, and
compare medians over multiple trials.

## Remaining practical bottlenecks

- The MediaPipe native pose inference, 1280×720 frame decode and repeated
  per-clip landmarker initialization dominate work and native RAM.
- Reusing one VIDEO-mode landmarker across independent clips might reduce
  startup work but risks cross-clip tracking-state contamination; **not
  enabled** without a proven model-reset design.
- Aggressive frame subsampling, smaller input frames, `num_poses=1` or
  reduced thresholds might improve speed but could worsen missed falls or
  multi-person safety. None was enabled.
- Real CCTV or device streaming CPU/RAM/latency need separate on-target
  profiling and subject-disjoint positive/negative validation.
