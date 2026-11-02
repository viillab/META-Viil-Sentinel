# VIIL Sentinel
**Meta-first Fall Candidate Intelligence via Edge Vision — Hackathon MVP**

> **Local development foundation, not a finished fall detector or medical product.** This repository was freshly developed during the 2026 Meta Global AI Developer Hackathon. Existing AFDCare code, model weights, research datasets and proprietary assets have not been copied.

VIIL Sentinel aims to provide **non-clinical, human-supervised incident awareness**:
Video → Edge fall candidate → consented keyframes → Meta-first evidence assessment (planned; current backend MOCK) → validated informational in-app advisory or follow-up → Caregiver acknowledgement / override → Traceable incident management.

## Two-person team: Member 1 (Edge + Dashboard) and Member 2 (Backend + Meta)

See [current two-member assignments and Meta-first design](handoff/team/TEAM_ROLES_AND_META_FIRST.md).
**Member 2's first stop:** [START HERE — verified offline handoff](handoff/member2/START_HERE.md).
From `services/edge-vision`, run `python -m sentinel_edge.handoff_preflight` to check the
Edge candidate contract, synthetic fall/non-fall, roster and frontend readiness
without credentials, network or private data. Optional
`--verify-local-models` adds SHA-256 checks when private model files are present.
This is developer readiness, **not** a real-world detection benchmark.
Start at [Member 1 delivery package](handoff/member1/README.md) for the
live code/API ownership, canonical candidate JSON contract, new strictly
versioned private 1500ms research-model loader and source-verified model
reproduction, hardware measurements and honest deployment blockers.
The 1500ms trained research model is **not yet a validated real fall detector**
and is **not wired to the backend**. Synthetic/demo endpoints remain separate.
For safe folder structure and phased refactor instructions see
[Folder architecture](handoff/member1/ARCHITECTURE.md).

### Flutter mobile caregiver demo · apps/mobile

**Member 1 Flutter app:** [VIIL-Sentinel Care demo guide](apps/mobile/README.md).
The app is a self-contained **OFFLINE / SIMULATED** caregiver experience with
Home, Alerts, Event Details, History, and Demo Control screens. It lets a judge
start a one-tap **guided 4-step demo** (Generate → Review → Acknowledge →
History), generate other fictional fall/follow-up scenarios, locally
acknowledge an event and see it move to History, or reset instantly.
The guided CTA stays pinned at the bottom on compact displays. Opening an
unfinished walkthrough reuses its pending candidate; Replay after review
replaces only that scripted sample. Demo-only memory is bounded at 32
fictional events, with no real incident retention or backend calls. Sitting generates no
candidate. **No camera, backend, Meta provider, push alerts, emergency dispatch
or real fall verification occurs on mobile.** All sample data is in memory,
with conspicuous DEMO labels. From `apps/mobile`:

```powershell
flutter pub get
flutter analyze
flutter test
flutter run -d chrome
flutter build apk --debug
```

Mobile also provides an **Offline Caregiver Contract Sandbox** under Demo
Control. It validates a generated `viil.backend.caregiver_inbox.v1`
metadata sample or rejects an injected image field, using strict keys,
32 KiB/30-record bounds, timestamp and receipt consistency checks.
From there, **Open read-only Inbox Preview** demonstrates three
fictional selectable advisory records with safe details; stale samples
are hidden after 30 seconds or when the app leaves the foreground.
The preview cannot acknowledge or send an alert and does not alter the
existing Demo Alerts queue. No HTTP request is made and Live/Auth/Meta/
Push stay disabled. Flutter
tests compare the codec to the handoff JSON Schema. See the
[mobile guide](apps/mobile/README.md).

Connecting a live mobile caregiver inbox is deferred until Member 2 ships an
authenticated, authorized backend service. The current `caregiver_inbox.v1`
dashboard contract is a *proposal*, not a verified production endpoint.

### Python Edge → Dashboard contract verification

