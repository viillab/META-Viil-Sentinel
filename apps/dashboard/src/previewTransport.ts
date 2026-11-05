/** Member1 loopback-only preview transport diagnostics.
 * Edge JPEG production is NOT evidence the browser rendered an image.
 * Production Member2 backend does not need to implement this optional route.
 */
import type { CameraPreviewSession } from "./cameraPreview";
import { previewBasePath, safeCameraId } from "./cameraPreview.ts";

export const PREVIEW_TRANSPORT_SCHEMA = "viil.local.preview_transport_status.v1" as const;
const MAX_RESPONSE_BYTES = 2048;
const sessionIdPattern = /^[A-Za-z0-9_-]{16,80}$/;

export type PreviewTransportStatus = Readonly<{
  schema_version: typeof PREVIEW_TRANSPORT_SCHEMA;
  camera_id: string;
  session_id: string;
  edge_first_jpeg_verified: boolean;
  edge_preflight_started: boolean;
  browser_image_display_verified: false;
}>;

export function parsePreviewTransportStatus(
  raw: unknown, session: CameraPreviewSession,
): PreviewTransportStatus {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("Invalid local preview transport status");
  }
  const v = raw as Record<string, unknown>;
  const fields = [
    "schema_version", "camera_id", "session_id", "edge_first_jpeg_verified",
    "edge_preflight_started", "browser_image_display_verified",
  ];
  if (Object.keys(v).length !== fields.length
      || !fields.every(key => Object.hasOwn(v, key))
      || v.schema_version !== PREVIEW_TRANSPORT_SCHEMA
      || !safeCameraId(session.camera_id)
      || !sessionIdPattern.test(session.session_id)
      || v.camera_id !== session.camera_id
      || v.session_id !== session.session_id
      || typeof v.edge_first_jpeg_verified !== "boolean"
      || typeof v.edge_preflight_started !== "boolean"
      || v.browser_image_display_verified !== false
      || (v.edge_first_jpeg_verified === true && v.edge_preflight_started !== true)) {
    throw new Error("Invalid local preview transport status");
  }
  return v as PreviewTransportStatus;
}

export async function fetchPreviewTransportStatus(
  session: CameraPreviewSession, signal?: AbortSignal,
): Promise<PreviewTransportStatus> {
  if (!safeCameraId(session.camera_id) || !sessionIdPattern.test(session.session_id)) {
    throw new Error("Invalid local preview transport status");
  }
  const response = await fetch(
    `${previewBasePath(session.camera_id)}/${session.session_id}/status`,
    {
      method: "GET", credentials: "same-origin", mode: "same-origin",
      cache: "no-store", redirect: "error",
      headers: { Accept: "application/json" }, signal,
    },
  );
  if (!response.ok || !response.body) {
    throw new Error("Local preview transport status unavailable");
  }
  const length = response.headers.get("content-length");
  if (length && (!Number.isFinite(Number(length)) || Number(length) > MAX_RESPONSE_BYTES)) {
    throw new Error("Invalid local preview transport status");
  }
  const reader = response.body.getReader();
  const pieces: Uint8Array[] = [];
  let count = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      count += value.byteLength;
      if (count > MAX_RESPONSE_BYTES) {
        await reader.cancel();
        throw new Error("Invalid local preview transport status");
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
    offset += piece.byteLength;
  }
  try {
    return parsePreviewTransportStatus(
      JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)), session,
    );
  } catch {
    throw new Error("Invalid local preview transport status");
  }
}
