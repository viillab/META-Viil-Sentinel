# VIIL-Sentinel — Member 1 AI Detect + Web experiment phases

**28 Oct 2026** · Only Member 1 owns Edge AI / Detection and React Web UI.
Member 2 owns the Backend, Meta Model API, durable incident processing,
evidence permissions and server-side security. No third member.
This document is an **implementation and evaluation plan**, not an accuracy
claim, release certification or promise of clinical reliability.

## Decision principles (before any model change)

1. Keep **pose estimation**, **temporal fall candidate decision** and
   **web visualization** as separate units. Trained 1500 ms CAUCAFall
   logistic model runs **research-only Shadow** and emits no live alerts.
   The current versioned `viil.edge.candidate.v1` is from an
   **uncalibrated heuristic**. Never swap the sources of these scores.
2. Test on a frozen authorized dataset manifest, separating
   **people, camera/view, sites and time** across train/validation/test.
   Grouped splits prevent repeated clips/subjects from leaking between
   splits. Never select thresholds or optimize a model using a frozen
   test set.
3. Report event onset latency **only with independently reviewed onset
   timestamps**. Report observed false alarms per annotated non-fall
   hour, not `0 detected events in a synthetic trace`. A candidate
   count or score is not precision/accuracy.
4. Preserve failures and abstentions: no person, missing landmarks,
   two-person ambiguity, low light, partial occlusion, camera shake,
   sitting/lying/bending, fall without lying, slow collapse.
5. One budget at a time: keep MediaPipe Lite, minimize copies/pose
   buffers, benchmark sustained p50/p95 FPS, RSS and cold start on the
   target device. An improvement in replay speed alone is not evidence
   of improved fall recall.
6. No raw video, pose arrays, identifying metadata, unlicensed
   footage or private research weights in Git, browser local storage,
   backend transport or logs. Never transmit data to Meta during
   Member 1-only phases without an approved consent/privacy handoff.

## Phase plan (ordered gates)

| Phase | Priority | Concrete deliverable | Entry/exit gate |
|---|---|---|---|
| **P0: Baseline freeze** | Complete | Stable Edge v1, model hashes, 2-person roster and current handoff | Offline preflight passes, exact CI checked |
| **P1: Edge → Web Test Lab** | **Implemented this iteration** | Browser-local 256 KiB/100-candidate JSONL reader; synthetic fall and no-candidate sitting fixture; relative timestamps, declared provenance and uncalibrated scores; zero backend requests while Lab tab active | Fixture byte-parity with Edge canonical JSON, hostile payload tests, TypeScript/Vite build and hosted CI |
| **P2: Real local video / webcam experiments** | Next | Edge Python + MediaPipe Lite on authorized recorded clips/webcam; local stdout metadata can be imported into Lab; optional on-screen landmarks in *local-only preview*, no saved frames | Verify consent, multiple scenarios, absence of event for known negatives, reset on source/gap, no raw export |
| **P3: Blinded model evaluation** | Research gate | Human-reviewed onset/offset and uncertainty labels, actor/camera-disjoint heldout sets, uncalibrated heuristic vs private 1500 ms Shadow metrics logged separately | Report per-class event recall, event FP/hour, missed falls, pose abstention, p50/p95 onset delay and bootstrap uncertainty; no test leakage |
| **P4: Controlled accuracy improvements** | Conditional | On same frozen splits compare original heuristic, corrected threshold variants and tiny causal TCN/temporal model if available; hard-negative mining from licensed ADLs | Select only using validation; improve recall/false alarms jointly, reproduce gains on unseen holdout; preserve baseline rollback |
| **P5: Edge runtime optimization** | Conditional | One persistent pose task per continuous session, CPU/perf/RAM/gap tests, sensitivity tests for resizing/frame sampling | Matched 3+ repeated runs, cold start and 30+ minute sustained measurements, no regression in event-level metrics |
| **P6: Member 2 integration** | Blocked until Member 2 | Backend-authenticated v1 candidate ingestion + consented Meta-first evidence flow, with Web consuming backend-generated presentation DTO | External authorization/idempotency/consent rules, strict source authentication, audit and informational-only notifications; no automated rescue |

### Data and metrics gate for P3 (DO NOT fabricate)

For an independently human-labeled evaluation run, report:
- **Event recall** = matched real fall events / independently labeled
  falls, with identity-aware matching window and separate late/missed.
- **False alarms / no-fall hour** = unmatched candidate events divided by
  annotated ADL duration in hours; report long-form ADLs.
- **Onset detection delay (p50/p95)** = edge event timestamp minus
  independently reviewed fall-onset timestamp. Check timestamp basis.
