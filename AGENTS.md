# VIIL Sentinel — mandatory agent development rules

Project: Meta Global AI Developer Hackathon 2026 (new work, public at submission).
Remote: https://github.com/viillab/META-Viil-Sentinel.git

## Git authority: HUMAN-ONLY MAIN

- **NEVER create commits on `main`, merge into `main`, rebase `main`, reset `main`, push to `main`, or change the default branch.** Only a human operator may promote code to `main` manually.
- AI/development assistants MUST create or switch to a topic branch based on the latest `origin/preprod`. Valid member streams are `member1/feature/*` (Edge Vision), `member2/feature/*` (Meta AI + Backend) and `member3/feature/*` (Dashboard + Notifications); maintenance may use `fix/*`, `chore/*`, `docs/*`, `test/*`. Do not start implementation on `main`.
- After every completed bounded code change: run appropriate validation, inspect the diff and secrets, commit on the topic branch, and **push that topic branch to origin**.
- **Member 1 override (27 Oct 2026):** after validation, push only the `member1/feature/*` branch. The HUMAN user explicitly reserves promotion/merging Member 1 work into `preprod`. Never merge or push `preprod` for Member 1 work without a newer, explicit instruction. Other member streams follow their assigned integration process. For conflicts or failed validation, leave `preprod` untouched and report the blocker.
- Do not force-push, delete shared branches, skip validation, or change remote visibility.
- The user explicitly delegates routine topic-branch and `preprod` pushes; this does NOT delegate any changes to `main`.
- Use reviewed commits/pull requests where possible. CI and local hooks are advisory; GitHub branch rules are required for server-side enforcement.
- If `preprod` does not exist, initialize it once from `main`; move existing uncommitted foundation work to `feature/hackathon-foundation`, then merge that feature into `preprod`.
- After Member 1 work, leave the workspace on the completed Member 1 feature branch until the human reviews or merges it. Other work may return to `preprod` after authorized integration.

## Hackathon safety
- Never copy AFDCare source/model weights/datasets unless organizer approval is verified.
- All real Meta API work needs authorized staged imagery, minimal metadata, explicit cost safeguards and backend-only API keys.
- Clearly label mocks; never portray generated mock reports as genuine live Meta AI outputs.
- No AI-generated medical advice, diagnosis, emergency dispatch or real-patient monitoring.
- Do not include any secrets, private frames, proprietary data, or copyright-restricted datasets in commits; final source must be ready for public release.

## Validation commands
- Backend: `cd services/api && python -m pytest -q && python -m ruff check .`
- Dashboard: `cd apps/dashboard && npm run build`
- Before pushes: `git diff --check`, inspect `git status` and `git diff --cached --stat`.
- Do not push changes if required tests fail; describe unverified aspects clearly.
