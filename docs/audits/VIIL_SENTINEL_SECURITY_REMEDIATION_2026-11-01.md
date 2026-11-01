# VIIL-Sentinel — Member 1 Dataset & Hikvision Parser Security Remediation

**Date:** 2026-11-01 (KST).
**Reference:** [Full Stack Audit](VIIL_SENTINEL_FULL_STACK_AUDIT_2026-11-01.md).
**Ownership:** Member 1 Edge/Research. No changes to Member 2 Backend, protected `preprod` or human-only `main`.

## Scope and code change

The previous audit identified three **Bandit MEDIUM** findings: two `B310` uses of generic urllib `urlopen` for publisher-pinned research clips, and one `B314` use of the standard-library XML parser for **Hikvision ISAPI configuration metadata**.

1. **Pinned GitHub public dataset downloads** now go through
   `sentinel_edge.pinned_https_download.fetch_pinned_https`. Both
   GMDCSA-24 and ASSIST callers construct an **exact allowlist**
   from their frozen publisher commit and catalog filenames. The
   shared downloader rejects other hosts, protocols, queries,
   fragments, URL credentials, unexpected paths, over-limit bodies,
   non-200 responses, and **all HTTP redirects** (even to another
   path on the approved host). It also refuses environment-proxy
   routing and checks the final URL before accepting a response.
   The existing byte-limit, publisher Git blob checks, separately
   calculated media SHA-256, private local output paths and
   synthetic training safeguards are retained.
2. **Hikvision read-only metadata XML parsing** uses
   `defusedxml>=0.7.1,<0.8` and explicitly
   `forbid_dtd=True, forbid_entities=True, forbid_external=True`.
   The earlier 64 KiB limit, DOCTYPE/ENTITY byte screening, strict
   fields and redacted errors still apply. The ISAPI audit
   does not request images, RTSP PLAY or PTZ commands.
3. **Synthetic-only regression coverage** tests allowlist rejection
   before opening any HTTP client, all common redirect statuses,
   changed response URLs, byte-limit overflows, native URL/error
   redaction, required no-proxy/no-redirect handlers, and explicit
   XML parser security arguments. Existing ISAPI and dataset
   contract tests remain in the regression suite.

The code is stricter: **a publishing server that now redirects,
or a deployment that requires an HTTP proxy, may no longer download
these clips** without a reviewed endpoint and policy change.
This is intentional fail-closed behavior, not a measured failure
or proof of actual live downloads. Real downloads and physical camera
access were **not** performed during this remediation.

## Security finding disposition

| Bandit result | Earlier audit (2026-11-01) | After this change |
|---|---:|---:|
| HIGH | 0 | 0 |
| MEDIUM | 3 | 0 |
| LOW | 24 | 24 |

These are **static scanner heuristics**, not a penetration test or
whole-project production certification. Existing Python build-tool
`pip`/`setuptools` advisories from the full audit remain **unresolved**
and are not conflated with the Bandit source findings.

## Member 2 & production handoff

At the 2026-11-01 `git fetch origin --prune` snapshot,
`origin/member2/feature/initial` remained at `22969e0`
(28 October 2026); its last observed GitHub Actions run
`40720662359` was successful. This does **not** verify Candidate
Ingestion, authentication, tenant RBAC, durable storage, real Meta
multimodal evidence, or caregiver notification delivery.

Production is **not ready**. A genuinely approved signed camera/site
privacy policy, supervised Hikvision decoded frames/browser playback,
real independent Fall/ADL validation, Member 2 authenticated
idempotent candidate handling and reliable Meta/caregiver workflows
all remain independent blockers.

## Local repeatable validation

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m pytest -q tests/test_pinned_https_download.py tests/test_public_dataset_ingest.py tests/test_assist_external.py tests/test_hikvision_isapi_audit.py
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pip check
cd ..\api
.\.venv\Scripts\python.exe -m pytest -q tests
cd ..\..\apps\dashboard
npm run build
```

For a **static** security follow-up, run `bandit` against only
`services/api/app`, `services/edge-vision/sentinel_edge` and
`services/edge-vision/scripts` (the same earlier audit scope).
A clean Bandit scan does not replace all other dependency, secret,
auth/privacy, camera-performance or model evaluation gates.
