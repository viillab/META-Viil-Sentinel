# VIIL-Sentinel Member 1 — Research-backed Edge Fall Detection Decision

28 October 2026 | Research and reproducible engineering rationale
**Not a medical device, clinical evaluation, or production alert authorization**

## Recommendation (conditional, NOT yet scientifically superior in VIIL)

Choose **local MediaPipe Pose Lite -> confidence/visibility masks ->
fixed causal 1.5-second sequence -> a tiny causal 1D TCN candidate
-> calibrated, human-reviewed event-level evaluation**.

Keep **30D Linear 1.5s** as the independent, already executable
research baseline, and preserve the separately pinned **8s Linear V1
shadow** for historical comparison only. Also keep the hand-designed
2-second CausalMotionProbe as **untrained diagnostic**, never AI or
ground truth. Do not merge their incompatible model weights.

An operational candidate must be *two-stage*: a low-latency *research
signal* and a separately validated post-event/confirmation policy.
Do not reuse either as an automated alarm, diagnosis or ambulance
notification without real validation, governance and human review.

## Evidence from published papers (primary links and scope)

| Reference | Verified observation | Limitation / how VIIL should use it |
|---|---|---|
| Yu et al., *Pervasive and Mobile Computing* 2025, TCN+Transformer skeleton-based fall recognition, DOI 10.1016/j.pmcj.2025.102016 | Reports 19 FPS (single person) / 17 FPS (two people) on Jetson Orin NX with YOLOv8 pose/BoT-SORT; TCN captures temporal motion | Numbers are from THEIR hardware/data, not ours; a Transformer is not necessary by default |
| *A Lightweight CNN–TCN–Attention Framework*, *Electronics* 2026, 15(16):3748, https://doi.org/10.3390/electronics15163748 | 33-landmark MediaPipe input, approximately 30,000 parameters; Raspberry Pi Zero 2 W study reports 325.88ms average state-decision latency | Dataset-specific pre-fall pseudo-onset uses nose vertical velocity; not independently reviewed fall onset; cannot claim 325ms end-to-end detection in VIIL |
| Schneider et al., *OmniFall* (ECCV 2026), https://dsch.ai/omnifall/ and https://arxiv.org/abs/2505.19889 | Unifies staged, synthetic and genuine wild footage under a shared taxonomy/protocol; emphasizes staged-to-wild transfer | Source version/release taxonomy differs between original arXiv and ECCV revision. Verify LICENSE and person/likeness rights before any ingestion, avoid random clip split |
| *Real-Time Vision-Based Fall Detection Systems for the Elderly: A Systematic Review*, *Sensors* 2026, DOI 10.3390/s26165069, https://pmc.ncbi.nlm.nih.gov/articles/PMC13517638/ | Of 588 screened records only 11 reported requisite physical-hardware timing, and studies lacked older-adult real-world deployment validation | Measure actual full capture->pose->classifier->decision pipeline, not just matrix multiply |
| Masood et al., *Expert Systems with Applications* 2026, DOI 10.1016/j.eswa.2026.132675 | Neuromorphic event-camera model's simulated-to-real benchmark changed from 98.65% synthetic to 81.4% real domain | This is event-camera data, NOT transferable VIIL RGB accuracy; supports out-of-domain validation priority |
| Google AI Edge, MediaPipe pose guide, https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker | GHUM Lite architecture and device-optimized on-device pose landmarks | Manufacturer performance on reference devices is not VIIL end-to-end speed |

## Why not immediately replace 30D Linear with GRU/Transformer?

With VIIL's current, repeatedly-examined **40 CAUCAFall staged
publisher-labeled clips**, the separate 1500ms Linear research
experiment had only **31 pose/context-eligible clips**: 21 TRAIN,
5 VAL and 5 previously exposed TEST. The old test contained
3 eligible staged Falls; the model labeled **1 correctly, 2 missed**,
and 2 ADLs were eligible/negative while 2 further test ADLs
abstained. Event onset truth was NOT independently reviewed.
A bigger network cannot fix wrong or missing onset annotations or
guarantee generalization from 21 training clips.

The **best NEXT trainable architecture to compare, not yet a winner**:
a compact **strictly causal dilated depthwise-separable TCN** consuming
30 time samples x 6 motion channels, with explicit observed-pose
mask, 1.5s time horizon, small channel count and bounded RAM.
Compare against the 30D Linear using the SAME subjects, onset-aligned
windows and hardware, with the same frozen selection criterion.
A one-directional GRU and a compact temporal CNN without dilation
are valid baselines if there are enough independently reviewed
training samples. Do not use bidirectional/lookahead attention for
real-time inference even if offline classification appears better.

