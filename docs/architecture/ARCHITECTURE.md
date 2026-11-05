# VIIL Sentinel — Component architecture and trust boundaries

```text
            Webcam or authorised staged video
                        |
      [Edge Vision: pose + temporal fall candidate]
                        |
         [Event + selected consented keyframes]
                        |
        [Meta Model API: scene observations]
                        |
      [Meta-first verified evidence (TARGET)]
      [Report validation + uncertainty + evidence]
                        |
    [Agent orchestration / notification state machine]
                        |
        [Caregiver review and verification UI]
                        |
          [Caregiver aware / override]
          [No emergency dispatch]
```

## Current Member 1 handoff and safe trust boundary (28 Oct 2026)

The canonical, tested integration entrypoint is
[handoff/member1/README.md](../../handoff/member1/README.md). Original
heuristic emits only strict `viil.edge.candidate.v1` **LOCAL stdout**
metadata for a FUTURE authenticated Member 2 ingest. The separate
1500ms research classifier, its private 30D weight JSON and the
1500ms streaming Shadow are NOT routed to FastAPI or caregiver alerts.
Member 1 owns the caregiver Dashboard and Notifications (there is **no Member 3**). The Dashboard consumes only backend-reviewed incident state, not raw model
scores, source video or PoseFrames. Full production ingestion/auth/Meta
provider and real notifications remain incomplete, and no one may
reinterpret unreviewed publisher clip labels as real fall event accuracy.

## Current baseline (new hackathon code)
- FastAPI owns typed incident schemas, in-memory repository and state-transition policy.
- `IncidentService` runs a strictly simulated event and produces a mock-labelled report.
- Caregiver dashboard fetches the local incident feed, displays explanations, and submits named human actions.
- The orchestrator enforces transitions; it cannot dispatch real emergency services.
- API endpoints are local-only / unauthenticated development routes. NEVER expose the development server on the internet.

## Future interfaces
- **Edge Vision**: video source adapter, pose observations, temporal classifier, timestamped candidate events and keyframe references; rights-cleared models only.
- **Meta Intelligence**: frame/data authorization gate, quota guards, request timeout/retries, structured output validation, evidence-grounding review, no diagnostics.
- **Storage**: real Postgres repository, migrations, per-incident idempotency and history.
- **Security**: authenticated caregivers, scoped authorization, incident retention controls and privacy review.
- **Notification**: durable delivery / acknowledgments and retries; no EMS integration.
- **Evaluation**: staged fall vs non-fall, detection latency, F1, report grounding, unsupported claims, notification workflow success.

## Privacy / reliability constraints
- PII-minimized keyframes only; never send raw continuous footage without consent/authorization.
- Meta free-credit terms may permit product improvement using submitted content. Staged footage recommended.
- **Target:** Meta may replace manual screening for an informational in-app caregiver advisory only after real authorized vision evidence, strict JSON/evidence validation and independent evaluation; ambiguous cases need follow-up. Consequential actions always require human control. Never infer medical severity.
- Confidence values in demo are **synthetic**, not measured model calibration.
- Fail closed on invalid model output; display source/provider and uncertainty to users.
