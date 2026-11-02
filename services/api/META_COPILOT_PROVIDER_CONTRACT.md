# VIIL-Sentinel — Meta Copilot Provider Contract, Offline v1

**2026-11-02 • Member 2 • Meta Model API dry-run over `httpx.MockTransport` only**

## What is now implemented

Previous milestone: an independently anchored synthetic Evidence Registry and
an opt-in, deterministic read-only Meta Copilot endpoint. This milestone
connects the **prospective Muse Spark Chat Completions request** to an
**HTTP provider response parser and strict allowlisted task runner**, without
using an actual Meta API call or spending additional credits.

`app.meta_copilot_mock_transport.MockOnlyMetaPlanner` takes a real
`httpx.MockTransport` instance. It refuses every real
`httpx.AsyncHTTPTransport`, accepts **no Meta API key**, uses no
authentication headers, disables environment proxy inheritance and redirects,
and cannot create a network connection to Meta. The URL is used solely to
verify the request's compatibility with the expected provider contract.

```text
Member1 synthetic Edge detection (pinned mathematical poses)
  -> signed candidate FastAPI localhost TCP
  -> SQLite synthetic receipt + SHA256 event-bound evidence Manifest
  -> separate independent HMAC audit checkpoint
  -> CHECK evidence, event ID, source scope, audit integrity, signing anchor
  -> PREPARE strict Muse Spark JSON Schema request (metadata, no image)
  -> mock-only Chat Completions POST with simulated provider JSON
  -> validate model + choice + stop + assistant + token caps + JSON fields
  -> validate exact UUID and 3-tool read-only allowlist, reject duplicates
  -> RECHECK independent evidence and signed checkpoint after mock response
  -> backend deterministic Copilot preview, no state change
  -> caregiver remains responsible for follow-up; NO external notification
```

**Important distinction:** The mock **does not** represent a Meta inference.
`MockMetaPlannerResult` returns `provider_response_simulated=true`,
`meta_api_called=false`, `meta_budget_modified=false`,
`real_media_sent=false`, `state_changed=false`. The existing
`GET /api/v1/caregiver/copilot/{event_id}` still truthfully reports
`mode=offline_readonly_shadow`, `meta_api_called=false` and
`model_has_executed_tools=false`. It does not expose a paid model call.

## Request/response boundaries

The model request uses `muse-spark-1.3` with
`reasoning_effort=minimal`, `max_completion_tokens=512`, and
`viil_meta_copilot_proposal_v1` strict JSON Schema. It sends only
frozen, non-person synthetic UUID/hash/time metadata. There are **no**
camera frames, PNGs, real persons, user names, caregiver tokens,
private keys, Meta bearer tokens, shell commands, or unrestricted tool
definitions in the request.

The response parser rejects:

- Unknown/wrong model, missing/multiple choices, refusal, non-`stop`
  finish reason and direct provider `tool_calls`
- Non-assistant role, missing content, truncated/malformed/oversized JSON,
  repeated JSON keys, NaN/Infinity and abnormal provider token counts
- Unknown tool names, unknown tool arguments, wrong/mixed Event UUIDs,
  duplicate tasks, omitted mandatory tasks or extra unapproved fields
- Non-200 simulated HTTP response (401/429/5xx), without retries,
  redirects, raw provider-body logging or exceptions containing secrets
- Missing/tampered independent anchor before the call, **or altered
  anchor during the response** (the backend rechecks before preparing
  any read-only preview)

The **only** accepted proposals contain these three known tools for the
same event, once each: `check_event_linkage`,
`verify_audit_integrity`, `prepare_caregiver_handoff`.
The model can reorder these but cannot invent any side-effecting action.
The backend does all verification and produces fixed safe summary codes,
not model-generated diagnosis, escalation or emergency alerts.

## Run tests

From `D:\VIIL-Sentinel\services\api`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_meta_copilot_mock_transport.py
.\.venv\Scripts\python.exe -m app.synthetic_evidence_smoke
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Smoke success: `SYNTHETIC_EVENT_BOUND_EVIDENCE_PASS`, plus

- `meta_copilot_mock_provider_contract_verified=true`
- `meta_copilot_mock_provider_calls=1` (one **mock** request only)
- `meta_copilot_mock_provider_rejected_after_anchor_corruption=true`
- `real_meta_api_called=false`, `meta_budget_modified=false`

The smoke also sends a **real TCP HTTP** request to the local FastAPI
service. This is distinct from the synthetic Meta HTTP call, which
is an in-process mocked transport and never reaches the internet.

## Why not enable real Meta now?

The previous authorized four Meta test attempts are exhausted on the
workstation. The on-disk ledger is still **4/4 attempts**, with
`$0.514148` in conservative local reservations. This number is **not**
Meta Billing or confirmation of the organization's remaining $150 credit.
Neither this dry-run nor its tests touch that ledger.

Before a separate **actual** Meta planner can exist:

1. Reconcile official Meta Usage/Billing and get approval for a bounded
   spend envelope; do not reset or bypass existing MetaBudget.
2. Review whether even pseudonymous event IDs and hashes may leave the
   workstation, along with purpose-specific real media consent/revocation
   and retention requirements.
3. Build a distinct, explicitly gated live provider adapter with
   per-source/event deduplication, token budgets, audit logging,
   idempotent retries disabled and a hard kill switch.
4. Bind only verified outputs to an authenticated caregiver session.
   Never let model output authorize camera access, real-person uploads,
   human rights, medical triage, urgent notifications or dispatch.
5. Measure real accuracy, false positives and false negatives on
   independently labeled licensed staged fall and ADL datasets.

Nothing in the current code enables a paid provider, auto-notifications,
remote mobile access, production care workflows, or a validated fall
detection claim.
