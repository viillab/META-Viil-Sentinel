# VIIL Sentinel — Developer-friendly folder architecture

28 October 2026. This is an **incremental non-breaking layout**.
The current Python package deliberately stays stable so existing 600+
tests, automation, and other members' import paths keep working.
Do not rename dozens of active module files during handoff.

## Authoritative current repository map

    VIIL-Sentinel/
    |-- AGENTS.md                       # Human-only main; team branch rules
    |-- README.md                       # App purpose, demo status
    |-- handoff/
    |   +-- member1/                    # ENTRYPOINT for Member 2/3
    |       |-- README.md               # Integration sequence / commands
    |       |-- ARCHITECTURE.md         # THIS document / ownership
    |       |-- PERFORMANCE.md          # Verified budgets + remaining work
    |       +-- delivery_manifest.v1.json
    |-- services/
    |   |-- edge-vision/                # Member 1, Python 3.11
    |   |   |-- pyproject.toml
    |   |   |-- README.md                # Detailed research / historical work
    |   |   |-- docs/
    |   |   |   |-- CANDIDATE_HANDOFF_V1.md
    |   |   |   |-- edge_candidate_v1.schema.json  # SINGLE source of truth
    |   |   |   +-- ... historical validated experiment reports
    |   |   |-- examples/
    |   |   |   +-- synthetic/           # NO real person/video/weights
    |   |   |-- sentinel_edge/
    |   |   |   |-- runner.py             # Camera -> MediaPipe -> heuristic
    |   |   |   |-- detector.py           # Original unvalidated candidate path
    |   |   |   |-- pose_adapter.py       # Fail-closed, 2-person ambiguity
    |   |   |   |-- contracts.py          # Local typed frame/event contracts
    |   |   |   |-- handoff.py            # Member 1 -> 2 canonical v1 emitter
    |   |   |   |-- handoff_cli.py        # Synthetic/local stdout ONLY
    |   |   |   |-- causal_1500ms_research.py
    |   |   |   |                        # Original video -> 1500ms train
    |   |   |   |-- causal_1500ms_artifact.py
    |   |   |   |                        # Separate PRIVATE 1500ms weights
    |   |   |   |-- causal_1500ms_shadow.py
    |   |   |   |                        # Rolling past-only research counts
    |   |   |   |-- private_model_training.py
    |   |   |   |                        # INCOMPATIBLE legacy 8s V1/V2
    |   |   |   |-- temporal_training.py # Shared NumPy numeric baseline
    |   |   |   |-- window_export.py     # 30-slot time sampler
    |   |   |   +-- edge_resource_profile.py
    |   |   +-- tests/                   # Synthetic + bounded actual smoke
    |   |-- api/                         # Member 2, FastAPI, DEMO ONLY
    |   |   |-- app/main.py
    |   |   |-- app/models.py
    |   |   +-- tests/
    |   +-- orchestrator/               # Planned controlled workflow docs
    |-- apps/
    |   +-- dashboard/                  # Member 3, React/TypeScript
    |       +-- src/
    |-- docs/                            # Cross-team architecture/roadmap
    |-- models/                          # ignored LOCAL MediaPipe .task
    |-- data/
    |   +-- private/                    # ignored: videos, traces, model JSON
    +-- .github/workflows/             # CI; no force push/protected main

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
    Member 3: read ONLY trusted backend incident/review states
              -> caregiver UX + explicit demo labels

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
owns backend/meta changes, Member 3 owns dashboard. Human exclusively
promotes actual preprod and main; do not push to those branches.
