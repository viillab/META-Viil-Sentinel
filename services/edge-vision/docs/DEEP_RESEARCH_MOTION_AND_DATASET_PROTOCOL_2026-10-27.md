# VIIL Sentinel — research-to-engineering upgrade (Member 1, 27 Oct 2026)

## Status (evidence, not a performance claim)

The current installed MediaPipe Lite pose model **runs**, but the production
fall candidate policy remains a non-clinical temporal heuristic. In its
existing eight-clip IKAR staged-human fall pilot, only **one positive of eight**
was detected. Those IKAR clips lack the normal-activity (ADL) negative class,
so this is *not* a deployment reliability estimate and cannot determine
false-alert rates, calibration or human safety.

This change is **two research-support components**, not a trained replacement:

1. An **opt-in experimental temporal feature extractor** that calculates
   time-aware hip vertical velocity, torso angular velocity, pose geometry,
   visibility and a missing-landmark mask using the existing four torso
   landmarks. It keeps a bounded O(256)-sample window and does not persist
   image/pose data. These features are dimensionless normalized image-space
   estimates, NOT actual physical velocity in m/s. The optional
   `video_benchmark --motion-study` exports only aggregate maxima by
   pseudonymous clip ID. No default fall-detection decision is modified.
2. A **metadata-only train/val/test subject-disjoint split audit** (v2 schema)
   requiring Fall and ADL examples in EACH split. Same subject across
   splits, same recording/alternate camera view across splits, reused
   SHA-256 of media, duplicate clip ID, inconsistent labels, missing
   groups or privacy-dangerous fields all fail closed. Output includes only
   counts; assertions on identity and consent must still be externally
   verified. This audit is a training preflight, NOT an authorization to
   download or use any dataset.

## Research findings and project implications

### Temporal and structural modeling

Yu et al. (2025), *A Real-time skeleton-based fall detection algorithm based
on temporal convolutional networks and transformer encoder*, Pervasive and
Mobile Computing 107:102016, DOI:10.1016/j.pmcj.2025.102016,
https://doi.org/10.1016/j.pmcj.2025.102016

- Uses skeleton pose sequences and TCN + Transformer Encoder, and
  weighted focal loss for class imbalance. Reported 19 FPS on Jetson Orin NX
  in their specific environment; **not a performance number for VIIL Sentinel**.
- Relevance: unlike a single torso horizontal angle, temporal change and
  contextual movement are learnable. Our new motion window provides an
  initial *feature interface*, not an implementation of TCNTE.

2025 Scientific Reports, *Fall recognition using a three stream
spatio temporal GCN model with adaptive feature aggregation*,
https://doi.org/10.1038/s41598-025-95508-7

- Joint geometry, joint motion and temporal residual streams can complement
  one another. Relevance: track motion and missing confidence separately
  rather than depending on one static geometric gate.
- **Our four-torso-keypoint feature extractor cannot reproduce a full
  17/33-joint ST-GCN**. Expanding to more joints will require separately
  reviewed contracts, privacy and tracking tests.

Google AI Edge Pose Landmarker official API:
https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker

- Outputs normalized 2D and 3D world landmarks. Our current design uses
  2D image coordinates and a bounded, in-memory feature window. No
  metric velocity or real-world physical acceleration is inferred.
- Model and input selection must be tested together. Earlier local trials
  found that downscaling 1280px inputs to 640/480px was NOT faster overall.

### Evaluation quality and subject leakage

*Methods for the Real-World Evaluation of Fall Detection Technology:
A Scoping Review* (2018), Sensors 18(7):2060,
https://doi.org/10.3390/s18072060

- Report sensitivity/recall alongside precision and false alarms per
  observation/exposure hour when properly defined. The **definition of an
  event and observed monitoring time matters**. Fall-only data cannot
  establish normal-activity false alerts.
- Relevance: keep clip-level and event/onset metrics distinct, do not
  falsely convert a clip-level precision of 1/1 to real-life performance.

*Auditing Multimodal Fusion Benchmarks: Leakage, Attribution, and
Calibration in Elderly Fall Detection* (2026),
https://www.mdpi.com/2504-4990/8/10/298

- Motivates subject/group-wise holdouts and fitting preprocessing only on
  the training fold. Clip-random splits risk subject identity leakage.
- Relevance: strict `split_audit.py` blocks declared person,
  same-recording and same-media overlap across train/val/test. It cannot
  detect falsely recorded subject identities or video near-duplicates
  without an additional independent source audit.

### Potential additional datasets — check licenses *before* use