The `edge-dashboard-contract` CI job now invokes the **real Python Edge v1
emitter** on invented fall and sitting traces and validates both outputs
through the exact Dashboard TypeScript JSONL parser. Unlike checking only a
copied fixture, this detects drift in timestamp, heuristic score, safety
fields, provenance, or JSONL representation. The fall trace currently emits
one unconfirmed candidate at source-relative **850 ms**, score **0.928**
(uncalibrated, **not a fall probability**); sitting emits zero. It also
rejects forged staged authorization and unsafe source IDs. From Windows:

```powershell
cd D:\VIIL-Sentinel\apps\dashboard
node --experimental-strip-types scripts/verify-edge-emitter.mjs --python D:\VIIL-Sentinel\services\edge-vision\.venv\Scripts\python.exe
```

No actual camera, Meta API, backend ingestion, or real-world fall accuracy is
verified by this offline test.

### Synthetic Chrome webcam UI test

The Dashboard also has a same-origin `connect-src` CSP that blocks
off-device MediaPipe SDK logging attempts. A dedicated **local-only**
test can load the existing private task model, run the actual MediaPipe
CPU inference over a synthetic Canvas stream (at least 16 analyzed
frames), print locally measured processed FPS and inference p50/p95,
exercise model reload, frozen-frame and hidden-tab teardown, and check
that all external SDK requests are blocked by CSP:

```powershell
cd D:\VIIL-Sentinel\apps\dashboard
npm run smoke:fake-webcam -- --pose-model D:\VIIL-Sentinel\models\pose_landmarker_lite.task
```

No private model is included in CI or Git. This test proves runtime
plumbing, not real-person pose detection, fall accuracy or medical safety.

The `webcam-browser-smoke` CI job opens a disposable Chrome Headless
instance and injects an animated Canvas `MediaStream` into the actual
React laptop-webcam UI, so it never touches a real laptop camera. It verifies
fresh frames, manual Stop/restart, simulated hidden-tab and frozen-frame
fail-closed cleanup, late permission resolution, redacted permission denial,
an absolute 60-second deadline armed when a stream is granted (also when
`video.play()` never settles), released video tracks, an operator-review
session report, and no POST/upload.
Run `npm run smoke:fake-webcam` from `apps/dashboard` (Node 22 and local
Chrome/Edge required). This is **not**
hardware or fall-model validation. See
[Webcam testing guide](docs/integrations/LAPTOP_WEBCAM_DEMO.md).

### Offline browser Pose heuristic scenarios

The **AI Detect Test Lab** now includes an interactive, browser-local
synthetic Pose trace simulator built on the exact torso-motion heuristic
used by the Laptop Webcam Demo. Its generated upright-to-horizontal
sequence produces **one UNCONFIRMED candidate at 1000 ms**; sitting,
horizontal-without-baseline, pose loss and multiple-person sequences
produce none. The timeline displays derived state and measurements only.
It does **not** invoke MediaPipe, open a camera, call Meta/backend, emit a
Python Edge JSONL event, or notify a caregiver. An isolated Chrome UI
smoke checks all scenarios. See
[synthetic Pose trace guide](docs/integrations/SYNTHETIC_POSE_HEURISTIC_LAB.md).

## Member 1 AI Detect + Web Test Lab (Phase 1)

The browser-local **AI Detect Test Lab** is available from the sidebar (the default Dashboard screen is Judge walkthrough).
It replays strictly validated, metadata-only `viil.edge.candidate.v1` JSONL
from the real Python Edge emitter with **zero backend requests while the
Lab tab is selected**; no photo, person trace or private model upload.
It includes synthetic fall and sitting/no-candidate buttons, bounded local
file import and clear non-calibrated score/relative-time labels. It does
**not** perform AI inference in the browser, prove accuracy or deliver
alerts. Existing Incident operations remains a separate mock-only tab.

