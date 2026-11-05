# Git strategy — Feature Branches → preprod → Human-only main

**Updated 28 Oct 2026 — exactly two active members.** Member 1 owns Edge Vision, AI model, Dashboard and Notifications; Member 2 owns Meta Model API, Backend, Database and Orchestration. Historical references to three parallel development streams are superseded. **Important precedence:** `AGENTS.md` has the current Git authority. Validated Member 1 changes integrate only into `member/feature/preprod`, not into the protected shared `preprod`, and only a human may promote to `preprod`/`main`. The legacy branch diagram below is historical, not authority to push protected branches.

```text
origin/main                  HUMAN-ONLY release/promotion
     │ (initial common ancestor)
     └──── preprod           AI-supported integration & QA
              ├── feature/edge-vision
              ├── feature/meta-intelligence
              ├── feature/dashboard
              ├── fix/...
              └── chore/...
                    │
         tests + review → commit → push topic
                    │
           merge --no-ff into preprod
                    │
                push preprod
                    │
       Only human promotes preprod → main
```

## Source of truth
- `main`: release or final production snapshot. Agents never write to this branch.
- `preprod`: shared integration branch, updated from feature branches after validation.
- `feature/*`, `fix/*`, `chore/*`, `docs/*`, `test/*`: isolated work, pushed after validated changes.

## Default process for every change
1. `git fetch origin` and verify `git status` is clean.
2. Start from the latest `preprod`: `git switch preprod`, `git pull --ff-only origin preprod`.
3. `git switch -c feature/<topic>` (or appropriate prefix).
4. Implement and test, inspect staged changes and secret exposure.
5. `git add <reviewed paths>` and `git commit -m "type: concise change"`.
6. `git push -u origin feature/<topic>`.
7. Return to `preprod`, fast-forward from origin, merge the topic branch using `git merge --no-ff feature/<topic>`.
8. Run integration validation after merging, and `git push origin preprod`.
9. Never make any AI-created commit, merge or push on `main`.

Conflict rule: **stop and resolve carefully**; do not force-push, rewrite teammate work or auto-merge failed builds.

## Local safety hooks
Use `powershell -ExecutionPolicy Bypass -File scripts/setup-git-hooks.ps1` once per clone.
- `.githooks/pre-commit` rejects direct commits on local `main`.
- `.githooks/pre-push` rejects pushes to `refs/heads/main`.
- Hooks are local and can be bypassed; they **do not replace GitHub server-side protection**.

## GitHub settings that repository administrators should enforce
In **Settings → Rules → Rulesets** (or Branch protection rules):
- Protect `main`: require pull requests and review by the human maintainer, restrict direct pushes, disallow force-push/deletion.
- Do not grant bot accounts bypass permissions for `main`.
- Consider requiring successful backend/frontend status checks before human promotion.
- Consider protecting `preprod` from force pushes and deletion while allowing the intended integration process.
- Verify branch-protection capabilities available in your GitHub plan, particularly for private repos.

## Release
**Only the human maintainer** may review and merge/push `preprod` to `main`. Agents should prepare review notes only. Opening a PR toward `main` requires an explicit human request.

## Hackathon public-submission gate
After final checks, the team lead can change the repo from Private to Public. Inspect the **full Git history** for secrets, PII and license conflicts. The submission requires a public GitHub link and a 3-minute demo.
