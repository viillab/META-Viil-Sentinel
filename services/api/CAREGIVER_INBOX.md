# VIIL-Sentinel Member 2 — Read-Only Caregiver Inbox (Local Synthetic Contract)

**Implemented 2026-11-02.** Developer-only bridge between the existing
signed, metadata-only Edge v1 ingestion ledger and the Member 1
`viil.backend.caregiver_inbox.v1` Flutter/Dashboard handoff contract.

This is NOT real camera monitoring, verified fall detection, caregiver
authentication/RBAC for production, Meta inference, external alert delivery,
or emergency-response infrastructure. In-app Mobile/React screens are **not
connected** to this HTTP endpoint by this change.

## New endpoint

`GET /api/v1/caregiver/inbox` — **disabled by default**.
When explicitly configured, the endpoint:

- Requires an **independent** caregiver bearer token (minimum 32 UTF-8 bytes).
  The Edge HMAC signing secret and Meta API key must **never** be reused.
- Refuses clients outside loopback (`127.0.0.1` / `::1`), except the
  special test client's in-memory `testclient` host.
- Uses the one configured synthetic source ID and a SQL parameterized
  source filter; no source/tenant ID is accepted in the caller's request.
- Opens the existing ignored SQLite Edge candidate ledger **read-only**,
  projects the 30 newest receipts, and never stores or returns raw HTTP
  candidate bodies, digest hashes, images, pose landmarks, paths, identity,
  model files, API keys, or personal medical information.
- Adds `Cache-Control: no-store` and returns exactly the versioned
  `handoff/team/caregiver_inbox.v1.schema.json` fields.
- Never sends notifications or calls Meta. There is **no acknowledge**,
  review mutation, emergency dispatch, or medical advice capability.

Each advisory is labeled `simulated=true`, `stage=edge_candidate`,
`meta_provenance=none`, `delivery_state=not_sent`,
`receipt_verified=false`, `review_state=pending`,
`human_follow_up_required=true`, `fall_confirmed=false` and
`emergency_dispatch_authorized=false`.

**Crucial timestamp interpretation:** `occurred_at` currently maps to the
backend's **receipt UTC**, because the upstream Edge
`source_timestamp_ms` is relative to its source start, not Unix time.
This is *not* a verified moment of a real fall. Client UI must label it
"Recorded by local backend" or "Synthetic receipt time", not fall onset.

## Offline end-to-end demonstration (no secrets and no billing)

Run from `D:\VIIL-Sentinel\services\api`:

```powershell
.\.venv\Scripts\python.exe -m app.synthetic_intake_smoke
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

The smoke runs **synthetic Member 1 fixture → signed in-process FastAPI
request → durable temporary SQLite → guarded caregiver inbox**. It tests
an unsigned GET returns 401, an authorized GET returns exactly one
metadata-only advisory, duplicate ingestion adds no second advisory,
and both `meta_called` and `notification_sent` stay false. No local
network port is opened; the temp DB is deleted. The fake token and fake
HMAC signer used by this test have no operational authority.

## Optional local operator configuration (not required for smoke)

To start a local-only server for development, write **new random**,
**independent** secrets in ignored `services/api/.env`. Never commit
them, paste them in GitHub/Frontend, or include them in request logs.

```dotenv
META_PROVIDER=mock
EDGE_CANDIDATE_INGEST_ENABLED=true
EDGE_CANDIDATE_SOURCE_ID=synthetic-clip-01
EDGE_CANDIDATE_HMAC_SECRET=<NEW_RANDOM_DEVELOPMENT_HMAC_KEY_AT_LEAST_32_BYTES>
CAREGIVER_INBOX_ENABLED=true
CAREGIVER_INBOX_TOKEN=<DIFFERENT_RANDOM_DEVELOPMENT_READ_TOKEN_AT_LEAST_32_BYTES>
```

Run from `services/api`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The operator must pass `Authorization: Bearer <CAREGIVER_INBOX_TOKEN>`
when reading the inbox. Missing/invalid auth is HTTP 401; disabled route is
404; unconfigured/weak/reused token is 503; non-loopback client is 403.
No browser-accessible key management is provided. Do **not** embed the
bearer token in Flutter, a compiled React app, URL query string or source
repository. Mobile devices cannot use the host's loopback endpoint without
an additional secured network and authorization architecture.

The configured candidate DB can be missing; the authorized endpoint then
returns an empty inbox without creating a DB. A damaged or inaccessible
existing DB fails closed with 503. SQLite connections are now explicitly
closed on both ingestion and inbox reads, including on Windows.

## Hand-off and remaining blockers

- UI contract source copied unchanged from Member 1:
  `handoff/team/caregiver_inbox.v1.schema.json`.
- The endpoint currently projects **only** synthetic v1 receipts already
  stored in the Edge intake ledger, not the legacy demo incidents.
- No authentication service or individual caregiver identity, tenant RBAC,
  federated SSO, secure session lifecycle, durable alert outbox, evidence
  consent verifier, real device auth, transport TLS, mobile backend client,
  persistent audit retention policy or production readiness has been established.
- All tests use fake tokens and synthetic fixtures. No real Meta Model API
  request occurs in this change; the previous two-call Meta local trial
  ledger and the user's $150 team allowance are left untouched.

Do not change `simulated` or `fall_confirmed` semantics merely to make a
judge/demo look live. A production deployment must not reuse this local
prototype token model.
