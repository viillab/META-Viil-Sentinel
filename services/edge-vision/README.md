# Member 1 — Edge Vision and Model Evaluation

**Owner:** Member 1 (you)

**Member 1 branches:** `member1/feature/*`

**Integration:** `member/feature/preprod` (actual `preprod` and `main` promoted by human)

**Status:** Actual MediaPipe pose AI inference **works**; fall-candidate heuristics remain **unvalidated for reliable safety alerts**. NOT a clinical or production safety detector.

## Research-driven model preparation (27 Oct 2026)

New [research-to-engineering audit](docs/DEEP_RESEARCH_MOTION_AND_DATASET_PROTOCOL_2026-10-27.md)
provides an experimental **bounded temporal motion-feature window** and
`--motion-study` aggregate-only real-video diagnostics, plus a strict
subject-/recording-/media-disjoint research manifest audit:

```powershell
python -m sentinel_edge.split_audit --manifest examples/synthetic/subject_disjoint_v2.example.json
```

These are **research scaffolding, not a trained TCN/GRU model**. Fall
candidate production thresholds and outputs are unchanged; the original
8-clip positive-only IKAR evaluation remains 1/8. No additional person
images, models or subject metadata have been committed.

## Private Pose-to-Window Export (reviewed human video only)

A consent-gated [local reviewed-window exporter](docs/PRIVATE_WINDOW_EXPORT_2026-10-27.md)
now connects real MediaPipe video inference to **30×6 masked motion windows**
for the existing research trainer. Group IDs, media SHA-256 and human-reviewed
interval labels must be supplied, with Fall AND ADL among disjoint train/val/test
people. Exported derived features are sensitive: the CLI ONLY creates files
inside Git-ignored `data/private`, with explicit authorization and no overwrite.

A real **in-memory IKAR pilot** decoded 87 frames and produced a 30×6 window
without assigning a Fall/No-Fall label or saving the features. IKAR was **not**
used for supervised training. A separate publisher-labeled, unreviewed
CAUCAFall study (below) has since fitted a research-only classifier; neither
experiment validates a deployed fall detector.

## CAUCAFall real-video Fall/ADL research curation

The private [CAUCAFall research curation protocol](docs/CAUCAFALL_RESEARCH_DATASET_2026-10-27.md)
uses the downloaded Zenodo OmniFall CAUCAFall derivative, publisher MMAction2
and original CSV annotations to create a **fixed subject-disjoint 40-video
proposal** (20 fall-motion, 20 clean ADL) with verified media SHA-256.
It never infers ADL labels from the names of fall source recordings,
includes no `fallen` as a fall event, and sets `label_reviewed=false`
until manual review. Optional **publisher-labeled** in-memory baseline
training is *research-only* and reports pose-quality exclusions and held-out
subjects; it does **not** assert independent human label verification.

## Independent annotation review gate (requires real human verification)

The [two-reviewer label-verification protocol and developer handoff](docs/INDEPENDENT_ANNOTATION_REVIEW_HANDOFF_2026-10-27.md)
adds `python -m sentinel_edge.annotation_review` as a **private-only**
preprocessing gate. It can generate a template with **two blank, unapproved
review entries per clip**, then compile an exporter-compatible reviewed
manifest **only if two distinct reviewers attest matching Fall/ADL activity,
timing and SHA-256 source media** for every clip. Disagreement, ambiguity,
untouched templates, changed video and missing participants fail closed.
The tool cannot independently verify reviewer identities or consent.

**No CAUCAFall clip has been newly approved by this tool:** historical
publisher-labeled research scores remain unreviewed, and data must not be
presented as independently validated until humans complete real visual review.
Private review files and derived pose remain ignored under `data/private`.

## Freeze & verify independently reviewed datasets before pose export

A [private unsigned SHA-256 dataset freeze guide](docs/REVIEWED_DATASET_FREEZE_HANDOFF_2026-10-27.md)
adds `python -m sentinel_edge.reviewed_dataset_seal` with three explicitly
acknowledged offline modes: **freeze**, **verify** and **export**. It checks
the complete two-person review, subject split separation, video hashes and
canonical fingerprints of all input manifests, then rejects changed inputs
before sensitive pose export. Raw media, review records, derived windows
and hashes are restricted to ignored `data/private`. This is a drift-check
and does NOT prove reviewer identity, participant consent, or clinical safety.

As of 27 October 2026, CAUCAFall has 40 selected clips but zero independently
reviewed labels: the freeze path must correctly reject them until legitimate
human review is completed. Previously reported prototype scores are *not*
evidence that this approval step has been passed.

