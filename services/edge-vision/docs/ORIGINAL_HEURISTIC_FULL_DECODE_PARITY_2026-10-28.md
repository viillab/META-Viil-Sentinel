# Original Heuristic — Strict Full-Decode Parity

28 October 2026 · VIIL-Sentinel / Member 1 · Offline research only

## What was repaired

Before this change, `reviewed_event_benchmark.collect_original_heuristic_events`
only reconciled the number of frames observed by its callback with the
number reported by its streaming collector. If decoding stopped early,
**both numbers could still agree** and the result could be mistaken for
a complete negative/positive reference video. In contrast, the newer
`capture-early` research path already compared decoding to original video
metadata.

The original temporal heuristic now uses the **same source-frame-integrity
gate as early-motion research**:

1. Reverify each video SHA-256 after the pinned original manifest/blob check.
2. Read bounded OpenCV frame count and FPS; reject zero, invalid,
   fractional/bool frame counts, invalid/non-finite/bool FPS and counts
   above the 6,000-frame budget.
3. Bound the collector with `max_frames=expected_source_frames`.
4. Reject missing/extra frames and a mismatch between expected count,
   callback count and collector-reported count, even when the last two
   agree with one another.
5. Reject malformed collector event statistics and any event count that
   differs from the actual callback. Continue validating strict timestamp
   ordering and media duration as before.

Both research collectors now check numeric FPS types; the model task is
also bounded to a nonempty 60 MiB maximum in the original collector.
Neither the detector threshold nor any camera production alert logic,
model wiring, trained weights, or human-review gate changes.

## Private reproduction

From `D:\\VIIL-Sentinel\\services\\edge-vision`:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest -q
.\\.venv\\Scripts\\python.exe -m ruff check .

$root = "D:\\VIIL-Sentinel\\data\\private\\public-datasets\\assist-iot-external"
.\\.venv\\Scripts\\python.exe -m sentinel_edge.reviewed_event_benchmark `
  --mode capture --root $root `
  --pose-task "D:\\VIIL-Sentinel\\models\\pose_landmarker_lite.task" `
  --output "$root\\assist-original-heuristic-full-decode-20261028-parity.json" `
  --acknowledge-media-rights --acknowledge-review-privacy
```

Capture outputs must be created **exclusively under ignored `data/private`**;
repeated experiments require a **new filename**. Never commit event times,
paths, original videos, landmarks or reviewer identities. The sample tests
use fabricated poses/bytes only and do **not** constitute human fall-event
labels or algorithm accuracy.

The 11 original ASSIST-IoT publisher-staged Fall/ADL clips are previously
exposed research media, not an untouched actor/camera-disjoint test. Event
recall, false *alarm* rates, real-world sensitivity and clinical safety
remain **unverified** without two independent valid human event-onset
reviews and stronger prospective testing.

## Source-verified real replay

**Completed real source replay — 28 October 2026.** The source-hash-gated
`--mode capture` command completed with exit code 0 over all **11 original
ASSIST-IoT MP4 videos**, and created only a Git-ignored private JSON file.
The separate private early-motion research evidence was used for aggregate
parity checking, never copied into Git.

| Verifiable measure | Original heuristic | Untrained 2s motion cue |
|---|---:|---:|
| Original source-pinned videos decoded in full | 11/11 | 11/11 |
| All decoded frames | 3,396 | 3,396 |
| Strict pose-eligible frames | 2,169 | 2,169 |
| Unconfirmed event candidates | **0** | **3** |

Every one of the 11 candidate rows had exactly the same original media
SHA-256, decoded-frame count and pose-eligible frame count in both private
manifests. There are **no independently human-reviewed onset labels** in
either artifact, so 0 vs 3 is a cue-count comparison, **not event recall,
specificity, accuracy, or a false-alarm-rate study**. No incident was
dispatched and no original detection thresholds were adjusted.

Local validation after the final source changes: **518 Edge pytest cases
passed**, Edge Ruff passed, **6 Backend pytest cases passed**, Backend Ruff
passed and Dashboard production build passed. GitHub Actions must be checked
again on the exact new topic and team-integration commit hashes before
calling this change integrated.


## Next developer checklist

Use the reviewer-gated `score` command only after two genuine independent
reviewers annotate every source video. Preserve the original and new
candidate manifests separately and compare frame coverage and candidate
counts before interpreting event results. Treat any incomplete decode as a
hard research pipeline failure rather than estimating missing labels or
silently converting missing data into no-fall predictions.
