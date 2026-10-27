# Member 1 — Optional input resolution experiments (2026-10-27)

**Experiment status: NOT PROMOTED.** Production runner and normal offline
benchmark still process the original decoded frame resolution by default.
The extra `--max-inference-side` option is **offline benchmark-only** and
opt-in. No frame dropping, interpolation of detector timestamps, reducing
`num_poses`, altering temporal thresholds, dataset changes or extra uploads.

## How it works

- `max_inference_side=0`: default; no image resize or additional copy.
- `256..4096`: optional longest-side cap in pixels. Images with longest
  side already below the cap remain untouched; larger BGR frames are
  downscaled using OpenCV INTER_AREA while preserving aspect ratio.
- Original BGR image is not overwritten, frame count remains identical,
  relative timestamps and the original MediaPipe model are unchanged.
- This still **changes image content reaching MediaPipe**, potentially
  impacting pose estimation and fall candidate outputs. It is NOT a safe
  production replacement unless separately validated on representative
  positive and negative recordings.

## Local measurements on real filmed human poses

Source: IKAR (Opyrchał et al., AGH University, 2026, CC BY 4.0),
https://doi.org/10.58032/AGH/A1NZPE.
These eight videos contain *staged volunteer falls*, not spontaneous
accidents. Same licensed local Pose Landmarker Lite task and the same
8 positive-only clips used for prior baseline; 889 decoded frames.
The three measurements below were **serial** (one model process at a
time) on the Windows workstation, with optional psutil reading resource
usage from within the inference process. They are single-run figures
including startup, model load, decoding and scoring.

| Measure | Original (0 cap) | 640 px cap | 480 px cap |
|---|---:|---:|---:|
| Elapsed wall time (s) | 33.319 | 35.041 | 36.982 |
| Overall effective throughput (FPS) | 26.68 | 25.37 | 24.04 |
| CPU total (seconds) | 40.219 | 35.656 | 39.031 |
| Native-inclusive peak working set (MiB) | 248.49 | 245.55 | 244.17 |
| Pose-valid frames | 831 | 855 | 861 |
| Fall candidates / clips | 1 / 8 | 1 / 8 | 1 / 8 |
| Fall candidate timestamp | slips-01 at 2000ms | same | same |

**Result:** Downscaling reduced peak memory by only ~2.94 to 4.32 MiB
and 640 px reduced cumulative CPU time in this run, but neither
downscaled cap improved end-to-end elapsed time: 640 was ~5.2% slower,
480 was ~11.0% slower. The extra resize may cancel inference savings.
**Do not promote any downscale cap to the default.**

The apparent increase in valid Pose frames (831 → 855 / 861) only
means more frames met current pose validity checks; it **does not mean
better detection accuracy**. Detected falls remain **1/8 (12.5% recall
on this tiny positive-only subset)**; there are no normal-activity
negative clips, subject-disjoint validation or precise onset labels.
The identical one-event outcome is not proof that unseen fall movements
or multi-person scenes would behave identically.

The experiments were executed sequentially for time/RAM comparison.
Two exploratory runs were originally launched concurrently and are
excluded from the table because load contention makes timing unfair.
One trial per cap is still insufficient to claim stable speed ranking.
Use balanced randomized trial order and medians on actual target hardware
before making performance recommendations.

## Reproduce (offline, consented/licensed media only)

Run PowerShell in `D:\VIIL-Sentinel\services\edge-vision`:

```powershell
# Original default:
.\.venv\Scripts\python.exe scripts/profile_edge.py --manifest "D:\VIIL-Sentinel\data\private\ikar\IKAR_dataset\ikar_sample_manifest.json" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --confirm-consent

# Experimental 640 px cap:
.\.venv\Scripts\python.exe scripts/profile_edge.py --manifest "D:\VIIL-Sentinel\data\private\ikar\IKAR_dataset\ikar_sample_manifest.json" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --confirm-consent --max-inference-side 640

# Experimental 480 px cap:
.\.venv\Scripts\python.exe scripts/profile_edge.py --manifest "D:\VIIL-Sentinel\data\private\ikar\IKAR_dataset\ikar_sample_manifest.json" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --confirm-consent --max-inference-side 480
```

The reporter emits aggregate metadata to stdout only. Third-party
videos and model files stay under Git-ignored local folders.
Neither pipeline uploads private images or derived poses.

## What to focus on instead

1. Native MediaPipe model initialization and per-frame inference remain
   dominant; reducing input pixels alone did not improve wall time here.
2. Obtain permission-cleared **No-Fall/ADL** human recordings to measure
   false alerts (sitting, bending, lying, standing), then perform a
   subject-disjoint fall/non-fall benchmark.
3. Compare model variants, CPU delegate options and latency with the same
   privacy / people-count safeguards on *target edge hardware*. Treat any
   design affecting tracking-state continuity as a separate experiment.
4. Preserve conservative unverified candidate contract and human review.
