# Member 2 — Authenticated Edge v1 Candidate Intake (synthetic-only)

**Status 2026-11-02: Implemented + offline testable. Not approved for real
cameras, real people, real incident processing or production monitoring.**

## What this adds

The backend implements `POST /api/v1/edge/candidates` for the exact
Member 1 `viil.edge.candidate.v1` *metadata-only* format. This is **not**
the legacy `POST /api/v1/incidents/demo`, which remains a fictional,
mock-only workflow. The canonical source files from Member 1 are included
unchanged so source drift can be checked:

- `services/edge-vision/docs/edge_candidate_v1.schema.json`
- `services/edge-vision/examples/synthetic/candidate_v1.example.json`

Request rules are intentionally narrower than the full Edge producer schema.
Only `input_provenance=synthetic_pose_trace`, `simulated=true`, the
configured `synthetic-*` source ID, `model_sha256=null`, relative
source timestamp, no evidence refs, uncalibrated score and an explicitly
**unconfirmed** candidate are accepted. Camera and even consented real-person
video provenance are refused until a separately reviewed privacy system is
ready. User-provided provenance/consent claims alone never authorize images.

Each request requires:

- A **separate** backend-only source HMAC key of at least 32 bytes (do not
  reuse the Meta Model API key), enabled explicitly through the local config
- The sole approved synthetic source ID, matching signed header and JSON
- A fresh signed UNIX timestamp (within 60 seconds, distinct from the
  event's *relative-to-source-start* `source_timestamp_ms`)
- `Content-Type: application/json`, JSON size at most **4096 bytes**,
  18 exact required fields, no unknown or repeated keys
- One SQLite transaction per authenticated request, durable event UUID
  idempotency / conflict detection; **30 requests per source per minute**
  and a **10,000-event storage ceiling**, after which intake fails closed

The HMAC-SHA256 signature is over the UTF-8 ASCII string:

```text
viil.edge.candidate.v1
<source_id>
<unix_timestamp_seconds>
<lowercase_sha256_hex_of_exact_raw_http_body>
```

The `X-VIIL-Signature` header is `sha256=<lowercase_hmac_hex>`.
Provide `X-VIIL-Source-Id` and `X-VIIL-Timestamp` headers too.
The exact HTTP JSON body bytes are signed. The signer is authenticated as
the one preconfigured synthetic source, **not** as a real camera.

The response is `viil.backend.candidate_receipt.v1`: 201 for a newly
accepted event, 200 for an exact duplicate, 401 for invalid signature,
403 for source mismatch/outside loopback, 404 when disabled, 409 for event
UUID conflict, 413 for excessive bytes, 415 for non-JSON, 422 for unsafe
payload, 429 for rate limit and 503 for missing key/ledger/capacity.
Every receipt says `review_required=true`, `confirmed_fall=false`,
`meta_called=false`, `notification_sent=false`. This is **not**
a caregiver inbox, confirmation of a fall or real alert receipt.

The *server* attaches an UTC **receipt time**, without converting the Edge
candidate's source-relative timestamp to a fabricated wall-clock event.
The SQLite database lives under ignored `data/private` by default, not
in a tracked Git source file. It stores only candidate UUID, source,
request digest, and receipt UTC. The body/image is not persisted.

**Privacy and operations:** This release only accepts loopback client IPs,
plus the in-process `TestClient` hostname for automated tests. Start the
actual API bound to `127.0.0.1`, not a public interface. The backend has
no fully authenticated multi-tenant caregiver RBAC, durable notification
outbox, real-world consent verifier, model hash registry or camera registry
yet. The key, storage and timestamps are local development mechanisms,
not a production identity or hospital-grade monitoring solution.

## Run the complete safe demo — no keys, no Meta API, no billing

From `D:\VIIL-Sentinel\services\api`:

```powershell
.\.venv\Scripts\python.exe -m app.synthetic_intake_smoke
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

The smoke test uses the canonical synthetic Member 1 fixture, a **fake**
ephemeral test-only signing key, FastAPI `TestClient`, and a temporary
on-disk SQLite ledger. It verifies a single 201 acceptance, deduplicated
200 second receipt, 401 for missing signature, 422 for camera provenance,
403 for unauthorized non-demo incident reads, and *zero* Meta or alerts.
It opens no local TCP port and uploads no image. The temp ledger disappears
after the command exits.

## Operator-only local endpoint setup (optional; disabled by default)

Create a new unique, random source signing secret separately from the Meta
key, store it only in ignored `services/api/.env`, and set:

```dotenv
EDGE_CANDIDATE_INGEST_ENABLED=true
EDGE_CANDIDATE_SOURCE_ID=synthetic-clip-01
EDGE_CANDIDATE_HMAC_SECRET=<NEW_RANDOM_32_PLUS_BYTE_SECRET>
```

Do not use this demo secret for external camera access; do not commit the
`.env` or include keys in logs, URLs or example scripts. Run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

A purpose-built source client must sign each request with exactly the
registered `EDGE_CANDIDATE_HMAC_SECRET`. No frontend/mobile code should
receive that secret. The signed envelope **still has no evidence or real
candidate authority**. Never set `META_PROVIDER` to a live value for this
route; its implementation does not call Meta by design.

## Remaining blockers

No real-person candidate intake, signed privacy authorization, per-tenant
RBAC, verified model provenance, trusted video wall-clock anchoring,
hardened multitenant source registry, durable alert outbox, privacy retention
policy or physical camera acceptance has been demonstrated. Real Meta
structured output is also unverified (prior two capped local trial calls);
its budget ledger is completely separate and must **not** be reset. The
$150 team allowance is not spent by any of these offline tests.
