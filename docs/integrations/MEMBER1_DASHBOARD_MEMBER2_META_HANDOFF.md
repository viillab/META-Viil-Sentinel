# VIIL-Sentinel — Member 1 Dashboard ↔ Member 2 Meta/Backend Handoff

**28 Oct 2026 · implementation/coordination note · not production approval**

## Ownership and architecture

Member 1 now owns the old Member 3 presentation scope: Dashboard, camera
integration **UI**, Edge AI, visual event inspection, and caregiver UX.
There is **no active Member 3**. Do not develop on the historical member3
branch. Member 2 owns authenticated backend APIs, Meta model adapter,
evidence permissions/storage, service authorization, incidents and delivery.

```text
 Authorized RTSP / USB cameras
         |
 [Member 1 Edge vision workers]  ---> local privacy-validated unconfirmed
         |                           candidate v1 metadata only
         v
 [Member 2 authenticated backend ingestion]
         |             +--- source RBAC / replay dedupe / privacy audit
         |             +--- approved evidence (not direct browser access)
         v
 [Member 2 Meta Model API adapter] ---> verified backend assessment v1
         |
 [Member 2 incident + caregiver delivery backend]
         |
 authenticated same-origin /api JSON projections
         |
 [Member 1 Integration Center + Incident Operations UI]
```

**Do not directly connect React to RTSP, ONVIF, camera admin, FFmpeg,
Meta Model API, or cloud video.** Browser never receives credentials.
Make all evidence operations opt-in, approved and backend-owned. A fall
candidate is not a verified fall, medical result or emergency instruction.

## Implemented UI

- `apps/dashboard/src/IntegrationCenter.tsx`: polished source cards,
  camera privacy status, Edge and Meta connection status, caregiver pipeline
  readiness and sample-only preview; this is now the default workspace.
- `apps/dashboard/src/integrationOverview.ts`: strict metadata-only
  allowlist, schema versioning, bounded response size, stale detection,
  sanitized errors. No outgoing POST and no direct provider calls.
- `apps/dashboard/src/metaReview.ts`: existing fail-closed, read-only
  incident-level Member 2 Meta review DTO projection.
- `apps/dashboard/src/EdgeTestLab.tsx`: browser-local research JSONL.
  No upload, model execution or API calls.
- `apps/dashboard/vite.config.ts`: dev-only same-origin `/api` proxy to
  local `http://127.0.0.1:8000`; real deployments need an authenticated
  HTTPS same-origin reverse proxy.
- Frontend polls at most every 10 seconds while Integration Center is
  visible. Requests have a 7s AbortController timeout. On failed auth,
  malformed data, missing route or stale evidence, the UI **clears**
  previous live status instead of showing obsolete "online" cards.
- Sample Preview is explicit in-memory mock data and NEVER uses the backend
  or claims genuine Meta inference. The default mode does not fabricate
  devices. No real camera has been connected in this implementation.

## Member 2 API to implement (NOT yet available)

Machine-readable cross-team contract: `handoff/team/integration_overview.v1.schema.json`.
Member 2 may use it for response validation; the browser also applies additional
cross-field, freshness, duplicate-ID and provenance checks that JSON Schema
alone does not enforce. The schema file's example namespace is not a deployed URL.

`GET /api/v1/integrations/overview`

- Require authenticated session and permission to list only the current
  operator's camera sources (object-level + function-level authorization).
- Respond `401` unauthenticated and `403` unauthorized, never `200`
  with global organization cameras. Do not accept arbitrary origin URLs.
- `Content-Type: application/json`, `Cache-Control: private, no-store`.
  No credentials, network addresses, video, image URLs, pose landmarks,
  model prompts/responses, email, phone numbers, biometric records,
  raw timestamps identifying people or actual evidence bytes.
- Hard cap response <=32 KiB; max 16 cameras; pseudonymous source IDs.
- `generated_at` and active heartbeats must be **server-derived UTC**
  timestamps. A reported online device must have signed/authorized current
  telemetry and a heartbeat within the prior 30 seconds. Camera privacy
  cannot be "approved" unless it is actually verified on the Edge worker
  and source authorization is scoped to the logged-in operator.
- `access_scope="authenticated_operator"` is a *backend report*, not
  security proof. Auth + RBAC MUST be enforced by Member 2 on the server.
- Meta `state="ready"` requires a genuine authorized `meta_model_api`
  adapter with evidence pipeline ready and a real verified call record.
  Mock output must report `provider="mock", state="not_configured"`
  or a nonready state, never `ready`. A Meta model answer never grants
  permissions, confirms a fall or allows emergency dispatch.
