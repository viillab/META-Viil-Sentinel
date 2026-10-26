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
      [Report validation + uncertainty + evidence]
                        |
    [Agent orchestration / notification state machine]
                        |
        [Caregiver review and verification UI]
                        |
           [Human decides next steps]
```

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
- Require signed-off human review before consequential response; never infer medical severity.
- Confidence values in demo are **synthetic**, not measured model calibration.
- Fail closed on invalid model output; display source/provider and uncertainty to users.