| Dataset | Fall and normal activity? | Provenance / licensing caveat |
|---|---|---|
| IKAR (2026, current local subset) | No — 8 chosen positive samples only | CC BY 4.0; 278 publisher clips of staged human falls; maintain attribution, no identifying frames in Git |
| CAUCAFall (2022) | Yes — five fall types, five ADLs, 10 subjects | Dataset article published CC BY, https://doi.org/10.1016/j.dib.2022.108610 ; verify exact video repository rights and consent terms before local download |
| UR Fall Detection (2014) | Yes — 30 falls, 40 ADLs | **CC BY-NC-SA 4.0, noncommercial academic use**; do not merge into distributable commercial training without additional permission, https://www.fenix.ur.edu.pl/~mkepski/ds/uf.html |
| SAFER-Activities (ECCV 2026) | Yes — >66h, 46 subjects, frame-level labels & lookalike sitting/lying | **CC BY-NC-SA 4.0**; excellent academic research comparison, NOT blanket commercial permission, https://safer-activities.github.io/ |
| Figshare 2017 activities from 29 subjects (2025) | Yes — 999 falls, 1017 ADL listed | Metadata describes CC BY 4.0, total download ≈2.36 GB, verify precise package applicability and subject IDs: https://figshare.com/articles/dataset/28596332 |

Research figures from other publications **must not** be presented as VIIL
Sentinel measured accuracy or compared numerically without matching
cohorts, labels, preprocessing, perspectives and evaluation protocols.

## Local real-human staged-fall motion study (non-classifier)

Command:

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m sentinel_edge.video_benchmark --manifest "D:\VIIL-Sentinel\data\private\ikar\IKAR_dataset\ikar_sample_manifest.json" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --confirm-consent --motion-study
```

Verified: **889 frames processed** and positive-only detection baseline
remained **TP=1, FN=7**, 1/8. Derived aggregate exploratory signals
(per-video maximum over frames, clipped to bounded magnitudes):

| Staged fall clip | Max absolute normalized hip motion per second | Max abs torso rotation, deg/s |
|---|---:|---:|
| blackouts-01 | 1.531 | 360 (clipped) |
| blackouts-02 | 1.036 | 360 (clipped) |
| faintings-01 | 0.683 | 360 (clipped) |
| faintings-02 | 0.986 | 237.386 |
| slips-01 (only detected clip) | 0.614 | 360 (clipped) |
| slips-02 | 0.628 | 261.480 |
| trips-01 | 0.703 | 77.779 |
| trips-02 | 1.811 | 360 (clipped) |

**Interpretation:** Some *missed* events have more detected motion than the
only detected clip. Therefore motion is a promising candidate explanatory
input; peak speed alone is **not** a fall rule and likely also occurs when
sitting abruptly, running or moving close to the camera. Clipping can
saturate; 360 means ≥360 deg/s, not necessarily exactly 360. Image-relative
hip movement is sensitive to framing/camera movement.

### Research split validation (synthetic metadata example)

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m sentinel_edge.split_audit --manifest examples/synthetic/subject_disjoint_v2.example.json
```

The example contains only invented subject names and dummy metadata. The
command validates declarations, outputs group/class *counts only*, has no
network dependency, downloads nothing and trains no model. Actual privacy
and licensing clearance are still separate tasks. Do not reuse the v1
video evaluation manifest as a v2 training manifest by guessing subject IDs.

## Next model development protocol (not yet implemented or validated)

1. Collect authorized Fall + ADL with stable *pseudonymous participant and
   recording/take* group IDs, true source license and full video provenance.
   Use subject-disjoint train, development and **untouched test** split.
2. Identify events at frame-level fall onset where feasible. Add sitting,
   lying, picking up, getting up, walking and rapid non-fall movements.
   Maintain complete non-fall exposure duration to estimate false alarms/h.
3. Fit normalization on *train subjects only*; freeze preprocessing, feature
   schema, model selection and alert threshold based on validation subjects.
   Do not train on IKAR's eight prior benchmark clips and then treat their
   accuracy as held-out generalization.
4. Compare (a) unchanged legacy heuristic, (b) a truly trained lightweight
   TCN/GRU on a **fixed-rate, mask-aware time window** (this version
   computes time-aware speed but does **not** resample frames), and (c)
   optional ST-GCN or TCN+Transformer if enough licensed subjects and
   compute budget are available. Use an identical split and published
   experiment configuration; measure generalization on unseen people.
5. Report person-wise recall, event-level precision, false alarms per
   negative observation hour, fall-onset detection latency, RAM/CPU/FPS
   on target hardware, model bytes and robustness on multi-person,
   occluded and camera-shifted conditions.
6. Do not connect candidate output to automatic emergency dispatch.
   Human review remains mandatory; only Member 2 may add a separately
   authenticated real Meta API path with owner approval.

**Shipped in this change:** motion features + aggregate-only offline
diagnostics + split audit + synthetic tests/docs. **Not shipped:** actual
trained TCN/GRU/ST-GCN weights, real-world accuracy improvements,
production alert policy changes, additional licensed human datasets.
