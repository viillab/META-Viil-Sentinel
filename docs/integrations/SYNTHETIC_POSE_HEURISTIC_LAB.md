# Synthetic browser Pose trace · Member 1 (offline)

This is a **research-only demonstration** of the same
`LocalFallCandidateHeuristic` that the consent-gated Laptop Webcam Demo
uses. It does **not** run the MediaPipe model, read a camera, produce
`viil.edge.candidate.v1` JSONL, call the backend or Meta API, send a
caregiver notification, or confirm a real fall.

## Demo in Dashboard

1. Start `apps/dashboard` locally using the existing Vite commands.
2. Open **AI Detect Test Lab → 04 / Browser heuristic · synthetic Pose trace**.
3. Click **Run synthetic fall trace**. The deterministic invented 7-step
   motion sequence has two upright poses followed by descent to a
   horizontal torso; it produces exactly **one UNCONFIRMED candidate**
   at a synthetic, source-relative offset of **1000 ms**.
4. Select individual step buttons to read the *derived* heuristic state,
   hip Y and torso angle, not saved landmarks.
5. Select sitting, horizontal-without-baseline, tracking-loss or
   multiple-people scenarios. Each must produce **zero candidates**.
   Incomplete tracking fails closed and never implies a safe scene.
6. Click **Clear synthetic trace** to clear the report.

This is **not** a real fall-detection benchmark: the data were specifically
constructed to exercise threshold rules. No sensitivity, specificity,
accuracy, precision, false-alarm rate or practical clinical validity can be
inferred. The Python Edge emitter has a **separate** synthetic handoff test
and its output is not equated with this browser heuristic.

## Run tests

```powershell
cd D:\VIIL-Sentinel\apps\dashboard
node --experimental-strip-types --test tests/syntheticPoseTrace.test.mjs
npm run smoke:fake-webcam
npm run build
```

The Node test executes the actual browser heuristic against all scenarios
and asserts bounded, deterministic, metadata-only output. The existing
Chrome Headless/Canvas smoke also clicks all five scenario buttons in the
real React UI **after closing the simulated camera**, checks that no POST
requests occurred, and ensures the fall event is always marked unconfirmed.
The default smoke uses neither the operator's camera nor the private
`.task` model. For the *separate* real MediaPipe CPU synthetic-video test
see `LAPTOP_WEBCAM_DEMO.md`.

This file is a developer test artifact, not permission to access RTSP,
USB cameras, personally identifiable records, or send real alerts.
