# Agent orchestration and notification workflow

Current backend code: `services/api/app/agent.py` and `service.py`.

- Explicit state machine for DETECTED → ANALYZING → REVIEW_REQUIRED → NOTIFIED → ACKNOWLEDGED → VERIFIED/FALSE_ALERT → RESOLVED.
- A named human reviewer must choose actions; invalid transitions receive HTTP 409.
- Simulation records a notification in the in-app feed only; no real SMS/email/emergency dispatch.
- No hidden automatic escalation or medical advice.

For real operations, add persistent events, authentication, idempotency, durable retries and external incident notification delivery (only authorized caregivers).
