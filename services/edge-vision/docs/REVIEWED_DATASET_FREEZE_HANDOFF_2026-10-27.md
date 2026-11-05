# VIIL-Sentinel Member 1 — Reviewed Dataset Freeze & Drift Gate

**27 October 2026 · Research prototype only · no trained model deployed**

## Status and motivation

CAUCAFall's **40 publisher-labeled** selected clips have **not** undergone
independent manual annotation review. There are presently **0 completed
two-person reviews out of the 80 review entries required**. Dataset freeze
is **not possible** until real authorized human review decisions exist. The
tool explicitly **does not** synthesize or auto-approve missing reviews.

Previous staged publisher-labeled research with the old held-out group and
4-fold development-subject CV remains available for comparison but is not
new independent safety evidence. Do not promote V2 based on reused test clips.

## What the new `reviewed_dataset_seal.py` does

1. Reuses the existing strict independent two-reviewer approval compiler.
   Each source clip needs two distinct reviewer statements, matching actual
   Fall/ADL activity, start/end boundaries within 200ms, explicit review
   certainty, matching source-media SHA-256, and complete coverage in every
   partition. Missing or disputed reviews **block the entire batch**.
2. Reuses `window_export.validate_source_plan()` to **read and hash every
   actual video file** and enforce subject, recording and media split audit,
   relative bounded paths, readable file sizes and exact review contract.
3. Computes **canonical sorted-key JSON SHA-256 fingerprints** of the
   original group manifest, publisher proposals, all review decisions and
   the compiled reviewed segments, plus aggregate split counts.
   Clip *list order* is intentionally significant: moving or replacing a
   record breaks the existing freeze fingerprint even if labels remain equal.
4. Writes an **unsigned private JSON freeze record** only inside the
   Git-ignored `data/private` directory, using exclusive creation with
   no overwrite. This record never includes participant/reviewer IDs,
   full clip path lists, videos, pose windows, model weights or raw images.
5. `verify` recomputes the entire gate against the original files and
   compares the exact seal. **Any edit requires an intentional new reviewed
   dataset revision** instead of silently continuing.
6. `export` takes exactly those frozen inputs, **verifies seal before
   invoking expensive pose decoding**, rechecks source hashes again during
   the existing secure reviewed-window exporter, and exclusively writes the
   30x6 motion feature bundle inside that same private dataset root.
   Consent and sensitive pose privacy acknowledgements are mandatory.
7. The default/research-only model training commands, heuristic candidate
   detector, and production incident/Meta API flows are **not changed**.

**Important security boundary:** This is an unsigned SHA-256 checksum-based
consistency guard against accidental drift, not an authenticated digital
signature. Someone able to change ALL inputs and generate a fresh seal can
forge a matching record. No tool can prove the human watched a video,
reviewers are independent, the labels are correct, or participant consent
is valid. An organizational SOP and auditable access to source recordings,
licenses and reviewers remain mandatory.

## Required private inputs

`root` = existing ignored local dataset folder with:

| Input | Schema / meaning |
|---|---|
| `groups-v2.json` | Exact v2 subject/recording/media-separated groups; one clip ID, Boolean Fall/ADL, SHA-256 per clip |
| `publisher-proposals-v1.json` | Original `label_reviewed=false` source clips; correct clip-relative intervals |
| `human-review-decisions-v1.json` | Independent two-person complete private decisions per clip; see previous handoff |
| `frozen-reviewed-dataset-v1.json` | NEW private, unsigned, immutable-for-this-revision SHA-256 fingerprints |
| `reviewed-windows-v1.json` | OPTIONAL private 30×6 pose features after seal-gated export; never commit |

See [Independent Annotation Review Handoff](INDEPENDENT_ANNOTATION_REVIEW_HANDOFF_2026-10-27.md)
for how humans create the review statements. The freeze/verify/export command
is *strictly downstream* of this stage. The module does not invent data.

## Reproducible commands (Windows / PowerShell)

Use the isolated Edge Vision virtual environment (not system Python):

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
& $py -m pytest -q
& $py -m ruff check .