## Versioned private research model weights (Member 1)

The [version-2 linear research artifact contract](docs/VERSIONED_LINEAR_RESEARCH_ARTIFACT_2026-10-28.md)
binds every **new** private 30D Linear V1 weight JSON to the fixed
train-only Z-score clamp [-12,+12] preprocessing. Legacy version-1 files
remain strictly validated and readable for older frozen research evidence,
without rewriting their bytes or changing the frozen shadow SHA/threshold.
Corrupt/mismatched numeric metadata is refused. The 30D model architecture,
original heuristic incident path, private dataset rights and lack of real
Fall accuracy/alert authority are unchanged.

## V1/V2 train-to-inference normalization parity (Member 1)

The [scaler/inference consistency handoff](docs/TEMPORAL_V1_V2_INFERENCE_SCALER_PARITY_2026-10-28.md)
repairs the research NumPy Linear V1/V2 scoring path so both fitting and
prediction use **train-only Z-score normalization clamped to [-12,+12]**.
Malformed/nonfinite descriptors now fail closed rather than producing
unbounded or NaN research probabilities. Existing weights and the
production heuristic/alert path are unchanged; this is a numerical
correctness repair, **not evidence of higher real-world Fall accuracy**.

## Lightweight V1/V2 model-quality comparison (Member 1 handoff)

The [V2 implementation and next-developer handoff](docs/MEMBER1_MODEL_QUALITY_V2_HANDOFF_2026-10-27.md)
adds a 40-dimensional mask-aware motion descriptor alongside the unchanged
30-dimensional V1 baseline. It uses train subjects for weights, validation
subjects to select candidate/threshold, and held-out test subjects for
diagnostic comparison only. The real publisher-labeled CAUCAFall pilot can
be rerun in memory without overwriting the private manifests:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.model_quality --synthetic-demo
```

**This is research model selection, not a production fall-alert model.**
Model improvements must be supported by held-out results and pose coverage,
never claimed from synthetic fixtures or validation-set optimization alone.

## Development-subject Cross-Validation (optional research gate)

The [4-fold cross-subject research protocol and next-developer instructions](docs/DEVELOPMENT_SUBJECT_CV_HANDOFF_2026-10-27.md)
add an opt-in `--dev-crossval` to the in-memory V1/V2 CLI. It rotates
train/inner-validation/outer-scoring groups over **development subjects only**.
No final test labels or features influence the CV. The same 40 real CAUCAFall
clips yielded 29 eligible *development* clips from 8 declared participants:
V1 outer-fold fall recall **9/15**, V2 **4/15**; both flagged 3 of 14 ADL
clips as fall. Inner validation chose V1 in all four folds. These clips
are staged publisher-labeled activities, not deployment evidence. The
predeclared V1 selection remains unchanged.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.model_quality --synthetic-demo --dev-crossval
```

## Original-heuristic full-video decode integrity (Member 1)

The [original/early full-decode parity handoff](docs/ORIGINAL_HEURISTIC_FULL_DECODE_PARITY_2026-10-28.md)
hardens the original offline benchmark to reject truncated source decoding,
invalid frame metadata and mismatched event counts before evidence capture.
Real source-pinned replay of 11 ASSIST-IoT videos confirms identical source
hashes and 3,396 decoded frames for both methods, with zero original
heuristic candidates versus three **untrained, unconfirmed** motion cues.
These are research-only event-candidate counts, not human-validated accuracy;
production alerts and reviewer requirements remain unchanged.

## Human-reviewed event gate for 2-second research motion cues (Member 1)

