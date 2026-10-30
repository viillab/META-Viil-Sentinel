/** Visual-only safety timeout; server authorization and TTL remain authoritative.
 * Some browsers delay multipart MJPEG image events, so this timeout reports
 * missing browser confirmation, never claims the backend decoded no frames.
 */
export const FIRST_IMAGE_EVENT_TIMEOUT_MS = 20_000;
export const EXPIRY_SAFETY_MARGIN_MS = 1_000;

export function firstImageEventWaitMs(expiresAt: string, nowMs = Date.now()): number {
  const deadline = Date.parse(expiresAt);
  if (!Number.isFinite(nowMs) || !Number.isFinite(deadline)) return 0;
  const remaining = deadline - nowMs - EXPIRY_SAFETY_MARGIN_MS;
  if (remaining <= 0) return 0;
  return Math.min(FIRST_IMAGE_EVENT_TIMEOUT_MS, remaining);
}

/** Prevent late browser load/error events from changing a closed/new session. */
export function isActivePreviewId(
  expectedSessionId: string,
  currentSessionId: string | null | undefined,
): boolean {
  return Boolean(expectedSessionId && currentSessionId === expectedSessionId);
}
