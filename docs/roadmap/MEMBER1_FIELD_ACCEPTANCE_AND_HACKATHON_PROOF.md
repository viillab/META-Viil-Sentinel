# VIIL-Sentinel — Member 1 Field Acceptance & Competition Proof Kit

**28 October 2026 · Offline/metadata-only verification. NOT a real-world
fall reliability report, legal audit, clinical certification or live alert.**

Official hackathon page distinguishes:
- Indie track: creativity, technical ambition, and whether it works.
- Startup track: technical execution and whether it holds up in production.

Source: https://dev.meta.ai/events/global-hackathon
The **project deadline listed there** is November 4, 2026 at 9:00 PM ET;
confirm local organizer updates and your actual assigned track. The public
event page does NOT assign specific numerical scoring weights to these
criteria. Never cite unrelated hackathons' percentage rubrics.

## 1 — Reproducible offline proof (no API, camera or patient data)

From the repo's `services/edge-vision` directory:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.field_acceptance
# After pip install -e .:
viil-edge-field-acceptance

# Optional: check LOCAL private MediaPipe task + research model SHA
.\.venv\Scripts\python.exe -m sentinel_edge.field_acceptance --verify-local-models
```

Outputs ONE privacy-minimal JSON line with:
- canonical **synthetic** fall count (1) and synthetic sitting candidate count
  (0), derived by running the existing Edge producer against test traces;
- exact shared `viil.backend.integration_overview.v1` and
  `viil.backend.caregiver_inbox.v1` metadata schema presence and limits;
- optional local ignored private model integrity, **not** accuracy;
- optional per-camera *configuration-only* checks;
- all remaining blockers, explicitly marking `production_or_clinical_use_authorized=false`.

A successful exit code means **offline developer contract verification passed**,
not that a clinical or unattended fall detector is safe. No images, raw pose,
camera names, RTSP endpoints, URLs, API keys, private IDs or event UUIDs
appear in the report.

## 2 — Check local multi-vendor camera *configuration* safely

A responsible operator must first complete legal/privacy review for the
actual cameras. Sign an approval through the documented reviewer procedure
in `docs/security/GLOBAL_PRIVACY_SECURITY_BASELINE.md`. Keep private JSON
and `VIIL_PRIVACY_APPROVAL_KEY` outside Git.

Set the device's authorized RTSP secret in the appropriate
`VIIL_...` environment variable, and then run:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.field_acceptance `
  --camera-registry C:\PrivateConfig\cameras.json `
  --privacy-approval C:\PrivateConfig\approved-privacy.json `
  --camera-id zone-a --camera-id operator-usb
```

**This verifies only** matching camera IDs, registry safety, private-address
RTSP syntax/allowed port/required secret presence, scoped HMAC approval,
expiry and static policy restrictions. It does NOT connect to the camera,
decode a frame, test password correctness, measure FPS, read a private IP
over the network or execute AI.

The command rejects malformed/partial configuration, unknown/duplicate IDs
and unapproved sources *before* any network access. Reports only counts
of RTSP and USB cameras, not actual device identifiers or credentials.

## 3 — Actual field test (human operator, controlled conditions)

After approvals and physical camera availability, perform *separately*:

1. Test at least one RTSP-compatible camera from each available vendor
   and one USB/UVC source, including RTSP codec/firmware combinations.
   Start with the existing `sentinel_edge.camera_health` and the
   privacy-approved `sentinel_edge.runner` / `camera_fleet` commands
   documented under `docs/integrations/`. **Never run on unapproved people.**
2. Record actual 30+ minute sustained capture with stable duration,
   per-source FPS p50/p95, decode/inference latency p50/p95, reconnect
   behavior, sampled RSS, CPU, codec and frame count. Use sanitized
   records only in reports; keep camera credentials/footage private.
3. Independent human onset/offset review on consented staged falls
   and long no-fall activities; hold out people and cameras across
   training and test. Track false alarms per annotated no-fall hour,
   missed falls, pose abstentions and response delay. Never claim
   precision/recall from the single synthetic fixture.
4. Test camera disconnect, backend disconnected, privacy revocation,
   Meta provider unavailable, duplicate event, and multi-person
   ambiguity, validating **fail-closed** behavior.
5. Have users and caregivers with visual, auditory, mobility and
   cognitive accessibility requirements test the Caregiver Inbox and
   alternative means of asking for assistance. Record actual feedback.
6. Member 2 must separately prove authenticated per-source ingestion,
   allowed evidence transfer, actual Meta API invocation/provenance,
   auditable notification delivery/receipt and backend permission checks
   before any real end-to-end alert can be claimed.

If any of those are missing, the project remains a prototype regardless
of whether Node/Python tests and GitHub CI are green.

## 4 — Judge demo script (three-minute technical story)

- **0:00–0:35:** Problem & impact: people who may not be able to reach
  a phone after a suspected fall; include wheelchair-transfer ambiguity,
  accessibility, and the need for human follow-up.
- **0:35–1:10:** Show Edge Camera Registry support for vendor-neutral
  RTSP/USB; actual detection uses MediaPipe + temporal event processing.
  If no physical camera is available, run the synthetic local trace
  and explicitly say so. No real person/fall accuracy claim.
- **1:10–1:40:** Open Dashboard **AI Detect Test Lab** and load the
  canonical synthetic Fall and Sitting examples. Explain unconfirmed
  score, source-relative time and privacy-minimal JSON.
- **1:40–2:10:** Show Privacy Approval Gate and this new Field Acceptance
  JSON, plus a rejected/expired-camera scenario. Explain why no private
  video is automatically sent to Meta.
- **2:10–2:40:** Open Integration Center or Judge Walkthrough if merged;
  show proposed Meta role: contextual reasoning on lawfully authorized
  keyframes, not heavy 24/7 cloud inference. Explicitly distinguish
  mock/provider-unavailable from genuine Meta.
- **2:40–3:00:** Show accessible Caregiver Inbox with fictional preview.
  Human follow-up, keyboard accessibility, no fabricated delivery.
  Finish with measured results and clear remaining integration gates.

Note: Judge Walkthrough UI may be developed in another parallel Member 1
branch. This kit does NOT depend on that page and does not alter its files.

## 5 — Security and acceptance principles

- Keep API provider credentials server-side. No browser calls to Meta.
- No raw CCTV or identifying pose traces in public Git or test outputs.
- Never bypass signed Privacy Gate for real capture.
- A synthetic candidate does not prove model accuracy or response time.
- Model verification is not authorization. Legal and medical classification
  require qualified review in each relevant jurisdiction.
- Hackathon viability is not equivalent to life-safety reliability.

Supporting docs:
- `handoff/member1/PERFORMANCE.md`
- `handoff/member1/delivery_manifest.v1.json`
- `docs/security/GLOBAL_PRIVACY_SECURITY_BASELINE.md`
- `docs/integrations/MEMBER1_DASHBOARD_MEMBER2_META_HANDOFF.md`
- `docs/integrations/MEMBER1_ACCESSIBLE_CAREGIVER_INBOX.md`
