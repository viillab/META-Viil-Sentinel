# Member 2 — START HERE: Receive Member 1 without touching model code

**VIIL-Sentinel · 28 Oct 2026 · two members only**

**Member 1** owns Edge Vision, the research pose/fall model, Dashboard
and in-app Notification UI. **Member 2** owns backend authenticated
candidate ingestion, real Meta vision provider, evidence authorization,
persistent store and orchestration. The following is a **development
handoff**, NOT real-time fall detection proof or a production alert API.

## 1. Run the handoff check — no API key, account or images required

Clone the repo on branch `member/feature/preprod`. From
`services/edge-vision` (Windows PowerShell example):

```powershell
python -m pip install -e ".[dev]"
python -m sentinel_edge.handoff_preflight
```

This one **read-only and zero-network** command checks:
- exactly Member 1/2 ownership and current delivery manifest;
- canonical strict `viil.edge.candidate.v1` JSON Schema and example;
- one invented synthetic fall produces **one unconfirmed** candidate;
- invented sitting/non-fall produces **zero** candidates;
- no raw images/pose or clinical outcomes in either candidate;
- React read-only future DTO version and contract/build test presence;
- all blocked production flags remain explicitly **false**.

It prints a single JSON summary with
`status="ready_for_developer_handoff_only"` and
`private_model_integrity="not_checked"` by default. This does NOT
test real model accuracy or imply genuine Meta API connectivity.

For a second optional step **only if both private model files are
installed** (see Member 1 [model and Drive guide](../member1/README.md)):

```powershell
python -m sentinel_edge.handoff_preflight --verify-local-models
```

This additionally verifies the **original** pinned private SHA-256 of
the 5,777,746-byte MediaPipe Lite `.task` and the 2,654-byte
1500ms research classifier JSON, using the secure local-only loader.
Never commit, upload or post these private files to an incident API.
Failure exits nonzero; do not continue using a wrong model.

## 2. Understand the source contract before implementing ingestion

These are the existing **only approved outbound Edge files**:

| Purpose | Existing repo path |
|---|---|
| Versioned event schema | `services/edge-vision/docs/edge_candidate_v1.schema.json` |
| Contract specification | `services/edge-vision/docs/CANDIDATE_HANDOFF_V1.md` |
| Actual emitter | `services/edge-vision/sentinel_edge/handoff.py` |
| Local-only emitter CLI | `services/edge-vision/sentinel_edge/handoff_cli.py` |
| Synthetic fall/staged sitting traces | `services/edge-vision/examples/synthetic/{fall,sitting}.jsonl` |
| Example metadata envelope | `services/edge-vision/examples/synthetic/candidate_v1.example.json` |
| Model bundle + original SHA hashes | `services/edge-vision/sentinel_edge/handoff_verify.py` |
| Frozen research-only Shadow | `services/edge-vision/sentinel_edge/causal_1500ms_shadow.py` |
| Frontend read-only display adapter | `apps/dashboard/src/metaReview.ts` |
| Frontend future DTO details | `handoff/member1/FRONTEND_READINESS.md` |

**Local demonstration without video or network:**

```powershell
python -m sentinel_edge.handoff_cli --trace examples/synthetic/fall.jsonl --source-id synthetic-clip-01 --provenance synthetic_pose_trace
python -m sentinel_edge.handoff_cli --trace examples/synthetic/sitting.jsonl --source-id synthetic-clip-01 --provenance synthetic_pose_trace
```

The first emits *one JSON line*; the second emits *nothing*. Every run
generates a new UUID; never assert a particular UUID across runs.
`source_timestamp_ms` is relative to the **clip/camera start**,
never UTC. `detector_score` is **uncalibrated heuristic**.
`simulated=true` is mandatory for these synthetic fixtures.
`confirmed_fall=false`, `human_review_required=true`,
`evidence_refs=[]`, `delivery_mode=local_stdout_only`.

There is currently **no network POST**, trusted consent signal,
authenticated backend ingestion endpoint, durable outbox or persistent
incident state. A future transport needs a separate reviewed design.
**Never send this stdout to `/api/v1/incidents/demo`**, which is
intentionally a distinct mock-only developer endpoint.

## 3. Backend implementation belongs solely to Member 2

1. Define a separate authenticated ingest endpoint and explicit
   canonical v1 schema rejection; permit only registered sources.
2. Require device/source authorization **outside** the model's input
   provenance string; cap sizes, rate limits and replay window.
3. Deduplicate on canonical `event_id` and persist trust/retention
   metadata. Correlate source-relative timestamps with trusted clocks.
4. Keep incoming Edge candidates **unconfirmed**. License, privacy and
   consent must be checked before **independently selected** keyframes
   can go to the real Meta Model API (not the mock).
5. Verify real provider/model identity, timeout/cost limits, typed
   observations and actual frame references; route uncertainty and
   missing evidence to follow-up rather than treating generative
   negatives as proof of no fall.
6. Coordinate an optional versioned `viil.backend.meta_review.v1`
   response projection with Member 1. That is a **frontend proposal**,
   not an existing API contract. Keep the existing mock endpoint intact.
7. Preserve informational-only advisory gating; never implement medical
   diagnosis, automatic emergency-service dispatch, or unconsented video.

## 4. Frontend and testing boundaries

Member 1's Dashboard **only reads the current demo feed today**.
Its new passive proposed Meta status display shows MOCK for fake
incidents, PENDING for future true events with no assessment,
and will only label a backend-validated payload INFORMATIONAL ADVISORY
(not a confirmed fall). Browser projections are **not security gates**.

```powershell
cd ..\..\apps\dashboard
npm ci
npm run build
```

`npm run build` runs 28 dependency-free synthetic adapter tests,
TypeScript strict compilation and the Vite build. The Node 22
runtime and a suitable npm version are required. No live provider,
WebSocket or real notification channel exists yet.

## 5. Known blockers / definition of handoff done

| Handoff readiness | Current state |
|---|---|
| Strict synthetic Edge v1 output / negative trace | READY |
| Model artifact SHA verification CLI | READY, optional private files |
| React future Meta result display adapter | READY, passive / demo-only |
| Versioned two-member folder layout and manifest | READY |
| Real backend ingest, authentication and persistence | **NOT READY — Member 2** |
| Real Meta Model API and rights-cleared keyframes | **NOT READY — Member 2** |
| Backend-to-frontend approved review DTO | **NOT AGREED — Members 1 + 2** |
| Caregiver real notification delivery | **NOT READY — Member 1 UI + Member 2 backend** |
| Blind real-world fall event and false alarm validation | **NOT ESTABLISHED** |

**Quick escalation:** if `handoff_preflight` fails, share its
error **without copying private videos/weights**. If a new backend
field or transport is needed, propose a versioned contract with
both members rather than changing `viil.edge.candidate.v1` in place.

## Source of truth

- `handoff/member1/README.md`: original Edge/model handoff.
- `handoff/member1/ARCHITECTURE.md`: stable folder map (do not
  move existing imports during integration).
- `handoff/member1/PERFORMANCE.md`: honest local measurements.
- `handoff/member1/delivery_manifest.v1.json`: versioned readiness.
- `handoff/team/team_roster.v1.json`: only two owners.
- `AGENTS.md`: human-only `main` and shared `preprod` safeguards.
- `member/feature/preprod`: authorized integrated feature branch.

Do not claim the 1500ms research linear model is validated for live
fall alerts. It is separate from the original heuristic v1 emitter.
