# VIIL-Sentinel — Full-Stack Test & Security Audit

**Audit date:** 2026-11-01 (KST)
**Repository:** `viillab/META-Viil-Sentinel`
**Audited baseline:** `member/feature/preprod` @ `43b5e05362d6fb14d3dbc7d6fd2539fecdc21505`
**Scope:** Member 1 Edge Vision, local camera bridge, Dashboard, Member 2 demo Backend, versioned handoffs, locally installed dependencies, reachable Git history and CI.
**Evidence basis:** Real command executions on the connected Windows workstation, not inferred from green labels or earlier conversations.
**Safety boundary:** No real Hikvision frames decoded, no private signed operator policy generated, no Meta provider called, no genuine caregiver alert sent. All live/evidence prerequisites remain blocked.

## Decision

- **Offline developer demo / contract verification:** PASS under synthetic-only and local prototype conditions.
- **Automated tests, lint, build, dependency consistency:** PASS on the audited checkout.
- **Production deployment or real-person fall monitoring:** **NOT APPROVED / NOT VERIFIED**. Green CI does not prove real-world accuracy, identity/authorization, or lawful camera access.
- **Security:** One independently reproduced **production-blocking authorization gap** in the demo Backend's read routes, plus unfinished ingestion, persistence, security telemetry and end-to-end integration. Python toolchain advisory findings require remediation before release use. The audit also annotated two legacy non-security digest uses, eliminating two misleading HIGH Bandit heuristic flags without changing their output.
- **Ownership:** Member 1 fixes only Edge/Dashboard/handoff. Member 2 owns API authentication, storage, Meta, incident/evidence and delivery. Do not use this report as authorization to modify Member 2's branch or promote protected `preprod`/`main`.

## Automated evidence matrix

