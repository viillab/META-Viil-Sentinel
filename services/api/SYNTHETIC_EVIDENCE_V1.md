# VIIL-Sentinel — Synthetic Event-Bound Evidence v1

**Member 2 • 2026-11-02 • Offline privacy-safe preparation only**

This is the next safe integration step after two successful live Meta Model API
vision contracts. **It does not call Meta again**: all four previously
approved local Meta attempts are consumed, and the related budget ledger
must not be reset. No camera access, person images, face data, real fall
video, patient identifiers, or external uploads occur.

## What it delivers

`services/api/app/synthetic_evidence.py` takes the exact bytes of one
`viil.edge.candidate.v1` produced by Member 1's real Python temporal-pose
detector on a SHA256-pinned **fictional** mathematical trace. It creates
a reproducible three-panel *pose schematic*, not photographic evidence:

| Frame | Source-relative time | Drawing |
| --- | ---: | --- |
| 0 | 0 ms | Torso before synthetic downward transition |
| 1 | 300 ms | Synthetic horizontal torso |
| 2 | 850 ms | Synthetic horizontal torso, matching candidate event timestamp |

Image resolution: **336×112 RGB PNG**. The source contains only four
fictional torso-point coordinates (shoulders and hips). It has no
photographic pixels and cannot prove a real fall or medical severity.
The relative time is **not** UTC incident time.

The new `viil.synthetic.evidence.v1` Manifest has *required*, strictly
validated fields:

- Event UUID, configured pseudonymous source ID and source-relative time
- SHA-256 of the exact raw Candidate HTTP bytes, the frozen local JSONL trace
  and the deterministic generated PNG
- Exact three frame timestamps, MIME, renderer version and origin
- `simulated=true`, `contains_real_person=false`,
  `consent_for_real_media_verified=false`,
  `external_upload_authorized=false`,
  `meta_inference_performed=false`,
  `permanent_storage_allowed=false`, `fall_confirmed=false`

The builder rejects modified producer metadata, incorrect source/time,
non-synthetic provenance, any `evidence_refs`, unexpected scores, forged
real-media claims, unsupported timestamps, modified canonical fixture,
changed trace hash, and invalid JSON. The validator deterministically
regenerates expected output and compares **all** Manifest fields and
the **exact PNG bytes** against the Candidate. Both the trace and
canonical Member 1 example are SHA256-pinned.

**Hash binding is not source authentication:** It establishes integrity
and deterministic association only for this frozen *local* demonstration.
Production requires signed provenance, actual source/time attestation,
camera and evidence registry, consent verification, independent auditing,
key rotation, and tenant-scoped authorization before accepting real media.

## Safe offline Meta request preparation

`build_offline_pose_meta_request(...)` constructs a would-be Meta JSON
Schema request using the image **only after** it passes the complete
synthetic source/event/hash check. The developer instruction says the
input is a three-panel schematic, not human video, and demands an
`uncertain` response with no support indices. **No HTTP request is sent.**

Crucially, `MetaSyntheticVisionClient` **still refuses this image**:
its existing paid adapter accepts only the original canonical uniform-color
64×64 PNG. In a separate unit test, even with `live_enabled=True`,
the posed schematic is rejected *before* a budget reservation. Nothing
in this change bypasses the exhausted **4/4** paid-call guard.

The separate, offline synthetic Meta response used in the end-to-end
smoke is clearly marked **MOCK**, not genuine inference. The
`GET /api/v1/caregiver/inbox` endpoint is unchanged and continues
to report `meta_provenance=none`, `simulated=true` and
`fall_confirmed=false`.

## One-command end-to-end smoke

Run in `D:\VIIL-Sentinel\services\api`:

```powershell
.\.venv\Scripts\python.exe -m app.synthetic_evidence_smoke
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Expected `status`: `SYNTHETIC_EVENT_BOUND_EVIDENCE_PASS`.

The smoke runs the Member 1 emitter on the pinned `fall.jsonl`, confirms
`sitting.jsonl` emits no false candidate, POSTs **signed raw candidate
bytes over real localhost TCP** to the real FastAPI and its temporary
SQLite ledger, constructs/validates the manifest and PNG from those *same*
bytes, checks the offline would-be Meta JSON request against the strict
response schema, routes one explicitly mocked output to human follow-up,
and reads the source-scoped Caregiver Inbox. The Uvicorn listener and
SQLite ledger are shut down/removed after the test. Image bytes are held
only in process memory. No image is persisted, sent to Meta, or exposed by
an API route.

The test suite additionally covers:

- Cross-event UUID substitution, source mismatch, changed relative time,
  different provenance, synthetic/real confusion, unexpected detector score
- Manifest tampering, PNG byte corruption, oversized or non-PNG input,
  fixed fixture SHA mismatch and duplicated JSON fields
- Canonical output size/geometry, stable rerendering and distinct pose phases
- The existing paid client rejecting non-canonical image data **without**
  spending or creating any budget ledger

## Work remaining before real Meta fall tests

1. Obtain explicit organizer/site consent and licensed staged **human**
   videos with retention limits, opt-out paths and secure isolation.
2. Implement a **separately reviewed** production evidence validator and
   source signer, with transport encryption, per-camera identity, trusted
   wall-clock alignment and event→frame cryptographic chain.
3. Evaluate the four-point pose heuristic against independently labeled
   staged falls and daily activities. Report false positives, false negatives,
   sensitivity, latency, cohort/source splits and uncertainty.
4. Only after privacy approval and fresh budget authorization, develop a
   distinct Meta real-evidence adapter; do not reuse the synthetic-only
   adapter or silently alter the call budget.
5. Implement backend-scoped caregiver sessions, secure in-app previews and
   audit/notification outbox before enabling any actual advisory.

**Do not present this schematic as a camera snapshot or label the frozen
synthetic test a validated, deployed fall detector.**