# Use only actual authorized, independently human-reviewed data:
$root = "D:\VIIL-Sentinel\data\private\research\my-reviewed-batch-v1"
$base = @(
  "--root", $root,
  "--groups", "$root\groups-v2.json",
  "--proposals", "$root\publisher-proposals-v1.json",
  "--reviews", "$root\human-review-decisions-v1.json",
  "--seal", "$root\frozen-reviewed-dataset-v1.json",
  "--acknowledge-media-rights",
  "--acknowledge-review-privacy"
)

# 1. Verify full human annotation claims, source SHA-256 and group splits;
#    exclusively write a new unsigned freeze. --seal must equal --output.
& $py -m sentinel_edge.reviewed_dataset_seal --mode freeze @base `
  --output "$root\frozen-reviewed-dataset-v1.json"

# 2. Read media and all original review inputs again, verify zero drift.
& $py -m sentinel_edge.reviewed_dataset_seal --mode verify @base

# 3. ONLY with documented human consent/rights, make pose derived windows.
& $py -m sentinel_edge.reviewed_dataset_seal --mode export @base `
  --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --output "$root\reviewed-windows-v1.json" `
  --confirm-consent --acknowledge-pose-privacy
```

`freeze` will **FAIL on today's CAUCAFall** because its existing 40
publisher-annotated clips have not been independently reviewed. It is
correct to fail; do not bypass the gate just to produce a trained model.

The commands fail on any missing reviewed clip, altered two-person decision,
changed source video SHA-256, subject/recording cross-split leakage, wrong
clip identity, review interval disagreement, invalid/oversized JSON or unsafe
private destination. They do not overwrite existing freeze/feature files.

Run `python -m sentinel_edge.temporal_training --manifest ... --features ...`
only as a **separate** offline research operation when the reviewed feature
bundle has been generated safely and the final evaluation plan is frozen.
**WARNING:** The old generic trainer has no mandatory `--seal` flag; do
not mistake its direct CLI for seal-enforced provenance.

## Handoff and future promotion requirements

- When importing another public dataset, obtain documented rights before
  using real-person footage. Convert clips into **v2 pseudonymous manifest**
  and **unreviewed v1 proposal** with exact media SHA-256, stable subject IDs,
  explicit origin recordings and declared train/val/test groups; ensure BOTH
  Fall and ADL in each split. The existing reviewer/compiler batch cap is
  64 clips; partition new datasets into controlled review batches and do
  not accidentally reuse one subject across dataset-wide splits.
- Independently review every clip with two people. Disagreements require human
  adjudication and a new reviewed revision; **not** a forced flag change.
- Freeze inputs before a model run and keep SHA-256/review records in private.
  Comparing only two unsigned SHA-256 records does not prove provenance.
- Next validate an **entirely new never-inspected subject cohort**, across
  varied real ADLs, camera placement and occlusion. Report pose abstention,
  event recall, false alarms/hour, latency, runtime RAM/CPU/FPS, calibration
  and uncertainty. The current small staged study is not safety-certified.
- Developer workflow: new `member1/feature/*` branch, test, scope/review
  changes, push, then merge into **`member/feature/preprod` only**;
  human-owned `preprod` and `main` must remain untouched.

## Code references

- `sentinel_edge/reviewed_dataset_seal.py`: canonical SHA-256 seal, verify,
  optional private pose export
- `sentinel_edge/annotation_review.py`: independent two-reviewer structural gate
- `sentinel_edge/window_export.py`: actual media verification and pose exporter
- `sentinel_edge/split_audit.py`: disjoint split metadata audit
- `tests/test_reviewed_dataset_seal.py`: completely invented, nonhuman
  fixtures testing seal drift, no-decode before preflight, review, export
- `docs/INDEPENDENT_ANNOTATION_REVIEW_HANDOFF_2026-10-27.md`: human SOP

**Rollback:** Revert only this scoped Member 1 feature/merge commit after
review. No prior model architecture or live alert behavior changed.
