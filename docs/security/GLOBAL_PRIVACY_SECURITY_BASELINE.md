# VIIL-Sentinel: Global Privacy & Security Baseline (Member 1)

**Design baseline dated 2026-10-28. NOT legal advice, international legal
certification, regulatory authorization, or ISO certification.**

VIIL-Sentinel processes camera frames to produce *unconfirmed* fall
candidates, potentially inferring sensitive information about a person.
Neither a checkbox nor a signed JSON file makes such activity lawful.
**Every jurisdiction, deployment scenario, controller/processor role, user
group, data flow, and use-case must be reviewed by an authorized local legal
and privacy team BEFORE real collection.** If in doubt, block deployment.

## Global technical baseline: default-deny

- Capture input is local, authorized RTSP-on-private-LAN or USB/UVC. No
  auto-discovery, public camera endpoints, personal surveillance, profiling,
  face recognition, model-training reuse, cloud sending or dispatch.
- ALL `sentinel_edge.runner` LIVE camera paths (`--source rtsp`,
  `--source usb:0`, numerical webcam and `--source camera`) now require
  `--privacy-approval` with a verifiable signed authorization. Local
  prerecorded file replays keep their existing research/privacy rules.
- RTSP camera preflight (`sentinel_edge.camera_health`) and the
  `sentinel_edge.camera_fleet` launcher also require a signed approval.
- The approval is bound to specific pseudonymous camera IDs, jurisdictions,
  a documented purpose, documented legal-basis references for *each*
  jurisdiction, controller reference, privacy notice, impact assessment,
  sensitive-data review, rights request procedure, and a short validity
  interval (up to **90 days**). A mismatch, expiry, unsigned/modified
  document or missing signing key blocks camera startup.
- The policy requires local-only processing, zero raw-frame retention,
  no cross-border/cloud export, no face identification, no reuse for
  training, no automatic emergency dispatch, and human review.
- HMAC-SHA256 protects the approval against undetected edits, provided
  the `VIIL_PRIVACY_APPROVAL_KEY` stays secret. **It does NOT authenticate
  the legal competence/identity of the reviewer or prove the stated
  legal basis.** The authorized reviewer must issue and guard the key
  through operational procedures, use separate restricted accounts, and
  rotate it when personnel or trust changes. The key is also needed by
  verifying worker processes; this is a demo design, not separation of
  duties suitable for production. Future production approval should use
  public-key signatures with private signing keys offline and managed
  verification/key rotation.

## Approving staged live cameras — do not commit these private files

An accountable controller should first complete all relevant notices,
lawful-basis assessment, DPIA/risk review, permission to film, and required
local approvals. The example below is a **template of the fields to collect,
NOT an approval and NOT a suggestion that consent is always the lawful basis**.

```json
{
  "schema_version": "viil.edge.privacy_approval.v1",
  "approval_ref": "REPLACE_APPROVAL_REF",
  "purpose": "consented_staged_fall_candidate_research",
  "jurisdictions": ["TH"],
  "legal_basis_by_jurisdiction": {"TH": "consent"},
  "controller_ref": "REPLACE_CONTROLLER_REF",
  "notice_ref": "REPLACE_NOTICE_REF",
  "privacy_impact_review_ref": "REPLACE_DPIA_REF",
  "sensitive_data_review_ref": "REPLACE_SENSITIVE_DATA_REF",
  "rights_procedure_ref": "REPLACE_RIGHTS_PROCEDURE_REF",
  "approved_camera_ids": ["zone-a", "zone-b"],
  "valid_from": "REPLACE_YYYY-MM-DD",
  "expires_on": "REPLACE_YYYY-MM-DD",
  "site_authorization_confirmed": false,
  "notices_confirmed": false,
  "human_review_required": true,
  "local_only": true,
  "raw_frame_retention_days": 0,
  "cloud_transfer_enabled": false,
  "face_identification_enabled": false,
  "training_reuse_enabled": false,
  "automatic_emergency_dispatch_enabled": false
}
```

The sample does not work until the appropriate human reviewer has verified
the actual scenario, filled the references, selected lawful basis for
**every applicable jurisdiction** (which may not be consent), confirmed
permissions/notices, set a validity range of at most 90 days, and signed
the canonical JSON using the separate, access-controlled
`VIIL_PRIVACY_APPROVAL_KEY` (at least 32 UTF-8 bytes).
`sentinel_edge.privacy_gate.sign_policy(unsigned_body, secret_bytes)`
returns the signed dictionary; the reviewer writes it to a private
JSON file using restrictive OS file permissions. This signing helper is
NOT a legal review, and signing a file without real supporting records is
not authorized. Do not store private keys/approval files in Git or public
CI artifacts. Keep approval references non-identifying.

