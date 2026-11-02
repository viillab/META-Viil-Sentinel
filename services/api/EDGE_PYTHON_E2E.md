# VIIL-Sentinel — Actual Edge v1 Python Emitter → Backend → Caregiver Inbox

**Member 2 acceptance / 2 Nov 2026 / OFFLINE SYNTHETIC DEMO ONLY**

## What really runs

Unlike the earlier `app.synthetic_intake_smoke`, which imported a static
JSON fixture, this scenario **executes the original Member 1 Python temporal
pose detector** through the upstream `sentinel_edge.handoff_cli` on two
frozen, deliberately fictional mathematical pose sequences:

1. `examples/synthetic/fall.jsonl` — generates **one new UUID** candidate
   at **850 ms relative-to-source-start**, with an **uncalibrated heuristic
   score of 0.928**.
2. `examples/synthetic/sitting.jsonl` — generates **zero candidates**.

The test uses the Member 1 v1 emitter restored from the shared integration branch (with import-order formatting only)
`services/edge-vision/sentinel_edge/handoff.py` and
`services/edge-vision/sentinel_edge/handoff_cli.py`. The frozen
`viil.edge.candidate.v1` producer output is compared field by field against
the canonical source-owned example, except for the intentionally fresh UUID.

The process then signs the exact emitted JSON bytes with a **fictional**
dedicated Edge HMAC key, sends the request in-process to the real FastAPI
route `POST /api/v1/edge/candidates`, verifies SQLite acceptance and duplicate
rejection, then reads `GET /api/v1/caregiver/inbox` with a **different**
fictional caregiver token. The inbox must contain exactly one advisory with
the new Edge-generated event UUID, metadata-only and marked:

- `simulated=true`, `stage=edge_candidate`, `fall_confirmed=false`
- `meta_provenance=none`, `delivery_state=not_sent`
- No emergency dispatch, notification, camera identity or medical severity

Additional offline checks reject missing caregiver authorization, forged Edge
signatures, or events that falsely claim authorized real camera input. No
actual Meta Model API request is made, and no real imagery is processed.

## Run the end-to-end demonstration

From `D:\VIIL-Sentinel\services\api` with Python backend dependencies installed:

```powershell
.\.venv\Scripts\python.exe -m app.edge_emitter_e2e
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

For independent Member 1 detector tests, from
`D:\VIIL-Sentinel\services\edge-vision`:

```powershell
..\api\.venv\Scripts\python.exe -m pytest -q
```

Expected main status: `REAL_EDGE_SYNTHETIC_TO_INBOX_PASS`.

The smoke launches a single, local, bounded Python subprocess for each
source trace; **both trace files are pinned to literal SHA256 hashes**
and the CLI is invoked only with hard-coded `synthetic_pose_trace`.
The child receives a minimal OS/Python environment, without inherited
`META_MODEL_API_KEY`, `HIKVISION_PASSWORD`, cloud or caregiver credentials.
No custom file path, person, camera or network address can be passed.
A temporary SQLite ledger is created and removed in the same run, after
all database connections are properly closed (Windows-safe).

The HTTP calls use in-process `TestClient`, **not** a running server,
real browser session, remote camera, phone, cloud queue or public socket.
This is actual producer→backend functional interoperability in test mode,
NOT a field trial. The sample sequences are entirely synthetic; their
passing scores cannot establish accuracy, low false-alarm rate or model
performance with people.

## Live Meta follow-on test (separate, explicit script)

On 2026-11-02, two additional user-approved Meta Model API calls succeeded
after selecting `reasoning_effort="minimal"`, and a synthetic-only
Edge→Backend→Meta probe→Inbox live integration check passed. This original
in-process smoke remains entirely offline. The new opt-in integration command
is `python -m app.meta_system_live_demo` (offline without paid flags);
details are in `services/meta-intelligence/LIVE_META_TEST_REPORT_2026-11-02.md`.
The spend guard is now exhausted at **4/4 cumulative calls**, and a local
conservative reservation is not Meta's actual charge or team $150 balance.
Do not reset the ledger or send real camera images.

## Outstanding deployment blockers

- This is a local in-memory transport and temporary SQLite, **not** an
  authenticated real camera/client → deployed Backend integration.
- No production caregiver login/RBAC, tenant-scoped identity, signed
  site/consent approvals, camera source/model registry, verified image
  evidence or clock alignment has been demonstrated.
- No real caregiver delivery, acknowledgment receipt, in-app authenticated
  mobile integration, SMS, push, emergency escalation or real-time fall
  accuracy evaluation is implemented by this workflow.
- The Flutter/Dashboard app must not advertise the demo as a live Meta
  result or a verified medical fall.
- The source-owned Edge detector may have other in-progress work on Member 1
  branches. Validate integration conflicts and version drift before any merge
  into the shared integration branch; this Member 2 topic does not modify
  the developer's untracked `apps/mobile` or `apps/dashboard/public` files.
