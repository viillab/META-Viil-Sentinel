# Member 1 — Accessible Caregiver Inbox / Member 2 Integration

**2026-10-28. Implementation readiness only. NOT a real notification system,
medical device, fall accuracy proof, or WCAG certification.**

## What was added

- `apps/dashboard/src/CaregiverInboxView.tsx`: caregiver-facing read-only inbox,
  unconfirmed incident context, backend-reported review/delivery status.
- `apps/dashboard/src/caregiverInbox.ts`: strict 32-KiB, 30-item, metadata-only
  allowlisted DTO validation; no raw media, person identity, camera URL, API key,
  model-generated instructions, medical diagnosis or emergency dispatch.
- `apps/dashboard/src/caregiver.css`: responsive UI with explicit high-contrast,
  larger text/controls, keyboard-focus styling, and system reduced-motion.
  Page navigation includes a skip-to-content link; nonurgent status changes
  use polite live regions rather than disruptive blocking alerts.
- `apps/dashboard/tests/caregiverInbox.test.mjs`: hostile payload, provenance,
  delivery-receipt, auth, stale data, response cap, and same-origin tests.
- `handoff/team/caregiver_inbox.v1.schema.json`: shared JSON Schema.
- A voluntary **SAMPLE ONLY** preview with two purely fictional scenarios
  (wheelchair transfer and rapid posture change). Neither sends a message,
  accesses a camera, calls Meta, nor posts any state change.

### This is not a confirmed fall or actual delivery

An Edge uncalibrated candidate does not prove a fall. Meta first-pass evidence
may provide an informational advisory but cannot confirm a fall, diagnose,
authorize medical triage or initiate emergency dispatch. The browser never
calls Meta directly and never turns a user click/view into a backend
acknowledgment. No sound, vibration, Push API, desktop notification or SMS
is activated. Underlying incident records/delivery receipts must be
authorized, durable and verified by Member 2.

The UI **does not poll** the proposed endpoint when another tab is selected
or when displaying the explicitly marked sample. It polls at most every
10 seconds in the visible caregiver view, with 7-second timeout and
abort-on-hidden behavior. On any 401/403, invalid data, stale response,
missing route or loss of access it clears the previous advisory list rather
than preserving old "online"/delivered claims. Snapshot validity window
is 30 seconds (plus limited future-skew tolerance). An empty inbox or
offline state is **not** proof that no fall occurred.

## Proposed Member 2 endpoint (NOT implemented in this release)

`GET /api/v1/caregiver/inbox`, same-origin, JSON,
`Cache-Control: private, no-store`, authenticated caregiver access
and fine-grained organization/tenant + **camera-level** authorization.

Never return global/other-tenant cameras. Enforce authentication
and per-object authorization **server-side**; client-provided
`access_scope` is just a schema marker, not authentication proof.
Use minimal source IDs (not addresses, names, room numbers, URLs),
no personal identity, media links, arbitrary AI prose or PII.

Limits: response <=32 KiB, max 30 records, unique incident/advisory UUID,
UTC timestamps, backend-generated `generated_at`, no stale auth or
replay. Support HTTP 401/403 for denied sessions. Avoid redirects
from the endpoint. Apply rate limits and security headers.

### Fields (see canonical shared JSON Schema)

```json
{
  "schema_version": "viil.backend.caregiver_inbox.v1",
  "generated_at": "2026-10-28T09:00:10Z",
  "access_scope": "authenticated_caregiver",
  "advisories": [{
    "advisory_id": "edf0468f-c0ec-47ab-a10c-ddfef3d4966e",
    "source_id": "demo-zone",
    "occurred_at": "2026-10-28T09:00:00Z",
    "stage": "follow_up_required",
    "context_code": "unknown",
    "meta_provenance": "mock",
    "delivery_state": "not_sent",
    "receipt_verified": false,
    "review_state": "pending",
    "simulated": true,
    "fall_confirmed": false,
    "emergency_dispatch_authorized": false,
    "human_follow_up_required": true
  }]
}
```

**Sample only; no real Meta call or sent alert.** Enum values:
- stage: edge_candidate | follow_up_required | informational_advisory
- context_code: unknown | near_floor | wheelchair_transfer | rapid_descent
- meta_provenance: none | mock | meta_model_api
- delivery_state: not_sent | pending | delivered | failed
- review_state: pending | acknowledged | closed

`informational_advisory` requires actual provider provenance reported
by backend, non-simulated input and appropriate independent authorization
checks. No direct Meta JSON may populate `meta_provenance`, delivery,
acknowledgement or privacy flags. `delivered` requires a verified
server-side receipt. The frontend checks field and state consistency but
**cannot independently prove backend assertions**. Unauthorized sources
and stale data must be rejected on the server.

To enable real actions **in a later Member 2 project**, design audited
idempotent PATCH/POST endpoints with CSRF protection where needed,
accessibility-tested confirmation, source-level scope and review-state
transitions. This Member 1 release does not supply such actions.

## Validation / human review still required

- Test with actual screen-reader and keyboard users, including people with
  visual, hearing, motor or cognitive accessibility requirements.
- Evaluate against WCAG 2.2 AA, including focus order, status messages,
  readable text, contrast, target sizes and keyboard usability.
- Real caregiver user testing, delivery failure/retry workflow, full-cycle
  acknowledgement and escalation policies; avoid alarm overload.
- Battery, audio/haptic and device notification delivery are future opt-in
  client capabilities requiring permission and separate tests.
- Verify that a real person has alternate ways to call for help when
  cameras, network, Meta or backend fail; no reliance on this prototype.

Official guidance:
- W3C WCAG 2.2: https://www.w3.org/TR/WCAG22/
- W3C status messages: https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html
- OWASP API Top 10: https://owasp.org/API-Security/editions/2023/en/0x11-t10/
