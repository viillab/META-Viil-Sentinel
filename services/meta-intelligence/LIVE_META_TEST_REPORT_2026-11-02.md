# VIIL-Sentinel — Meta Model API REAL Test Report

**Date:** 2026-11-02
**Member:** 2 (Backend & Meta Intelligence)
**Mode:** Muse Spark 1.3 **Standard**, synthetic-only, backend-owned key
**Status:** Live structured vision API **VERIFIED**; local synthetic
Edge→Backend→Meta probe→Inbox integration **VERIFIED**.
**NOT VERIFIED:** Real fall-recognition accuracy, real camera evidence,
consent, human identity/RBAC, mobile/backend auth, real notifications.

## Tests that really reached Meta

Two additional API requests were explicitly authorized to evaluate the
previous 2-call test failure. Both received live HTTP responses **and**
passed strict Pydantic JSON assessment validation after setting:

```json
{"model":"muse-spark-1.3","reasoning_effort":"minimal","max_completion_tokens":1024}
```

| Local call # | Test | Meta result | Input tokens | Output tokens | Approx. token charge* |
| --- | --- | --- | ---: | ---: | ---: |
| 1 | Original flat PNG | Local safety validation failed | unknown | unknown | Meta Billing required |
| 2 | Original flat PNG | Incomplete, token-capped output | unknown | unknown | Meta Billing required |
| 3 | Flat PNG + strict schema + minimal reasoning | **Validated**, verdict `uncertain`, route `require_follow_up` | 233 | 163 | ~$0.000984 |
| 4 | Actual synthetic Edge candidate → signed local HTTP Backend → real Meta probe → read-only Inbox | **Validated**, verdict `uncertain`, route `require_follow_up` | 233 | 234 | ~$0.001286 |

*Token cost estimates use Meta's published Standard rates as of 2026-11-02
($1.25/M input; $4.25/M output, treating all input as uncached). These are
**estimates**, not statements or exports from the team's Meta billing.
The two validated calls together estimate ~$0.002270 in token use. Billing
for calls #1–2 and the team's actual $150 credit usage is **not verified**.

### What the integrated live test actually did

```text
Member 1 Python Edge detector on pinned fictional pose traces
    -> synthetic FALL_CANDIDATE (850 ms source-relative, heuristic 0.928)
    -> signed HTTP POST to FastAPI on ephemeral 127.0.0.1
    -> SQLite durable event receipt, no duplicate, no real camera
    -> a separate generated 64×64 uniform-color PNG to Meta Model API
    -> strict MetaVisibleAssessment validated from real Meta reply
    -> untrusted/ungrounded evidence -> REQUIRE_FOLLOW_UP
    -> read-only caregiver inbox still shows synthetic edge_candidate only
    -> local TCP server shuts down, temporary SQLite deleted
```

**Critical:** The PNG sent to Meta is **NOT** an image extracted from the
Edge candidate. It intentionally contains no person, no movement, and
no real fall evidence. The real Meta output therefore MUST NOT be called
a fall classification or a camera-alert decision. A correct `uncertain`
verdict verifies the interface and conservative routing, not accuracy.

## Actual bugs discovered / fixes

1. **Output truncation:** Muse Spark uses hidden reasoning tokens which
   count against `max_completion_tokens`. Earlier runs omitted
   `reasoning_effort`. Set `reasoning_effort="minimal"` for simple
   synthetic visual contract tests; preserve 1024 total output tokens.
2. **False grounding risk:** Even an apparently valid structured response
   could claim `supporting_frame_indices=[0]` despite the flat PNG not
   containing any temporal evidence. The synthetic adapter now rejects
   **all non-empty supporting indices**, keeping the verdict untrusted.
3. **No provider retry storm:** Every real call permanently reserves a
   bounded allowance in the shared local SQLite ledger **before** sending.
   Network timeout or malformed output never refunds it; there is no
   automatic retry, and no frontend route can trigger the Meta provider.
4. **Insufficient integration evidence:** Previous tests used in-process
   MockTransport or TestClient, while the new live test uses real TCP to
   local FastAPI and a real outbound call to Meta. Only the Meta synthetic
   probe, **not real Edge frames**, leaves the workstation.

## Safety budget, guard and shutdown

The original budget was **2 local calls**, **$0.50** cap. Following
specific user approval, an **explicit** option permits up to **4
cumulative calls** and **$0.75 cumulative local conservative reservations**.
Default application and old `--live-once` path are still gated at 2/0.50.

Confirmed final local ledger after call #4:
- **4 / 4 attempts**; no further live requests permitted even with approval
- **$0.514148 reserved** from all four requests (including failures)
- These reservations are **NOT** actual charges, not the team's total
  balance, and not a Meta Billing spending limit.
- No key was placed in CLI arguments, source control, mobile apps or
  browser scripts; `services/api/.env` remains ignored.

The total experiment used TWO new network calls. **Do not reset or raise**
the local budget without a separate review of Meta Billing, user approval
and an explicit new test plan. Rotate the previously pasted Meta API key
using Meta's official key-management UI.

## Reproduction (defaults are offline and do not spend)

From `D:\VIIL-Sentinel\services\api`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m app.meta_live_probe --approve-two-extra-tests
.\.venv\Scripts\python.exe -m app.meta_system_live_demo
```

The two last commands are offline without `--live-once`.
Adding `--live-once --approve-two-extra-tests` requires intentional paid
network access **and is now rejected** because all 4 local calls are used.

## Priority improvements before testing real people

1. **Independent privacy/consent and evidence registry:** signed staged
   source approval, ownership/retention, per-camera identities, hashes,
   opt-out and visibility controls. Never treat a camera's claimed consent
   field as proof of authorization.
2. **Actual temporal fall visual evidence:** develop an explicitly
   authorized, reviewed, non-clinical staged fall + ADL dataset, with
   video frames tied cryptographically to the Edge event and trusted
   relative-to-UTC timing. Test blind negative controls and misses.
3. **Model output grounding / safety evaluation:** record sanitized
   uncertainty, detect contradictions and hallucinations, verify frame
   support, compare to independently labeled ground truth, and measure
   latency and false alerts before enabling low-impact advisories.
4. **Real auth and durable workflow:** session-based caregiver RBAC,
   authenticated incident reads, source-scoped event intake, approved
   push/in-app outbox and acknowledgments, audit trails and retention.
5. **Cost operations:** review Meta developer Billing for exact usage and
   credit balance. Configure provider-side spend alerts/limits when
   supported; local SQLite only protects this workstation.

Official docs:
- https://dev.meta.ai/docs/pricing-rate-limits
- https://dev.meta.ai/docs/reasoning
- https://dev.meta.ai/docs/structured-output
- https://dev.meta.ai/docs/image-understanding
