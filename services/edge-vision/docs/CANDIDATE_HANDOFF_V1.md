# Member 1 → Member 2: Edge Candidate Contract v1

**Version:** `viil.edge.candidate.v1`
**Owner:** Member 1, Edge Vision
**Consumer (planned):** Member 2, Meta Intelligence + authenticated incident orchestration
**Status:** Local metadata-only handoff schema; **no ingestion endpoint** is implemented.

## Semantics

An event is an **UNVERIFIED FALL CANDIDATE** emitted by a non-clinical,
uncalibrated pose-geometry heuristic. It is **not a diagnosis, not a confirmed
fall, not a medical severity score, and not emergency dispatch authorization**.

The envelope is intentionally minimal:

- `event_id`: canonical UUID of one detector event; a future authorized
  receiver may use this to detect duplicate deliveries
- `source_id`: pseudonymous ASCII camera/clip identifier, not a person name
- `source_timestamp_ms`: monotonic source-relative timestamp, **NOT UTC time**
- `timestamp_basis`: fixed `relative_to_source_start`
- `detector` and optional lowercase SHA-256 model bundle checksum for reproducibility
- `detector_score`: `0..1` **uncalibrated heuristic**, `score_calibrated=false`
- `input_provenance`: `synthetic_pose_trace`, `consented_staged_video` or
  `authorized_local_camera` — caller-declared and not evidence of consent
- `confirmed_fall=false`, `human_review_required=true`,
  `medical_assessment_performed=false`
- `evidence_refs=[]`: references are **deliberately prohibited** at this stage
- `delivery_mode=local_stdout_only`: this code does not call a network API

The application does NOT transmit images, raw landmarks, paths, facial
identifiers, people names, evidence notes, private recordings or health details
through this envelope. All input still requires lawful authorization, and the
schema cannot independently verify it. The producer **rejects** attempts
to include unreviewed evidence refs or invalid source identifiers.

## Synthetic contract demonstration

From `services/edge-vision`:

```powershell
python -m sentinel_edge.handoff_cli --trace examples/synthetic/fall.jsonl --source-id fictional-01 --provenance synthetic_pose_trace
```

Outputs one JSONL event (a new UUID on every run); synthetic flag is true,
no request is made to an API. With the current pinned synthetic fall trace,
the actual Python emitter produces source-relative offset **850 ms** and
uncalibrated heuristic score **0.928** (not probability). The corresponding
`sitting.jsonl` fixture produces no event. No frame/image data is present.
`--model-sha256` is
optional; **do not fabricate a hash** for synthetic numerical fixtures.

To process an authorized staged pose trace, specify
`--provenance consented_staged_video --authorized-staged-data`.
The flag is an acknowledgment by the operator, not automated consent proof.
No output is written until the entire trace has validated successfully.

## Real local-video/webcam runner output

Use the existing authorized local runner:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge --source "D:\staged-private\fall01.mp4" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --source-id staged-clip-01 --candidate-format v1 --confirm-consent
```

For local webcam replace the source with `0`. This mode computes the
actual local model SHA-256 and emits the exact same versioned JSONL contract
from the `process_capture` detector. It never sends data to Meta AI or
any backend. Only use it with the owner's explicit permission.

## Frozen v1 schema safeguards (1 Nov 2026)

Before a Member 2 handoff, run the **offline** command
`python -m sentinel_edge.handoff_preflight`. In addition to comparing
synthetic emitted fields and a single fall/non-fall trace, the preflight
now freezes the **entire safety-relevant v1 JSON Schema property
constraints**: unconfirmed and human-reviewed status, zero evidence
references, uncalibrated score in 0..1, exact source-relative timestamp
basis, simulated boolean, allowed provenance, UUID/source/detector
identifiers, optional SHA-256 syntax, and `local_stdout_only` delivery.
Changing only these schema restrictions (even without changing field
names or the example payload) causes a fail-closed error. Dedicated
mutation tests verify this behavior. The preflight additionally compares
all non-UUID fields of the canonical synthetic example against freshly
emitted Python output, preventing stale judge/demo figures.

**Actual Python → TypeScript contract smoke (no network/media):**

```powershell
cd D:\VIIL-Sentinel\apps\dashboard
node --experimental-strip-types scripts/verify-edge-emitter.mjs --python D:\VIIL-Sentinel\services\edge-vision\.venv\Scripts\python.exe
```

This runs both real Python CLI synthetic traces and parses stdout with
Dashboard's production `parseEdgeCandidateJsonl` adapter. It requires a
previously installed local Edge package, returns no candidate IDs, validates
that no-fall remains empty, and rejects forged staged authorization/source
identifiers. The dedicated `edge-dashboard-contract` GitHub CI job runs the
same check with Python 3.12 and Node 22. Synthetic contract success is **not**
camera validation, model accuracy, real Meta API or backend ingestion.

This check is a **version-specific repository contract drift guard**,
not a general JSON Schema parser, input authorization test, or a proof
that Member 2 securely accepts untrusted data. Member 2 still needs
independent strict request-body schema validation, authenticated source
identity, replay/idempotency controls, and signed site/privacy review
before real ingestion. Legitimate semantic changes require a separately
reviewed versioned contract, not relaxing v1 in place.

## Integration requirements for Member 2

1. Implement an **authenticated and authorized** ingestion endpoint, with
   content-type/version validation, schema validation and rate limiting.
2. Restrict allowed sources to authorized devices/clips; never trust
   `input_provenance` or the consent flag as independent consent proof.
3. Verify `model_sha256` against an approved registry; reject unknown versions.
4. Use `event_id` as an **idempotency key** with durable storage and replay
   protection; no durable transport/outbox exists in Member 1.
5. Convert timestamp to wall-clock time only when a trusted, synchronized
   source start timestamp is available; never misinterpret as Unix epoch.
6. Keep `confirmed_fall=false` from the uncalibrated Edge producer. A future
   Meta-first authorized evidence assessment may propose an **informational
   caregiver advisory** without a person screening every candidate, but
   must never relabel the original Edge candidate as a verified fall.
   Invalid/uncertain/negative/missing visual evidence remains unconfirmed
   for follow-up; never silently discard on generative-model output alone.
   Any consequential response remains human-controlled. Document the
   false-positive and missed-fall evaluation before enabling automation.
7. Store only necessary metadata with retention/access controls; obtain
   separate authorization before selecting or sending keyframes.
8. Keep the existing `/api/v1/incidents/demo` **strictly simulated**.
   Do not post real detector events to it.
9. Document if the receiver changes schema, scoring or semantics before
   using it for any demo or public repository.

## Known limitations

There are currently no reliable real-fall performance measurements or
real-person benchmark results. The existing tests use synthetic pose
transitions and a black-video negative control. This contract only
validates event serialization and provenance labeling.
