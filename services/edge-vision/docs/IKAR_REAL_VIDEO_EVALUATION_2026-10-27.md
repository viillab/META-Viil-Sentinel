# VIIL Sentinel — first real-human recorded fall video evaluation (IKAR)

**Date:** 2026-10-27, Thailand
**Status:** Completed locally on 8 positive-only volunteer-staged recordings.
**Scope:** Baseline prototype exploration; **NOT a generalizable fall accuracy
benchmark, medical performance validation, deployment approval or accident study.**

## Source and rights

* Dataset: **IKAR: Intelligent Kinetic Activity Recognition - Fall Detection Dataset**,
  version 1.0, September 29, 2026.
* Authors: Kamil Opyrchał, Łukasz Burliga, Maja Zielińska, Karolina Zając,
  Maria Potwora, Martyna Jagoda, Dominik Mika, Franciszek Kubala.
* Publisher: AGH University of Krakow / RODBUK.
* DOI: https://doi.org/10.58032/AGH/A1NZPE
* License: **CC BY 4.0**, requiring attribution for reuse and adaptations:
  https://creativecommons.org/licenses/by/4.0/
* The videos show **real volunteers performing staged falls onto protective
  mats**, not spontaneously recorded falls or medical episodes.
* Original archive: `IKAR_dataset.tar.gz`, public Dataverse datafile
  ID `16904`, **MD5 confirmed**
  `2667661c258610c0c0aa4bc58a7fc7c2` against the publisher's
  listed checksum.
* The publisher provided 278 clips across blackouts, faintings, slips and
  trips, from 7 participants. IKAR provides no non-fall/ADL class.
* Only 8 local sample videos and their bounding-box annotations were extracted;
  no third-party media or derived landmarks were committed to Git.

Archive and sample paths (never commit, ignored by Git):

```text
D:\VIIL-Sentinel\data\private\ikar\IKAR_dataset.tar.gz
D:\VIIL-Sentinel\data\private\ikar\IKAR_dataset\
  blackouts/videos/blackouts_0.mp4, blackouts_1.mp4
  faintings/videos/faintings_0.mp4, faintings_1.mp4
  slips/videos/slips_0.mp4, slips_1.mp4
  trips/videos/trips_0.mp4, trips_1.mp4
  ikar_sample_manifest.json
```

## Environment / protocol

* On-device MediaPipe Pose Landmarker Lite, local model at ignored
  `D:\VIIL-Sentinel\models\pose_landmarker_lite.task`.
* Model SHA-256:
  `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`.
* Existing VIIL temporal fall heuristic; default thresholds unchanged:
  56° torso horizontal-angle threshold, 0.13 relative hip descent,
  450 ms sustained horizontal/descent hold; minimum pose visibility 0.55.
* One label per clip: fall=true, from the IKAR category. Labelbox spatial
  bounding boxes **do not provide a manually verified fall-onset timestamp**,
  so no `onset_ms` was supplied and true detection latency cannot be scored.
* Detector runs on all decoded frames, without storing images, video copies,
  or pose traces. Source media remains on local disk, ignored by Git.
* Two clips per category, deterministically selected by filename
  (`*_0.mp4` and `*_1.mp4`). NOT a randomized or subject-disjoint sample.
* No threshold tuning was performed against these evaluation clips.

## Measured result — 8 all-positive clips

| Clip (pseudonymous) | GT | Detected | Frames | Valid pose frames | Signal gate diagnostic |
|---|---|---|---:|---:|---|
| ikar-blackouts-01 | Fall | No | 103 | 102 | Horizontal+descent held at most 300 ms vs 450 ms threshold |
| ikar-blackouts-02 | Fall | No | 136 | 114 | 8 horizontal frames, 0 satisfying horizontal+descent |
| ikar-faintings-01 | Fall | No | 133 | 129 | 0 horizontal frames |
| ikar-faintings-02 | Fall | No | 118 | 104 | 0 horizontal frames |
| ikar-slips-01 | Fall | Yes | 87 | 87 | 35 horizontal+descent frames, 1133 ms maximum joint gate run |
| ikar-slips-02 | Fall | No | 71 | 71 | Maximum observed descent 0.1273 vs required 0.13 |
| ikar-trips-01 | Fall | No | 110 | 85 | 1 horizontal frame, no qualifying joint gate |
| ikar-trips-02 | Fall | No | 131 | 128 | 0 horizontal frames |
| **TOTAL** | **8 Fall** | **1 detected** | **889** | **831** | **58 frames without valid pose** |

**Detected events:** 1 true-positive clip (`ikar-slips-01`,
candidate at 2.000 seconds *relative to video start*); **7 misses**.
**Observed recall: 1/8 = 12.5%** on this specific, tiny positive-only subset.
Pose availability **831/889 = 93.48%** across evaluated frames.

The numeric confusion-matrix output for this subset was TP=1, FN=7,
FP=0 and TN=0. Its precision=1 and F1≈0.222 are **not reliable evidence
of specificity, false-positive control, or general accuracy** because
zero negative clips were evaluated; no meaningful false-positive rate can
be calculated. The updated CLI labels those limitations explicitly.

Descriptions of missed gate conditions are aggregate observables, not
verified causes of failure: video perspective, action timing, geometry
assumptions, inference noise and state machine logic may contribute.
No claim about specific clinical conditions can be inferred.

## Reproduce without including media in Git

From `D:\VIIL-Sentinel\services\edge-vision` after privately acquiring
the CC BY 4.0 licensed IKAR archive and extracting the matching 8 files
into the dataset root:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_ikar_manifest.py --dataset-root "D:\VIIL-Sentinel\data\private\ikar\IKAR_dataset" --samples-per-category 2 --acknowledge-cc-by

.\.venv\Scripts\python.exe -m sentinel_edge.video_benchmark --manifest "D:\VIIL-Sentinel\data\private\ikar\IKAR_dataset\ikar_sample_manifest.json" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --signal-diagnostics --confirm-consent
```

The manifest generator uses exclusive creation and refuses overwriting an
existing manifest. If it was already generated, skip its command and run
only the evaluator. Users should review the original license and consent
conditions. No remote endpoint is called by these commands.

## Required next evidence — before changing thresholds

1. Acquire separately licensed, consented real-human **non-fall/ADL**
   recordings; IKAR's four fall categories alone are not enough.
2. Collect more participants and viewpoints, and keep subject-disjoint
   threshold-development and held-out evaluation sets.
3. Validate frame-accurate fall onsets manually if measuring latency.
4. Add distinct fall subtypes, occlusions, partial falls and sitting/
   lying/bending confounders, then compare false alarms per exposure hour.
5. Evaluate candidate detector enhancements (motion dynamics beyond
   horizontal torso assumption) on *development* data, then confirm on
   held-out footage; never tune against this eight-clip test and report
   the result as held-out generalization.
6. Keep event handoff `confirmed_fall=false`, score uncalibrated, and
   human review required; do not treat negative outputs as safe conditions.
