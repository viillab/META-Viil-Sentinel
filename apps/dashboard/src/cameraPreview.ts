/**
 * Browser-facing, same-origin *session* contract only.
 *
 * An authenticated, camera-scoped backend must independently verify signed
 * Edge policy, notice/site approval and viewer RBAC before creating a session
 * AND on every MJPEG request/frame. A Vite proxy is NOT that backend.
 * No camera host, RTSP URL, credential, frame buffer or bearer token enters JS.
 */
export const CAMERA_PREVIEW_SCHEMA = "viil.backend.camera_preview_session.v1" as const;
export const MAX_PREVIEW_JSON_BYTES = 2048;
export const MAX_PREVIEW_LIFETIME_MS = 30_000;
const cameraIdRe = /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/;
const sessionIdRe = /^[A-Za-z0-9_-]{16,80}$/;
const dateRe = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;

export type CameraPreviewSession = Readonly<{
  schema_version: typeof CAMERA_PREVIEW_SCHEMA;
  camera_id: string;
  session_id: string;
  expires_at: string;
}>;

export function safeCameraId(value: unknown): value is string {
  return typeof value === "string" && cameraIdRe.test(value);
}

export function previewBasePath(cameraId: string): string {
  if (!safeCameraId(cameraId)) throw new Error("Invalid preview camera ID");
  return `/api/v1/cameras/${cameraId}/preview-sessions`;
}

export function previewImagePath(session: CameraPreviewSession): string {
  // Generate only from IDs; expiry is rechecked by UI timer/backend, not
  // during React render (a render error could leave a session unrevoked).
  if (!session || typeof session.session_id !== "string"
      || !sessionIdRe.test(session.session_id)) {
    throw new Error("Invalid preview session ID");
  }
  return `${previewBasePath(session.camera_id)}/${session.session_id}/mjpeg`;
}

export function parseCameraPreviewSession(
  value: unknown, expectedCameraId: string, nowMs = Date.now(),
): CameraPreviewSession {
  if (!safeCameraId(expectedCameraId)
      || !value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid camera preview session");
  }
  const obj = value as Record<string, unknown>;
  if (Object.keys(obj).length !== 4
      || !Object.hasOwn(obj, "schema_version")
      || !Object.hasOwn(obj, "camera_id")
      || !Object.hasOwn(obj, "session_id")
      || !Object.hasOwn(obj, "expires_at")
      || obj.schema_version !== CAMERA_PREVIEW_SCHEMA
      || obj.camera_id !== expectedCameraId
      || typeof obj.session_id !== "string" || !sessionIdRe.test(obj.session_id)
      || typeof obj.expires_at !== "string" || !dateRe.test(obj.expires_at)) {
    throw new Error("Invalid camera preview session");
  }
  const lifetime = Date.parse(obj.expires_at) - nowMs;
  if (!Number.isFinite(lifetime) || lifetime <= 0
      || lifetime > MAX_PREVIEW_LIFETIME_MS) {
    throw new Error("Camera preview session not current");
  }
  return obj as CameraPreviewSession;
}

async function boundedJson(response: Response): Promise<unknown> {
  const length = response.headers.get("content-length");
  if (length && (Number(length) > MAX_PREVIEW_JSON_BYTES
      || !Number.isFinite(Number(length)))) {
    throw new Error("Invalid camera preview session");
  }
  if (!response.body) throw new Error("Invalid camera preview session");
  const reader = response.body.getReader();
  const pieces: Uint8Array[] = [];
  let count = 0;
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      count += value.byteLength;
      if (count > MAX_PREVIEW_JSON_BYTES) {
        await reader.cancel();
        throw new Error("Invalid camera preview session");
      }
      pieces.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(count);
  let offset = 0;
  for (const piece of pieces) {
    bytes.set(piece, offset);
    offset += piece.length;
  }
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
  } catch {
    throw new Error("Invalid camera preview session");
  }
}

/** Called ONLY after an operator presses Open on a fresh, approved camera. */
export async function openCameraPreview(
  cameraId: string, signal?: AbortSignal,
): Promise<CameraPreviewSession> {
  const path = previewBasePath(cameraId);
  const response = await fetch(path, {
    method: "POST", credentials: "same-origin", mode: "same-origin",
    cache: "no-store", redirect: "error",
    headers: { Accept: "application/json", "X-VIIL-Preview-Intent": "operator-click" },
    signal,
  });
  if (!response.ok) {
    // Never reflect HTTP response content: it can contain secrets.
    throw new Error(response.status === 401 || response.status === 403
      ? "Operator authentication or camera access denied"
      : "Protected camera media gateway unavailable");
  }
  return parseCameraPreviewSession(await boundedJson(response), cameraId);
}

/**
 * Backend must treat DELETE as idempotent revocation, scoped to same operator.
 * Expiry is authoritative on server even if browser loses network/visibility.
 */
export async function closeCameraPreview(
  session: CameraPreviewSession,
): Promise<void> {
  const id = session.camera_id;
  if (!safeCameraId(id) || typeof session.session_id !== "string"
      || !sessionIdRe.test(session.session_id)) return;
  try {
    await fetch(`${previewBasePath(id)}/${session.session_id}`, {
      method: "DELETE", credentials: "same-origin", mode: "same-origin",
      cache: "no-store", redirect: "error",
      headers: { "X-VIIL-Preview-Intent": "operator-close" },
      keepalive: true,
    });
  } catch {
    // Fail closed in UI; short server-side expiry is the final safeguard.
  }
}
