/**
 * Member 1 read-only caregiver inbox contract.
 * Only Member 2 authenticated backend may create real advisories/receipts.
 * Never render raw video, identity, health information or model prose.
 * Contract acceptance in the browser is NOT authorization proof.
 */
export const CAREGIVER_INBOX_SCHEMA = "viil.backend.caregiver_inbox.v1" as const;
export const MAX_INBOX_BYTES = 32 * 1024;
export const MAX_ADVISORIES = 30;
export const INBOX_TTL_MS = 30_000;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const SLUG = /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/;
const ISO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;

export type AdvisoryStage = "edge_candidate" | "follow_up_required" | "informational_advisory";
export type ContextCode = "unknown" | "near_floor" | "wheelchair_transfer" | "rapid_descent";
export type DeliveryState = "not_sent" | "pending" | "delivered" | "failed";
export type ReviewState = "pending" | "acknowledged" | "closed";
export type MetaProvenance = "none" | "mock" | "meta_model_api";
export type CaregiverAdvisory = Readonly<{
  advisory_id: string;
  source_id: string;
  occurred_at: string;
  stage: AdvisoryStage;
  context_code: ContextCode;
  meta_provenance: MetaProvenance;
  delivery_state: DeliveryState;
  receipt_verified: boolean;
  review_state: ReviewState;
  simulated: boolean;
  fall_confirmed: false;
  emergency_dispatch_authorized: false;
  human_follow_up_required: true;
}>;
export type CaregiverInbox = Readonly<{
  schema_version: typeof CAREGIVER_INBOX_SCHEMA;
  generated_at: string;
  access_scope: "authenticated_caregiver";
  advisories: readonly CaregiverAdvisory[];
}>;

function record(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}
function exact(v: unknown, names: readonly string[]): v is Record<string, unknown> {
  return record(v) && Object.keys(v).length === names.length
    && names.every(key => Object.hasOwn(v, key));
}
function oneOf<T extends string>(v: unknown, values: readonly T[]): v is T {
  return typeof v === "string" && values.includes(v as T);
}
function timestamp(v: unknown): v is string {
  if (typeof v !== "string" || !ISO.test(v)) return false;
  const parsed = Date.parse(v);
  return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 19) === v.slice(0, 19);
}
function validateAdvisory(v: unknown, generatedMs: number): v is CaregiverAdvisory {
  if (!exact(v, [
    "advisory_id", "source_id", "occurred_at", "stage", "context_code",
    "meta_provenance", "delivery_state", "receipt_verified", "review_state",
    "simulated", "fall_confirmed", "emergency_dispatch_authorized",
    "human_follow_up_required",
  ])) return false;
  if (typeof v.advisory_id !== "string" || !UUID.test(v.advisory_id)
    || typeof v.source_id !== "string" || !SLUG.test(v.source_id)
    || !timestamp(v.occurred_at) || Date.parse(v.occurred_at) > generatedMs + 5_000
    || !oneOf(v.stage, ["edge_candidate", "follow_up_required", "informational_advisory"])
    || !oneOf(v.context_code, ["unknown", "near_floor", "wheelchair_transfer", "rapid_descent"])
    || !oneOf(v.meta_provenance, ["none", "mock", "meta_model_api"])
    || !oneOf(v.delivery_state, ["not_sent", "pending", "delivered", "failed"])
    || !oneOf(v.review_state, ["pending", "acknowledged", "closed"])
    || typeof v.simulated !== "boolean"
    || v.receipt_verified !== (v.delivery_state === "delivered")
    || v.fall_confirmed !== false
    || v.emergency_dispatch_authorized !== false
    || v.human_follow_up_required !== true
    || (v.stage === "informational_advisory" && v.meta_provenance !== "meta_model_api")
    || (v.meta_provenance === "meta_model_api" && v.simulated)
    || (v.stage === "edge_candidate" && v.meta_provenance === "meta_model_api")) {
    return false;
  }
  return true;
}

