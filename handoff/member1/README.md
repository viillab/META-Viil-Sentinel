# VIIL Sentinel — Member 1 handoff

**28 October 2026 · Owner: Member 1 Edge Vision**
**Status: READY FOR DEVELOPER HANDOFF, NOT A PRODUCTION FALL DETECTOR**

Start here. The adjacent delivery_manifest.v1.json is the machine-readable
contract inventory, ARCHITECTURE.md is the folder map and PERFORMANCE.md
records actual machine measurements. All old package imports and CI
entrypoints are intentionally preserved: no disruptive mass folder move.

## What other members can consume

| Interface | Consumer | Readiness |
|---|---|---|
| viil.edge.candidate.v1 metadata-only heuristic JSON | Member 2 Backend | **Producer/schema READY**; no authenticated ingestion yet |
| Backend validated incident state | Member 3 UI | Demo exists; real ingestion/notifications NOT YET |
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
- Preserve unconfirmed status; display and act only after human review.
  No medical advice, real emergency dispatch, unconsented video or pose.
- Meta real provider still needs separate authorization, API keys only on
  backend and output validation. Do not portray MOCK outputs as real.

## Member 3 — exact integration handoff

React demo consumes the backend's simulated incident feed. It does NOT
currently consume the Edge v1 local stdout stream. Add a human-facing
state/UI only after Member 2 validates incidents, implements secure durable
storage and authenticated review. The 0..1 Edge detector_score is
UNCALIBRATED HEURISTIC, not a probability of true fall. Clearly mark DEMO
data; do not offer emergency actions or use shadow counters as events.

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

## Mandatory delivery acceptance

- Synthetic v1 envelope passes the canonical Schema; extra keys,
  fake consent, non-UUID IDs and calibrated probability claims fail.
- Actual 1500ms weight JSON passes private numeric and provenance
  validation; original 8s reader refuses it and vice versa.
- Source video/pose/weights never committed or transmitted.
- Backend ingestion, Meta real provider and persistent notifications
  are still explicitly unimplemented. They are Member 2/3 responsibilities.
- Independent two-human onset review, new actor/camera blind test
  cohorts and long no-fall negatives are still MISSING. Therefore
  no real-world fall sensitivity / false alerts-hour / onset delay claim.
- The only allowed integration is member/feature/preprod; shared preprod
  and main stay human controlled.
