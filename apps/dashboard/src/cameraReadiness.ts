/** Operator-only local Edge prerequisites. NEVER an evidence of live video. */
export const CAMERA_READINESS_SCHEMA = "viil.local.camera_readiness.v1" as const;
const MAX_READINESS_BYTES = 2048;
const idPattern = /^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/;

export type CameraReadiness = Readonly<{
  schema_version: typeof CAMERA_READINESS_SCHEMA;
  camera_id: string;
  signed_privacy_approval_verified: boolean;
  private_rtsp_configured: boolean;
  pyav_decoder_installed: boolean;
  opencv_jpeg_encoder_installed: boolean;
  eligible_for_supervised_trial: boolean;
  real_camera_frame_verified: false;
}>;

export function parseCameraReadiness(raw: unknown): CameraReadiness {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("Invalid local camera readiness response");
  }
  const v = raw as Record<string, unknown>;
  const names = [
    "schema_version", "camera_id", "signed_privacy_approval_verified",
    "private_rtsp_configured", "pyav_decoder_installed",
    "opencv_jpeg_encoder_installed", "eligible_for_supervised_trial",
    "real_camera_frame_verified",
  ];
  if (Object.keys(v).length !== names.length
    || !names.every(k => Object.hasOwn(v, k))
    || v.schema_version !== CAMERA_READINESS_SCHEMA
    || typeof v.camera_id !== "string" || !idPattern.test(v.camera_id)
    || names.slice(2).some(k => typeof v[k] !== "boolean")
    || v.real_camera_frame_verified !== false
    || v.eligible_for_supervised_trial !== (
      v.signed_privacy_approval_verified === true
      && v.private_rtsp_configured === true
      && v.pyav_decoder_installed === true
      && v.opencv_jpeg_encoder_installed === true
    )) {
    throw new Error("Invalid local camera readiness response");
  }
  return v as CameraReadiness;
}

export async function fetchCameraReadiness(signal?: AbortSignal): Promise<CameraReadiness> {
  const response = await fetch("/api/v1/operator/camera-readiness", {
    method: "GET", credentials: "same-origin", mode: "same-origin",
    cache: "no-store", redirect: "error",
    headers: { Accept: "application/json" }, signal,
  });
  if (!response.ok || !response.body) {
    // A 404 means Member 2's production backend, not the local Edge bridge.
    throw new Error("Local camera readiness unavailable");
  }
  const size = response.headers.get("content-length");
  if (size && (!Number.isFinite(Number(size)) || Number(size) > MAX_READINESS_BYTES)) {
    throw new Error("Invalid local camera readiness response");
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let used = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      used += value.byteLength;
      if (used > MAX_READINESS_BYTES) {
        await reader.cancel();
        throw new Error("Invalid local camera readiness response");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(used);
  let index = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, index);
    index += chunk.byteLength;
  }
  try {
    return parseCameraReadiness(
      JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)),
    );
  } catch {
    throw new Error("Invalid local camera readiness response");
  }
}