Do NOT increase neural-model complexity until new human-reviewed
fall onset and matched ADL data exist. A large model trained only
on clip-end pseudo-positives can learn the **already fallen** state
rather than detect an unfolding fall.

## Current bounded engineering milestone

The research-only **Causal1500msModelShadow** accepts injected
separately fitted 1.5s predictor, not 8s frozen weights, and operates
entirely in RAM using 30 uniformly spaced nearest pose frames,
from time (t-1500ms,t], at most one score per 250ms AFTER
1500ms source-time warm-up.

Strict source/gap resets, 10/30 minimum torso-visible slots and
256-pose maximum buffer prevent stale/missing context from
masquerading as valid evidence. Only aggregate scored, positive,
negative and abstained counts are exposed. No photo, raw pose, model
score, timestamp, clip identifier, incident or API dispatch.
Any replay with a fake predictor is *pipeline feasibility* only,
not a new trained classifier evaluation.

**This module is NOT wired to live camera, API, deployment or alert.**
An injected predictor's expected training contract must be pinned by
its future versioned 1500ms artifact before any opt-in real camera
shadow can be proposed. No research results authorize production.

## Verified local research plumbing (28 October 2026)

- Original source-hash-verified real CAUCAFall **TRAIN ADL clip**
  decoded fully: **115 of 115 source frames**, with original
  SHA256 rechecked after processing.
- Injected a **constant synthetic mock** (explicitly tagged
  1500ms/30D), NOT a trained fall model. The RAM-only shadow
  evaluated **12 temporal sample windows**, abstained **5** on
  insufficient valid poses, held at most **32 PoseFrames** and
  generated **zero incidents or alerts**.
- This result confirms *mechanical feasibility of past-only
  timestamp sampling with real pose input*, not learned classification,
  fall detection sensitivity, false alarms/hour, or fall onset latency.
  The fixed 1.5s model from the prior research phase was not loaded
  into this new shadow; a versioned 1.5s-only model binding is a
  remaining milestone.
- The shadow also requires exact 1500ms/30D model interface metadata
  (an accidental 8s/40D model binding is refused), strict integer
  frame timestamps and finite probability values. Interface tags are
  only safety checks, NOT cryptographic proof of training origin.
- **Full software regression:** Edge Vision **602/602 pytest passed**
  and Ruff passed. Backend **6/6 pytest**, Ruff passed;
  Dashboard TypeScript/Vite production build passed.
- **GitHub feature and integration CI:** _PENDING_EXACT_SHA_CI_.

## Frozen measurement protocol needed for claims

1. **Truth:** Two independent human reviewers annotate verified
   original full videos with FALL ONSET in milliseconds, post-fall
   recovery and hard-negative sitting, lying, kneeling, bending,
   camera shake, occlusion, multi-person scenes and no-fall periods.
   Resolve disagreement before evaluating. Publisher action class
   alone is not a fall-onset label.
2. **Partition:** Group by true individual, original take and
   camera/domain. Ensure view duplicates and person identities
   don't bridge train/val/test. New unseen site/camera and wild
   sources held out *before* feature or threshold selection.
3. **Train:** Deterministic 30 samples / 1500ms, per-step mask,
   use train-only normalization; choose class weighting,
   architecture, score smoothing and operating threshold only in
   train+validation; never tune to previously exposed held-out.
4. **Event-level:** Pre-register one-to-one match window around human
   onset. Report fall-event sensitivity and missed events, mean/P95
   true detection delay relative to onset, false candidate/alert
   events per **monitored verified no-fall hour**, pose abstention
   minutes and 95% uncertainty, by scene/subject, not just accuracy
   per clip. A zero false alarm count on two tiny ADLs is NOT
   demonstrated safe operation. Also audit the absence of future
   information in windows.
5. **Hardware:** Measure wall-clock capture/Pose/TCN/smoothing
   components (including p50/p95), FPS and real RAM on target
   CPU/GPU and connected camera. No claim of <2-second fall
   onset-to-notification until those timestamps are verified.
6. **Go/no-go:** Compare fixed-recipe models blind on new
   independent data. Prefer the simplest model satisfying
   *both* prospective event-level sensitivity AND operational
   false alarm + latency budgets. If not satisfied, continue
   research; do not enable notifications or silently change
   protected branches.

## Next steps for another developer

Build the true human-reviewed onset and negative-activity inventory;
then train/version the tiny 1D causal TCN and one-directional GRU
as *comparators* using matched labels; run source-verified streaming
shadow under opted-in local conditions; validate on staged-to-wild
OmniFall protocols only after actual license/person permission
review. Keep the existing production heuristic unchanged until
independent approval and proven metrics.

Sources are third-party public literature, not VIIL performance
certification or transferred ML weights.
