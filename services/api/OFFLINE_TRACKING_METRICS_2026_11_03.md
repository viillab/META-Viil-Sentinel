# VIIL-Sentinel — Offline Tracking Diagnostics v1

**2026-11-03 KST · Member 2 · Pure offline/aggregate research · Not a release decision**

## What was actually developed

Created `services/api/app/offline_tracking_eval.py` and a
synthetic-only test suite `tests/test_offline_tracking_eval.py`.

The module accepts a **separately annotated detection-to-actor
correspondence** file and the previously introduced
`viil.research.actor_disjoint_manifest.v1` dataset manifest.
It validates both before computing **descriptive identity-continuity
counters** for the sealed `test` split only.

This does **not** produce a person tracker, predict who an individual
is, extract new images, train a model, measure a real field tracking
benchmark, or change Member 1's production Edge/RTSP, caregiver API,
Mobile or Dashboard. There is no Meta API call.

The previous seeded stress experiments proved that eight-point
geometry alone may silently link a different person occupying the
same coordinates. Therefore an **independent human annotation of
which ground-truth actor corresponds to each detection** is a
prerequisite; it CANNOT be inferred merely from a pose or supplied
by the current experimental `AnonymousTrackletResearch` as
validated identity.

## Input contract

### Dataset manifest (v1)

Reuse `app.actor_disjoint_admission` exactly: strict source
SHA-256 content digests, pseudonymous actors/sessions/cameras,
explicit `visible` / `occluded` / `out_of_frame` per actor
per frame, no split leakage in declared tokens, monotonic timestamps,
bounded frames and documentary review declarations.

A passed manifest means **its structure was checked**, not that
the claims about consent, independent actors or legal rights
were independently confirmed.

### Predictions file (v1)

The exact JSON schema ID is
`viil.research.offline_track_evaluation.v1`. Its root has:

```json
{
  "schema": "viil.research.offline_track_evaluation.v1",
  "manifest_sha256": "<canonical JSON SHA-256 of the annotated manifest>",
  "clips": [
    {
      "clip_token": "C_tst",
      "frames": [
        {
          "frame_index": 0,
          "timestamp_ms": 0,
          "status": "accepted",
          "reason": "none",
          "observations": [
            {
              "detection_index": 0,
              "track_token": "T_left",
              "actor_token": "A_c333"
            }
          ]
        }
      ]
    }
  ]
}
```

The snippet shows one frame of the contract only; an actual
predictions file must contain **every frame of every test clip**
from the manifest, with identical frame indexes and timestamps,
including abstained and empty frames. It must not contain train
or validation clips.

`actor_token` is a **privately, independently annotated
reference match**, not output from the tracker. For a false
positive/unmatched detection set `actor_token: null`.
Every observation needs a per-frame unique detection index 0–7
and a unique `T_[a-z0-9]{3,24}` research track token. At most
eight detections are permitted per frame.

`status=accepted` requires `reason=none`.
`status=abstained` requires a fixed reason
(`ambiguous`, `occluded`, `missing_pose`, `time_gap`, or
`human_review`) **and zero observations**. The reason is a
closed enumeration to prevent accidental free-text/PII leakage.

The evaluator rejects:
- Schema alterations and duplicate/extra/missing prediction clips
- Unbound annotation content (SHA-256 mismatch, including changes
  in declared source digest, actor labels or rights metadata)
- Any missing, duplicate, reordered or mistimed frame
- A predicted actor not marked visible in the independent reference
- Duplicate track tokens, detection indexes, or matched reference
  actors in one frame
- Invalid/bare human-readable actor identifiers, unbounded data
  or fabricated `abstained` frames carrying associations
- Bad or missing rights declarations, split leakage, invalid
  annotation, unsafe private paths/symlinks/JSON, as checked by
  the existing Dataset Admission gate

## Exact metric interpretation

These are descriptive counters, **not IDF1/HOTA/MOTA** or
independently verified accuracy percentages.

- `reference_visible_actor_frames`: each `visible` actor/frame
  declared in the reference.
- `matched_actor_frames`: visible actor/frame with an annotated
  correspondence in predictions.
