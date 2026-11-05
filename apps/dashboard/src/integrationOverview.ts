/**
 * Member 1 ↔ Member 2 read-only integration surface.
 * Strict allowlisted metadata; no RTSP URLs, frames, API keys, prompts,
 * identities or evidence payloads. Browser NEVER connects directly to Meta.
 * An accepted JSON envelope is NOT itself proof of backend authentication.
 */
export const INTEGRATION_SCHEMA = "viil.backend.integration_overview.v1" as const;
export const MAX_INTEGRATION_BYTES = 32 * 1024;
export const MAX_CAMERA_SOURCES = 16;
export const SNAPSHOT_TTL_MS = 30_000;

export type CameraTransport = "rtsp" | "usb";
export type CameraHealth = "online" | "degraded" | "offline" | "unknown";
export type PrivacyState = "approved" | "expired" | "revoked" | "unverified";
export type IntegrationState = "ready" | "degraded" | "offline" | "not_configured";

export type CameraSummary = Readonly<{
  camera_id: string;
  transport: CameraTransport;
  health: CameraHealth;
  privacy: PrivacyState;
  last_heartbeat_at: string | null;
  observed_fps: number | null;
}>;
export type IntegrationOverview = Readonly<{
  schema_version: typeof INTEGRATION_SCHEMA;
  generated_at: string;
  access_scope: "authenticated_operator";
  edge: Readonly<{ state: IntegrationState; last_heartbeat_at: string | null }>;
  cameras: readonly CameraSummary[];
  meta: Readonly<{
    provider: "meta_model_api" | "mock" | "unavailable";
    state: IntegrationState;
    evidence_pipeline: "ready" | "blocked" | "not_configured";
    last_verified_call_at: string | null;
  }>;
  notification: Readonly<{ state: IntegrationState }>;
}>;

