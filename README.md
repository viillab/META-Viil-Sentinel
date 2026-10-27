# VIIL Sentinel
**Autonomous Fall Detection & Rescue Agent via Edge Vision — Hackathon MVP**

> **Local development foundation, not a finished fall detector or medical product.** This repository was freshly developed during the 2026 Meta Global AI Developer Hackathon. Existing AFDCare code, model weights, research datasets and proprietary assets have not been copied.

VIIL Sentinel aims to provide **non-clinical, human-supervised incident awareness**:
Video → Edge fall candidate → Evidence extraction → Meta multimodal incident interpretation → Structured report → In-app alert → Caregiver verification → Traceable incident management.

## Status

| Component | Foundation | Real functionality |
|---|---|---|
| FastAPI Incident API | Implemented | In-memory, local demo only |
| Review state machine + audit trail | Implemented | Human-controlled demo workflow |
| Mock incident interpretation | Implemented | Clearly labelled simulation only |
| Meta Model API | Interface defined | **Not yet connected** |
| Webcam/recorded video/pose estimation | Temporal pose heuristic and optional MediaPipe video runner added (Member 1) | **Unvalidated heuristic; requires external pose model and authorized recordings** |
| React caregiver dashboard | Implemented | Simulated events via API |
| In-app notifications | Simulated feed | External channels not implemented |
| Evaluation | Protocol documented | Benchmarks pending |

### Quick start on Windows

**Backend — terminal 1 (Python 3.11+)**

```powershell
cd D:\VIIL-Sentinel\services\api
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- API docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health
- Run tests: `python -m pytest -q`

**Dashboard — terminal 2 (Node.js 20.19+ or 22.12+)**

```powershell
cd D:\VIIL-Sentinel\apps\dashboard
npm install
npm run dev
```

Open http://127.0.0.1:5173. Click **Generate staged incident** to test the mock workflow.

**Important:** Do not add `META_MODEL_API_KEY` until Meta's official API contract, billing, data governance and image authorization have been confirmed. The code never accesses Meta AI while `META_PROVIDER=mock`.

## Architecture

- `services/api`: Small FastAPI app with schemas, workflow, in-memory store and mock interpreter.
- `services/edge-vision`: Member 1 pose-feature temporal heuristic, optional MediaPipe webcam/video runner, synthetic tests and evaluation metrics; see its README.
- `apps/dashboard`: React + TypeScript caregiver demonstration UI.
- `services/edge-vision`: Planned webcam/video/pose + temporal classifier interface.
- `services/meta-intelligence`: Planned official Meta API adapter and schema validation.
- `services/orchestrator`: Documentation for controlled incident flow.
- `docs/`: Roadmap, eligibility checks, architectural decisions and demo script.
- `evaluation/`: Metrics and staged-data evaluation protocol.

This is a **single-process backend with modular components**, deliberately not a multi-service production deployment.

## Competition compliance

- New work between **26 Oct and 4 Nov 2026**; preserve Git history and distinguish all reused dependencies.
- Team size: three approved members, within the four-person limit.
- Repository may remain Private during development based on organizer confirmation; make **Public before submission** and test in a logged-out browser.
- Submit a **3-minute demo video**, team roster and public repository link.
- Deadline: **5 Nov 2026, 09:00 ICT**; internal target **4 Nov 2026, 21:00 ICT**.
- Don't present mock outputs as working CV or Meta model inference.
- Anti-project risks: avoid simple image analyzer, dashboard-only project or AI medical advice.
- No autonomous emergency dispatch or diagnostic statements.
- Consult `docs/competition/RULES.md` before submitting.

## Next development milestones

1. Create a safe webcam/recorded-video source interface using staged or permitted material.
2. Implement and evaluate temporal fall candidate detection.
3. Implement evidence/keyframe selection and PII minimization.
4. Verify the latest Meta Model API documentation and implement a **real** vision adapter with strict cost limits.
5. Implement evidence-grounded JSON validation and unsupported-claim testing.
6. Add persistent incident storage, authenticated caregivers, real in-app notification delivery and reliable retry.
7. Record reproducible metrics and a 3-minute honest demo.

## Project safety and scope
Research/staged demonstration only. Use human verification for all consequential decisions. This is not a medical device, patient monitoring guarantee or rescue dispatcher.

See `SECURITY.md`, `CONTRIBUTING.md` and `docs/architecture/ARCHITECTURE.md`.
