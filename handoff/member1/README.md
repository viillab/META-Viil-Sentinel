# VIIL Sentinel — Member 1 handoff

**28 October 2026 · Owner: Member 1 Edge Vision + Dashboard + Notifications**

**2 active members only:** Member 1 owns Edge+Frontend; Member 2 owns Meta+Backend. Read [current role assignments](../team/TEAM_ROLES_AND_META_FIRST.md).
**Status: READY FOR DEVELOPER HANDOFF, NOT A PRODUCTION FALL DETECTOR**

**Member 2 quick start:** [START HERE (one-command offline preflight)](../member2/START_HERE.md).
The preflight is `python -m sentinel_edge.handoff_preflight` from `services/edge-vision`.
It validates the versioned metadata producer with synthetic Fall and Sitting traces,
checks the team roster and future frontend interface, and has an optional
`--verify-local-models` argument for private SHA-256 checks. It never posts data.

Start here. The adjacent delivery_manifest.v1.json is the machine-readable
contract inventory, ARCHITECTURE.md is the folder map and PERFORMANCE.md
records actual machine measurements. All old package imports and CI
entrypoints are intentionally preserved: no disruptive mass folder move.

## What other members can consume

| Interface | Consumer | Readiness |
|---|---|---|
| viil.edge.candidate.v1 metadata-only heuristic JSON | Member 2 Backend | **Producer/schema READY**; no authenticated ingestion yet |
| Backend validated incident state | Member 1 UI / Notifications | Demo exists; real ingestion/notifications NOT YET |
| viil.edge.causal_1500ms.linear_research.v1 private weights | Member 1 research; optionally Member 2 local offline QA | Opt-in verified private export, no alerts |
| Causal1500msModelShadow | Member 1 local research | 1500ms context, 250ms hop, counters only; no incident events |

**Never route research-only model scores to an actual incident or Meta
provider or caregiver notification.** The synthetic event emitter belongs
to the existing original **unvalidated heuristic**. It is NOT derived
from the newly trained 1500ms model.

## Member 2 — exact integration handoff

Canonical files in services/edge-vision:
- [Versioned contract guide](../../services/edge-vision/docs/CANDIDATE_HANDOFF_V1.md)
- [Strict JSON Schema](../../services/edge-vision/docs/edge_candidate_v1.schema.json)
- [Synthetic JSON example](../../services/edge-vision/examples/synthetic/candidate_v1.example.json)
- [Emitter](../../services/edge-vision/sentinel_edge/handoff.py)
- [Synthetic trace CLI](../../services/edge-vision/sentinel_edge/handoff_cli.py)

From services/edge-vision, simulate ONE fake fall candidate without a camera:

    .\.venv\Scripts\python.exe -m sentinel_edge.handoff_cli --trace examples/synthetic/fall.jsonl --source-id synthetic-clip-01 --provenance synthetic_pose_trace

Check that the emitted JSONL carries simulated=true, confirmed_fall=false,
score_calibrated=false, human_review_required=true and
delivery_mode=local_stdout_only. It does NOT POST to a network API.
The same command with sitting.jsonl should yield no candidate.

**Member 2 tasks:**
- Create authenticated, authorized, size-limited intake separate from
  /api/v1/incidents/demo. That demo route is for synthetic incidents only.
- Validate the canonical v1 schema exactly, idempotency by event UUID,
  source registry, allowlist, replay protection, per-source rate limits.
- source_timestamp_ms is relative to the camera's start, NOT Unix time;
  require trusted clock correlation before attaching wall-clock times.
- Preserve unconfirmed status; let Meta-first evidence assessment propose an informational in-app advisory only after real authorized and validated image evidence. Ambiguous/invalid/negative results stay unconfirmed and require follow-up. Do not infer a confirmed fall or authorize emergency response.
  No medical advice, real emergency dispatch, unconsented video or pose.
- Meta real provider still needs separate authorization, API keys only on
  backend and output validation. Do not portray MOCK outputs as real.

## Member 1 — Competition field acceptance (new)