The full experiment gates and exact Windows commands are in
[Member 1 Edge + Web Phases](docs/roadmap/MEMBER1_EDGE_WEB_PHASES.md).

## Status

| Component | Foundation | Real functionality |
|---|---|---|
| FastAPI Incident API | Implemented | In-memory, local demo only |
| Review state machine + audit trail | Implemented | Human-controlled demo workflow |
| Mock incident interpretation | Implemented | Clearly labelled simulation only |
| Meta Model API | Interface defined | **Not yet connected** |
| Webcam/recorded video/pose estimation | Temporal pose heuristic and optional MediaPipe video runner added (Member 1) | **Unvalidated heuristic; requires external pose model and authorized recordings** |
| React caregiver dashboard | Implemented | Simulated events via API |
| In-app notifications | Simulated feed | External channels not implemented |
| Evaluation | Protocol documented | Benchmarks pending |

### Quick start on Windows

**Backend — terminal 1 (Python 3.11+)**

```powershell
cd D:\VIIL-Sentinel\services\api
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health
- Run tests: `python -m pytest -q`

**Dashboard — terminal 2 (Node.js 20.19+ or 22.12+)**

```powershell
cd D:\VIIL-Sentinel\apps\dashboard
npm install
npm run dev
```

Open http://127.0.0.1:5173. Click **Generate staged incident** to test the mock workflow.

**Important:** Do not add `META_MODEL_API_KEY` until Meta's official API contract, billing, data governance and image authorization have been confirmed. The code never accesses Meta AI while `META_PROVIDER=mock`.

## Architecture

- `services/api`: Small FastAPI app with schemas, workflow, in-memory store and mock interpreter.
- `services/edge-vision`: Member 1 pose-feature temporal heuristic, optional MediaPipe webcam/video runner, synthetic tests and evaluation metrics; see its README.
- `apps/dashboard`: React + TypeScript caregiver demonstration UI.
- `services/meta-intelligence`: Planned official Meta API adapter and schema validation.
- `services/orchestrator`: Documentation for controlled incident flow.
- `docs/`: Roadmap, eligibility checks, architectural decisions and demo script.
- `evaluation/`: Metrics and staged-data evaluation protocol.

This is a **single-process backend with modular components**, deliberately not a multi-service production deployment.

## Competition compliance

- New work between **26 Oct and 4 Nov 2026**; preserve Git history and distinguish all reused dependencies.
- Team size: **two active members**, within the maximum-four rule; Member 1 also owns the Dashboard and Notifications formerly assigned to Member 3.
- Repository may remain Private during development based on organizer confirmation; make **Public before submission** and test in a logged-out browser.
- Submit a **3-minute demo video**, team roster and public repository link.
- Deadline: **5 Nov 2026, 09:00 ICT**; internal target **4 Nov 2026, 21:00 ICT**.
- Don't present mock outputs as working CV or Meta model inference.
- Anti-project risks: avoid simple image analyzer, dashboard-only project or AI medical advice.
- No autonomous emergency dispatch or diagnostic statements.
- Consult `docs/competition/RULES.md` before submitting.

## Next development milestones

1. Create a safe webcam/recorded-video source interface using staged or permitted material.
2. Implement and evaluate temporal fall candidate detection.
3. Implement evidence/keyframe selection and PII minimization.
4. Verify the latest Meta Model API documentation and implement a **real** vision adapter with strict cost limits.
5. Implement evidence-grounded JSON validation and unsupported-claim testing.
6. Add persistent incident storage, authenticated caregivers, real in-app notification delivery and reliable retry.
7. Record reproducible metrics and a 3-minute honest demo.

## Project safety and scope
Research/staged demonstration only. Proposed Meta-first assessment can automate routine *informational* advisory screening after real evidence validation; human control remains for consequential decisions. This is not a medical device, patient monitoring guarantee or rescue dispatcher.

See `SECURITY.md`, `CONTRIBUTING.md` and `docs/architecture/ARCHITECTURE.md`.
