# VIIL-Sentinel — Demo-first development plan (2026-11-01)

**Scope:** Meta Global AI Developer Hackathon 2026, two-member team. This is a staged, consented, informational prototype, **not** a clinical fall detector. All release claims require independent evidence.

**Current verified baseline:** Member 1 browser-only MediaPipe webcam preview and unconfirmed torso-motion candidate, strict offline `viil.edge.candidate.v1` producer, dashboard and FastAPI mock backend. Member 2's authenticated candidate intake, real Meta provider, persistent delivery and actual caregiver notifications are **not verified**. Team integration: `member/feature/preprod`; never change shared `preprod` or human-owned `main`.

## Priorities and proof gates

| Priority | Owner | Implementation | Required acceptance evidence |
| --- | --- | --- | --- |
| P0 | Member 1 | Laptop Webcam: frozen-frame protection, bounded rolling processed FPS, inference p50/p95 and single-pose coverage; prevent model replacement during capture | Dashboard contract tests + TypeScript/Vite build; user-approved 60-second browser webcam smoke, video/pose counters move, stop releases tracks |
| P0 | Member 1 | Real Edge field-readiness + candidate v1 handoff; do not mix browser heuristic with Python research models | `python -m sentinel_edge.handoff_preflight`; synthetic fall 1/unconfirmed and sitting 0; explicit schema validation |
| P0 | Member 2 | Authenticated, registered-source, replay-safe `viil.edge.candidate.v1` ingestion; idempotent incident store | Negative tests for invalid schema, unauthorized source, replay/duplicate, oversized payload; 401/403/fail-closed without exposing raw frames |
| P0 | Member 2 | Real authorized Meta evidence adapter, with independent keyframe approvals and hard spending/time budgets | Verified official endpoint/provider and staged-image authorization, schema-grounded output tests, no fabricated live provider claim |
| P1 | Both | End-to-end candidate → evidence gate → Meta review → informational caregiver view → human acknowledgement | Authorized on-device full integration smoke, secure event lineage, explicit MOCK/PENDING separation and no automatic rescue action |
| P1 | Member 1 | Subject-disjoint fall/no-fall evaluation, false alarms per annotated hour, measured CPU/RAM and latency | Source/provenance pinned, true negative coverage, uncertainty and abstention reported, no inflated accuracy |
| P1 | Both | Judge walkthrough, signed-off demo video, README and public release/privacy audit | Three-minute reproducible staged narrative, public code reviewed for secrets/rights, no PII or proprietary models; manual owner promotion |

## Recommended execution sequence

1. Finish Member 1 on-device diagnostics and tests **without any backend transport**. Demonstrate a pose model file loaded by explicit browser File selection, local camera consent, and accurate on-screen runtime counters. Stop/refresh/visibility-change must release the device and model.
2. Member 2 independently implement the authenticated intake contract and tests in `member2/feature/*`. Member 1 must not bypass privacy gates or post browser frames to the existing `/api/v1/incidents/demo` mock.
3. Run an **approved**, opt-in staged integration with the signed/privacy-gated Python Edge producer, strict v1 intake, real evidence authorization and Meta evaluation; report missing stages rather than mocking them silently.
4. Run supervised physical-camera acceptance: 60-second local browser smoke, then 30-minute authorized Edge endurance. Record observed frame processing FPS, inference p50/p95, CPU/RAM and source-specific failure rates. Never claim model recall based solely on synthetic examples.
5. Freeze an honest 3-minute demo and review consent, dependency licenses, Git history and competition rules before the human promotes to shared `preprod` and `main`.

## Definition of done

- **Software demo:** operator can manually start/stop a local webcam, see real pose overlays and unconfirmed fall-candidate diagnostics, with no auto upload; backend mock pathways clearly labelled.
- **Integration:** Member 2 confirms schema-safe authenticated ingestion and independently validates authorized Meta evidence before any advisory. It is **not done** merely because UI and contract tests pass.
- **Research validity:** externally labeled falls and ADL clips have independent provenance, subject-held-out metrics, negative controls and documented limitations. Unknown pose must never be interpreted as proof of safety.
- **Submission:** all actual claims backed by recordings/measurements on permitted media, no real-patient monitoring, no automatic emergency dispatch, no secrets/private frames in public Git.

**Deadline:** Repository README lists 5 Nov 2026, 09:00 ICT, with internal target 4 Nov 2026, 21:00 ICT. Verify organizer announcements before final submission.
