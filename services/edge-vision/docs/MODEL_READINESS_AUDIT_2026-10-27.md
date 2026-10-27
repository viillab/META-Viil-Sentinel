# VIIL Sentinel — AI model readiness audit, Member 1 (2026-10-27)

**Summary: POSE INFERENCE WORKS; FALL DETECTION NOT RELIABLE; META LIVE NOT INTEGRATED.**
This is an engineering/prototype status, **not** a clinical validation or
authorization for automated alarms or emergency dispatch.

## Actual local checks executed on Windows workstation

1. `python -m sentinel_edge.doctor --model D:\\VIIL-Sentinel\\models\\pose_landmarker_lite.task`
   - Successful: MediaPipe 0.10.35, exactly one OpenCV provider
     `opencv-contrib-python 5.0.0.93`, non-empty local `.task` present.
2. `python -m sentinel_edge.model_smoke --model ... --frames 30`
   - **Real MediaPipe model inference** ran in VIDEO mode on 30 generated 256×256
     all-black frames (no identifiable person).
   - Model SHA256:
     `59929e1d1ee95287735ddd833b19cf4ac46d29bc7afddbbf6753c459690d574a`
   - Detected humans: 0, fall candidates: 0. This is a negative control, not
     a true positive/false positive benchmark.
   - Mean frame inference 12.512 ms; p50 11.964 ms; p95 17.649 ms,
     max 20.920 ms; 30.37 effective frames/s including startup.
     These timing numbers are for black synthetic frames, not real 720p CCTV.
3. `python -m sentinel_edge.video_benchmark --manifest <licensed private IKAR manifest> --model <task> --confirm-consent`
   - The same actual model processed **8 real filmed human staged-fall clips**,
     889 frames total, 831 valid poses (93.48%).
   - Classified as fall candidates: **1 true positive / 8 positive clips**,
     **7 missed falls**, observed recall **12.5%** on this small non-random
     positive-only subset, not a generalizable expected detection rate.
   - No negatives (normal activities), so **no meaningful false-positive
     rate or specificity** exists. No ground-truth onset timestamps; no
     defensible event-to-fall latency measurement.
   - The prototype detector is `TemporalFallDetector`, **heuristic**:
     upright posture, hip descent and horizontal hold. It is **not** a
     supervised fall-classification neural network trained on real falls.
     The Pose Landmarker itself is a real pretrained ML model.
4. `services/api/app/meta.py` inspected and `provider_for("live")` tested.
   - `MockIncidentInterpreter` is the only implemented provider.
   - Selecting any non-`mock` provider raises a RuntimeError; there is no
     authenticated real Meta multimodal call, no vision report from Meta,
     and no real source event ingestion in the local demo Backend.
   - Do not interpret `META_MODEL_ID` placeholder or any demo observations
     as a successful live Meta API request.

The privacy-handling baseline is unchanged: all IKAR clips, source labels,
and the licensed local model remain in ignored local directories.
**No human video, model bundle, key, or landmarks are committed.**

## Automated readiness check added

The offline `video_benchmark` JSON now includes a `readiness_gate` object.
It documents evidence gaps rather than asserting an automatic pass. It is
implemented in `sentinel_edge/readiness.py` and intentionally
**never authorizes real-world alerting or emergency actions based on a
dataset report alone**. It checks consistency of ground-truth/confusion
counts and warns about missing normal-activity negatives, small samples,
observed misses, unannotated fall onsets, and lack of verified
participant-disjoint holdout/on-target testing.

The gate is an **advisory completeness check**, not a medical/certification
test or a measured classifier quality threshold.

## Practical build priorities

1. Member 1: obtain properly licensed/consented **No-Fall/ADL** footage,
   plus more filmed fall scenarios (camera angles, light, occlusion,
   different participants), with subject-disjoint train/dev/test groups.
2. Member 1: build and separately evaluate a **temporal classification
   model** or more robust motion representation. Test baseline heuristics
   vs actual trained classifier on withheld people; no claim of better
   accuracy until validated with real positives and negatives.
3. Member 1: annotate fall onsets where possible, benchmark camera-to-event
   latency, false alarms per non-fall hour, recall, precision and stability.
4. Member 2: independently verify official accessible Meta model API,
   implement an authenticated adapter and consent-based multimodal
   interpretation; never connect the research prototype to automated
   emergency dispatch.
5. Member 3: keep dashboard status **SIMULATION ONLY** until authenticated
   integration and explicit human validation are implemented.

## Reproduce (PowerShell)

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m sentinel_edge.doctor --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task"
.\.venv\Scripts\python.exe -m sentinel_edge.model_smoke --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --frames 30
.\.venv\Scripts\python.exe -m sentinel_edge.video_benchmark --manifest "D:\VIIL-Sentinel\data\private\ikar\IKAR_dataset\ikar_sample_manifest.json" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --confirm-consent
```

The evaluation command prints aggregate-only JSON (now including the
readiness gate). No uploads or camera access are performed.
