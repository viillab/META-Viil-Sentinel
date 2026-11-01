import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import {
  hasUsableVideoTrack, LAPTOP_WEBCAM_DEMO_MAX_MS,
  LAPTOP_WEBCAM_PLAYBACK_MAX_MS, LOCAL_WEBCAM_HOSTS,
  requestLaptopWebcam, stopLaptopWebcam, waitForLocalWebcamPlayback,
  webcamDemoSupported, webcamErrorLabel,
} from "../src/laptopWebcam.ts";

test("webcam demo only enabled in secure loopback browser contexts", () => {
  const devices = { getUserMedia: async () => ({}) };
  assert.deepEqual(LOCAL_WEBCAM_HOSTS, ["127.0.0.1", "localhost", "[::1]"]);
  for (const host of LOCAL_WEBCAM_HOSTS) {
    assert.equal(webcamDemoSupported(host, true, devices), true);
    assert.equal(webcamDemoSupported(host, false, devices), false);
  }
  for (const host of ["example.com", "192.168.1.10", "evil.localhost.com", "0.0.0.0"]) {
    assert.equal(webcamDemoSupported(host, true, devices), false);
  }
  assert.equal(webcamDemoSupported("localhost", true, null), false);
  assert.equal(webcamDemoSupported("localhost", true, {}), false);
});

test("manual getUserMedia asks for video only and bounded preview resolution", async () => {
  let requested;
  const devices = {
    getUserMedia: async (constraints) => {
      requested = constraints;
      return { synthetic: true };
    },
  };
  assert.deepEqual(await requestLaptopWebcam(devices), { synthetic: true });
  assert.deepEqual(requested, {
    audio: false,
    video: {
      width: { ideal: 640 }, height: { ideal: 360 },
      frameRate: { ideal: 15, max: 24 },
    },
  });
  assert.equal(LAPTOP_WEBCAM_DEMO_MAX_MS, 60_000);
});

test("playback watchdog releases hung starts without a native camera error", async () => {
  assert.equal(LAPTOP_WEBCAM_PLAYBACK_MAX_MS, 8000);
  assert.equal(await waitForLocalWebcamPlayback(Promise.resolve(), 10), true);
  assert.equal(await waitForLocalWebcamPlayback(new Promise(() => {}), 12), false);
  await assert.rejects(
    () => waitForLocalWebcamPlayback(Promise.reject(new Error("private device path")), 12),
    /private device path/,
  );
  let rejectLate;
  const late = new Promise((_, reject) => { rejectLate = reject; });
  assert.equal(await waitForLocalWebcamPlayback(late, 12), false);
  rejectLate(new Error("late playback rejection"));
  await new Promise(resolve => setImmediate(resolve));
});

test("stop shuts down all tracks, including unexpected audio", () => {
  let stopped = 0;
  const stream = { getTracks: () => [
    { stop() { stopped++; } },
    { stop() { stopped++; } },
  ] };
  stopLaptopWebcam(stream);
  stopLaptopWebcam(null);
  assert.equal(stopped, 2);
});

test("only a genuinely live video track permits preview", () => {
  assert.equal(hasUsableVideoTrack({
    getVideoTracks: () => [{ readyState: "live" }],
  }), true);
  assert.equal(hasUsableVideoTrack({
    getVideoTracks: () => [{ readyState: "ended" }],
  }), false);
  assert.equal(hasUsableVideoTrack({ getVideoTracks: () => [] }), false);
});

test("camera permission and device errors are redacted", () => {
  const failure = name => Object.assign(new Error("private /device/camera"), { name });
  assert.match(webcamErrorLabel(failure("NotAllowedError")), /permission denied/i);
  assert.match(webcamErrorLabel(failure("NotFoundError")), /no laptop camera/i);
  assert.match(webcamErrorLabel(failure("NotReadableError")), /in use/i);
  for (const err of [failure("SomeOtherError"), { secret: "rtsp://SECRET" }, null]) {
    const label = webcamErrorLabel(err);
    assert.equal(label.includes("SECRET"), false);
    assert.equal(label.includes("/device/"), false);
  }
});

test("webcam demo UI has no transport or recording implementation", () => {
  const source = readFileSync(
    new URL("../src/LaptopWebcamDemo.tsx", import.meta.url), "utf8",
  );
  assert.match(source, /requestLaptopWebcam/);
  assert.match(source, /visibilitychange/);
  assert.match(source, /pagehide/);
  assert.match(source, /const pageExit = \(\) => stop\("hidden"\)/);
  assert.match(source, /waitForLocalWebcamPlayback\(video\.play\(\)\)/);
  assert.match(source, /Camera playback timed out after 8 seconds/);
  assert.match(source, /stop\("playback_error"\)/);
  assert.match(source, /LAPTOP_WEBCAM_DEMO_MAX_MS/);
  assert.match(source, /LOCAL HEURISTIC/);
  assert.match(source, /poseFrames > 0/);
  assert.match(source, /poseStreamStalled/);
  assert.match(source, /candidateNoticeVisible/);
  assert.match(source, /setLastCandidateAt\(null\)/);
  assert.match(source, /Webcam frames stopped arriving/);
  assert.match(source, /Preview frame callbacks observed/);
  assert.match(source, /const count = \+\+sessionCounters\.current\.presentedFrameCallbacks/);
  assert.match(source, /poseStreamStalled\(ms, lastFrameMs \?\? firstWatchMs\)/);
  assert.match(source, /stop\("frame_stalled"\)/);
  assert.match(source, /setPreviewFrames\(count\)/);
  assert.match(source, /LOCAL · FRESH FRAMES OBSERVED/);
  assert.match(source, /LOCAL VIDEO FRAMES · NO POSE ANALYSIS/);
  assert.match(source, /requestVideoFrameCallback/);
  assert.match(source, /cancelVideoFrameCallback/);
  assert.match(source, /freshVideoFrameCount/);
  assert.match(source, /LocalPoseRuntimeMeter/);
  assert.match(source, /performance\.now\(\)/);
  assert.match(source, /Stop the webcam before changing/);
  assert.match(source, /modelRef\.current = null/);
  assert.match(source, /disabled=\{posePhase === "loading" \|\| phase === "live"/);
  assert.match(source, /Inference p50\/p95/);
  assert.match(source, /not fall accuracy/);
  assert.doesNotMatch(source, /video\.currentTime/);
  assert.match(source, /WAITING FOR FIRST LOCAL POSE INFERENCE/);
  assert.match(source, /Stop webcam/);
  for (const prohibited of [
    /\bfetch\s*\(/, /XMLHttpRequest/, /MediaRecorder/, /toDataURL/,
    /WebSocket/, /sendBeacon/, /RTSP_PASSWORD/, /createObjectURL/,
  ]) {
    assert.equal(prohibited.test(source), false, "preview must never upload/record");
  }
});