The [private evidence and two-reviewer protocol](docs/REVIEW_GATED_EARLY_MOTION_EVIDENCE_2026-10-28.md)
adds `python -m sentinel_edge.reviewed_event_benchmark --mode capture-early`
to export timestamps of **untrained, unconfirmed** early-motion
proposals **only under ignored `data/private`**, after checking all
11 original pinned ASSIST-IoT source videos and complete frame counts.
The existing `prepare` mode produces two genuinely **blank**
independent-review entries per source video; `score` remains
**fail-closed** without both complete, consistent human attestations.
Event metrics cannot be derived from publisher labels or the cue
alone. This is a preparatory research workflow: no model training,
no independent accuracy, no Alert events or API changes.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.reviewed_event_benchmark --help
```

## Causal 2-second early-motion research probe (Member 1)

[Source-verified handoff](docs/CAUSAL_TWO_SECOND_MOTION_PROBE_HANDOFF_2026-10-28.md)
adds independent, opt-in `--early-motion-probe` to the existing
camera/video Runner and `python -m sentinel_edge.early_motion_external`
for originally pinned ASSIST-IoT public videos. The **hand-designed
kinematic** probe uses at most 2s of strict fail-closed torso pose
context; requires recent upright posture, downward hip movement
and consecutive movement evidence, with source/gap/missing-pose resets.
It is **not a trained AI model** and does NOT produce additional
real fall incidents, medical confidence, event JSONL or API calls.
The original temporal heuristic and frozen Linear V1 remain unchanged.

Real predeclared-source research replay of all 11 original ASSIST-IoT videos
(3,396 frames) found untrained kinematic proposals in **3/3 publisher
staged Fall** videos and **0/8 short ADL** videos, while the unchanged
heuristic emitted zero events on both groups. These source videos were
previously exposed, have no independently reviewed event onset times,
and cannot establish actual Fall Recall or false alarms per hour.
The research probe never sends an alert or event to the backend.

The diagnostic reports aggregate category counts only: pose adapter
rejections, additional geometric motion-coverage abstentions and
unconfirmed motion cues, never video frames, landmarks, person identity,
individual timestamps or paths. Publisher clip names are not independent
event-onset labels; source data are already exposed. Do NOT interpret
motion-cue counts as accuracy, sensitivity, or false alarm/hour.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.early_motion_external --help
```

## AFDCare-inspired Linear V1 camera Shadow research (Member 1)

The [model-shadow handoff](docs/AFDCARE_INSPIRED_SHADOW_INFERENCE_HANDOFF_2026-10-28.md)
maps implementation ideas learned through *read-only* inspection
of AFDCare's real YOLO-Pose + GRU temporal pipeline to VIIL's
**independently coded, opt-in research-only** `--shadow-model`.
No AFDCare source, weights, datasets or confidential artifacts
are copied. Original MediaPipe strict multi-person abstention
and original heuristic fall candidate JSONL are **unchanged**.

The camera/video runner can verify and load VIIL's exact **frozen
Linear V1 research model** (SHA-256 pinned, threshold `0.53`)
for parallel inference; it emits **only aggregate Shadow counters
to stderr**, never an alert or event. Because V1 was trained on
30 sparse pose samples over 8 seconds, each 30D prediction needs
a full continuous 8-second context with 1-second inference hops.
Actual source-verified replay on all **11 public ASSIST-IoT MP4s**
(**3,396 frames**) yielded **12 ADL and 10 publisher Fall**
eligible shadow windows, but **zero Fall Candidate windows**
in both groups; **20 additional Fall windows abstained** due
to insufficient usable pose. Four ADL clips were shorter than
the required 8 seconds and generated no shadow windows.
The original heuristic also emitted zero events. A direct
`runner --shadow-model` smoke on one original 516-frame Fall
clip completed with one below-threshold shadow score and nine
abstentions; **no shadow alert/event**. These are previously
exposed publisher-labeled diagnostics, not human-reviewed
event recall or independent measured accuracy.

Missing poses are masked and undercovered windows abstain;
source changes / gaps over 700ms reset history. The original
VIIL V1 is **not** an instantaneous Fall detector, and no
safety readiness or event recall is inferred from Publisher labels.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.runner --help
.\.venv\Scripts\python.exe -m sentinel_edge.shadow_external --help
```

## Offline persistent PoseLandmarker performance experiment (Member 1)

The [persistent MediaPipe session handoff](docs/PERSISTENT_POSE_SESSION_RESOURCE_HANDOFF_2026-10-27.md)
adds `python -m sentinel_edge.persistent_pose_session` to replay
**8 source-verified IKAR staged Fall MP4s with ONE PoseLandmarker**
instead of reloading an instance for every video. The original
`TemporalFallDetector` is independently re-created at each
video cut to prevent cross-video fall evidence; the session
uses strictly monotonic MediaPipe VIDEO timestamps with 1,000 ms
synthetic boundary gaps. The original pose adapter, heuristic,
multi-person abstention and any live event code are untouched.

Real local Windows measurements: **889/889** frames complete,
**28.62 FPS**, **31.059 seconds** wall time, **241.82 MiB**
maximum sampled process RSS, **823** strict valid torso frames
and **1** original heuristic event. The previous independent
model-per-file replay measured **24.62 FPS**, **36.115 seconds**,
**248.24 MiB** sampled RSS and **831** valid torso frames,
with one heuristic event. The approximately **16.2%** higher
observed throughput is NOT isolated model-start benefit:
disk caches, processor load, test order and artificial scene
cuts can influence results. Tracker continuity changed the
accepted-frame count, so this is an **offline research diagnostic,
not a live webcam / safety deployment setting**.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.persistent_pose_session --help
```

