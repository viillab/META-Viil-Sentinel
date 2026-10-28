# Team development standards

Exactly **two active members** as of 28 Oct 2026. We work in separate feature branches and review changes:
- `member1/feature/*` — Member 1: Edge Vision, pose/model training and evaluation, React Dashboard, UX/UI, in-app notifications and integration
- `member2/feature/*` — Member 2: Backend, Meta Model API, Meta-first evidence verification, database, security, orchestration
- **No active Member 3**. Prior `member3/feature/*` references are historical only.

Do isolated development on the member feature branch. After tests and exact-SHA CI, validated Member 1 work may be integrated into the separate `member/feature/preprod`; the shared `preprod` and `main` are human-promoted only. No force pushes. Team ownership: `handoff/team/team_roster.v1.json`.

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
