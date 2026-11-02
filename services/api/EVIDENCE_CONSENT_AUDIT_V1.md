# VIIL-Sentinel — Synthetic Consent Gate & Evidence Audit Chain v1

**Member 2 | 2026-11-02 | synthetic-only | local development**

## Verified scope

This increment adds a **real, persisted, transaction-bound evidence audit**
and an explicit **all-deny** consent gate for synthetic evidence. It does
**not** approve, capture, classify, upload, or store photographs of people,
cameras, real fall incidents, personal data or medical records. It does not
call Meta, send notifications, or authorize emergency dispatch.

```text
Member 1 fictional fall pose trace -> edge candidate
  -> HMAC-authenticated localhost POST -> SQLite candidate receipt
  -> deterministic synthetic Pose Strip PNG + strict Manifest in memory
  -> immutable metadata-only SyntheticEvidenceRegistry.register()
     -> refuse if raw candidate hash mismatches signed receipt
     -> require_synthetic_consent_block() = not_verified_for_real_media
     -> BEGIN IMMEDIATE transaction
        -> verify existing audit chain + registry/candidate integrity
        -> INSERT manifest hashes, source ID, UUID, timestamp
        -> APPEND audit record (sequence, previous SHA256, entry SHA256)
        -> verify entire chain and all registry/candidate associations
        -> commit both together, or roll back both
  -> guarded HTTP GET of registry record and audit history
  -> existing caregiver inbox remains simulated/unconfirmed
```

## What is persisted

A new SQLite table `synthetic_evidence_audit` in the existing **private
synthetic Candidate ledger** stores a bounded global sequence; synthetic
event UUID; pseudonymous source; action `synthetic_manifest_registered`;
backend UTC registration time; candidate SHA256; manifest SHA256;
previous entry SHA256; entry SHA256; and explicit
`consent_state=not_verified_for_real_media` with
`external_upload_authorized=0`.

The SHA256 digest is computed over a deterministic, field-complete JSON
representation including the previous hash, UUID and denial flags.
The first entry links to a fixed all-zero genesis hash; later entries
link to the preceding committed entry. The checker validates **every**
link and verifies audit rows match the Registry and signed Candidate ledger.
It also checks no registered evidence is omitted from the audit history.
A repeated registration of identical evidence does not append an extra log.

The audit table does **not** include PNG/JPEG/video bytes, pose
landmarks, person names, user tokens, API keys, consent documents or
Meta responses. The existing registry continues to hold only metadata.
The audit checker is bounded by 10,000 records, matching the existing
local ledger capacity.

This provides **tamper detection for inconsistently modified local
records**, not an independently anchored or cryptographically signed
audit. An attacker with direct SQLite write privileges could rewrite the
whole chain and related registry rows, so this must **not** be marketed as
an immutable production audit trail.

## Strict real-media consent gate

`require_synthetic_consent_block(manifest)` returns:

```json
{
  "schema_version": "viil.synthetic.consent_gate.v1",
  "source_id": "synthetic-clip-01",
  "state": "not_verified_for_real_media",
  "reason": "no_independent_real_person_consent_authority",
  "external_upload_authorized": false,
  "human_evidence_authorized": false,
  "meta_call_permitted": false
}
```

This is a denial, **not an approval workflow**. The function has no
positive authorization path. Attempts to flip `simulated`,
`external_upload_authorized`, `consent_for_real_media_verified`,
`contains_real_person`, `meta_inference_performed`,
`permanent_storage_allowed` or `fall_confirmed` are rejected by the
strict synthetic evidence verifier or the consent gate.

To support real people, a **separate**, authorized consent system with
verifiable grantor, revocation, source/site scope, permitted purpose,
retention and expiry is still required. Do not repurpose this deny-only
synthetic module into real-media consent signing.

## Guarded API

`GET /api/v1/caregiver/evidence/{event_id}/audit`

The endpoint is OFF unless `EVIDENCE_REGISTRY_ENABLED=true`. It uses
the existing independent 32+-byte caregiver bearer and loopback-only
checks, responds with strictly typed
`viil.synthetic.evidence_audit.v1` metadata, and sets
`Cache-Control: no-store`. Missing/malformed bearer gives 401,
remote clients 403, disabled endpoint 404, missing event 404 and
broken/tampered chain 503. There is no POST, PUT or DELETE audit API.
A separate real identity/session RBAC architecture remains a production
blocker. The static bearer must never be included in Flutter/React builds.

The existing `GET /api/v1/caregiver/evidence/{event_id}` now also
verifies the entire audit chain before returning metadata. An existing
registry database created by the earlier pre-audit prototype, containing
Registry rows without audit records, **fails closed with HTTP 503**.
This is intentional; never fabricate retroactive audit entries. For
migration, use a separately reviewed read-only backup/transition plan
that labels historic rows as unaudited. Do not delete the private ledger
just to make a test pass.

## Test locally (no paid API)

In `D:\VIIL-Sentinel\services\api`:

```powershell
.\.venv\Scripts\python.exe -m app.synthetic_evidence_smoke
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

The smoke starts a temporary real Uvicorn HTTP listener on
`127.0.0.1`, uses independent random local keys to insert one signed
synthetic event, registers its evidence twice, verifies one chained audit
record via the caregiver HTTP GET, and checks the consent denial.
It stops the server and deletes temporary SQLite and in-memory image
data. It does NOT call Meta; its response to the offline Meta contract
is specifically MOCK.

Tests exercise two consecutive distinct UUIDs, cross-entry links,
idempotency, forged digests, action changes, fake consent, fake
Meta permission, deletion, missing/duplicate credentials, remote
header spoofing, POST/PUT/DELETE rejection, transaction rollback and
retroactive registry/ledger mismatches. The full backend suite and Edge
producer suite must still pass before integration.

## Remaining production blockers

- No independent consent authority, signed revocation or authenticated
  approval workflow for real-person recordings.
- No separately anchored audit signing, WORM storage, tamperproof
  retention policy, tenant permissions or legal review.
- No real-person image approval, encrypted image storage, frame evidence
  association, Hikvision camera intake, timestamp attestation or
  real-world fall accuracy evaluation.
- No authenticated remote Flutter/Dashboard caregiver session, secure
  network ingress or delivery/acknowledgment service.
- Local Meta spend ledger remains **4/4 attempts** exhausted with
  `$0.514148` conservative reservations, NOT official billing and NOT
  a spend control for the full team $150 allowance.

Never reset the Meta guard, interpret synthetic geometry as a real
fall, or enable an actual emergency dispatch based on this demo.