## Real offline Edge MediaPipe CPU/RAM/FPS profile (Member 1)

The [source-verified performance handoff](docs/REAL_EDGE_REPLAY_RESOURCE_PROFILE_2026-10-27.md)
adds `python -m sentinel_edge.edge_resource_profile` for
privacy-minimal frame-accurate local video **replay profiling**.
It uses the 8 SHA-pinned IKAR staged Fall MP4s, the unchanged
MediaPipe `num_poses=2` detector and strict original temporal
heuristic. No model weights, video pixels, landmarks, event times
or identifying data are exported; only private aggregate performance
statistics are saved.

On the actual Windows test computer, all **889/889** source frames
were decoded in both variants. Native complete per-file replay
(including video/model init, inference and heuristic) achieved
**24.62 FPS**, **36.115 s** total, peak **sampled**
process RAM **248.24 MiB**. Experimental aspect-preserving
512px side cap achieved **24.99 FPS**, **35.577 s**,
sampled RAM **245.20 MiB**, but changed strict accepted
Pose frames from **831 to 865** and original heuristic
candidate events from **1 to 2**. The tiny observed
~**1.5%** speed difference does NOT justify selecting 512px
for live use: these candidate events lack independently
reviewed ground truth and cached/thermal effects may differ.
Neither setting attains 30 FPS full per-file replay. This
is **NOT** a live webcam benchmark, event accuracy validation,
or clinical safety authorization.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.edge_resource_profile --help
```

## New IKAR 2026 public Fall-only external stress (Member 1)

The [IKAR source-frozen intake and measured stress handoff](docs/IKAR_2026_FROZEN_PUBLIC_STRESS_HANDOFF.md)
integrates a **new** September 2026 AGH University of Krakow
[CC BY 4.0 IKAR dataset](https://doi.org/10.58032/AGH/A1NZPE).
The reproducible `python -m sentinel_edge.ikar_domain_stress` CLI
verifies official Dataverse 1.0 metadata and a 127.3 MB archive
using official MD5 and pinned SHA256, safely extracts only the
**two prespecified lowest-indexed examples** from each of its four
staged Fall types, and runs the **unaltered** private joint V1
research model. Raw video/annotation files and reports are
strictly private and Git-ignored, with no source labels converted
into reviewed event ground truth.

On the first actual 8-video domain stress, 889 real frames were
decoded, 831 accepted by the strict Pose adapter, and 8/8
nonoverlapping sample windows were pose-eligible. Frozen V1 yielded
video-level Fall candidates in **3/8** publisher Fall clips
(2 slips, 1 blackout, no trips/fainting); the legacy heuristic
emitted one event. This **is NOT event recall or accuracy**:
the source has **278 staged FALL videos and NO ADL**, spatial
bounding-box labels rather than verified Fall onset timestamps,
and no reliable mapping of IDs to individual subjects. This
already-viewed subset may never be used to tune a model and
called untouched test data. Production alerts were not changed.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.ikar_domain_stress --help
```

## Actual NumPy Tiny MLP research training (Member 1)

The [Tiny MLP real-video research training SOP](docs/NUMPY_TINY_MLP_REAL_TRAINING_HANDOFF_2026-10-27.md)
adds `python -m sentinel_edge.tiny_mlp_training` to train a
**real, NumPy-only, 12-hidden-unit MLP** on the source-verified
CAUCAFall+GMDCSA-24 public Fall/ADL clips. It compares against a
newly fitted linear V1 on the **same declared TRAIN subjects**;
chooses architecture and threshold using **VAL subjects only**;
then reports older **already-exposed TEST subjects only as a
non-independent diagnostic**. Independent actor verification and
human review of publisher labels have NOT been performed, and
success in validation would not prove real-world safety.

**Real training completed:** from 31 TRAIN clips and 10 VAL clips,
Tiny MLP achieved **0.80** VAL balanced accuracy vs **0.90** for
re-fitted linear V1. The **predeclared decision retains linear V1**;
Tiny MLP cannot be promoted despite 4/6 vs 3/6 Fall detections
on ten old **previously exposed** TEST clips. The private MLP
is 3,568 parameter/scaler bytes (9,478-byte JSON) vs linear
736 RAM bytes, and is slower in a local NumPy per-window test.
See the SOP for full split counts and reproducible evaluation.

