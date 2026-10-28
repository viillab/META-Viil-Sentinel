# Hikvision / Tailscale supervised live test — Member 1

This is a **human-supervised operator procedure**, not evidence that the camera
has been opened, a real fall has been detected, or Meta AI has been called.

## Verified by remote read-only diagnostics

- Windows development machine has Tailscale installed and running.
- The authorized host-scoped site subnet route is advertised and TCP RTSP
  **554 is reachable**. A TCP handshake is *not* RTSP authentication or
  successful video decoding.
- The private camera registry exists with a pseudonymous camera ID,
  the signed privacy policy and session key *files exist*, and the pose
  task model is present. **Key verification did not complete** during
  remote diagnostics, because remote access to private key content was
  blocked. Do not bypass that safeguard.
- No current RTSP URL, user or password was found in the process's
  environment, including persistent Windows user/machine environment
  variables. Never commit, paste or expose them.
- Opening live video has **NOT** been performed in this phase.

## Secure supervised execution on the camera-authorized Windows host

**First rotate any camera password shown in past chat/screenshots.**
Use a *read-only* Hikvision account created by the authorized camera owner.
The operator must be physically at the console or use an authorized
interactive remote desktop with a private secure credential prompt.

Run this in a new interactive PowerShell terminal, not a remote CI job:

```powershell
cd D:\VIIL-Sentinel
.\services\edge-vision\scripts\run_hikvision_tailscale_supervised.ps1 -Mode Both
```

The launcher deliberately:

1. Asks the operator to enter the verified RFC1918 camera IPv4 address
   locally; it does **not** publish a site IP in Git.
2. Tests TCP 554 with a 4-second timeout.
3. Requires an explicit `AUTHORIZED` acknowledgment for this staged
   local nonclinical session.
4. Reads the existing private signing key on the local machine only
   and verifies the signed policy for `hik-tailnet-live` **before
   requesting camera credentials**. If denied, no RTSP stream opens.
5. Uses the **Get-Credential** local secure prompt for the rotated
   read-only account, percent-encodes components, and passes the URL
   strictly by ephemeral child-process environment variable (not CLI).
6. Attempts a **12-frame** read with the real camera health command.
   If that fails, it stops without running the pose model.
7. Only on successful decode, runs the official **bounded 100-frame**
   Edge Pose / Fall Candidate pipeline with a 60-second session limit
   and at most one reconnect. Output is local informational research
   data, not a caregiver alert or proof of fall.
8. Removes temporary environment variables even when it fails.

For camera decode only (no Pose Fall Candidate test), run:
```powershell
.\services\edge-vision\scripts\run_hikvision_tailscale_supervised.ps1 -Mode Health
```

No routine Windows Credential Manager storage, transcript, disk image
storage, cloud upload, password logging, public port-forwarding or
browser camera display is configured. Native codecs could still emit
diagnostic strings on failure; the launcher suppresses process stderr
but **does not guarantee every third-party native library is safe**.
Protect the machine and terminal session.

## Gate outcomes and next steps

- **TCP reachable only**: network connectivity works, not login/decode.
- **Privacy check denied**: stop; contact the authorized operator
  to issue a valid **signed** scoped policy. Never forge or re-sign.
- **401 / RTSP authorization failed or timeout**: verify rotated credentials,
  read-only camera account, enabled RTSP and substream Channel 102,
  device firmware, and Tailnet grant/route; avoid password in logs.
- **12/12 readable**: validates a bounded sample of decode only.
- **Runner 100 frames**: confirms local pose model and candidate pipeline
  can execute this limited session; zero candidates is NOT proof of safety.
- **Performance**: `--profile-rtsp` provides local cycle/RSS diagnostics,
  but FPS, network bandwidth, CPU, latency p50/p95, false-alarm rates and
  long soak still require properly collected data.
- **Git/merge**: the operator launcher may be tested/pushed as
  preparatory Member 1 code, but do **not** merge it under a
  "validated Hikvision live integration" title until the actual RTSP
  health and pose smoke tests have passed and their redacted evidence
  has been reviewed. Member 2 Backend/Meta work is out of scope.

## Offline regression commands

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

If PowerShell execution policy blocks a script, use an authorized
operator-approved session policy; do not disable organization security
controls or expand camera access without administrator review.