| Gate / invocation | Observed result | Notes |
|---|---|---|
| Edge: `services/edge-vision/.venv/Scripts/python.exe -m pytest -q tests` | PASS, **1,250/1,250** | Re-run after digest annotations: 1,250 passed, 1 existing Starlette/httpx2 warning, primarily synthetic/fixture-based |
| Backend: `services/api/.venv/Scripts/python.exe -m pytest -q tests` | PASS, **34/34** | Explicit correct Backend venv; existing Starlette warning |
| Dashboard: `cd apps/dashboard && npm run test:contract` | PASS, **223/223** | Node contract tests; no actual browser hardware or screen-reader E2E |
| Dashboard: `cd apps/dashboard && npm run build` | PASS | Includes contract tests, TypeScript compilation and Vite build |
| Edge: `python -m ruff check .` | PASS | Standard project lint rules |
| Research dataset legacy digest regression tests | PASS, **20/20** | Post-audit annotation of MD5/SHA-1 as `usedforsecurity=False`; digest bytes unchanged |
| Backend: `python -m ruff check .` | PASS | Standard project lint rules |
| Both environments: `python -m pip check` | PASS | No broken local dependency requirements |
| Dashboard: `npm audit --json` | PASS, **0 reported vulnerabilities** | Registry advisory database at scan time; reports 119 dependency entries |
| `python -m sentinel_edge.handoff_preflight` | PASS | `viil.edge.candidate.v1`; synthetic fall 1, sitting/non-fall 0; no network |
| `python -m sentinel_edge.submission_readiness` | PASS **offline artifact gate only** | Five fictional demo scenarios; production_ready=false; real accuracy false |
| `python -m sentinel_edge.member2_status` | PASS, static inspection | Remote-tracking branch snapshot only; cannot certify actual API security |
| `git diff --check`, Git worktree | PASS | Clean audited starting baseline |
| `git fsck --no-reflogs --connectivity-only` | exit 0 | Dangling/unreachable blobs reported; not a connectivity failure; unreachable objects were not part of normal reachable-history secret scan |
| GitHub Actions baseline [41287861528](https://github.com/viillab/META-Viil-Sentinel/actions/runs/41287861528) | PASS, **3/3** | Backend, Edge Vision, Dashboard on baseline SHA `43b5e05` |

**Total automated tests:** **1,507** (Edge 1,250, Backend 34, Dashboard 223). This is unit/contract/synthetic coverage, **not** measured percent code coverage, browser acceptance, model accuracy, camera soak, or pen testing. `pytest-cov` is not installed in the checked Edge environment, and no coverage percentage was claimed.

## Security findings (ranked by practical impact)

### P0 — Production blockers

**SEC-01 · Member 2 · Unauthenticated incident reads outside Demo Mode**
Reproduced with FastAPI `TestClient(create_app(Settings(demo_mode=False)))` without credentials:

| Request | HTTP | Implication |
|---|---:|---|
| `GET /health` | 200 | Expected public health route |
| `GET /api/v1/incidents` | **200** | Incident collection has no authentication even when demo is disabled |
| `POST /api/v1/incidents/demo` | 403 | Demo write correctly disabled |
| `POST /api/v1/incidents/{id}/review` | 403 | Review mutation correctly disabled |

`GET /api/v1/incidents/{incident_id}` is also defined without a credential/dependency guard. Current `IncidentRepository` is in-memory demo data, so **no actual real-person data breach is asserted**. Exposure becomes unacceptable if this API is deployed beyond a trusted local network or fed real records. **Fix/acceptance:** Member 2 deny unauthenticated/unauthorized list and detail reads, enforce tenant/source-scoped RBAC, and add negative/positive tests in both demo and non-demo modes **before any external deployment**.

**INT-01 · Member 2 · No authenticated Edge Candidate v1 intake**
The reviewed Backend `services/api/app/main.py` contains a simulated incident POST but no literal candidate/ingest-named POST. Route inventory is **limited to literal app decorators in that file**, not dynamic routers. Handoff declares `backend_ingestion_ready=false` and `delivery_mode=local_stdout_only`. **Acceptance:** authenticated source-scoped `viil.edge.candidate.v1` validation, size/rate bounds, durable event UUID idempotency/replay protection, trusted clock anchoring, provenance/consent verification and independent server-side checks. Never feed real Edge candidates into the demo endpoint.

**INT-02 · Member 2 · External inference, persistence, caregiver delivery unverified**
`provider_for` supports `mock` only and rejects non-mock providers; the Meta-first routing contract is a proposal, not an invoked real model. `IncidentRepository` is process-memory only. `notification_sent=true` means **in-app demo state only**, not delivered SMS/email/emergency services. Actual Meta multimodal request signatures, backend-only key management, cost ceilings, validated evidence, reliable storage, delivery receipts and incident authorization remain unimplemented/unverified.

**SAFE-01 · Member 1 + accountable human reviewer · Physical camera and real-world safety gates blocked**
No genuinely completed site/person privacy assessment and signed permission was established by this audit; **no Hikvision media was opened**. Previous RTSP OPTIONS/port handshakes and synthetic MJPEG/browser tests cannot establish first decoded camera frames. No independent human-labeled fall-vs-ADL measurements, actor/camera-disjoint recall, false alarms/hour, onset delay, uncertainty bounds or 30-minute reconnect soak were verified. Never claim safety/medical/production readiness.

### P1 — Dependency, defensive parsing and validation work

**DEP-01 · Build/developer toolchains · `pip-audit` advisory findings**
The scanner used the installed distributions in each virtual environment via `--path` and queried the advisory database. Findings were deduplicated by **package + advisory ID**; repeated feed entries were not double-counted:

| Environment | Package/version | Unique reported advisory IDs | Remediation candidate |
|---|---|---:|---|
| Edge venv | `pip 24.0` | 6 | latest compatible pip at or beyond 26.2 |
| Edge venv | `setuptools 65.5.0` | 5 | latest compatible setuptools at or beyond 84.1.0 |
| API venv | `pip 25.0.1` | 6 | latest compatible pip at or beyond 26.2 |

The 6 pip advisory IDs overlap across both virtual environments. The scanner reported **no other versioned application runtime dependencies with advisories** in these scans, but that does **not** establish that the project or transitive dependencies are vulnerability-free. Editable local project distributions without a reliable published version were not interpreted as third-party vulnerabilities. `pip`/`setuptools` are tooling/install surfaces rather than observed exposed HTTP endpoints. **Do not blindly upgrade a live environment**: recreate/test a dedicated venv, pin compatible build tools, re-run `pip-audit`, `pip check` and all suites. Findings are time-sensitive.

**SEC-02 · Member 1 · Bandit static findings, triaged in source context**
`bandit 1.7.8 -r services/api/app services/edge-vision/sentinel_edge services/edge-vision/scripts -f json -q` initially found **29 findings: 2 HIGH, 3 MEDIUM, 24 LOW**. After explicitly marking both publisher/Git legacy digest calls as **`usedforsecurity=False`**, the identical scope re-scan reports **27: 0 HIGH, 3 MEDIUM, 24 LOW**. This removes non-security hashing *heuristic alerts*, not SHA-1 collision weaknesses or a requirement for independent integrity pins. Scanner severity is not a confirmed exploit:

- Originally `B324` HIGH at `ikar_domain_stress.py`: legacy publisher MD5 archive comparison **alongside pinned SHA-256**. The call is now marked non-security; SHA-256 remains the strong integrity anchor and output is unchanged.
- Originally `B324` HIGH at `public_dataset_ingest.py`: SHA-1 is the publisher's **Git blob identifier** for immutable pinned-commit research clips, not authentication. The call is now marked non-security, with unchanged Git blob bytes. It is still weaker than independent SHA-256 content integrity. Pin SHA-256 per clip before promoting third-party data into a trusted model pipeline.
- `B314` MEDIUM at `hikvision_isapi_audit.py`: standard-library `ElementTree.fromstring` on untrusted camera XML. Existing **64-KiB cap, DOCTYPE/ENTITY rejection, strict codec fields** mitigate simple payloads but are not a proof against every XML parser vulnerability. Use a reviewed hardened XML parser and test crafted DTD/entity payloads, keeping camera access read-only.
- `B310` MEDIUM at `public_dataset_ingest.py` and `assist_external.py`: urllib `urlopen` for pinned HTTPS dataset files. Call sites restrict constructed commit/filename prefixes and byte limits; **automatic cross-origin redirects are not explicitly prohibited**. Deny redirects, enforce an exact HTTPS host/path policy and pin independent content digests before trusting data.
- LOW findings are primarily assertions in controlled research code, subprocess APIs with argument arrays, and intentionally broad error handling. Treat individually; not all are vulnerabilities.

**QA-01 · Member 1 + Member 2 · CI is a green correctness gate, not a security gate**
The single GitHub workflow installs Python/Node dependencies and runs `pytest`, Ruff and `npm run build`. It does not run Bandit, `pip-audit`, secret scanning, source dependency SBOM, coverage enforcement, Playwright browser E2E, real-camera performance testing or permission checks. Suggested next CI expansion: pinned-action permissions, dependency/vulnerability jobs, guarded secret scan, property-based negative auth tests and post-merge release-gate artifact.

**Small Member 1 remediation delivered in this audit:** The only runtime code modifications are `md5(usedforsecurity=False)` in IKAR publisher checks and `sha1(..., usedforsecurity=False)` for Git blob IDs, with source comments; they **do not** replace SHA-1 with SHA-256 or justify any production readiness claim. All 20 related offline tests passed, Ruff passed and Bandit HIGH fell from two heuristic findings to zero. The remaining Medium findings require dedicated parser/redirect hardening and tests.

### P2 — Traceability and end-to-end assurance

**SEC-03 · Repository secret-pattern scan has known coverage limits**
A read-only regex scan of **344 currently tracked files** found **no matching PEM private keys, AWS keys, GitHub PATs, OpenAI-style or Meta EAA tokens**. Four long password-literal patterns were located in **synthetic camera test fixtures**, not the production config. A separate read-only scan of **241 reachable commits / 59,861 patch lines** found no matches for those named high-confidence token patterns. This does not prove absence of secrets encoded differently, in generated data, untracked/unreachable Git objects, external CI logs, or connected systems. `gitleaks`/`trufflehog` were unavailable. Historical Git object integrity check reported dangling blobs and was not a full forensic secret scan; require a dedicated repo-wide secret scanner before public release. A GitHub vulnerability-alert API check returned **HTTP 404** (unavailable or insufficient permissions), so repository security-alert configuration **could not be verified**.

**QA-02 · No physical/browser/accessibility acceptance**
Dashboard has **223 Node contract tests** and compiled UI, but no observed cross-browser live camera `<img>` MJPEG validation, screen-reader test, keyboard-only assistive-tech evaluation, hardware source/driver soak, representative face/body privacy review or caregiver delivery acceptance. UI demo scenes are deliberately fictional. CI cannot validate these gates.

**OPS-01 · Branch/process boundary**
`AGENTS.md` reserves `main` and actual shared `preprod` for human promotion. This audit was performed on Member 1's separate `member/feature/preprod` baseline. No protected branch or Member 2 file was changed. GitHub branch-protection configuration was **not** audited by an authorized protection API and must be verified by a repository administrator.

## Member 2 snapshot

After `git fetch origin --prune` on 2026-11-01, the newest Member 2 remote-tracking branch remained **`origin/member2/feature/initial` at `22969e0`, commit dated 2026-10-28**. Its latest observed CI, [40720662359](https://github.com/viillab/META-Viil-Sentinel/actions/runs/40720662359), completed **success** on that SHA. No newer Member 2 push was found on the checked refs. A green branch CI does **not** imply source authentication, ingestion, real Meta inference or durable notifications.

## Next action owners and acceptance gates

| Priority | Owner | Concrete next gate |
|---|---|---|
| P0 | Member 2 | Require identity/tenant permission on incident collection/detail routes; add tests proving 401/403 for unauthenticated, cross-tenant, unauthorized reads when demo disabled |
| P0 | Member 2 | Implement independent authenticated `viil.edge.candidate.v1` ingestion with source validation, durable dedup/replay protection, body/size/rate caps and trusted timestamp anchoring |
| P0 | Member 2 | Real Meta API adapter ONLY with authorized evidence, backend secrets, cost/timeouts/retries and clearly attributed provider provenance; maintain mock/offline fallback |
| P0 | Member 1 + accountable site owners | Genuine signed legal/privacy authorization before any real camera; then decode 12 live frames, verify browser playback, run supervised 30-minute soak and actor-disjoint Fall/ADL evaluation |
| P1 | Member 1 | Harden XML camera parser and pinned public dataset redirect/content handling; add regression tests |
| P1 | DevOps/maintainers | Upgrade isolated Python build tools, rerun advisory scan and tests; add security/SBOM/secret/coverage jobs to CI |
| P1 | Both | Authenticated caregiver actions with tenant RBAC, persistence, delivery receipts, human oversight and fail-safe policy |
| P2 | Member 1 + QA | Browser E2E, accessible UI test with target users and performance/cost measurement on authorized hardware |

## Honest exclusions / reproducibility

This audit **did not** execute real-camera RTSP decode, open approval files, sign owner policies, record people, call live Meta APIs, send caregiver notifications, perform a full external penetration test, verify all third-party datasets/licenses independently or certify medical, legal/privacy or accessibility compliance. These are not accidental test omissions: several require explicit human permission and actual external infrastructure. Re-run the commands on the release SHA; report findings are a dated snapshot, not background monitoring.

### Quick rerun on Windows

```powershell
cd D:\VIIL-Sentinel
git fetch origin --prune

cd services\edge-vision
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m sentinel_edge.handoff_preflight
.\.venv\Scripts\python.exe -m sentinel_edge.submission_readiness
.\.venv\Scripts\python.exe -m sentinel_edge.member2_status

cd ..\api
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pip check

cd ..\..\apps\dashboard
npm run build
npm audit

cd ..\..
git diff --check
```

For an independent Python advisory scan, run `pip-audit --path <target-venv-site-packages> --format json` using the intended environment, interpret duplicate IDs once per package, and retain the advisory snapshot date. `bandit` is a *static heuristic scan*, not a penetration test.

**Audit conclusion:** All executed offline tests/build gates passed. **Production release is blocked** pending Member 2 authentication and real integration, genuine camera/privacy approval and independent model/UX/operational evidence. Treat this as a truthful engineering audit and a human-owned remediation plan, not a production certification.