function record(v: unknown): v is Record<string, unknown> {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}
function fields(v: unknown, keys: readonly string[]): v is Record<string, unknown> {
  return record(v) && Object.keys(v).length === keys.length
    && keys.every(k => Object.hasOwn(v, k));
}
function choice<T extends string>(v: unknown, values: readonly T[]): v is T {
  return typeof v === "string" && values.includes(v as T);
}
const healthStates = ["ready", "degraded", "offline", "not_configured"] as const;
const cameraStates = ["online", "degraded", "offline", "unknown"] as const;
const privacyStates = ["approved", "expired", "revoked", "unverified"] as const;
const isoRe = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
const slugRe = /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/;
function iso(v: unknown): v is string {
  return typeof v === "string" && isoRe.test(v) && Number.isFinite(Date.parse(v));
}
function isoOrNull(v: unknown): v is string | null {
  return v === null || iso(v);
}
function heartbeatIsCurrent(value: string, generatedAt: string): boolean {
  const elapsed = Date.parse(generatedAt) - Date.parse(value);
  return Number.isFinite(elapsed) && elapsed >= -5_000 && elapsed <= SNAPSHOT_TTL_MS;
}
function validCamera(v: unknown): v is CameraSummary {
  if (!fields(v, ["camera_id", "transport", "health", "privacy",
                   "last_heartbeat_at", "observed_fps"])) return false;
  return typeof v.camera_id === "string" && slugRe.test(v.camera_id)
    && choice(v.transport, ["rtsp", "usb"])
    && choice(v.health, cameraStates) && choice(v.privacy, privacyStates)
    && isoOrNull(v.last_heartbeat_at)
    && (v.observed_fps === null
      || (typeof v.observed_fps === "number" && Number.isFinite(v.observed_fps)
        && v.observed_fps >= 0 && v.observed_fps <= 240))
    && (v.health !== "online" || (v.privacy === "approved"
      && v.last_heartbeat_at !== null));
}
/** Reject unknown/sensitive fields rather than silently dropping data. */
export function parseIntegrationOverview(value: unknown): IntegrationOverview {
  if (!fields(value, ["schema_version", "generated_at", "access_scope",
                      "edge", "cameras", "meta", "notification"])
    || value.schema_version !== INTEGRATION_SCHEMA
    || !iso(value.generated_at)
    || value.access_scope !== "authenticated_operator"
    || !fields(value.edge, ["state", "last_heartbeat_at"])
    || !choice(value.edge.state, healthStates)
    || !isoOrNull(value.edge.last_heartbeat_at)
    || !Array.isArray(value.cameras)
    || value.cameras.length > MAX_CAMERA_SOURCES
    || !value.cameras.every(validCamera)
    || new Set(value.cameras.map((c: CameraSummary) => c.camera_id)).size !== value.cameras.length
    || value.cameras.some((c: CameraSummary) => c.health === "online"
      && (c.last_heartbeat_at === null
        || !heartbeatIsCurrent(c.last_heartbeat_at, value.generated_at as string)))
    || (value.edge.state === "ready"
      && (value.edge.last_heartbeat_at === null
        || !heartbeatIsCurrent(value.edge.last_heartbeat_at, value.generated_at as string)))
    || !fields(value.meta, ["provider", "state", "evidence_pipeline", "last_verified_call_at"])
    || !choice(value.meta.provider, ["meta_model_api", "mock", "unavailable"])
    || !choice(value.meta.state, healthStates)
    || !choice(value.meta.evidence_pipeline, ["ready", "blocked", "not_configured"])
    || !isoOrNull(value.meta.last_verified_call_at)
    || !fields(value.notification, ["state"])
    || !choice(value.notification.state, healthStates)) {
    throw new Error("Invalid integration overview contract (details redacted)");
  }
  if ((value.meta.provider !== "meta_model_api"
      && (value.meta.last_verified_call_at !== null || value.meta.state === "ready"))
      || (value.meta.provider === "meta_model_api" && value.meta.state === "ready"
        && (value.meta.evidence_pipeline !== "ready"
          || value.meta.last_verified_call_at === null))
      || (value.meta.state === "not_configured"
        && value.meta.last_verified_call_at !== null)) {
    throw new Error("Invalid integration provider state (details redacted)");
  }
  return value as IntegrationOverview;
}
export function snapshotIsFresh(snapshot: IntegrationOverview, nowMs = Date.now()): boolean {
  const elapsed = nowMs - Date.parse(snapshot.generated_at);
  return Number.isFinite(elapsed) && elapsed >= -5_000 && elapsed <= SNAPSHOT_TTL_MS;
}

export async function fetchIntegrationOverview(signal?: AbortSignal): Promise<IntegrationOverview> {
  // Same-origin reverse proxy only. Do not allow a user-provided URL or put
  // provider secrets into this request. Member 2 must enforce session/RBAC.
  const response = await fetch("/api/v1/integrations/overview", {
    method: "GET", credentials: "same-origin", cache: "no-store", redirect: "error",
    headers: { Accept: "application/json" }, signal,
  });
  if (!response.ok) throw new Error(
    response.status === 401 || response.status === 403
      ? "Authentication/authorization required by backend"
      : "Integration endpoint unavailable",
  );
  const size = response.headers.get("content-length");
  if (size && Number(size) > MAX_INTEGRATION_BYTES) {
    throw new Error("Integration snapshot too large");
  }
  // Enforce the limit WHILE streaming so a malicious/misconfigured
  // backend cannot force the browser to buffer an unbounded response.
  if (!response.body) throw new Error("Empty integration response");
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      received += value.byteLength;
      if (received > MAX_INTEGRATION_BYTES) {
        await reader.cancel();
        throw new Error("Integration snapshot too large");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(received);
  let offset = 0;
  for (const part of chunks) {
    bytes.set(part, offset);
    offset += part.byteLength;
  }
  let raw: string;
  try {
    raw = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new Error("Invalid integration response encoding");
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw) as unknown;
  } catch {
    throw new Error("Invalid integration response");
  }
  return parseIntegrationOverview(parsed);
}
