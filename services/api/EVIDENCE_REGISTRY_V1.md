# VIIL-Sentinel — Synthetic Evidence Registry v1

**2026-11-02 • Member 2 • Local-only, metadata-only, synthetic-only**

## Verified delivery

The private `SyntheticEvidenceRegistry` connects the real Member 1
Python pose detector, Member 2's authenticated synthetic candidate intake,
the existing SQLite ledger, the canonical synthetic Pose Strip Manifest,
and one new guarded read-only API:

```text
Pinned fictional fall.jsonl
  -> Member1 temporal detector -> viil.edge.candidate.v1 (UUID)
  -> HMAC-signed POST /api/v1/edge/candidates over localhost TCP
  -> SQLite candidates(event_id, source_id, SHA256 of EXACT raw request)
  -> build_synthetic_evidence(raw_candidate) in local Python
  -> verify_synthetic_evidence(raw_candidate, PNG and Manifest)
  -> SyntheticEvidenceRegistry.register() in SAME SQLite database
  -> synthetic_evidence_registry (metadata JSON + hashes only)
  -> GET /api/v1/caregiver/evidence/{event_id} (optional local bearer auth)
```

The registry verifies all of these conditions **before insertion**:

- Signed Edge candidate acceptance must already exist with matching UUID,
  source and SHA-256 of the **exact raw candidate HTTP body**; merely
  constructing a plausible JSON document cannot create a valid registry row.
- The original candidate must be exactly the frozen Member 1 synthetic fall
  fixture, apart from its new UUID. Non-synthetic provenance, camera data,
  external image references, invented detector confidence and wrong relative
  time are rejected upstream by the existing evidence validator.
- The frozen trace, canonical candidate example and rendered 336×112 PNG are
  each hash-checked and linked to the single event.
- `real_person_evidence_verified=false`,
  `consent_state=not_verified_for_real_media`,
  `external_upload_authorized=false`,
  `meta_called=false`, `fall_confirmed=false` and
  `notification_sent=false` are non-overridable in the output schema.
- Registry rows are immutable: exactly matching repeated registration is
  idempotent. Different evidence cannot replace a previously registered UUID.
  The metadata table is bounded by the same 10,000-event capacity as the
  local source ledger.

**What is stored:** event UUID, synthetic source ID, raw candidate SHA-256,
validated Manifest JSON (hashes and synthetic-only safety flags), and
backend registration UTC time. **What is not stored:** PNG/JPEG bytes, real
video, pose landmarks, faces, names, metadata API keys, original raw
candidate JSON, Meta provider responses, or consent documents.

The registry reads using SQLite `mode=ro`; it does not create a missing DB
and it refuses corrupt or tampered records. A no-record response is 404;
corruption/unavailable storage is 503. All database handles close explicitly
on Windows. This is a local developer registry, **not** cryptographically
tamperproof storage against an attacker who can rewrite the database.

## Optional read-only caregiver API

`GET /api/v1/caregiver/evidence/{event_id}`

The route is **off by default** (`EVIDENCE_REGISTRY_ENABLED=false`).
When enabled, it requires the same independent 32+-byte caregiver token and
loopback checks as `GET /api/v1/caregiver/inbox`. It emits metadata only
using schema `viil.backend.synthetic_evidence_registry.v1`, with
`Cache-Control: no-store`. Missing or duplicated bearer headers are 401,
non-loopback source addresses 403, missing records 404. `POST`, `PUT`
and `DELETE` for this route are not provided. The browser/Mobile must
**never embed the static backend bearer token**; a production session-based
RBAC design is still necessary.

For optional local testing, put separately generated keys into the ignored
`services/api/.env` and explicitly set:

```dotenv
EDGE_CANDIDATE_INGEST_ENABLED=true
EDGE_CANDIDATE_SOURCE_ID=synthetic-clip-01
EDGE_CANDIDATE_HMAC_SECRET=<separate-random-local-secret-32-bytes-minimum>
CAREGIVER_INBOX_ENABLED=true
CAREGIVER_INBOX_TOKEN=<different-random-local-token-32-bytes-minimum>
EVIDENCE_REGISTRY_ENABLED=true
META_PROVIDER=mock
META_LIVE_ENABLED=false
```

This setting **does not** create a public registration route; registration
remains an internal, reviewed Python action after successful candidate
intake. The synthetic example smoke below enables its own *ephemeral*
random secrets and registry flag without loading `.env`.

## Run the verified demonstration

In `D:\VIIL-Sentinel\services\api`:

```powershell
.\.venv\Scripts\python.exe -m app.synthetic_evidence_smoke
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Expected result:
`SYNTHETIC_EVENT_BOUND_EVIDENCE_PASS`, now including
`registry_same_signed_event_verified=true`,
`registry_read_via_local_http_verified=true`,
`registry_deduplicated=true`,
`registry_real_media_consent_verified=false` and
`registry_image_bytes_stored=false`.

The E2E smoke starts a temporary **real localhost TCP Uvicorn service**,
posts one signed synthetic candidate, registers the matching manifest
twice, reads it via an authenticated local HTTP GET, exercises a separate
MOCK Meta response and confirms the existing caregiver Inbox remains
unconfirmed. The temporary database and port are removed/closed.
No real images, notifications or paid Meta calls are involved.

Tests cover event/Hash mismatches, unregistered and spoofed UUIDs, tampered
PNG/Manifest consent flags, corrupt SQLite records, missing/duplicated
and remote authorization, disabled routes, read-only methods,
no image persistence, source isolation and idempotency.

## Consent and safety limitations — NOT production authorization

**This registry cannot verify a real person's consent.** A synthetic trace
does not require real-person consent and cannot grant permission for actual
camera video. This tool deliberately says "not verified for real media"
rather than pretending that a checkbox, signature string, or filename
establishes consent.

A signed candidate receipt in this demo means the **HTTP ingest gate**
validated a local synthetic HMAC. The registry itself checks the ledger
entry, but an operator with direct DB write access could fabricate a row.
Therefore database rows are not independent proof of cryptographic
source provenance, authenticity, or legal authorization.

Before future real camera evidence, implement a separate consent/ownership
verification authority, per-site and per-device scoped source credentials,
signed frame hashes and timestamps, privacy-retention controls, encryption,
immutable audit logs, auth sessions and a properly reviewed real-media
ingest pipeline. Do not simply change `simulated` to false.

Meta Model API remains exhausted at **4/4 paid attempts** in the local
budget ledger. This feature never reads or resets that ledger and never
contacts Meta. The team's true $150 balance remains subject to official
Meta Usage/Billing verification.
