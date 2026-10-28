# VIIL-Sentinel — Member 1 Judge Demo and Submission Runbook

**28 October 2026 · Team: 2 active members · non-clinical hackathon**
**Status: offline Member 1 competition walkthrough. NOT a production fall detector.**

Official event: https://dev.meta.ai/events/global-hackathon
Project submission: **4 Nov 2026, 9:00 PM ET** (listed by the
organizer; corresponds to 5 Nov 2026, 09:00 Thailand time after the
US time-zone change, subject to official updates).

Official track framing: Indie track judges creativity, technical
ambition and whether it works; Startup judges technical execution and
real-world production robustness. The work below supports evidence
for both, not guaranteed points. The application selection criteria
are distinct from final hackathon judging.

## The story judges must understand

- **Problem:** Users with mobility limitations, including wheelchair
  users, may be unable to call a caregiver after some falls. Standard
  pose-only detectors can confuse purposeful transitions with falls.
- **Proposed solution:** Member 1 uses privacy-approved local pose
  screening to produce **unconfirmed candidate metadata**. Member 2
  authenticates source/consent and, if approved, routes minimal evidence
  to genuine Meta multimodal reasoning for contextual assessment.
  Authorized caregiver-facing events appear in Member 1's accessible UI.
- **Differentiation:** Meta should analyze ambiguous *sequences and
  context*, not merely duplicate a per-frame Edge alert. Edge keeps
  continuous low-latency screening local. Contextual Meta inference is
  conditional and must be measured against Edge-only baselines.
- **Safety:** Neither Edge nor Meta diagnoses, proves that a fall
  occurred, authorizes emergency dispatch or secretly stores video.
- **Current truth:** Member 1 has Edge v1, reproducible synthetic
  fixture, privacy gate, multi-camera orchestration and UI. Member 2
  has not delivered the authenticated ingestion / real authorized
  Meta inference / verified caregiver delivery in this branch.

## Live competition walkthrough (UI, 2–3 minutes)

Start the dashboard offline. The default screen is **Judge walkthrough**.
It makes *zero* network calls and never prompts for keys or camera access.

1. **00:00–00:20 — Problem and affected users.**
   Explain mobility and wheelchair-transfer ambiguity, and
   human-in-the-loop follow-up.
2. **00:20–00:55 — Actual Edge evidence.**
   Select **Fall-like motion**. Show six pipeline stages and canonical
   synthetic Edge Candidate v1. Open **AI Detect Test Lab** for the
   actual parsed Edge fixture and its uncalibrated score. State that
   this is NOT a real fall/clinical sensitivity test.
3. **00:55–01:30 — Meta's meaningful role.**
   Select **Wheelchair transfer**. Show how Meta *would* inspect
   authorized temporal keyframes and scene context, and why uncertain
   evidence should route to human follow-up. The UI must say this is
   **not a genuine Meta response**.
4. **01:30–02:00 — Failure gates.**
   Select **Privacy blocks Meta** then **Meta API outage**. Confirm
   no cloud image transfer on privacy denial and no silent drop of an
   Edge candidate when Meta is unavailable.
5. **02:00–02:25 — Accessible caregiver UI.**
   Open **Caregiver inbox → Preview accessible sample**. Demonstrate
   keyboard focus, larger text and high contrast; note the incident is
   fictional and *no caregiver notification was sent*.
6. **02:25–02:50 — Engineering proof.**
   Show green GitHub CI, the Member 1 offline gate, camera adapter
   contracts and shared versioned JSON schemas. Explain precisely which
   Member 2 services remain prerequisites and what tests are missing.

### Short English narrator script

> "VIIL-Sentinel is a privacy-first assistive safety prototype.
> Our Edge engine looks for possible fall-like motion locally, while
> Meta's planned multimodal reasoning adds context, such as whether
> a person is transferring from a wheelchair rather than falling.
> We separate candidates from confirmed events and require permission
> before any visual evidence can leave a device. This interactive
> walkthrough uses verified synthetic Edge output and openly marks
> the backend and Meta stages as proposed until real integration
> tests exist. Our caregiver interface is designed for accessible
> follow-up — not autonomous medical or emergency decisions."

This script describes a **prototype**, not a verified life-safety product.
Once Member 2 has implemented real Meta inference, replace the proposed
narration only with genuinely recorded, authorized results and show
provider provenance and real latency/cost metrics.

## Reproduce the demo on Windows (no API keys)

From `D:\VIIL-Sentinel`, branch `member/feature/preprod`:

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m sentinel_edge.handoff_preflight
.\.venv\Scripts\python.exe -m sentinel_edge.submission_readiness
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
cd D:\VIIL-Sentinel\apps\dashboard
npm ci
npm run build
npm run dev -- --host 127.0.0.1
```

Open `http://127.0.0.1:5173`; default is Judge walkthrough.
All displayed scenarios are fictional; the Edge fall fixture actually
passes the canonical local schema, and sitting fixture contains zero
candidates. CI verifies Node contract tests, Python Backend and Edge,
but **does not** measure real hardware performance or medical accuracy.

The command `submission_readiness` produces JSON with
`status="member1_offline_artifact_gate_passed"` and explicit blockers.
It never creates a report file, accesses a camera or calls a provider.

## Real-device / model gates still required (do not misrepresent)

**Member 1 / Edge and UX:**
- Obtain lawful staged/approved camera access and camera-specific
  signed privacy approval; otherwise DO NOT open a physical camera.
- 30+ minute soak of real USB and RTSP cameras; verify reconnect,
  CPU/RSS, decode+pose FPS, dropped frames and responsiveness.
- Human-reviewed, actor/camera-disjoint Fall and ADL footage; report
  event recall, false alarms per *annotated non-fall hour*, abstention,
  onset-delay p50/p95 and confidence intervals. Do NOT claim any
  accuracy from one staged publisher example or 148+ contract tests.
- Run keyboard/Screen Reader/large-text and high-contrast testing
  with target users; WCAG 2.2 AA is a goal, not certified.
- Video demo with *clear permission for any real subjects*; otherwise
  show only the existing non-identifying synthetic fixture.

**Member 2 (do not implement from Member 1 branch):**
- Authenticated device ingestion, deduplication, per-camera RBAC,
  audit logs, consent/evidence gateway, privacy transfer approval.
- Actual Meta multimodal API request/response provenance, structured
  output checks, costs and graceful outage handling.
- Authenticated caregiver inbox, real idempotent delivery, delivery
  receipts, acknowledgements and review policy.
- Data-protection assessment, retention policy, security test and
  jurisdiction-specific legal signoff before real-world monitoring.

## Judge proof checklist

- The default walkthrough shows 5 clearly simulated scenarios
  and 6 bounded owner-marked stages.
- No real model call, sensitive video, outbound network or notification
  can be triggered in Judge Walkthrough.
- Edge Test Lab parses the canonical v1 synthetic event; the sitting
  trace produces zero events without making an accuracy claim.
- Privacy-denied and Meta-unavailable paths remain clearly blocked
  / under human follow-up.
- Integration Center and Caregiver Inbox are metadata-only, fail-closed,
  and explicitly label sample data.
- `npm run build`, Edge pytest/Ruff, Backend regression and hosted CI
  have passing evidence for the exact submitted commit.
- Model accuracy, actual Meta API use and device soak are described as
  **unverified** unless genuinely tested.
- Confirm all application/submission forms, team track, licences,
  participant rules and demo assets before the official deadline.

## Official context

- https://dev.meta.ai/events/global-hackathon
- https://events.cerebralvalley.ai/e/meta-ai-developer-hackathon
- https://www.w3.org/TR/WCAG22/