Run `python -m sentinel_edge.field_acceptance` from `services/edge-vision`
for an offline, no-upload assessment of the actual synthetic Edge producer,
both UI handoff contracts, and the remaining field blockers. Optionally add
`--verify-local-models` for private SHA checks, or a signed camera registry
and selected pseudonymous camera IDs for config-only authorization checks.
**This command does not open any camera or prove live fall accuracy.**
See [Member 1 Field Acceptance & Hackathon Proof](../../docs/roadmap/MEMBER1_FIELD_ACCEPTANCE_AND_HACKATHON_PROOF.md).

## Member 1 — AI Detect + Web Test Lab

**Phase 1 implemented:** browser-local Edge v1 metadata replay without Backend,
Meta, cameras or stored/private data; hardened JSONL import (256 KiB, 100 events),
synthetic Fall and Sitting examples, source-relative times and uncalibrated
score visualization. The Web Lab does **not run Pose/AI inference in browser**;
Python remains the tested Edge producer. Real source output interoperability
was tested independently of the fixture. Phase roadmap:
[AI Detect + Web staged evaluation gates](../../docs/roadmap/MEMBER1_EDGE_WEB_PHASES.md).

## Member 1 — Dashboard / Notifications (formerly Member 3)

**Frontend integration preflight ready:** [Frontend readiness and proposed Meta-first view DTO](FRONTEND_READINESS.md). Member 1 has implemented a read-only, fail-closed Dashboard adapter, 28 Node contract tests and a simulated notification-feed display. **This is presentation readiness, NOT an authenticated live Meta integration, real alert service or approved auto decision.** Member 2 backend is unchanged.

React Incident Operations consumes simulated backend incidents only after an
explicit developer opt-in on localhost; its default is no API access. The
new read-only accessible Caregiver Inbox is separate and awaits Member 2's
authenticated /api/v1/caregiver/inbox contract. It does NOT currently
consume the Edge v1 local stdout stream. Add a human-facing
state/UI and Meta-first advisory presentation (with fallback/manual override) only after Member 2 validates incidents, implements secure durable
storage and authenticated review. The 0..1 Edge detector_score is
UNCALIBRATED HEURISTIC, not a probability of true fall. Clearly mark DEMO
data; do not offer emergency actions or use shadow counters as events.

## Member 1 — competition judge walkthrough and submission gate

The default Dashboard view is now **Judge walkthrough**: five synthetic
scenarios, six explicit Edge→privacy→Meta→policy→caregiver stages, no network
and no fabricated Meta provider response. The actual Edge candidate shown
comes from the canonical synthetic fixture; downstream orchestration is a
clearly marked future contract.

Run `python -m sentinel_edge.submission_readiness` inside
`services/edge-vision` for a read-only Member 1 artifact acceptance
report. The report lists all non-demonstrated deployment blockers and
makes **no** real-world accuracy/Meta/caregiver readiness claims.
Detailed runbook: [Member 1 judge demo](../../docs/submission/MEMBER1_JUDGE_DEMO_RUNBOOK.md).

## Member 1 — accessible caregiver UI (latest)

The new **Caregiver inbox** tab renders only metadata from an authenticated
Member 2 service when available. It offers larger text, high contrast,
keyboard navigation and Screen Reader status announcements, plus an
explicitly fictional offline sample preview. It does not deliver any alert
or permit real emergency actions. See
[Caregiver Inbox / Member 2 handoff](../../docs/integrations/MEMBER1_ACCESSIBLE_CAREGIVER_INBOX.md).
Shared backend schema: `handoff/team/caregiver_inbox.v1.schema.json`.
Accessibility has not been independently audited or certified.

## Member 1 — private trained weights (new)

The 1500ms model has a distinct file format and loader, not the old 8s
v1/v2 model. Its 30D parameters are 736B; the source-derived weights
are NOT checked into GitHub. The following command creates only a new
file inside ignored D:\VIIL-Sentinel\data\private, NEVER overwrites.

PowerShell from D:\VIIL-Sentinel\services\edge-vision:

    $r = "D:\VIIL-Sentinel\data\private\public-datasets\caucafall-omnifall\extracted\Cauca_fall"
    $p = "D:\VIIL-Sentinel\data\private"
    $py = ".\.venv\Scripts\python.exe"
    & $py -m sentinel_edge.causal_1500ms_research --root $r --groups "$r\caucafall-research-groups-v2.json" --proposals "$r\caucafall-review-proposals-v1.json" --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --private-model-output "$p\caucafall-1500ms-linear-research-model-20261028.json" --acknowledge-publisher-labels --acknowledge-pose-privacy

