# VIIL-Sentinel — Local HTTP Edge→Backend→Caregiver Demo

**Member 2, November 2, 2026. Demonstrated on Windows, strictly synthetic.**

## What is implemented

A repeatable developer command now validates actual local **TCP HTTP** transport
with a real temporary Uvicorn server, instead of relying exclusively on
FastAPI's in-memory TestClient:

```text
Member 1 Python temporal-pose detector
  -> verified synthetic Fall trace (Sitting must remain negative)
  -> Member 1 viil.edge.candidate.v1 JSONL serializer
  -> HMAC-SHA256 authenticated POST over 127.0.0.1 TCP HTTP
  -> Member 2 strict schema/size/source checks
  -> temporary SQLite event UUID/idempotency ledger
  -> token-gated GET /api/v1/caregiver/inbox over real HTTP
  -> exact read-only synthetic metadata advisory
```

**Run from `D:\VIIL-Sentinel\services\api`:**

```powershell
.\.venv\Scripts\python.exe -m app.local_http_demo
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

Expected command result: `LOCAL_TCP_HTTP_EDGE_TO_INBOX_PASS`.

No external service, person, medical image, webcam, real camera, private
dataset, Meta Model API call, push notification, caregiver delivery or emergency
dispatch is involved. This is an end-to-end *developer synthetic demo*, **not**
validation of actual fall recognition or production monitoring.

## Precise safety boundaries

- Opens one **ephemeral IPv4 port bound only to `127.0.0.1`**; no
  `0.0.0.0`, Tailscale, LAN, public address, deployed server, ingress or
  externally available endpoint.
- The smoke uses temporary independent cryptographically random HMAC and
  caregiver bearer strings, rather than the operator's ignored `.env`
  secrets. It builds `Settings(_env_file=None, meta_model_api_key=None,
  meta_provider="mock", meta_live_enabled=False, demo_mode=False)`.
- Server access logging is off, proxy headers are disabled, and the client
  explicitly disables environmental proxies and redirects. Only the
  restricted Member 1 Python synthetic trace subprocess receives minimal OS
  environment settings. This subprocess does **not** receive Meta or camera
  keys.
- The probe checks the actual HTTP statuses: 201 accepted, 200 duplicate,
  401 forged HMAC, 401 absent/wrong caregiver token, 403 legacy demo POST
  disabled, and the absence of a CORS allow header for an untrusted Origin.
- Every accepted advisory is `simulated=true`, `fall_confirmed=false`,
  `meta_provenance=none`, `delivery_state=not_sent` and sourced exclusively
  from the verified Member 1 synthetic fall fixture.
- Server shutdown and SQLite file deletion are verified, including cleanup
  after exceptions. The random listener port and any secrets are **not**
  returned in the smoke's result JSON.
- The prior in-process, zero-socket `app.edge_emitter_e2e` remains intact
  for environments where binding localhost is disallowed. The newer HTTP
  test opens a real local socket; do not describe it as "no network".

## Additional demo-route hardening

All four original unauthenticated **fictional** incident routes are now
loopback-only when `demo_mode=true`:

- `GET /api/v1/incidents`
- `GET /api/v1/incidents/{incident_id}`
- `POST /api/v1/incidents/demo`
- `POST /api/v1/incidents/{incident_id}/review`

The same policy already protected synthetic candidate intake and caregiver
reads. The policy uses the actual ASGI client IP; changing `Host`,
`Forwarded`, `X-Forwarded-For` or `X-Real-IP` headers does not grant access
in normal application code. The in-process test client name `testclient`
is allowed only for unit tests. Outside demo mode, the unauthenticated
legacy routes continue returning 403.

**This is not authentication.** Do not publish these routes behind a
loopback-terminating reverse proxy, tunnel or gateway: such infrastructure
can make a remote caller appear local. Do not run this backend on a public
interface or connect it to real users without properly designed identity,
session RBAC, source authorization, TLS, audit logs and privacy approval.

## Scope and remaining blockers

Flutter and Dashboard still need a real, secure session-based Backend client
and cannot safely embed a static bearer token in distributed source or app
binaries. This implementation does not connect live Mobile or Browser views.

Real fall inference, benchmark acceptance, privacy/consent, remote Hikvision
networking, signed real camera intake, real evidence-grounded Meta inference,
notification outbox and caregiver acknowledgments remain separate work.

This particular `app.local_http_demo` command makes **no paid Meta requests**.
A different, explicitly authorized synthetic-only Meta test has since passed
the real image+schema protocol and local transport integration. See
`services/meta-intelligence/LIVE_META_TEST_REPORT_2026-11-02.md`.
All **4/4** local Meta requests are now exhausted. Do not reset the guard;
the team's actual $150 billing balance must be checked in Meta's portal.
