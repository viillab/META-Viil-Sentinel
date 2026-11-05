import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { makeWebcamSmokeReport } from "../src/webcamAcceptance.ts";

const sample = {
  elapsedMs: 60_000, presentedFrameCallbacks: 500, analyzedFrames: 250,
  reliablePoseFrames: 180, unconfirmedCandidates: 1,
  lastWindowInferenceP95Ms: 31.7, stopReason: "timeout",
};

test("local report contains only bounded technical counters and never claims hardware validation", () => {
  const report = makeWebcamSmokeReport(sample);
  assert.ok(report);
  assert.equal(report.schema_version, "viil.webcam.local_smoke.v1");
  assert.equal(report.status, "OPERATOR_REVIEW_REQUIRED");
  assert.equal(report.durationSeconds, 60);
  assert.equal(report.unconfirmedCandidates, 1);
  assert.equal(report.lastWindowInferenceP95Ms, 31.7);
  assert.equal(report.limitation, "LOCAL_RUNTIME_COUNTS_NOT_FALL_ACCURACY");
  assert.ok(Object.isFrozen(report));
  const serialized = JSON.stringify(report);
  for (const privateField of [
    "camera_id", "source_id", "model_path", "video", "landmarks",
    "evidence", "email", "face", "approved", "confidence",
  ]) assert.equal(serialized.includes('"' + privateField + '"'), false);
});

test("no model or camera frames still requires operator review, never a technical pass", () => {
  const report = makeWebcamSmokeReport({
    ...sample, elapsedMs: 250, presentedFrameCallbacks: 0,
    analyzedFrames: 0, reliablePoseFrames: 0,
    unconfirmedCandidates: 0, lastWindowInferenceP95Ms: null,
    stopReason: "manual",
  });
  assert.equal(report.status, "OPERATOR_REVIEW_REQUIRED");
  assert.equal(report.presentedFrameCallbacks, 0);
  assert.equal(report.lastWindowInferenceP95Ms, null);
  assert.equal(report.durationSeconds, 0.3);
});

test("preview-only reports fresh video frames without claiming Pose inference", () => {
  const report = makeWebcamSmokeReport({
    ...sample, elapsedMs: 12_000, presentedFrameCallbacks: 132,
    analyzedFrames: 0, reliablePoseFrames: 0, unconfirmedCandidates: 0,
    lastWindowInferenceP95Ms: null, stopReason: "manual",
  });
  assert.equal(report.status, "OPERATOR_REVIEW_REQUIRED");
  assert.equal(report.presentedFrameCallbacks, 132);
  assert.equal(report.analyzedFrames, 0);
  assert.equal(report.reliablePoseFrames, 0);
  assert.equal(report.lastWindowInferenceP95Ms, null);
});

test("malformed counters and unsupported stop reasons abstain without unsafe fallback", () => {
  for (const patch of [
    { elapsedMs: NaN }, { elapsedMs: -1 }, { elapsedMs: 90_001 },
    { presentedFrameCallbacks: Infinity }, { presentedFrameCallbacks: -1 },
    { analyzedFrames: 501 }, { analyzedFrames: 0.1 },
    { reliablePoseFrames: 251 }, { unconfirmedCandidates: 251 },
    { lastWindowInferenceP95Ms: NaN }, { lastWindowInferenceP95Ms: -1 },
    { lastWindowInferenceP95Ms: 60_001 },
    { stopReason: "successful_fall" }, { stopReason: "camera_access_approved" },
  ]) assert.equal(makeWebcamSmokeReport({ ...sample, ...patch }), null);
  assert.equal(makeWebcamSmokeReport(null), null);
});

test("all stop reasons report operator-review-required without alert or recording", () => {
  for (const stopReason of [
    "manual", "timeout", "hidden", "camera_disconnected",
    "frame_stalled", "inference_error", "playback_error", "unsupported_browser",
  ]) assert.equal(makeWebcamSmokeReport({ ...sample, stopReason }).status,
    "OPERATOR_REVIEW_REQUIRED");
  const src = readFileSync(new URL("../src/LaptopWebcamDemo.tsx", import.meta.url), "utf8");
  assert.match(src, /makeWebcamSmokeReport/);
  assert.match(src, /sessionStartedMonoMs/);
  assert.match(src, /Stop reason:/);
  assert.match(src, /Nothing is saved or uploaded/);
  assert.match(src, /setSmokeReport\(null\)/);
  for (const forbidden of [
    /\bfetch\s*\(/, /MediaRecorder/, /WebSocket/, /toDataURL/,
    /sendBeacon/, /XMLHttpRequest/, /localStorage/, /sessionStorage/,
  ]) assert.equal(forbidden.test(src), false);
});
