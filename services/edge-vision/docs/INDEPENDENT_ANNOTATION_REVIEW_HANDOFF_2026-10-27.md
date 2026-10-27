# Member 1 — Independent Human-Label Review Gate

**27 October 2026 · Research-only · not clinical/production-ready**

The existing CAUCAFall published labels are **NOT** independently reviewed.
The 40 videos used for the prior V1/V2 experiments remain publisher-labeled
proposals only. This addition DOES NOT review videos, approve a dataset,
establish consent/derivative rights or claim model reliability. Its purpose
is to create a strict workflow so the *next humans* can actually annotate
each clip before any reviewed-data training.

## Source of truth

- `data/private`: video, group manifests, unreviewed proposals, two-person
  review decision files, reviewed output, derived motion features. All are
  private/ignored; **never commit** any of these.
- `sentinel_edge/annotation_review.py`: bounded review preparation, pairwise
  independent-attestation agreement check, private-only JSON output.
- `sentinel_edge/window_export.py`: **unchanged** strict reviewed segment
  validator and 30 × 6 feature exporter.
- `sentinel_edge/split_audit.py`: **unchanged** disjoint participant /
  recording / media-sha256 group audit.
- `tests/test_annotation_review.py`: synthetic fake media tests for both
  valid and fail-closed paths.

## What the reviewer must actually do

**Before video access:** A human must verify licensing, permission for the
intended research use, privacy terms, derivative media redistribution and
participants' consent requirements. The command's rights acknowledgement
is NOT a substitute for legal permission. If not established, **do not run
the video-review/compile workflow**.

1. Two *different people* independently watch every actual clip (both
   Fall and ADL) and independently record the observed action, exact start/
   end time in clip-relative milliseconds, explicit Fall vs ADL decision,
   source-media SHA-256, review certainty, and a factual note. No auto-labeling.
2. Do not copy the publisher's labels blindly. Include hard negatives like
   sitting, lying, kneeling, standing, walking, bending and picking objects.
3. Each clip must have **exactly two distinct pseudonymous reviewer IDs**,
   two explicitly certain independent observations and agreement on label
   and activity. Their interval start/end boundaries may differ by no more
   than 200 ms. The intersection becomes the final reviewed window, which
   must still satisfy the 900–8000 ms duration contract.
4. Disagreement, uncertainty, unreviewed records, missing media or SHA-256
   mismatch **blocks the whole batch**. A human adjudication protocol
   must create a new, independently reviewed revision. **Never** silently
   drop ambiguous clips or pretend their source labels are ground truth.
5. If independent review contradicts the original group manifest,
   compilation intentionally fails. The research team must review and
   revise the metadata in an **entirely new version/split audit** before
   proceeding; do not quietly flip `expected_fall` in place.
6. The code can check recorded pseudonyms and statements but cannot
   verify that the humans really watched the video or are independent.
   Access logs and human review SOP are organizational responsibilities.

## Reproducible commands (PowerShell, Windows)

Use the isolated local Python; Windows system Python has had incompatible
MediaPipe dependencies.

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
& $py -m pytest -q tests/test_annotation_review.py
& $py -m pytest -q
& $py -m ruff check .
```

**Only AFTER media permissions and reviewer access are confirmed:**

```powershell
$root = "D:\VIIL-Sentinel\data\private\public-datasets\caucafall-omnifall\extracted\Cauca_fall"
$common = @(
  "--root", $root,
  "--groups", "$root\caucafall-research-groups-v2.json",
  "--proposals", "$root\caucafall-review-proposals-v1.json",
  "--acknowledge-media-rights",
  "--acknowledge-review-privacy"
)

# Creates a PRIVATE template containing TWO BLANK entries per clip.
# No expected label, reviewer or timestamp is prefilled or approved.
& $py -m sentinel_edge.annotation_review --mode prepare @common `
  --output "$root\independent-review-template-v1.json"

# Two people inspect actual media and COMPLETE every entry independently.
# Copy to a private decisions file first; never edit a file in Git.
# Both pseudonymous reviewer IDs, activity, label, interval, digest and notes
# MUST be entered. The blank template always fails the compile command.
& $py -m sentinel_edge.annotation_review --mode compile @common `
  --reviews "$root\independent-review-decisions-v1.json" `
  --output "$root\independently-reviewed-segments-v1.json"
```

Both commands refuse to overwrite a previously existing file.
`--mode compile` verifies the original group manifest and every media
SHA-256 using the reviewed exporter source validator *before* producing
`independently-reviewed-segments-v1.json`. The reviewed output is compatible
with the existing `python -m sentinel_edge.window_export` command, but
still requires that CLI's **separate consent and pose privacy** flags.
A successful JSON validation is NOT proof of real reviewer identity or consent.

## Review file contract

Private decisions JSON: `{"version": 1, "decisions": [...]}`.
Each entry has **exactly**:

| Field | Constraint |
|---|---|
| `clip_id` | Stable ID matching the group/proposal manifest |
| `reviewer_id` | Pseudonymous lowercase ASCII token; two distinct per clip |
| `expected_fall` | Explicit boolean; never null on approval |
| `activity` | `fall_motion` for fall; allowed ADL action token for normal |
| `start_ms`, `end_ms` | Integer clip-relative interval; fits source clip |
| `media_sha256` | Must equal the group manifest and actual source bytes |
| `independently_reviewed` | Literal `true`, human-entered |
| `uncertain` | Literal `false`; anything uncertain blocks |
| `review_note` | 15–200 printable characters, private, specific to the action |

The prepared template uses deliberately blank or false/null fields.
It **cannot** pass the compiler unchanged. Reviewer notes and IDs are NOT
included in the compiled segment manifest or printed into summary logs.
No face/video/keypoint/model files are produced or uploaded by this tool.

## Developer acceptance criteria and next step

- No default `label_reviewed=true` anywhere; no hidden manual overrides.
- Two-review agreement and explicit per-file SHA-256 verification is enforced.
- Exact one-to-one coverage including the declared Test split, no cherry-pick.
- Reviewed output remains in ignored `data/private` and matches the existing
  exporter's seven-field segment contract.
- Full test suite and lint pass on the isolated environment.
- The next model version must use newly independently labeled and consented
  participants/activities, with a **fresh untouched final test cohort**.
  Previously examined held-out results may no longer support unbiased model
  selection. Measure false alarms per monitored hour, operational latency,
  abstentions, CPU/RAM/FPS and representative ADL diversity.

**Branch policy:** Member 1 topic `member1/feature/*` then validated merge to
`member/feature/preprod`; do not change shared `preprod` or `main`.

**Rollback:** Revert the single scoped Member 1 topic/merge commit; no
production inference path changes, existing CAUCAFall research CLI untouched.