- `notification.state="ready"` means an actual authenticated backend
  delivery component is operational; it does not prove any specific message
  was delivered. Per-incident delivery receipts need their own contract.
- Every backend write/review request needs role and camera-level scope
  checks plus audit events, concurrency checks and rate limiting.

### Example shape (ILLUSTRATIVE ONLY — NOT LIVE EVIDENCE)

```json
{
  "schema_version": "viil.backend.integration_overview.v1",
  "generated_at": "2026-10-28T09:00:00Z",
  "access_scope": "authenticated_operator",
  "edge": {
    "state": "degraded",
    "last_heartbeat_at": "2026-10-28T09:00:00Z"
  },
  "cameras": [
    {
      "camera_id": "zone-a",
      "transport": "rtsp",
      "health": "online",
      "privacy": "approved",
      "last_heartbeat_at": "2026-10-28T09:00:00Z",
      "observed_fps": 12.5
    },
    {
      "camera_id": "operator-usb",
      "transport": "usb",
      "health": "unknown",
      "privacy": "unverified",
      "last_heartbeat_at": null,
      "observed_fps": null
    }
  ],
  "meta": {
    "provider": "mock",
    "state": "not_configured",
    "evidence_pipeline": "not_configured",
    "last_verified_call_at": null
  },
  "notification": {
    "state": "not_configured"
  }
}
```

**Exact allowlisted fields only.** Accepted state values:

- Edge, Meta, Notification: `ready | degraded | offline | not_configured`
- Camera health: `online | degraded | offline | unknown`
- Privacy: `approved | expired | revoked | unverified`
- Camera transport: `rtsp | usb`
- Provider: `meta_model_api | mock | unavailable`
- Evidence pipeline: `ready | blocked | not_configured`

Frontend rejects unknown fields, duplicates, invalid timestamps, infinite
FPS, camera URLs, extra AI keys, fabricated provider readiness, and inconsistent
online/privacy states. A valid envelope is **not** proof of jurisdictional
privacy compliance or the truth of its contents. Member 2 must sign/verify
telemetry, scope every query and avoid trust in client-supplied status.

### Existing incident API / Meta review

The current backend `services/api/app/main.py` still exposes **local demo**
incident routes with no authentication, and the current mock provider. This
integration UI does **not** reconfigure those endpoints or enable them for
public use. Incident creation and review buttons are now **disabled
by default**, unless the developer explicitly sets
`VITE_ENABLE_LOCAL_DEMO_MUTATIONS=true` at build time AND opens the UI
on localhost/127.0.0.1. That opt-in is NOT authentication and must never
be deployed publicly. Keep the backend loopback-bound regardless of UI
button availability. Before deployment Member 2 must own secure auth, RBAC, session
handling, CSRF appropriate to its auth scheme, private-network bindings,
audit/retention and incident source ownership. Refer to
`docs/security/GLOBAL_PRIVACY_SECURITY_BASELINE.md`.

The frontend already validates optional
`meta_review_v1` in `src/metaReview.ts` and will not show real-inference
status for simulated incidents or unverified model payloads. Exact source
must be authenticated, media licensed/consented, backend verified. No
confirmation of real falls, medical diagnosis, emergency dispatch or
automatic caregiver notification is authorized.

## Next integration acceptance checks

1. Member 2 implements **authenticated** read-only overview endpoint,
   tests 401/403/404, role isolation, tenant separation and secret leaks.
2. Member 1 + Member 2 conduct contract tests against the real backend,
   including RTSP connect/disconnect, expired/revoked privacy approvals,
   provider outage and a user with access to only one of multiple cameras.
3. Capture actual synthetic/staged evidence where specifically approved.
   Verify that UI clears stale data, no untrusted content reaches browser,
   no frontend can call Meta directly, and no fake notification counts are
   presented as actual delivery.
4. Independent privacy/security review, threat modeling, key management,
   pentesting and jurisdictional legal signoff before real use.

## Rationale / official sources

- OWASP API Security Top 10 (object- and function-level authorization,
  broken authentication, excessive data exposure):
  https://api-security.owasp.org/editions/2023/en/0x11-t10/
- TanStack Query polling guidance (the current small app uses a minimal
  visibility-aware `fetch` hook instead of introducing a dependency):
  https://tanstack.com/query/latest/docs/framework/react/guides/polling
- MDN Server-Sent Events (optional future transport behind authenticated
  backend; not implemented in this release):
  https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events