Weights, train scalers and threshold are privately persisted as a
strict, bounded numeric-only JSON below Git-ignored `data/private`,
never connected to the normal heuristic/incident system. The
original model files, remote services and automatic alerts are
unchanged; no PyTorch/GPU or paid API is required.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.tiny_mlp_training --help
```

## Two-reviewer event-level Fall benchmark (Member 1)

The [multi-onset event-review SOP](docs/REVIEWED_MULTI_EVENT_BENCHMARK_HANDOFF_2026-10-27.md)
adds `python -m sentinel_edge.reviewed_event_benchmark` with
`prepare`, `capture` and `score` modes. Source media from the
original pinned public ASSIST-IoT reference videos is verified before
output. `prepare` makes exactly TWO **blank, unapproved** manual
review slots per video; no publisher action name becomes ground truth.
`capture` records bounded timestamp-only candidate evidence from
the unchanged original temporal heuristic. `score` refuses to
calculate any event recall until two distinct independently attested
full-video reviews with matching source digests and agreed multiple
Fall onsets are provided for **every** clip.

Matching is one-to-one within an explicit -250 ms/+2,000 ms interval,
with redundant/early/late candidates accounted for separately.
Full-reviewed negative-video hours are shown alongside any false
candidate rate; tiny staged-reference recording durations must not
be called real-world false alarm reliability. No private video,
reviewer entries, model weights, pose tracks or timestamp evidence
are committed; the trained joint V1 window-level model is not
misrepresented as a live event-alert predictor.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.reviewed_event_benchmark --help
```

## Offline temporal multi-pose association research (Member 1)

The [temporal association engineering handoff](docs/TEMPORAL_MULTIPOSE_ASSOCIATION_HANDOFF_2026-10-27.md)
adds `python -m sentinel_edge.assist_external --mode association-audit`.
It measures tentative short-horizon continuity across multiple MediaPipe
torso hypotheses **without selecting or updating any person pose for the
actual fall detector**. An in-memory strict single-person anchor expires
after six frames; apparent unique matches, missing anchors and ambiguous
multi-pose frames are recorded as counts only. Candidate continuity
**does not prove person identity**, and the original production
multi-person abstention and model/threshold are unchanged. On the actual
11 ASSIST public reference MP4s it counted **108 tentative short-anchor
Fall multi-pose candidates out of 860**, while 742 multi-pose frames
had no current strict single-person anchor; ADL had 3 such tentative
candidates among 51 multi-pose frames. This is a diagnostic,
**not recovered PoseFrames or improved Fall event recall**. The source
MP4s and offline numeric weights stay locally private.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.assist_external --help
```

## Frozen multi-pose geometry audit (Member 1)

The [real-source spatial geometry handoff](docs/FROZEN_MULTIPOSE_SPATIAL_HANDOFF_2026-10-27.md)
adds an opt-in `python -m sentinel_edge.assist_external --mode spatial-audit`.
MediaPipe's **multiple returned torso pose hypotheses** are counted
as geometrically overlapping, spatially separated, ambiguous or
unusable; nothing chooses a person or changes the strict production
adapter. Source MP4s and the frozen private model remain unchanged.
Only categorical counts (no pose coordinates, individual tracks,
frames or confidences) are saved to ignored private reports. These
categories **cannot certify duplicate detections or true person
identity**, and no autonomous alerts are enabled. The real 11-video
spatial audit classified **820/860 multi-pose Fall frames as spatially
separated geometry** and 40 with insufficient torso geometry; none
met the strict close-overlap bucket. The 51 ADL multi-pose frames
split into 7 overlapping, 3 separated, 24 ambiguous, 17 unusable.
These are not independently verified person counts or a promotion result.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.assist_external --help
```

## MediaPipe multi-pose rejection reason audit (Member 1)

The [real ASSIST-IoT pose rejection reason handoff](docs/POSE_REJECTION_REASONS_HANDOFF_2026-10-27.md)
adds `python -m sentinel_edge.assist_external --mode reason-audit`,
which streams the unchanged frozen joint V1 model with a separate
**opt-in privacy-minimal reason taxonomy** for rejected pose frames.
Both the original edge adapter and auto alert logic stay unchanged.
Strict counters match all decoded frames; no images, landmarks or
fitted weights enter Git.

