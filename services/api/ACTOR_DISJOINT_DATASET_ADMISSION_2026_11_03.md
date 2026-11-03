# VIIL-Sentinel — Actor-Disjoint Research Dataset Admission v1

**2026-11-03 KST · Member 2 · Offline schema/annotation quality gate · NOT a dataset certification**

## Delivered

`services/api/app/actor_disjoint_admission.py` and its synthetic-only
test suite build the first **machine-checkable, fail-closed research dataset
admission contract** in preparation for a real multi-person tracking
evaluation. It does **not** obtain any new video or real identities,
train a tracking model, verify individuals, or change Member 1 Edge,
FastAPI production routes, Caregiver alerts, Mobile or Dashboard.

The motivation is empirical: the previous **32-seed synthetic
association audit** still found **32 incorrect adjacent links under the
multi-person abstention default** when one fictional actor silently
replaced another without a blank frame. We therefore need
independently annotated identity transitions and strict sealed splits,
not just more geometry-only simulated stress tests.

The new strict versioned manifest contract is
`viil.research.actor_disjoint_manifest.v1`, supported from Python 3.11
with no external services.

### Data requirements

The top-level JSON object has **exactly** `schema`, `rights` and
`clips`. A `rights` declaration requires one of the declared research
license IDs (`CC-BY-NC-4.0`, `CC-BY-4.0`, or
`CUSTOM_RESEARCH_CONSENT`), SHA-256 digests identifying provenance,
permission evidence, annotation review and a retention plan, plus six
explicit review declarations:

- Human rights/licensing review
- Research-purpose permission scope
- Privacy impact review
- Retention/deletion review
- Independent actor annotation review
- Actor grouping/identity-claim review

**These are documentary declarations, NOT proof of legal validity,
actual subject consent or independent identity correctness.**
The content behind the hashes is not downloaded, opened or
independently attested by the script. An external authorized
reviewer must independently examine it before any study.

Each clip requires exact keys
`clip_token`, `source_sha256`, `split`, `session_token`,
`camera_token`, `actor_tokens`, `frame_count` and `frames`.
The clip/actor/session/camera strings must be bounded, simple
**pseudonymous tokens** (e.g., `C_trial`, `A_k91q`).
Full personal names, email addresses, file paths and URLs are
not permitted in token fields.

Frame annotations list every declared actor with **exactly one**
`visible`, `occluded` or `out_of_frame` state,
`frame_index` (contiguous from zero) and increasing
clip-local `timestamp_ms`. There is no silent default of
"invisible means absent". No face embeddings, identifiable
descriptors, raw joint coordinates, photographs or person media
are part of this manifest schema.

Validation rejects:
- Missing `train`, `validation` or `test` clips
- The **same actor token** in different splits
- The **same capture session or camera domain** in different splits
  (deliberately stricter sealed evaluation for this research design)
- Duplicate clip IDs or exact duplicate source SHA-256 media
- Missing, duplicate, unknown or unobserved actor annotations
- Out-of-order/replayed frame indexes or timestamps
- Missing/unknown JSON keys, duplicate JSON keys, non-finite JSON,
  oversize private manifests, symlinked paths, or files outside
  `data/private`
- Review checklists with any missing or non-true declaration

The implementation is bounded to **3–40 clips**, **12,000
annotated frames total**, **up to eight actors per clip**, and a
**4 MB maximum JSON file**. It does not search the filesystem for
private data, perform network I/O or copy media.

### Research test split coverage

For the sealed `test` split the checker counts:
- Frames with two or more actors simultaneously `visible`
- Frames where at least one actor is explicitly `occluded`
- Adjacent frames where exactly one actor is visible on each side,
  but the declared actor changes (the single-pose handoff problem)

Missing test coverage is returned as explicit
`blocking_reasons` even if the JSON is otherwise structurally
valid. **A synthetic-demo manifest may have zero blockers yet is
still categorically not authorized** for real-world claims or
release.

Machine-checkable exact token disjointness is only a *claim*
of actor independence: the same real person can appear under
different pseudonyms and evade it. The tool cannot detect
near-duplicate video with different SHA-256 hashes, verify
independent annotation or inspect actual consent documentation.
Those limitations are intentionally visible in every result.

## Commands (verified fictional demo)

From `D:\VIIL-Sentinel\services\api`:

```powershell
# No real data or external calls. Internally creates a mathematical
# 3-clip, 12-frame mock with train/validation/test splits:
.\.venv\Scripts\python.exe -m app.actor_disjoint_admission --synthetic-demo

# Later, AFTER independent human review and written permission,
# only read a bounded manifest already placed in Git-ignored data/private:
.\.venv\Scripts\python.exe -m app.actor_disjoint_admission --inspect-private D:\VIIL-Sentinel\data\private\tracking_eval\manifest.json --acknowledge-person-data-review

# Synthetic-only CI, no raw human data required:
.\.venv\Scripts\python.exe -m pytest -q tests/test_actor_disjoint_admission.py
```

The synthetic demo demonstrates:
- 3 pseudonymous **fictional** clips, 12 annotated frames
- One clip per split
- Two simultaneous-visible frames, one occlusion frame and one
  single-visible-actor handoff within the fictional test split
- Explicit statuses and safe aggregate counts only
- `release_authorized=false`,
  `evaluation_cohort_ready_for_scientific_claim=false`,
  `automated_alert_authorized=false`,
  `external_legal_privacy_and_identity_review_completed_by_this_tool=false`.

The private manifest inspection mode requires the additional
`--acknowledge-person-data-review` option, refuses symlinks
including symlinked parent directories, and **prints only aggregate
counts and fixed blocker codes**. It does not print pseudonyms,
source digests, per-frame timestamps, raw annotation states or
video paths. Real source/permission documents remain the team's
responsibility and are not committed to GitHub.

## What is deliberately NOT shipped

No new real-person or multiple-person clips are downloaded.
No real-world ID-switch score, IDF1, MOTA, HOTA, track recall,
actor-disjoint external verification, fall sensitivity, false alarms
per hour or clinician claims can be generated from manifest
structure alone.

**RELEASE DECISION: NO-GO.** The main Edge runtime and fall
detector are unchanged, no external notification/dispatch is enabled,
no real camera imagery or pose data is sent to Meta, and no new
billable Meta request is made. Existing local Meta spend ledger
remains exhausted at **4/4 approved attempts**.

After obtaining independent consent/license, a legitimately
annotated multi-camera, actor-disjoint dataset may be placed in
`data/private` for separately authorized offline evaluation.
Independent review should check actors across different pseudonyms,
session provenance, duplicate frames from re-encodes, test-set
sealing, labeling disagreements and rights. This admission tool
must NOT be used as a replacement for those checks.
