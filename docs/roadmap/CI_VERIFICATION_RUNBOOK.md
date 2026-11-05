# VIIL-Sentinel — CI verification for Member 1 (28 Oct 2026)

GitHub Actions CI on every push and pull request runs three jobs:
- `backend`: FastAPI tests + Ruff (Member 2's ownership).
- `edge-vision`: Python tests + Ruff (Member 1's ownership).
- `dashboard`: npm contract tests, TypeScript and production build (Member 1's ownership).

As of this update, jobs use Ubuntu 24.04 (pinned to avoid the October–November
2026 ubuntu-latest image migration), Node 24 compatible official Actions v6,
minimal read permissions, 15-minute per-job timeout and `npm ci` from lockfile.
These changes must pass a **real hosted CI run**, not just local code checks.

## Member 1 safe delivery gate
1. Work on `member1/feature/*` branch; never modify `main` or shared `preprod`.
2. Run targeted and full local tests with the **project venv** (not global Python):
   `services/edge-vision/.venv/Scripts/python.exe -m pytest -q`
   and `-m ruff check .`.
3. `git diff --check`, review staged diff and scan for tokens, camera URLs,
   captured images, private datasets and model weights.
4. Push topic branch; merge verified work to `member/feature/preprod`, then push.
5. Verify the **exact merge SHA** using GitHub Actions on the repository:
   `gh run list --repo viillab/META-Viil-Sentinel --branch member/feature/preprod --limit 5`
   `gh run watch <run-id> --repo viillab/META-Viil-Sentinel --exit-status`
6. Inspect all three jobs for success; on failures, read logs and fix on a
   Member 1 topic branch. Do not state hosted CI passed while it is queued/running.
7. Check warnings separately; a green run can still contain deprecations.

**Privacy:** no camera secrets in environment dumps, CI artifacts, issue text or
logs. Live RTSP access is not part of public hosted CI. Fake capture + consent-safe
fixtures exercise the implementation in CI.

CI automatically runs on code changes; this guide is not a continuous scheduled
monitor/notification service. A separate watcher or authorized notification
workflow would be required for out-of-band alerts.
