# Ten-day hackathon roadmap (ICT)

| Date | Main deliverable | Responsibility |
|---|---|---|
| Oct 26 | Rules, new repo, component contracts, local mock foundation | All |
| Oct 27 | Meta API image / structured-output proof, incident schemas | Meta + Backend |
| Oct 28–29 | Webcam/recorded-video pipeline; temporal fall-candidate detection | Edge Vision |
| Oct 30–31 | Muse Spark grounding, incident state machine, notification | Meta + Backend |
| Nov 1 | Meta-first assessment status, caregiver Dashboard + in-app advisory with human fallback | Member 1 frontend + Member 2 Meta/backend |
| Nov 2 | End-to-end tests and benchmark with staged evidence | All |
| Nov 3 | Feature freeze, 3-minute demo, technical documentation | All |
| Nov 4 (21:00 ICT) | Internal submission target and logged-out public repo check | Team lead |
| Nov 5 (09:00 ICT) | Official deadline | Team lead |

## Definition of Done (competition)
- Authorized staged video yields a measurable fall-candidate event.
- Selected licensed/consented frames truly pass through real Meta AI and produce a validated, grounded report (not mock). AI may screen and recommend a non-emergency in-app advisory, but invalid/uncertain outputs route to follow-up.
- Caregiver sees evidence and uncertainty, receives an in-app notification and can acknowledge/verify/reject.
- Incident lifecycle and audit history are persistent and reproducible.
- Tests cover false-alert/non-fall and API failure cases.
- Public GitHub repo, three-minute video, **both Member 1 and Member 2 registered names**, final submission receipt.

## Scope not to build during hackathon
No Hikvision hardware requirement, SAO rescue integration, medical diagnosis, autonomous ambulance dispatch, or large-scale production clinical deployment.