Only run on authorized staged sources with verified licenses and privacy.
The CLI source-pins every video, trains on declared train subjects,
selects threshold on declared validation subjects and checks a
previously exposed tiny test sample. New artifact readback is compared
bitwise with actual fitted values before success.

Opt-in offline RESEARCH ONLY:

    from pathlib import Path
    from sentinel_edge.causal_1500ms_artifact import read_causal_artifact
    from sentinel_edge.causal_1500ms_shadow import Causal1500msModelShadow
    private = Path(r"D:\VIIL-Sentinel\data\private")
    predictor = read_causal_artifact(private / "caucafall-1500ms-linear-research-model-20261028.json")
    shadow = Causal1500msModelShadow(predictor)
    # shadow.observe(authorized_pose_frame)
    print(shadow.summary())  # aggregate counts; NOT incident or alert output

Never import the frozen 8s V1 model into the 1500ms shadow: model
file/temporal contract mismatch must fail closed. The private loader
rejects wrong format, unknown flags, path escape and nonfinite values.
DO NOT upload a real research weight JSON to a public PR.

## Google Drive team delivery and one-command offline verify

**Member 1 Drive folder (private / research only):**
https://drive.google.com/drive/folders/1k2SM7CdbJTjWDR5DetrAUuPg2umOG_tK

**Models directory:**
https://drive.google.com/drive/folders/1C3EkqQ9QYaLASq0y7rek8T-uf8dyPM8h

Download either the exact **3,603-byte ZIP** (contains validated 1500ms
classifier JSON + handoff + SHA256SUMS) or the separately checked **2,654-byte
VERIFIED JSON**:
https://drive.google.com/file/d/1KAYNfXXstgGrzLazwsmGfErIFzR399qx/view

The older 2,657-byte UTF-8 BOM JSON was intentionally moved into
`99_ARCHIVE_Do_Not_Use`. Do **NOT** use that file. Both the ZIP content
and new VERIFIED JSON were downloaded from Drive and SHA256 checked
against actual trained source `2faad54ea929f9f44ed8e1bfb733c59d907cb4516fe3979cc4b5f551697f3abb`.

Get the official MediaPipe Lite task from its source, subject to the
publisher's licensing terms:
https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task

Place the downloaded classifier (renamed exactly as below) and pose task
under the repo's ignored `data/private` and `models` folders.
From `services/edge-vision`, after installing the project with
`pip install -e ".[dev,video]"` if needed, run **without network access**:

```powershell
python -m sentinel_edge.handoff_verify
# or: viil-edge-verify-handoff
```

The verifier reads and SHA256-pins **both** model files, enforces 1500ms
30D research-only schema, checks private path and initializes a *zero-window*
local Shadow (without inference frames). Its JSON output is limited to
file sizes, compatibility flags and non-production status. It never sends
any data or calls Meta, camera, backend or alert. Any missing, wrong-BOM,
tampered, old-8s or incompatible model **fails closed**. This is an
**integrity check**, not a fall accuracy or deployment certification.

Default local exact destinations:

```text
VIIL-Sentinel/
  models/pose_landmarker_lite.task
  data/private/caucafall-1500ms-linear-research-model-20261028.json
```

Google Drive is private until the owner grants team-specific access.
Members 1 and 2 must NOT use research shadow positives as real incidents;
only the original heuristic emits v1 unconfirmed local candidate JSON.

## Mandatory delivery acceptance

- Synthetic v1 envelope passes the canonical Schema; extra keys,
  fake consent, non-UUID IDs and calibrated probability claims fail.
- Actual 1500ms weight JSON passes private numeric and provenance
  validation; original 8s reader refuses it and vice versa.
- Source video/pose/weights never committed or transmitted.
- Backend ingestion, Meta real provider and persistent notifications
  are still explicitly unimplemented. Backend/Meta belong to Member 2;
  frontend notifications and caregiver UX belong to Member 1.
- Independent two-human onset review, new actor/camera blind test
  cohorts and long no-fall negatives are still MISSING. Therefore
  no real-world fall sensitivity / false alerts-hour / onset delay claim.
- The only allowed integration is member/feature/preprod; shared preprod
  and main stay human controlled.
