import assert from "node:assert/strict";
import { test } from "node:test";
import {
  EXPIRY_SAFETY_MARGIN_MS,
  FIRST_IMAGE_EVENT_TIMEOUT_MS,
  firstImageEventWaitMs,
  isActivePreviewId,
} from "../src/previewTiming.ts";

test("first-image watchdog bounded by 20 seconds", () => {
  const now = Date.parse("2026-10-30T12:00:00.000Z");
  assert.equal(FIRST_IMAGE_EVENT_TIMEOUT_MS, 20_000);
  assert.equal(firstImageEventWaitMs(new Date(now + 25_000).toISOString(), now), 20_000);
  assert.equal(firstImageEventWaitMs(new Date(now + 8_000).toISOString(), now),
    8_000 - EXPIRY_SAFETY_MARGIN_MS);
});

test("expired/invalid session never gets an active browser watchdog", () => {
  const now = Date.parse("2026-10-30T12:00:00.000Z");
  assert.equal(firstImageEventWaitMs(new Date(now).toISOString(), now), 0);
  assert.equal(firstImageEventWaitMs(new Date(now + 500).toISOString(), now), 0);
  assert.equal(firstImageEventWaitMs(new Date(now - 25).toISOString(), now), 0);
  assert.equal(firstImageEventWaitMs("not-a-time", now), 0);
  assert.equal(firstImageEventWaitMs(new Date(now + 10_000).toISOString(), NaN), 0);
});

test("late load/error events cannot affect intentionally stopped or replaced preview", () => {
  const first = "session-abc-1234567890";
  const second = "session-def-1234567890";
  assert.equal(isActivePreviewId(first, first), true);
  assert.equal(isActivePreviewId(first, second), false);
  assert.equal(isActivePreviewId(first, null), false);
  assert.equal(isActivePreviewId(first, undefined), false);
  assert.equal(isActivePreviewId("", ""), false);
});
