# VIIL-Sentinel — Meta Copilot Control Plane v1

**Member 2 | 2026-11-02 | prototype | guarded OFFLINE shadow mode**

## Goal

Let Muse Spark eventually **assist with incident work**, not merely produce
one visual label. The system must remain safe when the model is wrong,
hallucinates, is prompt-injected, requests an unauthorized tool, or is
unavailable. Meta **plans and explains**; the backend **authenticates, verifies
evidence, enforces policy, controls spending and owns all durable state**;
the human caregiver **reviews any suspected fall**.

Actual Meta Model API multimodal calls have been proven on **synthetic flat
PNGs** in the earlier live test. The new Copilot does **not** reuse or spend
those calls; the local Meta trial is currently exhausted at **4/4**. This
feature does **not** pretend the model has analyzed a real person.

## Implemented backend roles

```text
Member 1 temporal Edge detector -> signed synthetic candidate -> SQLite
   -> event-bound synthetic evidence registry + verified audit chain
   -> independently HMAC-signed audit checkpoint
   -> Meta Copilot preview read-only gate
      ├─ check_event_linkage          (verified metadata check)
      ├─ verify_audit_integrity       (signed checkpoint check)
      └─ prepare_caregiver_handoff    (nonbinding next-steps draft)
   -> validated human follow-up UI metadata; NO mutation/dispatch
```

The new server-only endpoint is:

```text
GET /api/v1/caregiver/copilot/{event_id}
```

It is **off by default**. When explicitly enabled, it requires all of:
`META_COPILOT_PREVIEW_ENABLED=true`,
`EVIDENCE_REGISTRY_ENABLED=true`,
`EVIDENCE_AUDIT_ANCHOR_REQUIRED=true`, a **valid independently signed
checkpoint**, the existing independent 32+-byte Caregiver Bearer token,
and an actual loopback client. It never trusts `Host` or
`X-Forwarded-For` claims as proof of local identity. Only the pinned,
fictional source `synthetic-clip-01` can produce an eligible case.

The response is strictly typed as `viil.meta.copilot.preview.v1` and
`Cache-Control: no-store`. It returns only synthetic source UUID,
canonical evidence hashes, verified audit hash, allowlisted work items,
fixed safe summary/follow-up codes, and explicit:

```json
{
  "mode": "offline_readonly_shadow",
  "meta_api_called": false,
  "meta_inference_performed": false,
  "model_has_executed_tools": false,
  "simulated": true,
  "evidence_verified": true,
  "independent_audit_anchor_verified": true,
  "human_review_required": true,
  "fall_confirmed": false,
  "notification_sent": false,
  "emergency_dispatch_authorized": false,
  "real_media_upload_authorized": false,
  "persistent_mutation_performed": false
}
```

The code enforces these safety flags with Pydantic `Literal` fields.
They cannot be switched by model output or an HTTP request.

## Meta's prospective job: strictly typed tool planning

`app.meta_copilot` contains a **future** Muse Spark Structured Output
contract, `viil.meta.copilot.proposal.v1`. Its allowed plan contains
only three exact tools, each once, for the same event UUID:

| Tool | Backend responsibility | Authorized effect |
| --- | --- | --- |
| `check_event_linkage` | Compare signed candidate receipt and validated synthetic Manifest | Read-only verified status |
| `verify_audit_integrity` | Validate the entire SHA-256 chain against independent HMAC checkpoint | Read-only integrity status |
| `prepare_caregiver_handoff` | Build a fixed nonbinding, human-review follow-up draft | No state change, no delivery |

`validate_meta_proposal()` rejects unknown commands such as
`run_shell`, `notify_emergency`, `grant_consent`, `send_to_meta`,
any extra JSON field, missing required tool, reused tool, cross-event UUID,
nonfinite JSON, oversized output, duplicate keys or tool arguments.
The model cannot supply SQL, endpoints, OS commands, arbitrary tool
parameters, identity claims, risk scores, or medical severity.

`build_offline_meta_planner_request()` prepares a JSON Schema-constrained
Muse Spark 1.3 Chat Completions payload with `reasoning_effort=minimal`
and `max_completion_tokens=512`, but **does not send it or call Meta**.
The planned input consists of the pinned synthetic event UUID, hash IDs,
relative event time and verified audit indicators: no image, person data,
API key, caregiver token, or camera endpoint is included.

A later, **separately authorized** live planner would have to validate the
provider, enforce the existing persistent spend ledger, accept only strict
JSON, and submit the proposed task list to this local allowlist. No code
in this increment enables such a paid planner or new budget.

## Design for getting the most out of Meta without wasting credits

A recommended *future* progression after real-media authorization:

1. **Edge-first prefilter:** run local temporal fall heuristics; don't call
   a paid model on every video frame or repeated event UUID.
