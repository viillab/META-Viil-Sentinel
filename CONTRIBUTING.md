# Team development standards

Three approved hackathon participants. We will work in separate feature branches and use pull requests for review:
- `member1/feature/edge-vision` — Member 1 (user): Edge Vision, pose/temporal fall candidates, model evaluation
- `member2/feature/meta-intelligence` — Member 2: Muse Spark, incident intelligence and backend
- `member3/feature/dashboard` — Member 3: UI, notification and integration

All members branch from `origin/preprod`. Push validated work to member branches, then integrate into `preprod`. `main` is human-only.

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
