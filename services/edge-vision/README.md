# Edge Vision module — implementation planned

Responsibilities: webcam/prerecorded video source adapters; person/patient-agnostic pose estimation; temporal fall-candidate logic; event timestamps; keyframe selection and minimization.

Output contract (proposed):
```json
{"source_id":"staged-camera-01","confidence":0.8,"timestamp":"2026-10-27T12:00:00Z","evidence_refs":["authorized-frame-01"]}
```

The backend currently uses *simulated* events to exercise downstream workflows. No real detector is implemented, trained, or claimed.
Do not copy AFDCare code, research model checkpoints or datasets unless officially permitted.
