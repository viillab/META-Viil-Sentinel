# VIIL-Sentinel — Member 1 read-only Member 2 integration check

**30 October 2026 · Member 1 engineering handoff.** This checker
reports static evidence only and does NOT claim real backend integration,
real Meta AI, human approval, authenticated camera access or patient safety.

## Repeatable Windows operator check

From `D:\VIIL-Sentinel`:

```powershell
git fetch origin --prune
cd services\edge-vision
.\.venv\Scripts\python.exe -m sentinel_edge.member2_status
.\.venv\Scripts\python.exe -m sentinel_edge.handoff_preflight
```

The status command is **read-only and network-free**. Only the separate
`git fetch` command contacts GitHub; if GitHub access/fetch fails, the
local remote-tracking refs may be stale. The checker selects the newest
commit-dated `origin/member2/feature/*` ref, reports its SHA/date, reads
only `services/api/app/main.py` through `git show`, and examines
literal `@app.<METHOD>("/path")` decorators. It never imports/runs a
backend app, calls Meta, opens RTSP, reads approval files, changes Git,
or writes a report. Output is bounded JSON without source file contents,
camera details, credentials or runtime secrets.

`demo_incident_post_detected` means a **demo route only**. A
`candidate_ingestion_post_detected: false` result means no literal
candidate/ingest-named POST route was seen in that one backend file,
**not** that none exists in dynamic/registered routers or other files.
Even if a future route is found, all `*_verified` readiness flags remain
**false** until independently verified by Member 2 tests and security
review. Never send a real candidate to `/api/v1/incidents/demo` and
never assume that route authenticates Edge events.

### Actual snapshot after fetch — 30 October 2026

- Latest Member 2 remote-tracking branch: `origin/member2/feature/initial`
- Latest Member 2 branch HEAD: `22969e0` (28 October 2026)
- Literal backend `POST /api/v1/incidents/demo`: present
- Literal Member 2 candidate ingestion POST: **not detected**
- Source authentication, idempotency, true Meta provider, real
  incident/evidence workflow: **not verified**

This is a historical snapshot, not a continuous or automatic monitor.

### Member 2 implementation acceptance (owner: Member 2)

Before connecting Edge for actual use, Member 2 needs its own
authenticated, camera/source-scoped, size-limited candidate ingestion
endpoint that verifies the canonical
`services/edge-vision/docs/edge_candidate_v1.schema.json`.
It must reject unknown sources, invalid provenance, synthetic-to-real
mislabeling, uncalibrated scores used as calibrated probabilities,
duplicate/replayed event UUIDs and unauthorized evidence.
It must correlate source-relative timestamps with a trusted backend clock
rather than treating `source_timestamp_ms` as Unix time.
The backend must independently check identity/authorization, expiry,
idempotency and cost/privacy gates before Meta API calls or informational
notifications; no autonomous emergency dispatch or unverified medical
conclusions. The existing `meta_first_contract.py` is a future policy
proposal, **not real provider wiring**.

Keep Member 2 changes in `member2/feature/*`. Member 1's checker can be
rerun after each authorized fetch; the human promotes team integration
to protected `preprod` and `main` after real review.