2. **Consent + evidence gate:** verify site/device/subject authorization,
   retention and revocation, wall-clock alignment, signed keyframes and
   image hashes before sending any media.
3. **One grounded multimodal Muse Spark pass per eligible event:** request
   scene description, uncertainty, and frame-index references in strict
   Structured JSON; use sparse evidence frames rather than continuous
   stream uploads. Never treat visible model text as a source of rights.
4. **Meta Copilot planning:** allow Muse Spark to suggest from a tiny
   read-only task vocabulary. The backend validates every result and
   performs only the approved queries.
5. **Human safety review:** hand a clearly labeled, uncertainty-aware
   draft to a caregiver through real user RBAC, not automatic medical
   escalation or emergency dispatch.
6. **Cost/quality operations:** deduplicate by event, cache only
   authorized safe summaries, cap tokens and image count, instrument
   latency, false positives/negatives, human overrides and per-provider
   actual billing. Disable paid calls by default and stop at the spending
   threshold.

Muse Spark supports Structured Output, tool calling, reasoning control,
image understanding, and prompt caching; these capabilities can be combined
in a reviewed later phase. They are **not all deployed here**, and model
support alone does not authorize camera access or data transmission.

Official docs:
- https://dev.meta.ai/docs/overview
- https://dev.meta.ai/docs/structured-output
- https://dev.meta.ai/docs/tool-calling
- https://dev.meta.ai/docs/reasoning
- https://dev.meta.ai/docs/prompt-caching

## Try the real offline localhost integration

From `D:\VIIL-Sentinel\services\api`:

```powershell
.\.venv\Scripts\python.exe -m app.synthetic_evidence_smoke
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Expected: `SYNTHETIC_EVENT_BOUND_EVIDENCE_PASS` with
`meta_copilot_offline_preview_verified_over_http=true`,
`meta_copilot_workplan_tasks=3`,
`meta_copilot_no_anchor_rejected=true`, and
`meta_copilot_corrupt_anchor_rejected=true`.

The smoke starts a temporary **real localhost TCP** server with random
fake secrets, runs the real Member 1 synthetic Edge detector, signs and
ingests the event, registers its deterministic evidence and audit, shows
503 before anchor capture, captures a separate signed checkpoint,
reads the Copilot preview successfully, damages the checkpoint and
requires HTTP 503 from Copilot. It then shuts down the listener and
deletes all temporary artifacts.

## Provider-envelope dry-run validated

A follow-on [Meta Copilot Provider Contract](META_COPILOT_PROVIDER_CONTRACT.md)
now uses the **actual Chat Completions request shape** and processes a
strict Structured JSON response through a **mock-only HTTP transport**.
The same three allowlisted tools are checked again after the response and
a separate signed audit checkpoint is reverified. There is **no live
model inference or billable Meta request** in this path, and no change
to the local 4/4 budget cap. New tests reject provider failures, unsafe
tools, malformed/duplicate JSON, cross-event proposals and mid-request
anchor changes. The simulated provider result is intentionally labeled
`provider_response_simulated=true` and `meta_api_called=false`.

## Repeat-call protection and Meta readiness (shadow only)

The next [Shadow Dedup & Readiness milestone](META_COPILOT_SHADOW_DEDUP_V1.md)
stores per-event mock-run reservations and safe results in a **separate
private SQLite** file to prevent accidental duplicate mock requests.
Concurrent calls for the same event are serialized, failed attempts are
not retried automatically, and cache reads still require independently
anchored evidence. A new authenticated local read-only readiness endpoint
shows that **paid Meta is disallowed** and observes, without spending,
the existing local Meta test budget. This is not a real-provider adapter.

## Explicit exclusions and next work

- This is **NOT a live Meta-driven autonomous agent**. The current tasks
  are deterministic backend operations in an offline, labelled preview.
  The strict Muse Spark request and plan parser are preparation only.
- This is **NOT a real camera consent approval, fall classifier,
  clinical decision, emergency service, caregiver account login,
  notification service, or remote mobile API**.
- The local synthetic ledger is not guaranteed tamperproof against a
  principal who controls the signing key and independent checkpoint.
- The caregiver static Bearer token is server-side only and **must never
  be embedded in Flutter or Browser bundles**.
- The earlier four Meta Model API trial requests exhausted the *local*
  budget guard. **Never reset** `data/private/meta_spend.sqlite3` to
  force more attempts. The reserved ~$0.514148 is **not** Meta Billing
  and does not establish how much of the team's $150 credit remains.

To activate **actual** Meta-driven planning later, review official
Usage/Billing, authorize a new *bounded* spend plan, perform privacy and
real-source approval, implement a separately reviewed live planner
adapter and run labeled performance evaluations. Keep the model read-only
until verified end-to-end acceptance criteria are met.
