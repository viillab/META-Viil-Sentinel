# VIIL-Sentinel — Camera Input Layer & Security Review (Member 1)

**28 October 2026 — DEMO/RESEARCH ONLY.**

**Legal/privacy startup gate:** All live camera entrypoints now require a
signed `--privacy-approval` file and protected `VIIL_PRIVACY_APPROVAL_KEY`.
See `docs/security/GLOBAL_PRIVACY_SECURITY_BASELINE.md` before running any
camera. Consent CLI acknowledgement alone is not sufficient. This does not authorize real
patient monitoring, medical advice or emergency dispatch. Hardware
compatibility, field reliability and fall-detection accuracy are not yet
proven. Hikvision is ONE example, not the transport architecture.

## Supported source types (vendor-neutral)

| Input | How it is selected | Scope |
|---|---|---|
| IP camera/NVR/DVR with RTSP | `--source rtsp --rtsp-env VIIL_X` or registry | Vendor-independent RTSP over authorized private LAN, tested with fake capture only |
| UVC/USB webcam, capture card | `--source 0`, `--source usb:2` or registry | Windows local capture devices, index 0..15 |
| Rights-cleared local video files | `--source path-to-video.mp4` | Existing offline demo path; not live |
| Multiple registered cameras | `sentinel_edge.camera_fleet` | Up to four parallel LOCAL workers, bounded frames and explicit consent; experimental only |

Examples of potential RTSP-compatible equipment include Hikvision, Dahua,
Axis, Reolink, TP-Link VIGI, Uniview, certain ONVIF-compliant cameras and
NVRs **when RTSP is actually enabled**; no particular vendor, codec,
resolution or firmware was field-tested. ONVIF discovery, RTSP-over-TLS,
cloud camera APIs, browser WebRTC, HTTP MJPEG and phone camera apps are NOT
implemented or claimed supported. Those need separate approved adapters and
testing; they must not bypass input validation.

## Multi-camera registry (NO secrets or RTSP URLs in the file)

Create an access-controlled LOCAL file outside Git, for example
`C:\PrivateConfig\cameras.json`:

```json
{
  "schema_version": "viil.edge.camera_registry.v1",
  "cameras": [
    {"id": "zone-a", "kind": "rtsp", "rtsp_env": "VIIL_ZONE_A_RTSP"},
    {"id": "zone-b", "kind": "rtsp", "rtsp_env": "VIIL_ZONE_B_RTSP"},
    {"id": "operator-usb", "kind": "usb", "device_index": 0}
  ]
}
```

Set `VIIL_ZONE_A_RTSP` and `VIIL_ZONE_B_RTSP` separately in the
authorized operator's secrets manager / private environment. Do not type
camera passwords into a CLI command or put them into an issue, commit,
screenshot, access log or support chat. Assign a **unique pseudonymous ID**
to every camera. Registry accepts up to 16 definitions; a single runner
selects ONE and the opt-in fleet launcher selects up to FOUR.

Choose one camera with the existing runner:

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m sentinel_edge.runner --source camera --camera-registry C:\PrivateConfig\cameras.json --camera-id zone-a --privacy-approval C:\PrivateConfig\approved-privacy.json --model ..\..\models\pose_landmarker_lite.task --candidate-format v1 --confirm-consent --rtsp-retries 1 --rtsp-session-seconds 300 --max-frames 300
```

Select a USB camera by using `--camera-id operator-usb` and omitting RTSP
retry flags. The runner maps the registry ID to an independent edge
`source_id`; RTSP reconnect epochs get additional random session suffixes
to prevent time-base collisions.

Run up to FOUR selected cameras as independent processes, only for short,
supervised tests:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.camera_fleet --camera-registry C:\PrivateConfig\cameras.json --camera-ids zone-a zone-b operator-usb --privacy-approval C:\PrivateConfig\approved-privacy.json --model ..\..\models\pose_landmarker_lite.task --max-frames 300 --rtsp-retries 1 --confirm-authorized-cameras --confirm-consent
```

Each worker uses separate capture/pose/temporal state. Fleet requires
finite 1..3600 frames per worker, fails overall if ANY worker exits nonzero,
and does not send the RTSP URL in command-line arguments. Worker
environments omit other `VIIL_*` settings to reduce cross-camera secret
exposure. Native decoder stderr is suppressed for fleet workers; per-camera
logging is not yet a secure audit-log service. Child stdout is written to
the operator console and may contain pseudonymous candidate IDs.
**Concurrent stdout is not a guaranteed ordered/atomic data bus** and
must not be ingested as a reliable event feed; authenticated per-camera
transport is separate future work for Member 2.

## Source security controls now enforced

- Fail closed on unknown/malformed URL schemes, hostnames, public IPs,
  loopback, multicast, link-local addresses, encoded control characters,
  embedded newline/backslash, fragments, oversized URLs and multiple
  `@` separators.
- Network sources require a *literal private IPv4 address*
  (10/8, 172.16/12, 192.168/16) or private IPv6 ULA (fc00::/7).
  No DNS hostname lookups/rebinding; camera name discovery requires an
  explicitly reviewed future design.
- Standard RTSP ports 554 and 8554 are allowed. Other vendor ports can
  be enabled deliberately using `--rtsp-allow-port 10554`, without
  removing the private-IP restriction.
- Local USB index is 0..15. URL credentials and any network paths
  are refused as direct `--source` arguments.
- No password in registry JSON; access granted by a `VIIL_*` environment
  name. Streaming is explicitly opt-in and does not save raw frames by
  default. Trace outputs require separate privacy acknowledgement.
- Capture opening and reading use OpenCV/FFmpeg *requested* 8s/4s
  timeouts; **native backend timeout support is not guaranteed**.
- Fail-closed RTSP stream interruption and bounded retries with fresh pose
  model and detector sessions; no stale pose history across reconnects.
  Missing pose and camera loss are not negative fall observations.

## Residual risks / blockers (DO NOT claim production secure)

| Severity | Risk / required action |
|---|---|
| HIGH | Backend demo API has unauthenticated create/review routes. Keep API bound to loopback; Member 2 must implement authentication, role-based authorization, rate limits, audit logging and production network safeguards before exposure. CORS is NOT authentication. |
| HIGH | Native OpenCV/FFmpeg decoder and other libraries can log RTSP URLs/passwords even if Python messages are redacted. Restrict console permissions, use read-only camera accounts and log redaction/suppression at the process boundary. |
| HIGH | Private-IP validation is not a network sandbox: RTSP redirects, camera compromise and native decoder bugs remain possible. Use VLAN/egress firewall allowlisting camera IP:port, no public port-forwarding, sandboxed workers, and approved codecs. |
| HIGH | This demo does not deliver authenticated caregiver alerts, prove a real fall or guarantee service availability. Member 2 integration and labeled scenario evaluation remain pending. |
| MEDIUM | Source registry is local and does not implement signed enrollment, per-camera RBAC, certificate validation, signed firmware/stream verification or automatic device discovery. |
| MEDIUM | Multi-process stdout may interleave; fleet is not a durable multi-camera message bus, service manager or HA supervisor. Use isolated trusted backend ingestion before real deployment. |
| MEDIUM | No physical camera or network-failure test performed; camera-brand and codec support depend on actual firmware and local OpenCV/FFmpeg build. |

**Acceptance before public deployment:** closed-network staging, device-owner
permissions/consent, credential rotation, secure per-device registration,
TLS/authenticated backend, privacy impact review, malware/update policy,
network egress constraints and independently labeled non-clinical fall
evaluation. Never use on vulnerable individuals as a life-safety service.
