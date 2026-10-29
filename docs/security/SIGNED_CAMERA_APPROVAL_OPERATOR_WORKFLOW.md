# VIIL-Sentinel — Signed camera approval operator workflow

**This is a human-review process, not a way to bypass the camera gate.** The file is a project-specific signed policy, not a Hikvision license, not an official permit, and not independent evidence of consent or legal compliance. The site owner/controller must authorize filming and relevant privacy notices, legal basis, safety and rights procedures **before** signing. Do not sign a specimen just to make a camera connect.

The code is in `services/edge-vision/sentinel_edge/privacy_approval_operator.py`. Its only actions are offline JSON preparation, operator-attested signing and verification: no camera, RTSP, webcam, AI model or external network access.

## 1. Prepare a **denied-by-default** draft

From an interactive PowerShell on the approved operator's Windows computer:

```powershell
$privateFolder = Join-Path $env:USERPROFILE 'VIIL-Private'
New-Item -ItemType Directory -Path $privateFolder -Force | Out-Null
Set-Location D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m sentinel_edge.privacy_approval_operator template `
  --source-id staged-camera-01 `
  --output (Join-Path $privateFolder 'unsigned-privacy.json')
```

This produces only a **draft**. The draft intentionally has `site_authorization_confirmed: false`, `notices_confirmed: false`, `legal_basis_by_jurisdiction: {"TH": "REVIEW_REQUIRED"}`, placeholder references, placeholder dates, and **no signature**. The actual signed approval is not supplied by Hikvision.

## 2. Human controller/privacy review (required)

The accountable authorized reviewer must independently examine and document:

- Camera ownership and approved scope: `staged-camera-01` should actually correspond to the approved physical camera and location. Do not invent permissions.
- Purpose, jurisdiction(s), documented legal basis, the filming scenario, privacy notices to the affected people, responsible controller and data-subject requests procedure.
- References to completed impact and sensitive-data reviews, site authorization and applicable notices, and any required additional legal approvals.
- Valid start/expiry dates (no more than 90 days), and approved camera IDs.
- Local-only processing; no raw-frame retention, cloud transfer, face identification, training reuse or automatic emergency dispatch; mandatory human review.

The reviewer updates the **unsigned JSON** only after those conditions are factually met and approval evidence is retained through the organization's own process. The application cannot verify that legal or human review occurred. Require locally protected file permissions; a user-profile folder alone is not a guarantee that NTFS ACLs are appropriate. Do not put approvals or keys in Git.

## 3. Human operator signs the actually reviewed policy

The designated authorized signer must have an **existing, separately controlled HMAC key** (UTF-8 length at least 32 bytes), provided under the organization's key-management process. On the private Windows console:

```powershell
Set-Location D:\VIIL-Sentinel\services\edge-vision
$privateFolder = Join-Path $env:USERPROFILE 'VIIL-Private'
.\.venv\Scripts\python.exe -m sentinel_edge.privacy_approval_operator sign `
  --unsigned (Join-Path $privateFolder 'unsigned-privacy.json') `
  --output (Join-Path $privateFolder 'approved-privacy.json') `
  --source-id staged-camera-01 `
  --confirm-site-authorization `
  --confirm-privacy-review
```

The signer supplies the existing secret through a **masked local prompt**, or an already-configured `VIIL_PRIVACY_APPROVAL_KEY` environment variable. The key is **never** a command-line argument, written to a file or included in successful JSON output. Human confirmation flags are **attestations**, not evidence; never use them without the completed review.

Before creating the output, the CLI signs with `sign_policy` and checks the result using the **same `verify_privacy_approval` gate used by the running camera**. A missing approval, wrong camera, tampering, excessive dates, incorrect flags, incomplete fields, or mismatched key is rejected. The tool refuses to overwrite files and refuses to write approvals inside the repository.

## 4. Offline verification — still not a live camera test

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.privacy_approval_operator verify `
  --signed (Join-Path $privateFolder 'approved-privacy.json') `
  --source-id staged-camera-01
```

Only when the authorized reviewer has delivered **both** the signed file and its controlled key to the operator can they use the approved launcher:

```powershell
powershell -NoProfile -File D:\VIIL-Sentinel\scripts\start-hikvision-staged.ps1 `
  -CameraIp 192.168.10.204 `
  -PrivacyApproval (Join-Path $privateFolder 'approved-privacy.json') `
  -SourceId staged-camera-01 `
  -ShowPreview -PreviewDecoder pyav -PreviewSeconds 30
```

This launcher prompts locally for the camera's **dedicated read-only account** and HMAC key, verifies the same signed approval before capture, and attempts 12 decoded frames. Only then does it display a bounded local OpenCV window. Press Q/Esc to stop. PyAV is an optional dependency; it is currently installed on the checked Windows Edge development environment. This is **not a browser/Dashboard stream**. RTSP `OPTIONS 200 OK` or unit tests cannot prove camera video is readable.

A real signed approval with HMAC is a **technical gate**, not independent certification of lawfulness or a replacement for a signed permission document. See `GLOBAL_PRIVACY_SECURITY_BASELINE.md` for the deployment and legal review boundaries.
