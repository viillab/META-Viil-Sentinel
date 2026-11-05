/**
 * Local demo incident adapter: strictly bounded, simulated-only and
 * same-origin. This is NOT Member 2's authenticated production incident API.
 * It MUST NOT read real patient incidents or trust HTTP 200 as authorization.
 */
const MAX_BYTES = 128 * 1024;
const MAX_INCIDENTS = 50;
const LIMIT_MS = 8_000;
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const slugPattern = /^[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}$/;
const allowedStatuses = [
  "DETECTED", "ANALYZING", "REVIEW_REQUIRED", "NOTIFIED",
  "ACKNOWLEDGED", "VERIFIED", "FALSE_ALERT", "RESOLVED",
] as const;
const allowedActions = [
  "ACKNOWLEDGE", "VERIFY", "MARK_FALSE_ALERT", "RESOLVE",
] as const;
export type IncidentStatus = typeof allowedStatuses[number];
export type DemoAction = typeof allowedActions[number];
export type DemoIncident = Readonly<{
  id: string;
  source_id: string;
  status: IncidentStatus;
  confidence: number;
  simulated: true;
  notification_sent: boolean;
  created_at: string;
  updated_at: string;
  observation: Readonly<{
    posture: string;
    surroundings: string;
    uncertainty: readonly string[];
    evidence_refs: readonly [];
    generated_by: "mock";
    medical_severity: null;
  }> | null;
  history: readonly Readonly<{
    time: string; event: string; actor: string;
    from_status: IncidentStatus | null;
    to_status: IncidentStatus;
  }>[];
}>;

function isObject(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === "object" && !Array.isArray(v);
}
function matchesFields(
  v: unknown, required: readonly string[], optional: readonly string[] = [],
): v is Record<string, unknown> {
  return isObject(v) && required.every(key => Object.hasOwn(v, key))
    && Object.keys(v).every(key => required.includes(key) || optional.includes(key));
}
function safeText(v: unknown, max = 240): v is string {
  return typeof v === "string" && v.length <= max
    && !/[\x00-\x1f\x7f<>]/.test(v);
}
function timestamp(v: unknown): v is string {
  return safeText(v, 55) && v.includes("T")
    && Number.isFinite(Date.parse(v));
}
function status(v: unknown): v is IncidentStatus {
  return typeof v === "string" && allowedStatuses.includes(v as IncidentStatus);
}
function observation(value: unknown): boolean {
  if (value === null) return true;
  if (!matchesFields(value, [
    "posture", "surroundings", "uncertainty", "evidence_refs",
    "generated_by", "medical_severity",
  ])) return false;
  return safeText(value.posture, 240)
    && safeText(value.surroundings, 240)
    && value.generated_by === "mock" && value.medical_severity === null
    && Array.isArray(value.evidence_refs) && value.evidence_refs.length === 0
    && Array.isArray(value.uncertainty) && value.uncertainty.length <= 8
    && value.uncertainty.every((s: unknown) => safeText(s, 240));
}
function audit(value: unknown): boolean {
  return matchesFields(value, [
    "time", "event", "actor", "from_status", "to_status",
  ]) && timestamp(value.time) && safeText(value.event, 80)
    && safeText(value.actor, 80)
    && (value.from_status === null || status(value.from_status))
    && status(value.to_status);
}
export function parseDemoIncident(value: unknown): DemoIncident {
  const required = ["id", "source_id", "status", "confidence", "simulated",
    "notification_sent", "created_at", "updated_at", "observation", "history"];
  if (!matchesFields(value, required)
    || typeof value.id !== "string" || !uuidPattern.test(value.id)
    || typeof value.source_id !== "string" || !slugPattern.test(value.source_id)
    || !status(value.status) || value.simulated !== true
    || typeof value.notification_sent !== "boolean"
    || typeof value.confidence !== "number" || !Number.isFinite(value.confidence)
    || value.confidence < 0 || value.confidence > 1
    || !timestamp(value.created_at) || !timestamp(value.updated_at)
    || !observation(value.observation)
    || !Array.isArray(value.history) || value.history.length > 40
    || !value.history.every(audit)) {
    throw new Error("Invalid or unsafe local demo incident (redacted)");
  }
  return value as DemoIncident;
}
export function parseDemoIncidentList(value: unknown): DemoIncident[] {
  if (!Array.isArray(value) || value.length > MAX_INCIDENTS) {
    throw new Error("Invalid or oversized local demo incident list");
  }
  const incidents = value.map(parseDemoIncident);
  const ids = incidents.map(x => x.id);
  if (new Set(ids).size !== ids.length) {
    throw new Error("Duplicate demo incident IDs");
  }
  return incidents;
}
export function allowLocalDemo(hostname: string, enabled: boolean): boolean {
  return enabled === true && (hostname === "localhost" || hostname === "127.0.0.1");
}
async function fetchBounded(
  path: string, init: RequestInit, signal?: AbortSignal,
): Promise<unknown> {
  // UI can only access three fixed app-relative paths built below.
  const controller = new AbortController();
  const stop = () => controller.abort();
  signal?.addEventListener("abort", stop, { once: true });
  if (signal?.aborted) controller.abort();
  const deadline = setTimeout(stop, LIMIT_MS);
  try {
    const response = await fetch(path, {
      ...init, credentials: "same-origin", cache: "no-store",
      redirect: "error", signal: controller.signal,
    });
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        throw new Error("Backend authentication/authorization required");
      }
      throw new Error("Local demo endpoint unavailable");
    }
    const declared = response.headers.get("content-length");
    if (declared && (!/^\d+$/.test(declared) || Number(declared) > MAX_BYTES)) {
      throw new Error("Local demo response too large");
    }
    if (!response.body) throw new Error("Empty local demo response");
    const reader = response.body.getReader();
    const chunks: Uint8Array[] = [];
    let size = 0;
    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > MAX_BYTES) {
          await reader.cancel();
          throw new Error("Local demo response too large");
        }
        chunks.push(value);
      }
    } finally {
      reader.releaseLock();
    }
    const all = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      all.set(chunk, offset);
      offset += chunk.byteLength;
    }
    try {
      return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(all)) as unknown;
    } catch {
      throw new Error("Malformed local demo response");
    }
  } finally {
    clearTimeout(deadline);
    signal?.removeEventListener("abort", stop);
  }
}
export async function listLocalDemoIncidents(signal?: AbortSignal): Promise<DemoIncident[]> {
  return parseDemoIncidentList(await fetchBounded("/api/v1/incidents", {
    method: "GET", headers: { Accept: "application/json" },
  }, signal));
}
export async function createLocalDemoIncident(): Promise<DemoIncident> {
  return parseDemoIncident(await fetchBounded("/api/v1/incidents/demo", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_id: "STAGED-CAMERA-01", confidence: 0.82 }),
  }));
}
export async function reviewLocalDemoIncident(
  id: string, action: DemoAction, actor: string,
): Promise<DemoIncident> {
  if (!uuidPattern.test(id) || !allowedActions.includes(action)
    || !safeText(actor, 80) || !actor.trim()) {
    throw new Error("Invalid local demo review arguments");
  }
  return parseDemoIncident(await fetchBounded(
    `/api/v1/incidents/${id}/review`,
    { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, actor }) },
  ));
}