export function parseCaregiverInbox(v: unknown): CaregiverInbox {
  if (!exact(v, ["schema_version", "generated_at", "access_scope", "advisories"])
    || v.schema_version !== CAREGIVER_INBOX_SCHEMA
    || !timestamp(v.generated_at)
    || v.access_scope !== "authenticated_caregiver"
    || !Array.isArray(v.advisories)
    || v.advisories.length > MAX_ADVISORIES) {
    throw new Error("Invalid caregiver inbox response (redacted)");
  }
  const generatedMs = Date.parse(v.generated_at);
  if (!v.advisories.every((item: unknown) => validateAdvisory(item, generatedMs))
    || new Set(v.advisories.map((x: CaregiverAdvisory) => x.advisory_id)).size
       !== v.advisories.length) {
    throw new Error("Invalid caregiver advisory contract (redacted)");
  }
  return v as CaregiverInbox;
}
export function caregiverInboxFresh(v: CaregiverInbox, nowMs = Date.now()): boolean {
  const age = nowMs - Date.parse(v.generated_at);
  return Number.isFinite(age) && age >= -5_000 && age <= INBOX_TTL_MS;
}
export type AdvisoryPresentation = Readonly<{
  title: string;
  context: string;
  meta: string;
  delivery: string;
  review: string;
}>;
export function presentAdvisory(v: CaregiverAdvisory): AdvisoryPresentation {
  // Map strictly enumerated codes, never echo untrusted AI prose as instructions.
  const titles: Record<AdvisoryStage, string> = {
    edge_candidate: "Possible fall · unconfirmed Edge candidate",
    follow_up_required: "Follow-up needed · assessment uncertain",
    informational_advisory: "Informational advisory · backend-reported Meta assessment",
  };
  const contexts: Record<ContextCode, string> = {
    unknown: "No reliable activity context available",
    near_floor: "Person appears near floor in authorized scene",
    wheelchair_transfer: "Activity may involve wheelchair transfer",
    rapid_descent: "Rapid posture change was observed",
  };
  const deliveries: Record<DeliveryState, string> = {
    not_sent: "No notification dispatched",
    pending: "Delivery pending · not yet verified",
    delivered: "Backend reports verified delivery receipt",
    failed: "Delivery failed · requires human follow-up",
  };
  const reviews: Record<ReviewState, string> = {
    pending: "Caregiver review pending",
    acknowledged: "Backend reports acknowledged",
    closed: "Backend reports closed",
  };
  return {
    title: titles[v.stage],
    context: contexts[v.context_code],
    meta: v.meta_provenance === "meta_model_api"
      ? "Backend reports genuine Meta processing; not independently verified in browser"
      : v.meta_provenance === "mock" ? "MOCK only · no actual Meta inference"
        : "No Meta inference reported",
    delivery: deliveries[v.delivery_state],
    review: reviews[v.review_state],
  };
}

/**
 * Bounded same-origin GET. Backend MUST enforce session auth, tenant/source
 * RBAC, privacy/data minimization, and verified delivery receipts.
 */
export async function fetchCaregiverInbox(signal?: AbortSignal): Promise<CaregiverInbox> {
  const response = await fetch("/api/v1/caregiver/inbox", {
    method: "GET", credentials: "same-origin", cache: "no-store",
    redirect: "error", headers: { Accept: "application/json" }, signal,
  });
  if (!response.ok) {
    throw new Error(
      response.status === 401 || response.status === 403
        ? "Caregiver authentication and access permissions required"
        : "Caregiver inbox unavailable",
    );
  }
  const declared = response.headers.get("content-length");
  if (declared && (!/^\d+$/.test(declared) || Number(declared) > MAX_INBOX_BYTES)) {
    throw new Error("Caregiver inbox too large");
  }
  if (!response.body) throw new Error("Empty caregiver inbox");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let count = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      count += value.byteLength;
      if (count > MAX_INBOX_BYTES) {
        await reader.cancel();
        throw new Error("Caregiver inbox too large");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(count);
  let pos = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, pos);
    pos += chunk.byteLength;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)) as unknown;
  } catch {
    throw new Error("Malformed caregiver inbox response");
  }
  return parseCaregiverInbox(parsed);
}
