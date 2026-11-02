import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  makeWebcamSmokeReport, serializeWebcamSmokeReport,
} from "../src/webcamAcceptance.ts";

test("explicit local report export copies only allowlisted technical metrics", () => {
  const result = makeWebcamSmokeReport({
    elapsedMs: 12_345,
    presentedFrameCallbacks: 180,
    analyzedFrames: 0,
    reliablePoseFrames: 0,
    unconfirmedCandidates: 0,
    lastWindowInferenceP95Ms: null,
    stopReason: "manual",
  });
  assert.ok(result);
  const poisoned = {
    ...result,
    deviceId: "PRIVATE-DEVICE-123",
    camera_id: "PRIVATE-CAMERA",
    image: "PRIVATE-FRAME",
    model_path: "PRIVATE-MODEL",
    token: "PRIVATE-TOKEN",
  };
  const encoded = serializeWebcamSmokeReport(poisoned);
  assert.deepEqual(Object.keys(JSON.parse(encoded)), [
    "schema_version", "status", "durationSeconds", "presentedFrameCallbacks",
    "analyzedFrames", "reliablePoseFrames", "unconfirmedCandidates",
    "lastWindowInferenceP95Ms", "stopReason", "limitation",
  ]);
  assert.equal(JSON.parse(encoded).status, "OPERATOR_REVIEW_REQUIRED");
  assert.equal(JSON.parse(encoded).durationSeconds, 12.3);
  assert.equal(JSON.parse(encoded).analyzedFrames, 0);
  assert.equal(JSON.parse(encoded).lastWindowInferenceP95Ms, null);
  assert.equal(serializeWebcamSmokeReport(result), serializeWebcamSmokeReport(result));
  for (const secret of ["PRIVATE-", "deviceId", "camera_id", "image", "token"]) {
    assert.equal(encoded.includes(secret), false);
  }
});

test("copy requires explicit UI action and does not persist or transmit data", () => {
  const source = readFileSync(new URL("../src/LaptopWebcamDemo.tsx", import.meta.url), "utf8");
  assert.match(source, /Copy technical report JSON/);
  assert.match(source, /onClick=\{\(\) => void copyTechnicalReport\(\)\}/);
  assert.match(source, /navigator\.clipboard\.writeText\(serializeWebcamSmokeReport\(smokeReport\)\)/);
  assert.match(source, /if \(!smokeReport \|\| phase === "live"\) return/);
  assert.match(source, /Clipboard unavailable or denied/);
  for (const forbidden of [
    /\bfetch\s*\(/, /WebSocket/, /localStorage/, /sessionStorage/,
    /MediaRecorder/, /toDataURL/, /createObjectURL/, /sendBeacon/,
  ]) assert.equal(forbidden.test(source), false);
});
