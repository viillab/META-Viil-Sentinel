# Meta Model API — Member 2 takeover (2 Nov 2026)

## Meta Copilot — new orchestrator control plane

A [Meta Copilot Control Plane v1](../api/META_COPILOT_CONTROL_PLANE.md)
now defines an allowlisted Muse Spark **read-only task-planning contract**
and an opt-in local Caregiver preview for checking synthetic event linkage,
verifying its independently signed audit and preparing a human-review
handoff. The provider request is **prepared but never sent**; the HTTP
preview truthfully reports `meta_api_called=false` and remains in
`offline_readonly_shadow` mode. This is **not yet a live Meta autonomous
agent** or a real fall decision. The old 4/4 Meta spend guard is unchanged.

The new [mock-only provider contract integration](../api/META_COPILOT_PROVIDER_CONTRACT.md)
runs a Meta-shaped Chat Completions request against `httpx.MockTransport`,
checks the simulated Structured Output and revalidates the independent audit
anchor before preparing the Caregiver workplan. No actual provider
connection or cost is possible from that adapter; malformed or unsafe
model proposals are rejected without execution.

## Offline Meta Copilot shadow admission

[Meta Copilot Shadow Dedup & Readiness](../api/META_COPILOT_SHADOW_DEDUP_V1.md)
adds durable Event UUID idempotency, a one-mock-call-per-case shadow
reservation and a local Caregiver readiness endpoint.
The readiness gate categorically blocks real-provider calls and only
**reads** the existing local Meta budget state. It never reserves a new
paid attempt, grants real-media rights, or impersonates actual inference.

## Five licensed real-video Edge evaluation — blocking finding

Member 2 has now run **five actual staged human MP4s** through the
**unchanged Member 1 OpenCV + MediaPipe PoseLandmarker + TemporalFallDetector**
locally, *not* through Meta. The small diagnostic sample yielded
**0/3 fall candidates detected, 2/2 ADL clips without false alerts**
(clip-level TP 0, FN 3, TN 2, FP 0; recall 0%), despite 660/667 frames
producing valid torso poses. This exposes a serious gap in the strict
upright -> descent -> horizontal temporal gates; it is NOT a reliable
generalization metric or a clinical result. All five identifiable
videos and pose traces remain Git-ignored under `data/private`.
See [actual five-video evaluation, provenance and gate diagnostics](../api/PUBLIC_DATASET_5_VIDEO_EVALUATION_2026_11_02.md).
**Do not send these human videos to Meta or claim live fall detection is ready.**
No Meta Model API calls were made in the evaluation.

## Follow-up: V2 experimental review, never Meta on human media

The [experimental V2 review-only study](../api/EXPERIMENTAL_REVIEW_V2_DEVSET_2026_11_02.md)
tested another five local, hash-pinned noncommercial human-performed
clips (disjoint **clip IDs**, not proven distinct subjects). Its
two non-upright movement hypotheses produced review candidates for
3/3 fall-labeled development clips; the original V1 detected 2/3.
The previously inspected five clips were checked separately, with
2/3 review candidates versus V1 0/3, but are not a blind holdout.
This is **exploratory, not clinically validated**, and fast voluntary
sitting can cause a spurious candidate. **No videos/poses sent to Meta,
no new paid API calls, no alert dispatch**, and V1 runtime is unchanged.

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
- **Four cumulative Meta HTTP responses were received on 2026-11-02**.
  Calls #1–2 failed guarded validation/truncated. After setting
  `reasoning_effort="minimal"`, calls #3–4 **passed** strict live vision
  assessment and synthetic local Edge→Backend→Meta→Inbox integration.
  Neither test proves the model detects actual falls.
  See [2026-11-02 live test report](LIVE_META_TEST_REPORT_2026-11-02.md).
- The next **offline-only** step constructs deterministic 3-panel synthetic pose
  diagrams cryptographically tied (by SHA-256) to the generated Edge event
  UUID/source/timestamp/trace. The Meta live adapter **still refuses** these
  diagrams and no further provider calls are authorized. See
  [Synthetic Evidence v1](../api/SYNTHETIC_EVIDENCE_V1.md).
  The related [synthetic evidence registry](../api/EVIDENCE_REGISTRY_V1.md)
  now stores only linked receipt/manifest hashes after local signed Edge
  ingestion. A [synthetic-only deny consent gate and SHA256 audit chain](../api/EVIDENCE_CONSENT_AUDIT_V1.md)
  now records registration with independent read-only local verification.
  A [separately signed synthetic audit checkpoint](../api/EVIDENCE_AUDIT_ANCHOR_V1.md)
  can now independently verify the local SQLite audit head on protected
  read-only caregiver metadata endpoints. Real-media consent remains
  unverified and no model calls occur.
- No real camera pixels or private/person/patient evidence was transmitted.

## Budget, billing and safeguarding $150

Meta's published Standard Muse Spark rates on 2026-11-02:
**$1.25 per million input tokens**, **$4.25 per million output tokens**,
plus $0.15/M cached input if applicable. The chosen model is **NOT** the
Contributor model, since that mode permits submitted content to train Meta models.

The local `MetaBudget` uses a gitignored SQLite file at
`data/private/meta_spend.sqlite3`. A SQLite transaction reserves an
intentionally conservative per-request allowance **before** network I/O.
By default the original process allows **2 attempts** and **$0.50
reserved locally**. A separate, user-approved explicit two-test extension
permits at most **4 cumulative attempts** and **$0.75 reserved locally**;
there is no refund on timeout, errors or malformed output, and no retry.
All unit/integration tests besides the two explicitly described live calls
used fake keys/transports (no Meta spend).

On this workstation **all 4 attempts have been used**. The cumulative
conservative local reservations total **$0.514148** (not a billing charge).
The successful third and fourth API replies had respectively
233/163 and 233/234 input/output tokens. These are NOT Meta Billing
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
and never transmits the key or an image. The `--live-once` option is only for an explicitly approved synthetic
test; the extra approved call cap additionally requires
`--approve-two-extra-tests`. **Both are now blocked because 4/4 local
requests were used.** Never reset the ledger simply to get more calls.

## Remaining critical work (not shipped as working)

1. Inspect actual Meta Billing/Usage. The basic image+strict-schema+minimal
   reasoning path now works. A new **local synthetic-only** event→diagram
   hash binding has been tested offline, but **real human camera evidence**
   association and fall detection accuracy are NOT verified. Obtain a
   separately reviewed test budget before any additional paid call.
2. Implement signed, authenticated, consented, source-scoped evidence
   intake and an independent validator before allowing authorized real frames.
3. Synthetic metadata idempotency now uses SQLite, but production-grade
   source/tenant RBAC, approved in-app delivery receipts and durable
   notification system remain unimplemented.
4. Independently evaluate human-labelled fall/ADL examples, privacy
   protection, failure handling and safe escalation; no medical claims.
5. Non-demo incident reads are denied (403) in this branch. Full
   production login/session RBAC is not implemented.

Official references:
- https://dev.meta.ai/docs/api-reference
- https://dev.meta.ai/docs/pricing-rate-limits
- https://dev.meta.ai/docs/image-understanding
- https://dev.meta.ai/docs/structured-output
