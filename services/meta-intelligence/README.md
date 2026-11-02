# Meta Model API — Member 2 takeover (2 Nov 2026)

## Verified scope / current result

- A backend-only Meta Model API Chat Completions adapter exists at `services/api/app/meta_live.py`.
- Model: **`muse-spark-1.3` Standard mode**, not contributor. Official origin is fixed to
  `https://api.meta.ai/v1/chat/completions`. No web search, SDK telemetry,
  browser secret, redirects, automatic retries, file uploads, or real-person images.
- Initial probe accepts **only a generated 64x64 synthetic flat-color PNG**.
  The strict `MetaVisibleAssessment` output never authorizes a fall confirmation,
  medical triage, caregiver alert, or emergency dispatch.
- API `/api/v1/incidents/demo` remains MOCK; **no Meta call is triggered by UI or incident creation**.
  This separation deliberately avoids accidental spend and false real-inference claims.
- **Two live Meta HTTP responses were received on 2026-11-02**, but the guarded
  end-to-end assessment was **not verified**: first output did not pass local
  validation; the second was incomplete/token-capped. Do not claim live
  multimodal structured inference works end-to-end yet.
- No real camera pixels or private/person/patient evidence was transmitted.

## Budget, billing and safeguarding $150

Meta's published Standard Muse Spark rates on 2026-11-02:
**$1.25 per million input tokens**, **$4.25 per million output tokens**,
plus $0.15/M cached input if applicable. The chosen model is **NOT** the
Contributor model, since that mode permits submitted content to train Meta models.

The local `MetaBudget` uses a gitignored SQLite file at
`data/private/meta_spend.sqlite3`. A SQLite transaction reserves an
intentionally conservative per-request allowance **before** network I/O.
The process allows at most **2 attempts** and **$0.50 reserved locally**;
there is no refund on timeout, errors or malformed output, and no retry.
The tests used fake keys/transports (no spend).

On this workstation **both attempts have been used**. The estimated
conservative reservations total approximately **$0.255442** (the first
reserved $0.126089 and the second $0.129353). These are NOT actual Meta
charges; inspect the team's Meta Usage/Billing dashboard to get actual
consumption. The local reservation is not an account-wide or team-wide
budget cap; other keys/teams/processes and pricing changes can still spend
the separate $150 allowance. Do NOT remove/reset the ledger casually.
Set team spend limits/alerts in Meta billing where available.

## Set up safely

Put the key in `services/api/.env` (Git explicitly ignores `.env`):

```dotenv
META_PROVIDER=mock
META_LIVE_ENABLED=false
META_MODEL_ID=muse-spark-1.3
META_MODEL_API_KEY=YOUR_PRIVATE_META_MODEL_API_KEY
```

Keep the key server-side. Do not paste it into a public issue, git commit,
browser JavaScript, mobile APK, slides, test fixture, or shell arguments.
Rotate this key in Meta's developer dashboard after sharing it in chat.
Do not commit real screenshots or private image datasets.

From `services/api`:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m app.meta_live_probe
```

`app.meta_live_probe` **without arguments is completely offline**: it
validates request construction, shows the local reserved budget/call count,
and never transmits the key or an image. The `--live-once` option is
only for an explicitly approved live synthetic test. It remains blocked
on this workstation because the 2-call ledger is exhausted.

## Remaining critical work (not shipped as working)

1. Inspect actual Meta Billing/Usage; verify the endpoint's supported
   image+schema+reasoning token requirements and response shape with a
   newly reviewed token budget **before any additional paid call**.
2. Implement signed, authenticated, consented, source-scoped evidence
   intake and an independent validator before allowing authorized real frames.
3. Implement persistent event deduplication, RBAC across sources/tenants,
   approved in-app delivery receipts, and a durable notification system.
4. Independently evaluate human-labelled fall/ADL examples, privacy
   protection, failure handling and safe escalation; no medical claims.
5. Non-demo incident reads are denied (403) in this branch. Full
   production login/session RBAC is not implemented.

Official references:
- https://dev.meta.ai/docs/api-reference
- https://dev.meta.ai/docs/pricing-rate-limits
- https://dev.meta.ai/docs/image-understanding
- https://dev.meta.ai/docs/structured-output
