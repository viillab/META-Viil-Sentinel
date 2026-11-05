/**
 * Browser-local, ephemeral session summary for operator-led webcam acceptance.
 * No camera frames, landmarks, identity, device IDs or wall-clock timestamps.
 * The summary is NOT proof of hardware acceptance, fall accuracy or clinical safety.
 */
export type WebcamStopReason =
  | "manual" | "timeout" | "hidden" | "camera_disconnected"
  | "frame_stalled" | "inference_error" | "playback_error"
  | "unsupported_browser";

export type WebcamSmokeInput = {
  elapsedMs: number;
  presentedFrameCallbacks: number;
  analyzedFrames: number;
  reliablePoseFrames: number;
  unconfirmedCandidates: number;
  lastWindowInferenceP95Ms: number | null;
  stopReason: WebcamStopReason;
};

export type WebcamSmokeReport = Readonly<{
  schema_version: "viil.webcam.local_smoke.v1";
  status: "OPERATOR_REVIEW_REQUIRED";
  durationSeconds: number;
  presentedFrameCallbacks: number;
  analyzedFrames: number;
  reliablePoseFrames: number;
  unconfirmedCandidates: number;
  lastWindowInferenceP95Ms: number | null;
  stopReason: WebcamStopReason;
  limitation: "LOCAL_RUNTIME_COUNTS_NOT_FALL_ACCURACY";
}>;

/**
 * Explicit export allowlist for a user-triggered copy action.
 * Adding a private field to an internal report never implicitly copies it.
 */
export function serializeWebcamSmokeReport(report: WebcamSmokeReport): string {
  return JSON.stringify({
    schema_version: report.schema_version,
    status: report.status,
    durationSeconds: report.durationSeconds,
    presentedFrameCallbacks: report.presentedFrameCallbacks,
    analyzedFrames: report.analyzedFrames,
    reliablePoseFrames: report.reliablePoseFrames,
    unconfirmedCandidates: report.unconfirmedCandidates,
    lastWindowInferenceP95Ms: report.lastWindowInferenceP95Ms,
    stopReason: report.stopReason,
    limitation: report.limitation,
  }, null, 2);
}

const REASONS: ReadonlyArray<WebcamStopReason> = [
  "manual", "timeout", "hidden", "camera_disconnected",
  "frame_stalled", "inference_error", "playback_error", "unsupported_browser",
];

function count(value: number, max: number): boolean {
  return Number.isSafeInteger(value) && value >= 0 && value <= max;
}

export function makeWebcamSmokeReport(input: WebcamSmokeInput): WebcamSmokeReport | null {
  if (!input || !Number.isFinite(input.elapsedMs)
      || input.elapsedMs < 0 || input.elapsedMs > 90_000
      || !count(input.presentedFrameCallbacks, 20_000)
      || !count(input.analyzedFrames, 1000)
      || !count(input.reliablePoseFrames, 1000)
      || !count(input.unconfirmedCandidates, 1000)
      || input.analyzedFrames > input.presentedFrameCallbacks
      || input.reliablePoseFrames > input.analyzedFrames
      || input.unconfirmedCandidates > input.analyzedFrames
      || !REASONS.includes(input.stopReason)
      || (input.lastWindowInferenceP95Ms !== null
        && (!Number.isFinite(input.lastWindowInferenceP95Ms)
          || input.lastWindowInferenceP95Ms < 0
          || input.lastWindowInferenceP95Ms > 60_000))) return null;
  return Object.freeze({
    schema_version: "viil.webcam.local_smoke.v1",
    status: "OPERATOR_REVIEW_REQUIRED",
    durationSeconds: Math.round(input.elapsedMs / 100) / 10,
    presentedFrameCallbacks: input.presentedFrameCallbacks,
    analyzedFrames: input.analyzedFrames,
    reliablePoseFrames: input.reliablePoseFrames,
    unconfirmedCandidates: input.unconfirmedCandidates,
    lastWindowInferenceP95Ms: input.lastWindowInferenceP95Ms,
    stopReason: input.stopReason,
    limitation: "LOCAL_RUNTIME_COUNTS_NOT_FALL_ACCURACY",
  });
}
