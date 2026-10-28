# VIIL-Sentinel — 2-Member ownership & Meta-first review design

**Updated 28 Oct 2026. Exactly two active team members.** No Member 3.

## Owners

| Person | Implementation ownership | Branch |
|---|---|---|
| Member 1 | Edge Vision, pose inference, trained research fall model, accuracy / performance, React Dashboard, UI, caregiver in-app notifications and frontend integration | `member1/feature/*` |
| Member 2 | FastAPI, Meta Model API, AI evidence assessment, controlled orchestration, database, authentication, device registry, event idempotency | `member2/feature/*` |

Validated Member1 work may be merged into `member/feature/preprod` after CI.
The human maintainer alone promotes shared `preprod` and `main`.

## Lecturer's suggestion: Meta can replace routine HUMAN event screening

**Proposed target: automatic FIRST-PASS evidence assessment, not an autonomous
medical or emergency response.** The current API runs Mock Meta observations.
Do not portray a demo as live Meta inference.

1. Edge on the authorized device produces an **unconfirmed** candidate v1
   with strict schema, simulation flag, monotonic source-time, source binding.
   The 1500ms linear research Shadow remains isolated; it is NOT an alert source.
2. Member 2 checks device authentication and consent/privacy permissions.
   Rate-limits and deduplicates candidates and selects **2–5 permitted
   keyframes** from the candidate window. No continuous CCTV, identity, or
   uncontrolled external file URLs.
3. Only after verifying the real current Meta Model API contract/authorization,
   Member 2 sends permitted images and neutral instructions to a supported
   **Meta vision** model; include budget, timeouts, provider error handling
   and proof of which exact model served the request.
4. Request strict JSON Schema fields: `verdict` =
   `fall_likely | not_fall | uncertain`,
   `visible_observations[]`, `uncertainties[]`,
   `supporting_frame_indices[]` (not freeform medical/EMS commands).
   Local server validates output against strict types and the actual
   trusted evidence context, not the AI's claims about authorization.
5. An evidence-grounded **fall_likely** result from **real** authorized
   Meta API MAY propose an **automatic informational in-app caregiver
   advisory** after privacy/integration testing; this is NOT confirmed
   fall, clinical advice, or automatic emergency response. A person can
   acknowledge, dispute, and review that alert as needed.
6. `uncertain`, `not_fall`, unavailable provider, MOCK, invalid schema,
   missing/ambiguous evidence or consent: log as unconfirmed and route to
   follow-up (or additional evidence); **do not silently suppress an Edge
   candidate** solely on the basis of a generative model. Never infer
   medical severity or send ambulances.
7. Before enabling any true automation, test **sensitivity, missing
   falls/false negatives, false alarms per no-fall hour**, pose abstention,
   latency, token/image costs, data retention and camera/subject splits.

## Current code status

- Existing `services/api/app/meta.py`: **MOCK only**; no real Meta key or
  live provider. Existing `app.service`/human review API remains unchanged.
- New isolated `services/api/app/meta_first_contract.py`: Strict
  versioned *proposal* of model-generated visible observations, server
  trusted consent/source/evidence gate, and deterministic advisory-vs-
  follow-up routing (no I/O, no notification, no API, no incident state
  mutation). Member 2 must integrate and test it using real authorized
  Meta evidence; this is NOT a deployed Meta-first system.
- Existing Dashboard is in `apps/dashboard`; Member 1 now owns it,
  including notification presentation and accessible review/ack UX.
- Member1 model handoff:
  [README](../member1/README.md) and
  [verified Google Drive folder](https://drive.google.com/drive/folders/1k2SM7CdbJTjWDR5DetrAUuPg2umOG_tK).

## Confirmed Meta documentation (access and price still require checking)

- Model catalog: https://dev.meta.ai/docs/models
- Image inputs/allowed formats: https://dev.meta.ai/docs/image-understanding
- Structured JSON output: https://dev.meta.ai/docs/structured-output
- API examples show `https://api.meta.ai/v1` and JSON-schema constrained
  chat completions for `muse-spark-1.3`; **actual model entitlement,
  key, rate limits and product terms must be verified by Member 2**
  before connecting or charging credits.

## UI language

Display `META VERIFICATION: PENDING / MOCK / EVIDENCE INSUFFICIENT /
ADVISORY` as applicable; NEVER display "Confirmed fall" from generative
vision alone. Replace labels that say "Member 3 owns Dashboard" with
"Member 1 owns Dashboard." Manual controls are fallback/acknowledgement,
not a required approval for every low-impact automated advisory.