On 11 real reference MP4s, **860/860 rejected Fall frames** were
`multiple_people` (MediaPipe returned more than one detected pose)
versus ADL rejects: 252 `no_person`, 51 `multiple_people`,
15 `out_of_frame`. This is not proof of real multiple humans; it
may include duplicate detections. Another fully visible fainting
Fall still had no heuristic/V1 fall candidates, so improving
multi-pose coverage alone will not fix all missed falls. Exposed
reference data cannot be a fresh independent test.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.assist_external --help
```

## Frozen ASSIST-IoT fall-miss attribution (Member 1)

The [Fall-miss attribution research handoff](docs/FROZEN_FALL_MISS_ATTRIBUTION_HANDOFF_2026-10-27.md)
adds `python -m sentinel_edge.assist_external --mode diagnose`.
It streams the **same source-verified 11 ASSIST-IoT videos** with the
**unchanged** joint V1 model/threshold, counting the Torso adapter
coverage, geometry validity, sampled 30-bin motion coverage,
un-calibrated frozen model score bands and **original heuristic
candidate events**. It does not persist poses, media, windows or
fitted weights and does not modify real-time alerts.

Real external 27 Oct observations: the Fall clips yielded **698
adapter-eligible frames out of 1,558**, compared with 1,520/1,838
in challenging ADL. Two Falls had incomplete pose-window coverage,
yet a third staged fainting Fall had 453/453 torso-valid frames
and still no candidate from either the V1 model or heuristic.
This is research diagnostic evidence, **not independently reviewed
fall-onset accuracy**, a threshold-tuning opportunity or approval
to deploy fall alarms.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.assist_external --help
```

## Frozen ASSIST-IoT external video stress test (Member 1)

The [source-pinned external benchmark SOP](docs/ASSIST_IOT_EXTERNAL_FROZEN_HANDOFF_2026-10-27.md)
adds `python -m sentinel_edge.assist_external` to download exactly
**11 CC BY 4.0 ASSIST-IoT video references** (8 challenging ADL
and 3 staged Fall activities), verify Git blob and private SHA-256,
and run the *existing* frozen joint 30D V1 research model without
training or changing its 0.53 validation-selected threshold. It reports
per-class video candidate counts and pose abstentions, not false
alerts/hour or reliable real-world Fall event recall. Source-reference
participants are **not mapped to per-video identities**; this is an
external research stress test, **not a proven independent-subject test**.
All public MP4s and local model/report files stay under ignored
`data/private`. Live alerts are not connected.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.assist_external --help
```

## Joint public-dataset training (Member 1)

The [real CAUCAFall + GMDCSA-24 joint V1 training guide](docs/CROSS_DATASET_REAL_TRAINING_HANDOFF_2026-10-27.md)
adds `python -m sentinel_edge.joint_dataset_training`: a
**real-video**, opt-in **research-only** joint model. Both publisher
sources undergo actual MediaPipe and SHA-256 video checks, followed by
a **combined** subject/recording/media split audit. Only TRAIN subjects
fit the shared 30D V1 logistic weights; only VAL subjects select one
threshold. A private JSON artifact is saved, reloaded and verified.

The actual 56-video run had **51 pose-eligible clips, 31 TRAIN, 10 VAL,
10 previously exposed TEST**, with a validation-selected threshold of
**0.53**. Existing exposed TEST diagnostics yielded TP 3/FN 3/FP 0/TN 4
across both sources; these **are not new independent Test results**.
No human action-label review, safety validation or live alert promotion
is implied. Sensitive video, features and weights stay under ignored
`data/private`.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.joint_dataset_training --help
```

## Actual REAL-video trained research model (private weights)

