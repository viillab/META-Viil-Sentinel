/** A local privacy draft is not a signed approval or legal certification.
 * Only known field names may be displayed. Never expose private refs/paths.
 */
export const APPROVAL_CHECKLIST_SCHEMA = "viil.local.unsigned_approval_checklist.v1" as const;
const MAX_CHECKLIST_BYTES = 4096;
const SAFE_ISSUES = new Set([
  "schema_version", "purpose", "approval_ref", "controller_ref",
  "notice_ref", "privacy_impact_review_ref", "sensitive_data_review_ref",
  "rights_procedure_ref", "jurisdictions", "legal_basis_by_jurisdiction",
  "approved_camera_ids", "validity_window", "site_authorization_confirmed",
  "notices_confirmed", "human_review_required", "local_only",
  "cloud_transfer_enabled", "face_identification_enabled",
  "training_reuse_enabled", "automatic_emergency_dispatch_enabled",
  "raw_frame_retention_days",
]);

export type ApprovalChecklist = Readonly<{
  schema_version: typeof APPROVAL_CHECKLIST_SCHEMA;
  draft_available: boolean;
  draft_fields_structurally_complete: boolean;
  issues: string[];
  genuine_site_permission_confirmed_by_tool: false;
  signed_policy_verified: false;
  camera_access_granted: false;
}>;

export function parseApprovalChecklist(value: unknown): ApprovalChecklist {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid unsigned approval checklist");
  }
  const v = value as Record<string, unknown>;
  const fields = [
    "schema_version", "draft_available", "draft_fields_structurally_complete",
    "issues", "genuine_site_permission_confirmed_by_tool",
    "signed_policy_verified", "camera_access_granted",
  ];
  if (Object.keys(v).length !== fields.length
    || !fields.every(name => Object.hasOwn(v, name))
    || v.schema_version !== APPROVAL_CHECKLIST_SCHEMA
    || typeof v.draft_available !== "boolean"
    || typeof v.draft_fields_structurally_complete !== "boolean"
    || v.genuine_site_permission_confirmed_by_tool !== false
    || v.signed_policy_verified !== false
    || v.camera_access_granted !== false
    || !Array.isArray(v.issues)
    || v.issues.length > SAFE_ISSUES.size
    || v.issues.some(i => typeof i !== "string" || !SAFE_ISSUES.has(i))
    || new Set(v.issues).size !== v.issues.length
    || (v.draft_available === false && v.issues.length !== 0)
    || v.draft_fields_structurally_complete !== (
      v.draft_available === true && v.issues.length === 0
    )) {
    throw new Error("Invalid unsigned approval checklist");
  }
  return v as ApprovalChecklist;
}

export async function fetchApprovalChecklist(signal?: AbortSignal): Promise<ApprovalChecklist> {
  const response = await fetch("/api/v1/operator/approval-checklist", {
    method: "GET", mode: "same-origin", credentials: "same-origin",
    cache: "no-store", redirect: "error",
    headers: { Accept: "application/json" }, signal,
  });
  if (!response.ok || !response.body) throw new Error("Local approval review unavailable");
  const length = response.headers.get("content-length");
  if (length && (!Number.isFinite(Number(length)) || Number(length) > MAX_CHECKLIST_BYTES)) {
    throw new Error("Invalid unsigned approval checklist");
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let count = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      count += value.byteLength;
      if (count > MAX_CHECKLIST_BYTES) {
        await reader.cancel();
        throw new Error("Invalid unsigned approval checklist");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(count);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return parseApprovalChecklist(
      JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)),
    );
  } catch {
    throw new Error("Invalid unsigned approval checklist");
  }
}
