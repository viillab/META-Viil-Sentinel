# Team development standards

Three approved hackathon participants. We will work in separate feature branches and use pull requests for review:
- `feature/edge-vision`
- `feature/meta-intelligence`
- `feature/dashboard`

Recommended checks:
- Backend: `cd services/api && python -m pytest -q && python -m ruff check .`
- Frontend: `cd apps/dashboard && npm run build`

Rules:
1. Preserve commits made during the hackathon; never rewrite them to disguise pre-existing work.
2. Never import AFDCare source, model weights, or datasets without organizer clarification.
3. Add tests and docs for new capability; use contracts between modules.
4. Clearly mark mocks, simulated data and unavailable features.
5. Do not add real API keys; use placeholders in `.env.example`.
6. No diagnosis, medical advice, or autonomous rescue dispatch.
7. Before public submission, review third-party licenses, datasets, repo history, and the three-minute honest demo.
