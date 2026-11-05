# VIIL-Sentinel Member 1 — Frozen ASSIST-IoT External Stress Benchmark
27 October 2026 · Real public video, no training or automatic alerts

## Why this source

The prior GMDCSA+CAUCAFall joint V1 is a real trained *research* model,
but both corpora's former Test clips have already been inspected. This
benchmark introduces a **third, independently published external source**
whose activities were preselected by semantic difficulty, **before running
any model inference**. We do **not** claim participant independence:
ASSIST-IoT's human videos are *reference videos* with no sufficient
per-video participant-ID mapping for a proper subject-disjoint split.
Do not append reference recordings to a training dataset just because
they are public.

Dataset: **ASSIST-IoT Multimodal Fall Detection Dataset**,
Danilenka, Sowiński, Kobus, Dąbrowska, Rachwał, Bogacka & Baszczyński;
source https://github.com/ASSIST-IoT-SRIPAS/multimodal-fall-detection-dataset ;
archive DOI https://doi.org/10.5281/zenodo.8340428 .
Repository data license **CC BY 4.0**, with attribution and license terms
for downstream redistribution (we do not distribute the MP4 files here).
Upstream Git commit pinned to
`7a11c96b9a3576cef92f0795a19b3786c69a3335`.
Each exact official MP4 is SHA-1 Git blob verified before storing and
SHA-256 checked again before inference.

### Fixed 11-reference-video challenge set

- **Eight ADL hard negatives**: rapid sitting into a low chair, collapsing
  *onto a chair*, rapidly lying down, bending both with/without knee flexion,
  stumbling while walking, jumping/reaching and crawling.
- **Three publisher-designated staged Falls**: forward while walking,
  backward, and fainting/vertical. The source's fall reference videos
  show repeated staged actions, not independent individual cases.
  We have *not* manually audited frame-accurate fall onsets.
- These 11 exact filename/byte size/blob hash entries were fixed **before
  scoring**, preventing cherry-picking model outputs. Source chosen by
  public activity descriptions, not ML predictions.
- These are videos of **activities**, not eleven unique people.
  Human-subject disjointness or consent for new uses is not proven.

## Immutable model and repeatable commands

We run **the already trained** joint CAUCAFall/GMDCSA V1 research
checkpoint, not a newly trained model. The scorer refuses to execute if
its private JSON bytes do not match
`2e55abd9657148a5fb17c3291c96841c31d030695c18116e0da70d6489aec3ab`
and verifies that the validation-selected threshold remains **0.53**.
Neither values nor features are updated by this benchmark.

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$p = "D:\VIIL-Sentinel\data\private"
$root = "$p\public-datasets\assist-iot-external"

# Safe source-pinned private download / existing-source hash recheck.
& $py -m sentinel_edge.assist_external --mode download `
  --root $root `
  --acknowledge-publisher-labels --acknowledge-pose-privacy

# Run REAL offline MediaPipe Lite and frozen model once.
& $py -m sentinel_edge.assist_external --mode evaluate `
  --root $root `
  --model "$p\joint-cauca-gmdcsa-v1-publisher-research-20261027.json" `
  --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --report "$p\assist-external-frozen-report-20261027.json" `
  --acknowledge-publisher-labels --acknowledge-pose-privacy

& $py -m pytest -q
& $py -m ruff check .
```

Output report, media and any model JSON are under **Git-ignored
`data/private`**, excluded from commits and uploads. To make a
repeated run, use a newly named report file; old reports are not
overwritten. No raw pose frames, landmark trajectories or video
pixels are written to the JSON output. Public activity identifiers,
counts and categorical predictions are safe to document without human
identifiers.

## Actual completed external frozen-model run

This one-time evaluation was completed on the **11 authentic Git-blob
verified ASSIST-IoT MP4 files** totaling **25,583,326 bytes**.
The already fitted joint 30D V1 artifact was verified by exact file
SHA-256 against the frozen value above; its threshold remained 0.53.
No retraining, model change, or retrospective threshold selection occurred.

| Official reference group | Video count | Candidate Fall videos | 8-second-or-less windows | Pose-eligible windows | Abstained windows |
|---|---:|---:|---:|---:|---:|
| Challenging ADL | 8 | **0** | 11 | 11 | 0 |
| Staged Falls | 3 | **0** | 8 | 5 | **3** |
| **Total** | **11** | **0** | **19** | **16** | **3** |

**Interpretation:** Zero false-positive video flags appeared among
eight publicly designated ADL examples; this **does not prove low
false-alarm frequency per monitored hour**. More importantly, the
frozen model failed to flag all three publisher-designated Fall
reference videos. **Two of the three Fall videos have incomplete
pose coverage** (three missing windows total). The sole Fall video
with complete window visibility also had no Fall candidate. Therefore
only one complete-coverage video can cleanly be called a whole-video
no-candidate case, while the two partly pose-missing videos are
inconclusive about falls within their unobserved intervals.

This is a *blocking research failure*, not grounds to relax the
validation threshold after the fact. The earlier GMDCSA/Cauca
scores do not compensate for this new domain discrepancy. Follow-up
work should focus on video-specific pose visibility, temporal
event-onset validation and another genuinely independent source.

Private evidence file:
`D:\VIIL-Sentinel\data\private\assist-external-frozen-report-20261027.json`.
It includes the source commit, frozen checkpoint digest, per-activity
flag booleans and coverage counts, but no human video, landmarks,
trajectories or per-window model probabilities.

## Evaluation protocol and what NOT to claim

The sampler processes the whole publicly documented reference clip
with **non-overlapping 8-second-or-shorter windows**. Each window has
30 sampled pose positions and needs at least 10 visible/valid poses.
The pretrained 30D V1 scores only pose-eligible windows; missing
windows abstain and are reported separately. **A video is flagged**
if *any* eligible window exceeds the already frozen 0.53 threshold.
This is an exploratory **whole-video any-positive** criterion, not
an event-onset or real-time deployed alert. Any partly pose-abstained
video has incomplete coverage; videos with no eligible windows abstain.

For ADL reference recordings a fall candidate is a **false positive
video**; for publisher-designated Fall reference videos, no candidate
is an exploratory **miss**. Do not infer successful detection of each
repeated Fall inside a clip. Do not convert 8 ADL videos into
independent people or quote false-alarms/hour: this pipeline does
not independently adjudicate events, continuous monitoring time or
cooldown.

A public CC BY 4.0 license and a per-video activity name do NOT prove
independent fall-onset annotations, unique human identities, deployment
consent or clinical validity. This is a sensitivity/stress diagnostic
for the *unchanged* model. Regardless of outcome, a new verified
subject/scene-disjoint cohort is still required before any promotion
or threshold changes. No live camera, notification, dispatch, alerts
or backend model state are touched.

## Next developer responsibilities

- Obtain subject/camera provenance and independently review fall-onset
  times; build a genuinely unseen subject-disjoint reference cohort
  with both Fall and challenging ADL.
- Treat any discovered False Positive video as an engineering problem
  for a **new** development set, not permission to tune the frozen
  model and re-label this external evaluation as untouched.
- Measure false alert events/hour on long annotated negative footage,
  latency to individual fall, abstention versus subject and light,
  real edge CPU/RAM/FPS and repeated independent field trials.
- Continue on Member 1 feature branches and merge only into
  `member/feature/preprod`; human controls main/shared preprod.