The [real public-video training handoff](docs/REAL_PRIVATE_MODEL_TRAINING_HANDOFF_2026-10-27.md)
adds `python -m sentinel_edge.private_model_training`, an opt-in
train/validation subject-disjoint NumPy V1 training CLI on actual
GMDCSA-24 or CAUCAFall publisher-labeled video. It uses the existing
streamed MediaPipe pose extractor and saves only 30-dimensional
weights, train-only mean/scaler, and validation-only threshold to
Git-ignored `data/private/*.json` with strict finite-value validation,
source manifest digests and a reload check. Neither footage, full pose
windows nor weights are committed. The research model is **not wired to
production inference or automatic alerts**, and labels have not been
independently reviewed.

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.private_model_training --help
```

## Research-only trained Temporal Logistic baseline

A lightweight **NumPy-supervised model** can now be fitted on masked temporal
pose features in an **offline experiment**. It applies the v2 subject-disjoint
audit, trains and normalizes using train subjects only, selects threshold on
validation subjects, and scores a separate held-out test. Both fictional
synthetic demonstrations and a tiny real **publisher-labeled staged** CAUCAFall
pilot have been trained and evaluated in memory. Neither has independently
verified action labels or robust real-world evidence. This is NOT a TCN/GRU,
NOT a validated Fall Detection AI replacement and never connects to live alerts.

See [temporal baseline training and dataset gates](docs/TEMPORAL_TRAINING_RESEARCH_BASELINE_2026-10-27.md).

```powershell
python -m pip install -e ".[training,dev]"
python -m sentinel_edge.temporal_training --synthetic-demo
```

## AI model readiness — verified

See the [latest real runtime and model readiness audit](docs/MODEL_READINESS_AUDIT_2026-10-27.md):
Pose Landmarker Lite loads and infers locally, but the fall event classifier is
a heuristic with 1/8 detected staged falls in a tiny positive-only IKAR test.
The latest video report adds a conservative `readiness_gate`, never granting
automated alert/dispatch authorization. **Meta multimodal live inference is
not implemented** (Backend `meta.py` uses an explicitly labeled mock).

## What has been implemented

- Typed 2D normalized pose landmark contracts, with visibility validation.
- Temporal fall-candidate state machine requiring ALL of:
  1. a recent upright shoulder–hip torso orientation,
  2. downward hip movement relative to the same-camera recent baseline,
  3. a horizontal torso posture sustained for at least 450 ms,
  4. minimum landmark confidence and a cooldown for duplicate events.
- Explicit reset on a camera switch, missing/poor landmarks, or discontinuous timestamps.
- Candidate output with event UUID, timestamp, source_id and **uncalibrated heuristic score**.
- Optional local MediaPipe PoseLandmarker + OpenCV runner for webcam or authorized video.
- Synthetic unit tests for fall-like transition, no-fall sitting, pre-existing lying posture, occlusion/gaps and metrics.

This is a heuristic demonstration; it does not establish clinical reliability. **Do not call the heuristic score a validated probability**. It cannot infer injuries, consciousness, severity, or whether emergency help is required.

The first [real-human staged fall video evaluation](docs/IKAR_REAL_VIDEO_EVALUATION_2026-10-27.md)
used licensed IKAR CC BY 4.0 recordings and detected only **1/8** positive clips
with the original thresholds. This is an exploratory positive-only subset,
NOT a generalizable fall accuracy estimate. Diagnostic gate counts now help
investigate missed events without storing image or pose data.

The new [Local Video Benchmark](docs/VIDEO_BENCHMARK.md) evaluates
consented videos directly using local MediaPipe inference and clip-level
labels without writing derived pose traces. It is distinct from the
synthetic negative-control smoke test and cannot establish clinical accuracy.

For the exact readiness checklist and dependency-isolated camera commands, see
[Member 1 verification runbook](RUNBOOK.md). The latest MediaPipe optional
video dependency installs its own compatible OpenCV package; avoid mixing
multiple OpenCV wheels in the same Python environment.

## Setup and test

From `D:\VIIL-Sentinel\services\edge-vision` with Python 3.11+:

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
```

Optional video runner dependencies:

```powershell
python -m pip install -e ".[video,dev]"
```

To use a webcam or local video, obtain a **compatible MediaPipe Pose Landmarker .task model** yourself from the official documentation, verify the asset's terms, and save it outside Git (e.g. `D:\VIIL-Sentinel\models\pose_landmarker_lite.task`). The project does not bundle or download any model weights.

```powershell
# Explicitly authorized staged recording
python -m sentinel_edge --source "D:\staged-data\example.mp4" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --max-frames 1000

# Local webcam, no recording and no network uploads
python -m sentinel_edge --source 0 --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --display
```

Default mode never opens a display window, saves frames, sends notifications or calls Meta AI. Only event metadata is printed as JSON to stdout.

Official task reference: https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker/python

## Optional resolution experiment (NOT production)

Read the [real IKAR frame-size comparison](docs/RESOLUTION_EXPERIMENT_2026-10-27.md):
original-resolution inference remained faster end-to-end than experimental
640/480 px input caps in one local trial. The default is unchanged; the
`--max-inference-side` flag is benchmark-only and must not be promoted without
representative positive/negative validation on target devices.

## Performance and disk footprint

The default local video benchmark now evaluates detected events **as frames
arrive** without retaining per-frame landmark dictionaries or running the
fall detector a second time. A `--buffered-eval` reference mode remains
for bit-for-bit report comparisons, and `--signal-diagnostics` keeps its
specialized buffered path. See the [real IKAR performance audit](docs/PERFORMANCE_EFFICIENCY_2026-10-27.md)
for reproducible wall time/CPU/RAM measurements and local disk inventory.
No threshold or safety behavior was relaxed.

## Member 1 → Member 2 Candidate Handoff v1

