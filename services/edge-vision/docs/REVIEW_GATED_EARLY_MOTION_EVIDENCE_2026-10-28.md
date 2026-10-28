# VIIL-Sentinel — Real private early-motion evidence and two-reviewer event gate

28 October 2026 · Member1 · Research-only / no event dispatch

## Scope and source of the requirement

The previously frozen untrained two-second causal motion probe gave **3 unconfirmed motion proposals across 3 publisher-staged Fall videos**, compared with zero from the original heuristic. That is a *technical cue*, not fall sensitivity or true event recall: action labels in 11 original ASSIST-IoT videos are **not human-reviewed event-onset timestamps**. The old `reviewed_event_benchmark` offered human two-reviewer onset scoring, but accepted only candidates from the original heuristic, so it could not validate the independent two-second cue.

This update adds private event-time capture for the unchanged 2-second probe and reuses the existing stringent onset review gate. It does NOT train a model, alter cue thresholds, change PoseLandmarker behavior, select ambiguous people, publish raw landmarks, or send alerts.

## Threat model / fail-closed logic

- The standard `CausalMotionProbe` still emits **only aggregate counts** and does not create `FallCandidateEvent`, incident JSONL or backend API actions. New optional `private_proposal_consumer(timestamp_ms)` is used **only by the isolated offline reviewer evidence collector**, never by the camera Runner.
- Research timestamps and clip identifiers are sensitive linkage information even without images. They are saved *only* in a new exclusive-create JSON file under Git-ignored `data/private/...`. A user must hold media and privacy rights to run this program.
- The original **11 source-pinned public ASSIST-IoT MP4s** are reverified via manifest, original Git blob and SHA-256; video content SHA-256 is independently checked again immediately before each collector. Decode **every** declared video frame; compare callback, collector, probe and timestamp counts; refuse partial/mutated input.
- Generated private candidate evidence uses exactly the pre-existing schema `{version,dataset,source_commit,detector,clips}` with detector tag `causal_early_motion_probe_v1_untrained`. The legacy `original_temporal_heuristic_v1` tag is preserved. Unknown tags are rejected. Private event timestamps are strictly increasing, bounded and within source duration.
- A separate `prepare` command produces exactly **two BLANK review decisions per video**, never copying publisher Fall labels as human approvals. The existing `score` command requires all 11 clips to be reviewed in full by **two distinct independently attesting reviewers each**, SHA-matched original media and independently specified every fall onset including intentional empty onset lists. Uncertain, missing, conflicting or unsupported decisions abort without accuracy claims.
- This software checks consistent pseudonymous review declarations; **it cannot prove real reviewer identity, consent, blind review, or scientific quality**, and the video set has been seen during earlier development. Any future score is *exploratory only* and not an untouched independent Test. The output contains no individual candidate/onset timestamps and cannot authorize production alerts.

## Steps on authorized local Windows workstation

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$root = "D:\VIIL-Sentinel\data\private\public-datasets\assist-iot-external"

# 1. Make two blank real-review entries per original source clip;
#    do NOT prefill reviewer identities, onset times, or approval flags.
& $py -m sentinel_edge.reviewed_event_benchmark `
    --mode prepare --root $root `
    --output "$root\assist-two-reviewer-blank-20261028.json" `
    --acknowledge-media-rights --acknowledge-review-privacy

# 2. Reprocess all 11 original source MP4s and privately capture
#    unconfirmed two-second cue timestamps; not incident alerts.
& $py -m sentinel_edge.reviewed_event_benchmark `
    --mode capture-early --root $root `
    --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
    --output "$root\assist-early-motion-private-candidates-20261028.json" `
    --acknowledge-media-rights --acknowledge-review-privacy

# 3. Research reviewers independently inspect actual videos,
#    fill ALL 22 entries, and place the resulting review file
#    under $root; never fabricate independent review.

# 4. Score ONLY after complete real two-reviewer agreement:
& $py -m sentinel_edge.reviewed_event_benchmark `
    --mode score --root $root `
    --reviews "$root\REAL-two-reviewer-decisions.json" `
    --candidates "$root\assist-early-motion-private-candidates-20261028.json" `
    --output "$root\early-motion-reviewed-event-analysis.json" `
    --acknowledge-media-rights --acknowledge-review-privacy

# Run standard CI-equivalent Python checks:
& $py -m pytest -q
& $py -m ruff check .
```

All outputs use exclusive-create, so repeat experiments must use **new private filenames**; never overwrite original review evidence. The `score` step intentionally **cannot run now** without actual independent human decisions. It must not be "made green" with fictional reviews, publisher clip labels, or self-generated event timestamps.

## Technical scientific limitations

The event match uses the original fixed chronology and tolerance of
**250ms before** to **2000ms after** the manual onset. Event recall is not model accuracy, and the false *candidate* count per reviewed negative hour is NOT an actual false *alarm* rate. Even when complete real reviews arrive, the source clips are exposed and some have unknown actors/camera conditions. A prospective untouched, actor-disjoint and environment-disjoint data source is still needed. Clinical fall monitoring cannot be promoted without much stronger evidence.

Existing original heuristic events and trained 8s Linear V1 shadow model remain untouched. Protected `main` and `preprod` are untouched; only `member1/feature/*` and authorized `member/feature/preprod` are integration targets.

## Actual source verification

**COMPLETED real media replay:** 11 source-pinned original ASSIST-IoT
videos, each source hash checked and all decoded frames reconciled.

| Research-only observation | Publisher ADL | Publisher staged Fall |
|---|---:|---:|
| Original publisher MP4s | 8 | 3 |
| All source decoded frames | 1,838 | 1,558 |
| Captured PRIVATE untrained motion-cue timestamps | **0** | **3** |

- **3,396 frames**, 11/11 MP4s and 3 private event-time cues;
  no trained-model output and no assumption that publisher
  clip action labels are human-confirmed event onset truth.
- Two exclusive-create private files verified in the dataset root:
  `assist-two-reviewer-blank-20261028.json` (**22 blank entries**)
  and `assist-early-motion-private-candidates-20261028.json`
  (11 source SHA-matched rows and total 3 cue timestamps).
  No video frames or landmarks are written in either JSON.
- The real `--mode score` command was executed with the blank
  reviews against captured source-verified cue evidence:
  **expected nonzero refusal; NO score file created**.
  Do not "fix" this failure by fabricating reviewer attestations.
- All 11 videos require **two genuinely independent humans** to
  inspect full footage and enter every verified Fall onset (or
  deliberately empty list), with explicit uncertainty review and
  permission check. Software verifies declarations only; it cannot
  authenticate reviewers, onset truth or participant consent.
- This previously exposed reference dataset is **not an untouched
  model accuracy test**. Long independently reviewed ADL negative
  hours and new subject/camera-separated Fall onsets remain necessary
  before estimating real incident recall or false alerts per hour.
- The original heuristic and trained 8s V1 are unchanged. No
  backend alarm, dispatch or emergency policy is authorized.
