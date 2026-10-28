# VIIL-Sentinel — Hikvision via Tailscale Subnet Router (Member 1)

**Offline preparation only · 28 Oct 2026 · NO CAMERA CONNECTED BY THIS CHANGE.**

## What the operator supplied

A Hikvision RTSP proof-of-concept and a conversation screenshot of a camera
configured behind Tailscale. **The default camera IP in the supplied POC
script differs from the camera IP mentioned in the screenshot.** Confirm
which address is actually routed before any testing. Do not copy the actual
camera IP, operator name, credentials or screenshot into the public repo.

The supplied standalone POC uses PyAV, an interactive password and the
Hikvision `/Streaming/Channels/101` and `/Streaming/Channels/102`
conventions. It **does not** have the newer VIIL-Sentinel signed live-camera
privacy gate and cannot establish fall-detection performance. Do not execute
the standalone `--execute` against real subjects as a shortcut around the
project's operator authorization or signed policy requirements.

## Network topology

```text
Hikvision camera (private site LAN, RTSP enabled)
       |
  site LAN -> operator-authorized Tailscale subnet router
       |
  Tailscale private overlay + approved site subnet route + grants/ACLs
       |
  approved Edge host (signed VIIL camera privacy approval required)
       |
  VIIL MediaPipe pose + temporal fall-candidate (Member 1; local)
       |
  future authenticated Meta/evidence/caregiver backend (Member 2)
```

The camera typically **does not run Tailscale itself**. Tailscale must run
on an authorized site gateway with access to the camera's LAN; enable
`--advertise-routes` for the real route (prefer the narrowest route
compatible with the site design), approve the subnet route in the Tailscale
Admin Console, and grant access **only to the approved Edge host(s)**
and **only to the camera's required RTSP destination/port**. The client
must accept the route (Windows default; Linux requires `--accept-routes`).
Always avoid public RTSP port-forwarding, broad `0.0.0.0/0` grants or
exposing the camera management portal to the tailnet unnecessarily.

The site administrator must check for overlapping networks. The camera IP
should be a **private LAN literal** (RFC1918) reachable through the subnet
router, not the Tailscale overlay IP of the router. VIIL's current
`validate_rtsp_env` deliberately rejects Tailscale CGNAT (`100.64.0.0/10`)
endpoints and public IPs. We do not relax that trust boundary just to
make a tunnel work.

## Safe source configuration (no passwords in Git)

Copy the checked-in, secret-free example
`services/edge-vision/examples/camera_registry.tailscale.example.json`
to an **access-controlled** directory outside the repository and adapt
the pseudonymous camera ID / environment-variable name to your deployment.
The example deliberately stores no actual IP, password, person, or frame.

The operator supplies `VIIL_HIK_TAILSCALE_RTSP` in their private
environment/secret manager, containing an RTSP URL to their **verified
private LAN camera address**. Passwords and usernames with reserved
characters must be percent-encoded as URL components and the password
should belong to a dedicated *read-only* camera account. Never put a
real RTSP URL in a shell argument, Git commit, chat, screenshot or logfile.
Avoid `setx`, permanent shared shell history, and hardcoded demo secrets.

Hikvision convention **if supported by the particular device/firmware**:
- Main stream: `rtsp://<user>:<password>@<private-LAN-IP>:<port>/Streaming/Channels/101`
- Sub stream: `rtsp://<user>:<password>@<private-LAN-IP>:<port>/Streaming/Channels/102`

The user/password values above are placeholders ONLY. Use the *configured*
RTSP port; 554/8554 are already allowed by the VIIL URL validator. If the
device uses a different RTSP port, the CLI requires explicit
`--rtsp-allow-port`. Selecting Sub Stream usually reduces bandwidth,
but actual latency/quality must be measured; do not assert specific FPS.

## Verification while the operator is present, in order

1. Confirm the actual camera IP from the site operator, camera's LAN
   configuration, and its *read-only* account. **Rotate any password
   previously exposed in messages or screenshots before use.**
2. Check Tailscale is authenticated on both the site gateway and Edge
   machine, the correct subnet route is advertised and approved, and
   the Edge host grants/ACLs permit only the camera RTSP destination.
   Subnet-route reachability alone does **not** prove the RTSP camera works.
3. In a supervised session, check the known camera port using a scoped
   local network test such as
   `Test-NetConnection <verified-private-LAN-IP> -Port <configured-RTSP-port>`.
   Do not run this command unless the camera owner has authorized it.
4. Verify a separate signed `--privacy-approval` for the exact
   pseudonymous camera ID and the official `VIIL_PRIVACY_APPROVAL_KEY`.
5. Run the project's bounded `sentinel_edge.camera_health` CLI
   (see `docs/integrations/CAMERA_INPUTS_AND_SECURITY.md`) with an approved
   camera registry, correct camera ID, `--frames 12`, signed approval,
   and `--confirm-authorized-camera`. This **opens a real RTSP stream**;
   do not run remotely while the operator is absent.
6. If a smoke test passes, run the bounded official Edge runner with
   its privacy approval, `--candidate-format v1`, `--confirm-consent`,
   `--max-frames`, and bounded RTSP session/retry limits. Never
   use the standalone POC's YOLO `--ai` person detections as proof of
   fall detection; it is a different model/objective.
7. For the actual field readiness decision, measure decode/pose FPS,
   CPU/RAM, reconnects and a 30+ minute approved soak, then independently
   labelled fall/ADL metrics and false alarms per non-fall hour.
   Member 2's cloud evidence and notifications remain independent work.

No live camera connection or credential verification has been performed
by these docs/tests; no result is a clinical or production certification.

## Security note for operator

- Tailscale encrypts the overlay transport, **not necessarily the RTSP
  camera endpoint itself**. Traffic on the remote LAN between subnet router
  and camera may be plain RTSP; restrict that LAN path.
- A Tailscale route is not proof of owner consent, regional data-processing
  compliance, signed privacy approval, or authorization to send to Meta.
- Do not commit or reuse the shared screenshot password. Rotate it, then
  limit access through both Tailscale ACLs and camera account permissions.
- Keep native FFmpeg/OpenCV logs away from untrusted recipients; errors
  can contain camera URL credentials.

## Official references

- Tailscale subnet router:
  https://tailscale.com/docs/features/subnet-routers
- Windows Tailscale subnet routes:
  https://tailscale.com/docs/use-cases/personal-or-at-home-use/access-devices-without-tailscale?tab=windows
- Tailscale route injection and access controls:
  https://tailscale.com/docs/reference/route-injection
- Hikvision RTSP stream URL format:
  https://supportusa.hikvision.com/support/solutions/articles/17000129022-do-you-have-an-example-showing-the-format-for-getting-a-rtsp-stream-from-a-camera-