The new [versioned metadata-only candidate contract](docs/CANDIDATE_HANDOFF_V1.md)
exposes strictly labeled unverified fall candidates via local stdout JSONL.
It forbids raw frames, private landmarks and unreviewed evidence references,
and marks heuristic scores as uncalibrated. A standalone synthetic trace
exporter and opt-in `--candidate-format v1 --confirm-consent` video runner
mode can generate it. **No live Meta/Backend ingestion is implemented.**

## Legacy Handoff contract to Member 2

A candidate event has this shape (the numeric values are **illustrative only**, not measured):

```json
{
  "type": "FALL_CANDIDATE",
  "id": "a-uuid",
  "timestamp_ms": 880,
  "source_id": "staged-camera-01",
  "confidence": 0.8,
  "evidence_refs": [],
  "detector": "temporal-pose-heuristic-v0.1",
  "simulated": false,
  "evidence_notes": ["Human review is required"]
}
```

`confidence` is a heuristic score, NOT calibrated. No raw frames are attached. Member 2 will need to add evidence selection and an authenticated, provenance-preserving API integration before any real event can reach the caregiver workflow; **do not send candidate events through the existing `/incidents/demo` route as though they are staged events**.

## Remaining Member 1 work

- Run authorized fall-like and no-fall recordings; record ground truth at **event/clip level**, not individual frames.
- Verify subject-level train/test split, licensing and consent of any dataset.
- Calibrate thresholds and measure precision, recall, F1 and false-alert rate from real labeled evaluation sets.
- Implement real multi-person tracking (current PoseLandmarker runner tracks one pose only).
- Handle camera perspective, occlusions and sitting/lying false positives robustly.
- Add selected keyframes with local-only retention rules and user consent.
- Add confidence and uncertainty reporting independent of clinical implications.
- Test under realistic light, clothes, camera heights, frame rates and hardware conditions.
- Integrate the validated detection contract with Member 2/3 through an explicitly authorized authenticated service.

## New — Clip-level evaluation workflow

The Member 1 evaluator runs locally using **authorized, human-annotated clips**
represented by JSONL pose traces, then outputs clip-level confusion-matrix
counts, precision, recall, F1, false candidates per negative-video hour and
(optional) post-onset detection latency. These metrics are meaningful **only
for the clips you actually label and evaluate**. The included two-clip
synthetic demonstration is only a parser/logic smoke test.

You can run the synthetic smoke test immediately:

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
python -m sentinel_edge.evaluation --manifest examples/synthetic/manifest.json
```

### Collect local pose traces from an authorized video

After installing the optional video extras and obtaining a licensed local
Pose Landmarker model, this command exports only four normalized torso
landmarks per frame. Pose traces can still be identifying and may be
sensitive. **Use exclusively with consented staged media.** Store them in a
local ignored folder and never publish them.

```powershell
# From services/edge-vision, use a local video you are authorized to analyze.
# Create the private output folder yourself (e.g. D:\staged-private\).
python -m sentinel_edge --source "D:\staged-private\fall1.mp4" `
  --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --trace-output "D:\staged-private\fall1.pose.jsonl" `
  --acknowledge-pose-privacy
```

The output path must end in `.pose.jsonl` and must not already exist. The
export is **opt-in and local**; neither video nor poses are sent to Meta.
The tool does not export screenshots or raw frames.

### Annotate ground truth and evaluate

Create a manifest alongside the exported clips (see
`examples/synthetic/manifest.json`). Each clip requires a pseudonymous
ID, a relative trace path, an explicit `expected_fall` boolean and a
nonempty `permission_basis` documenting consent or licensing. For positive
clips you may specify `onset_ms` for detection latency measurements.
Run from the folder above:

```powershell
python -m sentinel_edge.evaluation --manifest "D:\staged-private\manifest.json"
```

Options: `--min-hip-descent`, `--horizontal-min-angle-deg` and
`--horizontal-hold-ms` enable controlled sensitivity experiments.
Do not tune thresholds on the held-out evaluation set. Use distinct
participants for development and evaluation clips, and document camera
angle, fps and consent.

**Interpretation limits:** This is *clip-level* fall/no-fall scoring, not
frame or event boundary localization. It cannot validate emergencies,
patient outcomes, or clinical sensitivity. Falling subjects may be missed
if pose is occluded, stationary, or the visual perspective hides descent.
Perfect scores on the tiny synthetic fixtures are not evidence of accuracy.

## Privacy and licensing

MediaPipe is an external third-party dependency; check the Pose Landmarker model asset license and permitted redistribution before making the GitHub repository Public. Do not commit raw footage, `.task` binaries, research models or personal data.

Use the official task documentation. No capability or performance has been tested against actual video or real-world falls in the synthetic unit tests.
