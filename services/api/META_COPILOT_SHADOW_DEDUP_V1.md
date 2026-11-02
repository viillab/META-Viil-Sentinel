# VIIL-Sentinel — Meta Copilot Shadow Admission, Deduplication & Readiness v1

**Member 2 • 2026-11-02 • Offline, synthetic-only, no paid Meta calls**

## Scope

The previous milestones validated **real synthetic-only Meta API** response
contracts (4 authorized local calls already consumed), event-bound fictional
pose evidence, HMAC-signed Edge ingestion, a local synthetic Evidence Registry,
audited evidence, a separate signed audit checkpoint, deterministic Copilot
review tasks and an **in-process MockTransport** Meta-shaped provider response.

This increment adds a **durable per-event shadow-run reservation** to ensure
one synthetic event can be dispatched to that mock provider **once only**,
even when the same request is repeated, the Python process restarts or two
local workers race. Nothing in this feature enables a paid Meta connection.

## Integration

```text
Member 1 synthetic pose trace
  -> signed Edge Candidate over real loopback HTTP
  -> SQLite Candidate receipt + deterministic synthetic pose Manifest
  -> SHA256 audit chain + independent HMAC-signed checkpoint
  -> authenticated, source-scoped Copilot read-only evidence checks
  -> MetaCopilotShadowLedger.run_mock_once()
     1) independently verify event, candidate, signed audit checkpoint
     2) READ the existing Meta local budget ledger (no reservation)
     3) always return real_provider_allowed=false
     4) BEGIN IMMEDIATE: claim event UUID in separate private SQLite ledger
     5) call mock-only Meta-shaped HTTP adapter ONCE
     6) strict model JSON / allowlist / tool validation
     7) re-verify signed evidence and checkpoint after the model-shaped response
     8) persist safe, nonbinding, synthetic Copilot preview on success
  -> next request for same UUID reads validated cache (zero provider calls)
  -> failure or crash: fail closed; no automatic retry/reset
```

**Important:** this is a SHADOW **mock-only** execution controller.
`httpx.MockTransport` produces simulated HTTP responses inside the
process. There is no real Meta API call, token spend, image transmission,
human consent, alert dispatch, or state transition to “fall confirmed”.

`MetaCopilotShadowLedger` persists only source ID, synthetic event UUID,
the verified Candidate SHA-256, signed Audit Head digest, hash of the
strict would-be JSON request, an explicit `reserved/completed/failed`
state, UTC reservation time and the **strict, safe Copilot preview**.
It does not store provider raw JSON, patient images, pose coordinates,
caregiver tokens, Meta API keys, private audit-signing keys, API usage
data or any real fall events.

SQLite `BEGIN IMMEDIATE` serializes claims across local processes.
A duplicate event with the identical verified hashes returns a cached,
strictly revalidated preview. A changed event UUID/hash/manifest/request
or modified independent signing anchor is rejected. A `reserved` or
`failed` row is **not retried automatically**. The shadow history is
bounded to 10,000 events and uses a different private SQLite database
from both the Candidate ledger and Meta spend ledger.

### Read-only Caregiver readiness endpoint

```text
GET /api/v1/caregiver/copilot/{event_id}/readiness
```

This endpoint is disabled unless the existing
`META_COPILOT_PREVIEW_ENABLED=true`,
`EVIDENCE_REGISTRY_ENABLED=true` and
`EVIDENCE_AUDIT_ANCHOR_REQUIRED=true` are set. It requires the same
independent Caregiver Bearer token and loopback-only access as the
other local Caregiver views, and checks the signed Evidence/Audit checkpoint
**before** returning data. The response includes:

- `mode=shadow_mock_only`, `real_provider_allowed=false`
- `real_provider_denial=synthetic_consent_not_verified_and_budget_unapproved`
- the local Meta test budget’s **read-only** attempt/reservation counters,
  whether its SQLite file exists, and whether the original approved
  **4-call/$0.75** maximum is exhausted
- `official_meta_billing_verified=false`,
  `real_media_upload_authorized=false`,
  `alert_dispatch_authorized=false`, `meta_api_called=false`

The endpoint does **not** create a new spend ledger, reserve tokens,
approve any further API call, create a shadow run, access a camera or
ask Meta for inference. No POST, PUT or DELETE endpoint exists.

The Meta budget values are **only this machine’s conservative local
test-reservation history**, not Meta’s official account-wide billing
or remaining team credits. In particular, missing on-disk budget data
is reported as `local_budget_ledger_present=false`, not proof of zero
actual provider spend. There is **no positive real-provider permission
path** in this release, even with unused test budget.

## Verification

In `D:\VIIL-Sentinel\services\api`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_meta_copilot_shadow_ledger.py
.\.venv\Scripts\python.exe -m app.synthetic_evidence_smoke
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Expected smoke status `SYNTHETIC_EVENT_BOUND_EVIDENCE_PASS`, including
`shadow_ledger_one_mock_call_per_event=true`,
`shadow_ledger_duplicate_cached=true`,
`shadow_ledger_readiness_denies_live_meta=true`,
`shadow_readiness_verified_over_local_http=true` and
`shadow_ledger_cache_invalidated_by_bad_anchor=true`.

The tests cover concurrent duplicate submissions, process-restart
idempotency, mocked provider 429 and permanent retry denial, interrupted
reservations, event mismatch, tampered cache, lost signed checkpoint,
run capacity and isolated test-budget 4/4 exhaustion. The real production
Meta local ledger is only **read** by readiness; no billable API is invoked.

## Future actual Meta planner blockers

This architecture is a stepping stone, NOT a production deployment.
To connect actual Meta planning, a **separate** code review must implement:

1. Confirm official Meta Billing/Usage and get a NEW explicitly approved
   bounded test allowance; **never reset the existing 4/4 ledger**.
2. Approved source, purpose, consent, revocation, retention and a strict
   allowlist of metadata/media permitted to leave the host. Even hashed
   event IDs may be sensitive depending on context.
3. A distinct live provider adapter with a server-only secret, a
   transactionally reserved paid budget tied to each event, rate limit,
   kill switch and explicit opt-in. Do not convert this mock-only
   adapter to a live transport.
4. Real caregiver session/RBAC (not a bearer in Flutter or React),
   append-only independently anchored audit service, independent
   incident accuracy evaluation and alert delivery approvals.
5. Human-in-the-loop review before any real fall conclusion or
   emergency escalation. Meta model output must never grant rights.

Current local Meta ledger remains **4/4 attempts**, with
**$0.514148** in conservative reservations; this is not a real
billing statement or a confirmed $150 balance.