- `missed_visible_actor_frames`: visible actor/frame with no
  annotated prediction.
- `unmatched_detections`: predicted detection with
  `actor_token=null`.
- `abstained_frames`: refused frame with zero emitted observations.
- `reference_adjacent_visible_transitions`: same reference actor
  visible in two adjacent sampled frames.
- `same_track_adjacent_continuations`: adjacent visible actor
  matched by the same track token in both frames.
- `adjacent_id_switches`: adjacent visible actor matched in both
  frames but with different track tokens.
- `adjacent_unobserved_links`: adjacent visible actor not
  matched in at least one of the two frames.
- `cross_actor_track_reuse`: the **same track token** appears in
  immediately adjacent frames and corresponds to different
  reference actors, including silent single-pose handoff.
- `reacquired_after_visible_gap`: a reference actor remained
  visible, had at least one missed match, and became matched again
  without leaving the `visible` state.
- `large_timestamp_intervals`: adjacent source frames separated
  by more than 200 ms; any same-token continuation of the same
  actor across such a gap is also counted as
  `untrusted_continuations_across_time_gap`.

Track IDs are only meaningful **within the same clip**, never
compared across source sessions or camera identities. A track
ID changing after an out-of-frame/occluded interval is **not**
automatically an adjacent ID switch; such cross-gap identity
cannot be verified by this tool.

A numerical count of zero does **not** establish that identity
association is safe. Independent annotation errors, actor
grouping mistakes, visually identical body poses, unseen entrants,
crossing frames, and camera motion may make the reference wrong.

Every output includes:
`real_person_tracking_accuracy_established=false`,
`matching_actor_labels_independently_attested_by_this_tool=false`,
`release_authorized=false`, `fall_confirmation_enabled=false`,
`emergency_dispatch_enabled=false`,
`meta_api_called=false`,
`raw_actor_tokens_tracks_or_coordinates_exported=false`.

## Verified entirely fictional example

```powershell
cd D:\VIIL-Sentinel\services\api
.\.venv\Scripts\python.exe -m app.offline_tracking_eval --synthetic-demo
.\.venv\Scripts\python.exe -m pytest -q tests/test_offline_tracking_eval.py
```

This uses the prior 3-clip/12-frame **synthetic** admission
manifest, scores its 4-frame fictional sealed test clip and
produces, by design:

| Fictional counter | Result |
|---|---:|
| Visible reference actor/frame observations | 6 |
| Matched actor/frame observations | 6 |
| Adjacent track ID switches | **1** |
| Track token reused across different actors | **1** |
| Unmatched detections | **1** |
| Release allowed | **No** |

CI tests verify that all frame/reference mismatches, duplicate
IDs, non-visible reference matches, malformed or oversize
prediction structures and unbound manifest hashes fail closed.
Additional tests cover intentional abstention, visible-state
fragmentation, timestamp gaps and aggregate-only reporting.

## Future private mode — only with legal/ethics authorization

After independent review of data subjects' permissions, provenance,
retention, true actor identities, annotation quality and test-set
sealing, authorized users may run this **locally**:

```powershell
.\.venv\Scripts\python.exe -m app.offline_tracking_eval --inspect-private D:\VIIL-Sentinel\data\private\tracking_eval\manifest.json --predictions D:\VIIL-Sentinel\data\private\tracking_eval\predictions.json --acknowledge-person-data-review
```

The files must physically reside under Git-ignored
`data/private` with no symlinked file/path components;
raw labels, track tokens, source hashes and per-frame records
are **never printed or saved by the evaluator**. The evaluator
only prints aggregate metrics and fixed reason codes.
The two input files themselves are potentially sensitive
person-related research records and must not be committed.

**Current status: NO-GO** for using any identity or fall decision
to automatically notify caregivers or dispatch emergency services.
No authorized real multi-person ground-truth and paired prediction
corpus has been presented for evaluation in this milestone.
Neither the production four-torso-joint runtime nor the
experimental pose model was modified, and no new Meta spend
was initiated. The separate Meta local ledger remains 4/4.
