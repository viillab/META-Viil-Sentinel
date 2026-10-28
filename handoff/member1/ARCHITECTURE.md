# VIIL Sentinel — Developer-friendly folder architecture

28 October 2026. This is an **incremental non-breaking layout**.
The current Python package deliberately stays stable so existing 600+
tests, automation, and other members' import paths keep working.
Do not rename dozens of active module files during handoff.

## Authoritative current repository map

```text
VIIL-Sentinel/
├── AGENTS.md                                # Protected branch/agent rules
├── README.md                                # Product and mock-only demo
├── handoff/
│   ├── member1/                             # Member 1: Edge + Frontend
│   │   ├── README.md                        # Canonical handoff entry
│   │   ├── ARCHITECTURE.md                  # This nonbreaking folder map
│   │   ├── FRONTEND_READINESS.md            # Future read-only Meta DTO
│   │   ├── PERFORMANCE.md                   # Measured local performance
│   │   └── delivery_manifest.v1.json       # Machine-readable readiness
│   ├── member2/
│   │   └── START_HERE.md                   # Member 2 first-run checklist
│   └── team/
│       ├── team_roster.v1.json             # Only Members 1 and 2
│       └── TEAM_ROLES_AND_META_FIRST.md
├── services/
│   ├── edge-vision/                         # Member 1 Python package
│   │   ├── pyproject.toml                   # Install and CLI entry points
│   │   ├── sentinel_edge/
│   │   │   ├── runner.py                    # Local consented camera/video
│   │   │   ├── detector.py                  # Uncalibrated heuristic
│   │   │   ├── handoff.py                   # Strict candidate v1 envelope
│   │   │   ├── handoff_cli.py               # Local stdout only
│   │   │   ├── handoff_preflight.py         # Offline cross-team checker
│   │   │   ├── handoff_verify.py            # Pinned private SHA verification
│   │   │   ├── causal_1500ms_artifact.py    # Private model loader
│   │   │   └── causal_1500ms_shadow.py      # Research-only, no events
│   │   ├── docs/
│   │   │   ├── edge_candidate_v1.schema.json
│   │   │   └── CANDIDATE_HANDOFF_V1.md
│   │   ├── examples/synthetic/              # No real person/weights
│   │   └── tests/                           # Includes preflight tests
│   ├── api/                                 # Member 2 owner; mock today
│   │   └── app/
│   └── meta-intelligence/                   # Member 2 planned adapter
├── apps/
│   └── dashboard/                           # Member 1 React/TypeScript
│       ├── src/App.tsx
│       ├── src/metaReview.ts               # Pure passive display adapter
│       └── tests/metaReview.test.mjs       # 28 contract tests
├── models/                                  # Local ignored MediaPipe .task
├── data/private/                            # Local ignored data and JSON
└── .github/workflows/ci.yml                # Hosted regression checks
```

This is a curated map of existing stable entry points rather than an
instruction to move packages. The repo also contains historical research
and evaluation modules under `sentinel_edge/` and `docs/`. Paths under
`models/` and `data/private/` are local and **not committed**.

**Run the complete Member 1/2 offline handoff check:**

    cd services/edge-vision
    python -m sentinel_edge.handoff_preflight
    # optional with actual ignored private artifacts:
    python -m sentinel_edge.handoff_preflight --verify-local-models

**This is developer contract readiness only.** The CLI runs one synthetic
Fall and no-fall fixture with no camera, uploads, API, alerts or database,
and verifies strict manifest, schema and frontend handoff consistency.
See [Member 2 START_HERE](../member2/START_HERE.md).

This is a **logical separation through a stable public entrypoint**,
not a claim that every planned folder already has production code.
Some entries in the tree (e.g. local ignored folders, orchestrator)
are optional or documentation-only. The actual app entrypoints are
Python modules and npm scripts already tested in CI.

## Ownership and permitted flows

    Authorized video/camera on Member 1 machine
             |
        MediaPipe Lite task                    [local only]
             |
      strict torso adapter                    [local, 2-person fail closed]
             |
             +-- original heuristic --------> CandidateEnvelopeV1 / stdout
             |                                [NO network POST]
             |
             +-- separate research 1.5s ----> private short model JSON
                  (30 slots x 6)              [NEVER in Git]
                         |
                   Causal1500msModelShadow
                         |
                 aggregate counters only      [NO events or alerts]

    Member 2: authenticated ingestion from authorized approved sources
              -> durable idempotent record -> optional reviewed Meta
              evidence -> human review state
    Member 1: dashboard reads ONLY trusted backend incident/review
              states -> caregiver UX + in-app notifications + demo labels

**Do not let the research branch bypass the human gate.** Neither a
private model score nor the uncalibrated heuristic score means a
verified fall event. A network publisher/outbox does not exist yet.

## Dependency boundaries

- Edge runtime: Python stdlib + optional OpenCV/MediaPipe runtime for
  real video. The strict v1 candidate emitter uses **no heavy ML libs**.
- Research training: NumPy extra; output tiny float64 weights,
  restricted to ignored data/private.
- Research model loader: strict JSON + NumPy and shared baseline maths.
  Never load pickle, torch checkpoint, executable scripts or remote
  model URLs. No GPU / CUDA dependency is currently required.
- API: separate Python environment. Edge never imports FastAPI,
  Meta provider credentials, dashboard or database.
- Dashboard: TypeScript+Vite. Neither pose nor private weights belong
  in browser bundles, CDN or frontend local storage.

## Safe future refactor (DO NOT begin mid-integration)

After the hackathon delivery is stable, move files in a SINGLE
explicit compatibility-maintaining branch to these logical
subpackages, keeping old import shims and tests:

    sentinel_edge/
       runtime/            # camera, resize, pose adapters
       candidates/         # original detector, event emitter
       research/           # model fit, temporal window, CV, datasets
       artifacts/          # strict private versioned artifact formats
       evaluation/         # source-gated performance and review metrics
       contracts/          # stable externally consumed metadata models

That proposed tree is not active yet. Before moving any module, audit
imports, package discovery, user CLI commands and validation. Avoid
two copies of the same contract or silently changing public imports.

## Branch contract

Member 1 works in member1/feature/* and integrates validated changes
into member/feature/preprod only after tests and SHA-pinned CI. Member 2
owns backend/meta changes; Member 1 also owns Dashboard/Notifications.
There is NO active Member 3. Human maintainer exclusively
promotes actual preprod and main; do not push to those branches.
