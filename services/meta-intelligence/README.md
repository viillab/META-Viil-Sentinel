# Meta intelligence module — live adapter pending

## Two-member ownership (28 October 2026)

**Member 2** owns this backend Meta integration. **Member 1** owns Edge Vision plus the React Dashboard and Notifications. There is **no active Member 3**. Source: [two-member handoff](../../handoff/team/TEAM_ROLES_AND_META_FIRST.md).

**Meta-first proposed verification:** strict grounded visible-observation JSON, trusted evidence authorization, automatic *informational* in-app caregiver advisory only after verified real provider and conditions pass; unclear/negative/mock/timeouts stay unconfirmed and route to follow-up. Not an automatic medical diagnosis or emergency dispatch. See `services/api/app/meta_first_contract.py` for an *isolated unconnected proposal*, not a live endpoint.

## Responsibilities
- Confirm current official Meta Model API model/endpoint/vision request schemas.
- Authorize and minimize keyframes (do not transmit unauthorized sensitive imagery).
- Prompt for factual visible observations and uncertainty, **not diagnosis or triage**.
- Validate schema and evidence references, reject unsupported claims and malformed responses.
- Provide retry/backoff, timeout, cost/quota guards and result provenance.

The current `services/api/app/meta.py` defines a Protocol and Mock interpreter. Real Muse Spark calls are **not** made by the foundation. Meta Model API current documentation offers Muse Spark (`muse-spark-1.3`) multimodal image understanding with schema-constrained `response_format`, but Member 2 must verify access, billing, consent, token/image budgets and actual endpoint before any real invocation. Prefer **Standard mode** for consented evidence; Contributor mode may permit use of provided content for training. Docs: https://dev.meta.ai/docs/models and https://dev.meta.ai/docs/structured-output and https://dev.meta.ai/docs/pricing-rate-limits. A working live adapter and verified test must be added prior to any claim of Meta integration.