When the reviewer supplies the private signed file and key to the
authorized demo device, from `services/edge-vision` use:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.runner --source camera --camera-registry C:\PrivateConfig\cameras.json --camera-id zone-a --privacy-approval C:\PrivateConfig\approved-privacy.json --model ..\..\models\pose_landmarker_lite.task --max-frames 300 --candidate-format v1 --confirm-consent --rtsp-retries 1
```

For a fleet, add `--privacy-approval C:\PrivateConfig\approved-privacy.json`
to the camera_fleet command. For RTSP preflight, add the same argument to
camera_health and ensure that the approved camera ID matches the registry
ID (or `--source-id` for legacy `--rtsp-env` input).

**These constraints apply to these Edge CLI entrypoints, not to someone
bypassing the application and opening a camera with their own code.**
Use OS ACLs, firewall egress rules, device accounts and process sandboxing
to close that gap. Private-IP validation alone is not an egress firewall.

## Country review matrix — human approval required in every row

| Region / jurisdiction | Review before deployment |
|---|---|
| Thailand — PDPA | Processing legal basis and notice; sensitive personal data if inferred; controller/processor roles, data subject rights, security measures, retention and international transfers. Confirm current PDPC subordinate rules and sector laws with Thai counsel. |
| EU/EEA — GDPR, EU AI Act | Art. 6 basis, transparency, necessity/proportionality, data subject rights, DPIA for high-risk processing, Art. 9 if special-category data processed; controller/processor agreement; Chapter V transfer mechanism. Separately classify the particular AI use under the *current* AI Act. |
| United Kingdom — UK GDPR/DPA | CCTV notice, necessity, documented purpose/basis, retention and DPIA where applicable; local ICO guidance and sector-specific CCTV laws. |
| United States — federal + state | Determine applicable state privacy/biometric/health laws, CCPA/CPRA in scope, HIPAA only when its covered-entity/business-associate conditions apply, and restrictions on surveillance or communications recording. No single blanket US rule. |
| Brazil — LGPD | Controller/processor roles, lawful basis, sensitive data, notice, rights, retention and international transfers under current ANPD rules. |
| South Korea — PIPA | Specific surveillance/camera, sensitive data, notification and transfer requirements; competent authority and current sector rules. |
| Japan — APPI | Handling of personal data, purposes, third-party provision, data-subject rights and cross-border rules. |
| Other countries | No automatic allow. Identify local data-protection, surveillance, medical-device, employment, children's, security and cross-border laws; assess and approve explicitly. |

There is **no software switch** that can assert compliance with every
country. The technical gate checks that a jurisdiction is named and has a
recorded basis; **it cannot independently determine if that basis is valid**,
whether notice was actually displayed, whether a DPIA is sufficient, or
whether an AI fall-detection tool legally qualifies as a medical device.
Any use as a medical/clinical or life-safety system requires separate
regulatory classification, validation, risk management and authorization.

## Engineering control framework (targets, not certification)

- ISO/IEC 27001:2022 — ISMS governance and risk ownership.
- ISO/IEC 27701:2025 — privacy information management and accountability.
- ISO/IEC 29100:2024 — privacy framework / PII principles.
- NIST CSF 2.0 — Govern, Identify, Protect, Detect, Respond, Recover.
- NIST Privacy Framework — privacy risk management.

No independent third-party certification, penetration test, formal DPIA,
accessibility review, end-to-end encryption review or production SOC
assessment has been performed.

## Deployment blockers — overall system not yet legally ready

1. **Member 2 Backend:** existing demo incident create/review endpoints have
   no user authentication. Restrict to loopback/dev network until Member 2
   implements authenticated roles, permissions per camera/incident,
   secure sessions, anti-CSRF if cookie auth, rate limits, centralized
   secret management, immutable audit trail, incident response and
   explicit production demo-mode disablement. CORS is not auth.
2. **Evidence & transfers:** local Edge currently has no approved
   privacy-preserving evidence export or verified cross-border processing
   agreement. Do not send raw video, faces or derived identifying
   information to Meta/cloud providers without explicit new reviewed
   controls and applicable transfer agreements.
3. **DSAR/retention:** invent a documented request/rectification/deletion
   workflow across logs, candidate events, incident records, backups and
   service providers; enforce purpose-based retention and secure deletion.
   Zero *raw-frame retention* at Edge is not zero retention elsewhere.
4. **Camera & worker hardening:** use read-only credentials, VLAN/egress
   firewall and device allowlists, safe firmware/codec handling, secured
   terminal logs (FFmpeg may print camera URLs), managed keys, rotation,
   vulnerability scanning, patching and intrusion response. Fleet stdout
   can interleave; it is not an authenticated message bus.
5. **Life/safety:** model accuracy, false alarms/hour, clinical validity
   and actual human notification response have not been validated. No
   real emergency/medical decision or unattended monitoring is allowed.

Official regulatory / standards starting points (review current local law):
- EU EDPB video guidance: https://www.edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-32019-processing-personal-data-through-video_en
- GDPR DPIA overview: https://europa.eu/youreurope/business/governance-and-sustainability/digital-and-data-compliance/data-protection-gdpr/index_en.htm
- EU AI Act: https://digital-strategy.ec.europa.eu/en/policies/regulatory-framework-ai
- UK business CCTV: https://www.gov.uk/data-protection-your-business/using-cctv
- California CCPA: https://www.oag.ca.gov/privacy/ccpa
- ISO/IEC 27701:2025: https://www.iso.org/standard/27701
- ISO/IEC 27001:2022: https://www.iso.org/standard/27001
- NIST CSF 2.0: https://www.nist.gov/cyberframework
- NIST Privacy Framework: https://www.nist.gov/privacy-framework/privacy-framework
