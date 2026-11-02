# VIIL-Sentinel — Independent Signed Synthetic Audit Checkpoint v1

**Member 2 • 2026-11-02 • Offline only • No live media, Meta calls, or alerts**

## Objective and verified improvement

The existing `synthetic_evidence_audit` SQLite rows form a SHA-256
hash chain; an administrator who can rewrite that database could
recalculate every link. This increment adds an **opt-in independent
HMAC-SHA256 checkpoint**, persisted as a separate JSON file, and a
read-time verification gate for the existing caregiver Evidence and Audit
metadata endpoints.

```text
Member 1 fictional pose trace -> Edge Candidate -> HMAC-signed localhost
  -> SQLite signed-candidate receipt and metadata-only evidence registry
  -> synthetic audit SHA256 chain, verified against Registry + Candidate
  -> explicit operator capture_checkpoint() with DIFFERENT independent HMAC key
  -> separate signed-head.json in a DIFFERENT directory
  -> opt-in EVIDENCE_AUDIT_ANCHOR_REQUIRED=true
  -> guarded GET /api/v1/caregiver/evidence/{event_id}
     and GET /api/v1/caregiver/evidence/{event_id}/audit
     -> compare entire verified SQLite history with independently signed head
     -> 200 if matched, 503 if missing, modified, stale or wrong signing key
```

**This is an audit-integrity guard, not a production consent authority.**
It never turns `consent_state` into approval, never authorizes image uploads
or camera access, never calls Meta AI or notifies caregivers, and never
claims a confirmed fall.

The checkpoint has only the strictly typed schema
`viil.synthetic.audit_anchor.v1`: source ID, UTC capture time, number of
records, first/last event UUID, first/last chain SHA-256, explicit
`not_verified_for_real_media` consent status, `external_upload_authorized=false`,
`meta_call_permitted=false`, and a domain-separated HMAC-SHA256.
No patient data, images, frames, consent documents, API keys, signing key,
or unredacted model responses are exported.

## Boundaries

- The checkpoint must live **outside the directory holding SQLite**.
  Use different OS permissions or custody as appropriate; merely using
  two folders does **not** independently protect against an admin who
  controls both.
- The checkpoint signing key is separate from the Edge candidate signer,
  caregiver token and Meta API key. Key material is never committed to Git,
  included in URL arguments, returned through HTTP, or printed.
- `capture_checkpoint` checks the ENTIRE pre-existing chain and its
  Registry/Candidate associations before signing. If a checkpoint already
  exists it verifies the prior HMAC and its prefix to prevent overwriting
  evidence of an earlier rollback or changed history. It is idempotent for
  an unchanged head and writes a new head using an atomic file replace.
- `verify_checkpoint` is **read-only**. It rejects wrong keys, forged
  JSON, duplicate JSON fields, malformed/non-UTC metadata, stale heads,
  missing files, deleted rows or any current audit/registry mismatch.
- If the database receives a new *synthetic* registration after capture,
  strict reads return 503 until an authorized operator captures a new
  checkpoint. This is intentional rather than silently trusting
  unaudited changes.
- `SyntheticEvidenceRegistry` in anchored-read mode **refuses writes**.
  Register the synthetic event using an ordinary offline internal Registry
  instance first, then explicitly export the checkpoint, then enable
  anchored reads. There is **no new public registration API**.
- Both caregiver endpoints remain disabled unless the existing
  `EVIDENCE_REGISTRY_ENABLED=true` flag is set, use loopback and an
  independent bearer secret, and return only metadata with no-store caching.
- A missing pre-existing checkpoint is a **verification failure**, not
  permission to fabricate a new history. Do not reset files to get a pass.

## Optional operator CLI

This is intentionally **not** an automatic side effect of incoming
candidates or browser requests. Set
`VIIL_SYNTHETIC_AUDIT_ANCHOR_KEY` securely in the operator's shell or
secret-management workflow. It must be a high-entropy independent secret
of at least 32 bytes; never use the Meta, Edge or caregiver credential.

From `D:\VIIL-Sentinel\services\api`:

```powershell
# Safe without arguments: prints OFFLINE_NO_CHANGES, does NOT read keys.
.\.venv\Scripts\python.exe -m app.evidence_anchor

# Example: adapt both paths to YOUR private ledger and separately protected
# existing checkpoint directory (do not copy the example as-is).
.\.venv\Scripts\python.exe -m app.evidence_anchor --capture --ledger "D:\private\receipts.sqlite3" --checkpoint "D:\separate-audit\synthetic-head.json"

.\.venv\Scripts\python.exe -m app.evidence_anchor --verify --ledger "D:\private\receipts.sqlite3" --checkpoint "D:\separate-audit\synthetic-head.json"
```

The example requires a previously populated synthetic Candidate + Evidence
Registry + Audit ledger; if no signed synthetic events exist, export fails
closed. The parent directory of the checkpoint must already exist. It
never starts a server or calls any external network service.

To require a valid independent checkpoint for the existing local caregiver
Evidence/Audit metadata reads, configure the backend **server-only**
environment (all disabled by default):

```dotenv
EVIDENCE_REGISTRY_ENABLED=true
EVIDENCE_AUDIT_ANCHOR_REQUIRED=true
EVIDENCE_AUDIT_ANCHOR_PATH=D:\separate-audit\synthetic-head.json
# Supply EVIDENCE_AUDIT_ANCHOR_SECRET from a private secret store,
# matching VIIL_SYNTHETIC_AUDIT_ANCHOR_KEY used at capture.
```

This is a developer-only mechanism. Environment variables and local
file ACLs are **not** production-grade KMS/HSM key custody. Do not
distribute the signing key with Flutter, web, or desktop clients.

## Test and live TCP smoke (zero paid usage)

```powershell
cd D:\VIIL-Sentinel\services\api
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m app.synthetic_evidence_smoke
```

The smoke uses fresh, random, **temporary** independent secrets and starts
a real ephemeral 127.0.0.1 Uvicorn server. It creates a signed synthetic
candidate from Member 1's genuine offline Edge detector, stores metadata,
appends an audit entry, demonstrates 503 before anchor capture, captures
an independent signed checkpoint, confirms successful authenticated
caregiver Evidence and Audit GETs, then corrupts the checkpoint and
confirms HTTP 503 on both endpoints. All test artifacts, SQLite, server
and checkpoint are removed on exit.

Additional negative tests deliberately **recalculate an internally
valid but malicious new SQLite hash chain**, show that the original
in-database verifier can still accept it, and show that the external
signed checkpoint refuses it. Other tests cover mismatched secrets,
stale checkpoints, explicit extension of a trusted prefix, replay,
missing file, forged consent flag, deleted rows, malformed JSON and
the off-by-default API boundary.

## Known limits — do not claim complete immutability

This snapshot is not transactional with **subsequent** SQLite writes.
After an event insert, reads intentionally fail until the operator
explicitly signs a newer checkpoint. A compromise that includes the
signing key or the independently held checkpoint can defeat this
control; retained external checkpoints and immutable audit storage
are still needed for real assurance. Simultaneous multi-process
checkpoint exporters are not serialized here. Standard filesystem
atomic replacement is not equivalent to a WORM store or external
time-stamping authority.

Production work still needs reviewed media consent/revocation,
identity and tenant RBAC, KMS/HSM keys, append-only external audit
service, secure signed camera evidence, timestamp attestation and
labeled fall-detection evaluation.

**The original local Meta Model API budget remains exhausted at
4/4 requests**. The estimated reserved $0.514148 is not the team's
official Meta Billing balance or an account-wide spending limit.
