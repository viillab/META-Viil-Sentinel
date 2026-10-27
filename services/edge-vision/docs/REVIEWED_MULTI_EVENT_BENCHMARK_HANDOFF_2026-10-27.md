# VIIL-Sentinel — Human-Reviewed Multi-Onset Fall Event Benchmark

27 October 2026 · Member 1 · **Offline research only; NOT a validated safety system**

## What this resolves

Our real public ASSIST-IoT external stress research showed three publisher-labeled
Fall videos without fall candidates. But the current joint V1 research weights,
the legacy heuristic, and publisher video titles **cannot establish real
event-level fall recall**: fall clips can contain **multiple staged falls**,
model sample windows can cover only part of the event, and no independent
human fall-onset labels had been verified. Earlier single `onset_ms` clip
scoring is useful but cannot measure repeated falls and duplicate alerts
one-to-one.

This addition is a **two-reviewer, fail-closed multi-event evaluation
pipeline**, not another assertion that the model became better. It also
captures original offline heuristic event timestamps from *real* source
video while keeping model/production logic unchanged.

## Ground truth is NEVER copied from Publisher labels

Input media: pinned original **ASSIST-IoT-SRIPAS** reference MP4s;
https://github.com/ASSIST-IoT-SRIPAS/multimodal-fall-detection-dataset ,
source Git commit `7a11c96b9a3576cef92f0795a19b3786c69a3335`,
CC BY 4.0. Source Git blob hashes, exact local video SHA-256, file
length, original manifest, all 11 expected filenames, and private
source paths are verified before creating a template, collecting events,
or scoring. All media remain under ignored `data/private`.

`prepare` creates **22 completely empty review decisions**
(two for each of 11 real videos):
`reviewer_id=""`, `media_sha256=null`,
`independently_reviewed=false`, `complete_video_reviewed=false`,
`uncertain=true`, `fall_onsets_ms=null`, `review_note=""`.
No publisher label, event onset or permission is auto-approved.

Two **distinct actual human reviewers** must inspect the COMPLETE
local video separately and manually attest the exact original media
hash and every observed fall onset in milliseconds. For a video
reviewed with no falls, explicitly set `fall_onsets_ms=[]`, **not null**.
Each must explicitly set `independently_reviewed=true`,
`complete_video_reviewed=true`, `uncertain=false`, provide a
pseudonymous reviewer ID, and provide a meaningful observation note.
The software checks syntax, complete coverage, hash equality, time
bounds, chronological order, independent reviewer IDs and agreement
within **200 ms** on every fall onset and on the number of events.

It does not know whether the reviewers are real, fully independent,
trained, have consent, or observed the source correctly. Attestations
are UNSIGNED and require organizational audit. One missing/uncertain
review or disagreement blocks ALL event-level accuracy calculation;
there is no silent majority vote, synthetic auto-approval, or
dropping difficult videos.

## Fixed event-scoring protocol (no retrospective tuning)

For each independently consensus-reviewed fall onset `t`, match
**at most ONE** originally emitted detector candidate within
`[t - 250 ms, t + 2000 ms]`. Match onsets in chronological order,
to the earliest unused candidate in its window. Remaining candidates
are false candidates (including duplicate detections). An unmatched
reviewed event is a missed event. A model alert before onset by up to
250 ms is shown as a **negative detection delay**; no latency
is fabricated when no event was matched.

Reports include actual reviewed-event denominators, matched/missed
events, false candidate counts, recall, mean matched detection delay,
total fully reviewed no-fall video hours, and false candidate density
restricted to **fully reviewed no-fall videos**. This last rate can be
calculated from a small duration but must **never** be sold as a
production false-alarm rate. Fall-containing videos may have early
and post-event false candidates; those are tracked in the overall
false count, **never divided by the smaller no-fall-video duration**.
Metrics are candidate-level; there is no claim of emergency response.

The implementation currently supports only the **original production
temporal heuristic** as event source. The joint NumPy V1 research
classifier is window-level and is **NOT falsely represented as an
event detector**. This module never loads or alters trained weights,
adjusts thresholds, updates the camera, or dispatches alarms.

## Actually executed source input preparation

All 11 original ASSIST-IoT MP4 media hashes and source manifest were
revalidated, and the blank review queue was created on the authorized
Windows workspace:

`D:\VIIL-Sentinel\data\private\public-datasets\assist-iot-external\reviewer-event-onsets-blank-20261027.json`