- **Abstention** = excluded windows/frames divided by eligible windows,
  segmented by quality, occlusion, multi-person and invalid trace.
- **Runtime** = measured decoded frames / wall time; warm and cold runs
  reported separately with sampling/CI and RSS peak vs sampled points.
- Report thresholds, counts, confidence intervals and manifest/source
  hashes. Avoid single headline "Accuracy" from 5 publisher-staged videos.

**Current model caveat:** Existing Member 1 notes record a previously
exposed tiny staged publisher sample where the 1500 ms research model
detected only **1 of 3 fall clips**. The existing one-clip
19.12 FPS number is a local train-ADL research replay, not 30-minute
live performance or evidence of real-world sensitivity. See
[measured limitations](../../handoff/member1/PERFORMANCE.md).

## How to use the new P1 Web Lab right now (Windows PowerShell)

From a clean clone of `member/feature/preprod`:

**Terminal A — Edge CLI, synthetic only, NO camera:**

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
python -m pip install -e ".[dev]"
python -m sentinel_edge.handoff_preflight
New-Item -ItemType Directory -Force ..\..\data\private | Out-Null
python -m sentinel_edge.handoff_cli --trace examples/synthetic/fall.jsonl --source-id synthetic-clip-01 --provenance synthetic_pose_trace > ..\..\data\private\fall_candidates.jsonl
python -m sentinel_edge.handoff_cli --trace examples/synthetic/sitting.jsonl --source-id synthetic-clip-01 --provenance synthetic_pose_trace > ..\..\data\private\sitting_candidates.jsonl
```

PowerShell may write a UTF-8 BOM; the Lab accepts one at the beginning.
The first file contains exactly one **unconfirmed** synthetic candidate.
The sitting output is an **empty** replay and is not proof of measured
specificity. All generated files are inside Git-ignored
`data/private/`.

**Terminal B — React Web Lab, no backend needed:**

```powershell
cd D:\VIIL-Sentinel\apps\dashboard
npm ci
npm run build
npm run dev
```

Open `http://127.0.0.1:5173`. Default is **AI Detect Test Lab**:
- Load the two explicit synthetic fixtures; or
- Select `fall_candidates.jsonl` or `sitting_candidates.jsonl`
  from the local file picker.
- View source-relative time, source identifier, declared provenance
  and uncalibrated score. **No webcam video, frames, raw pose or
  model weights are loaded into the page.**
- The separate **Incident operations (demo)** tab is the existing
  mock backend UI; only that tab polls the local Member 2 demo API.

For authorized staged video, the existing Python Edge runner may be
used **only under its explicit consent rules**; use the existing Edge
v1 `--candidate-format v1` output and import the metadata file.
Do not publish synthetic test results as real fall-detection metrics.

## P2 acceptance / experimental test matrix

| Scenario | What to inspect / log | Gate |
|---|---|---|
| staged safe fall | frame count, candidate count, source-relative time | Label and consent established; compare against reviewed onset |
| walking, sitting, bending, lying down | candidate counts per **annotated duration** | Do not mistake zero candidates from one fixture as good FPR |
| far camera, poor lighting, occluded torso | pose quality, abstentions, missing body joints | Fail-closed: no fabricated detection/visibility |
| 2+ people in view | person association/ambiguity | No cross-person pose stitching |
| video gaps or source switches | history reset, timestamp monotonicity | No reused pose state across different clips |
| different CPU/frame sizes | p50/p95 FPS, RSS sampled/peak, events | Matched protocols and event parity before optimization |

## Why this order (research references)

- Google MediaPipe Web Pose Landmarker documentation:
  https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker/web_js
  Its `detectForVideo` calls are **synchronous** and block the UI
  thread; if P2 adds in-browser pose inference, design Web Worker
  boundaries and device perf tests first. Today's P1 avoids those
  dependencies and performs no in-browser ML inference.
- **OmniFall, ECCV 2026**: https://dsch.ai/omnifall/
  and https://arxiv.org/abs/2505.19889.
  The benchmark demonstrates staged-vs-wild dataset bias and uses
  multi-domain, cross-view evaluation, motivating strict P3 splits.
- Existing repository source-of-truth:
  `services/edge-vision/docs/edge_candidate_v1.schema.json`,
  `services/edge-vision/sentinel_edge/handoff.py`,
  `handoff/member1/PERFORMANCE.md`.

## Ownership / version rules

Member 1 works on `member1/feature/*` and integrates validated code
into `member/feature/preprod` after exact SHA CI. Member 2 owns
`services/api` and Meta. Do **not** change candidate v1 semantics,
backend endpoints, or browser notification permissions to connect
this lab prematurely. Treat this phase as **developer test tooling**,
not a deployed fall-alert system.