The output is **strictly empty/unapproved**; source names and
timestamps alone cannot approve human ground truth. No valid
event-level accuracy number is available yet. A 2-reviewer
real-world review and potentially an independent third-party
adjudication of disagreements are still required.

### Completed real source-video capture (not fabricated labels)

The unchanged original temporal heuristic processed **ALL 11 real
source-verified MP4s** via the installed local MediaPipe Lite
PoseLandmarker and saved source/video SHA-linked timestamp evidence:

- Videos: **11/11 decoded and source verified**
- Decoded frames: **3,396**
- Torso-geometry-eligible frames: **2,169**
- Original heuristic event candidates: **0**
- Two-reviewer blank decisions created: **22/22** (ALL unapproved)
- Human review statements validated: **0**
- Event-level recall or model promotion claim: **NOT AVAILABLE**

This is consistent with, but not independent from, previously exposed
ASSIST-IoT tests. It **does not establish an event-level 0% recall**:
publisher class labels do not enumerate actual fall events and the
clips are not independent new participants.

Private timestamp-only evidence:
`D:\VIIL-Sentinel\data\private\public-datasets\assist-iot-external\original-heuristic-event-evidence-20261027.json`
(SHA-256:
`b6b00a63f55fd005a3653838156d92507598e200ddaf8bfbd619fc370157d1d4`)

Private blank reviewer queue:
`D:\VIIL-Sentinel\data\private\public-datasets\assist-iot-external\reviewer-event-onsets-blank-20261027.json`
(SHA-256:
`d7d61a2222b213207785fc0667bc0454842f2513f626ec963d035bdf6f66eba0`)

**Proof the safety gate rejects premature scoring:** Running `score`
with the actual blank 22-decision queue and real heuristic event
evidence returned exit code **2**, refusing with
`Require pseudonymous distinct reviewer ID`. The requested score
output was not created. This is expected **fail-closed behavior**,
not a failed accuracy benchmark.

## Commands for the next human developer

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$root = "D:\VIIL-Sentinel\data\private\public-datasets\assist-iot-external"

# 1. Pin/reverify media and create a NEW blank two-reviewer template.
& $py -m sentinel_edge.reviewed_event_benchmark --mode prepare `
  --root $root --output "$root\reviewer-event-onsets-blank-20261027.json" `
  --acknowledge-review-privacy --acknowledge-media-rights

# 2. Collect events from REAL video using the UNMODIFIED original heuristic.
& $py -m sentinel_edge.reviewed_event_benchmark --mode capture `
  --root $root `
  --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --output "$root\original-heuristic-event-evidence-20261027.json" `
  --acknowledge-review-privacy --acknowledge-media-rights

# 3. Only AFTER both independent reviewers manually enter the full
#    reviews in a NEW private file, score one-to-one events.
& $py -m sentinel_edge.reviewed_event_benchmark --mode score `
  --root $root `
  --reviews "$root\reviewer-event-onsets-completed.json" `
  --candidates "$root\original-heuristic-event-evidence-20261027.json" `
  --output "$root\human-reviewed-event-metrics.json" `
  --acknowledge-review-privacy --acknowledge-media-rights

& $py -m pytest -q
& $py -m ruff check .
```

The command names are illustrative. Existing output files must not
be overwritten: use new private output names for additional trials.
The future `reviewer-event-onsets-completed.json` **does not exist**
until real independent reviewers create it. `score` must fail closed
until then. All private review notes, pseudonymous reviewers, video,
candidate timestamps and evaluation outputs must remain local and
Git-ignored. Never commit any filled annotation or weights.

## Design limitations / next development

- Source actors and scene/person identities are not independently
  verified. These videos are **already exposed external diagnostics**,
  not a new unbiased domain-generalization test set.
- Human onset review is essential to distinguish stage actions and
  repeated falls; a single publisher class is not event ground truth.
- When truly reviewed new cohorts become available, expand this
  protocol with explicit pose abstention over each event, long ADL
  recordings, independent camera/subject holdout, alert deduplication
  and latency on actual edge devices.
- Separate the original live heuristic from future **window-level**
  NumPy/Tiny-TCN classifiers until each has defined event emission
  semantics and is calibrated only on training/validation sources.
- The already observed multi-pose strict abstention and fully visible
  fainting fall miss require additional reviewed development data;
  **do not optimize on the exposed ASSIST reference clips**.

Member1 feature branch:
`member1/feature/reviewed-event-benchmark`.
Authorized integration only into `member/feature/preprod`. The
shared `preprod` and human-only `main` must remain unchanged.
