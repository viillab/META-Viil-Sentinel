import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  drawTorsoOverlay, LocalFallCandidateHeuristic, torsoFeatures, validLocalPoseTask,
  MAX_LOCAL_TASK_BYTES, POSE_DEMO_INTERVAL_MS, POSE_DEMO_STALL_MS,
  CANDIDATE_NOTICE_MS, candidateNoticeVisible, poseStreamStalled,
  freshVideoFrameCount, LocalPoseRuntimeMeter, LOCAL_VISION_WASM_ROOT,
} from "../src/localPoseDemo.ts";

function body({ hipY = 0.6, shoulderY = 0.27, horizontal = false,
  visible = 0.95 } = {}) {
  const poses = Array.from({ length: 33 }, () => ({
    x: 0.5, y: 0.5, visibility: visible, presence: visible,
  }));
  poses[23] = { x: horizontal ? 0.7 : 0.45, y: hipY,
    visibility: visible, presence: visible };
  poses[24] = { x: horizontal ? 0.8 : 0.55, y: hipY,
    visibility: visible, presence: visible };
  poses[11] = { x: horizontal ? 0.2 : 0.45, y: shoulderY,
    visibility: visible, presence: visible };
  poses[12] = { x: horizontal ? 0.3 : 0.55, y: shoulderY,
    visibility: visible, presence: visible };
  return [poses];
}
const upright = () => body();
const prone = () => body({ hipY: 0.82, shoulderY: 0.82, horizontal: true });

test("Local model requires .task with reasonable size, no model included in git", () => {
  assert.equal(validLocalPoseTask({ name: "pose_landmarker_lite.task", size: 5777746 }), true);
  assert.equal(validLocalPoseTask({ name: "MODEL.TASK", size: 1024 }), true);
  for (const file of [
    null, { name: "video.mp4", size: 5777746 },
    { name: "x.task", size: 0 }, { name: "x.task", size: MAX_LOCAL_TASK_BYTES + 1 },
    { name: "x.task", size: NaN },
  ]) assert.equal(validLocalPoseTask(file), false);
  assert.equal(POSE_DEMO_INTERVAL_MS, 200);
  assert.equal(LOCAL_VISION_WASM_ROOT, "/vendor/mediapipe/wasm");
});

test("exactly one full-visible normalized torso produces valid features", () => {
  const value = torsoFeatures(upright());
  assert.ok(value);
  assert.ok(value.angleDeg < 32);
  assert.ok(value.hipY > 0.55);
  assert.ok(value.quality >= 0.55);
  assert.ok(torsoFeatures(prone()).angleDeg > 56);
});

test("unknown, ambiguous, low visibility, lost and malformed points abstain", () => {
  assert.equal(torsoFeatures([]), null);
  assert.equal(torsoFeatures([upright()[0], upright()[0]]), null);
  assert.equal(torsoFeatures(body({ visible: 0.2 })), null);
  const missing = upright(); missing[0][11] = null;
  assert.equal(torsoFeatures(missing), null);
  const outside = upright(); outside[0][23].y = 3.2;
  assert.equal(torsoFeatures(outside), null);
  const missingVisibility = upright(); delete missingVisibility[0][12].visibility;
  assert.equal(torsoFeatures(missingVisibility), null);
  const invalidPresence = upright(); invalidPresence[0][12].presence = NaN;
  assert.equal(torsoFeatures(invalidPresence), null);
});

test("sitting or sideways posture without upright descent never yields candidate", () => {
  const detector = new LocalFallCandidateHeuristic();
  let t = 0;
  for (let i = 0; i < 15; i++, t += 200) {
    assert.equal(detector.observe(body({ hipY: 0.82, shoulderY: 0.49 }), t).candidate, false);
  }
  assert.equal(detector.count, 0);
  for (let i = 0; i < 12; i++, t += 200) {
    assert.equal(detector.observe(prone(), t).candidate, false);
  }
  assert.equal(detector.count, 0);
});

test("upright, hip descent, sustained horizontal can emit one UNCONFIRMED candidate", () => {
  const detector = new LocalFallCandidateHeuristic();
  assert.equal(detector.observe(upright(), 0).status, "upright");
  assert.equal(detector.observe(upright(), 200).candidate, false);
  assert.equal(detector.observe(prone(), 400).status, "observing");
  assert.equal(detector.observe(prone(), 600).candidate, false);
  assert.equal(detector.observe(prone(), 800).candidate, false);
  const final = detector.observe(prone(), 1000);
  assert.equal(final.status, "candidate");
  assert.equal(final.candidate, true);
  assert.equal(detector.count, 1);
  assert.equal(detector.observe(prone(), 1200).candidate, false);
  assert.equal(detector.count, 1);
});

test("frame loss, multiple persons, long gaps and nonmonotonic timestamps erase evidence", () => {
  const cases = [
    { bad: [], at: 600 },
    { bad: [prone()[0], prone()[0]], at: 600 },
    { bad: prone(), at: 1500 },
    { bad: prone(), at: 399 },
  ];
  for (const { bad, at } of cases) {
    const d = new LocalFallCandidateHeuristic();
    d.observe(upright(), 0);
    d.observe(prone(), 400);
    assert.equal(d.observe(bad, at).candidate, false);
    for (const ts of [1800, 2000, 2200, 2400]) {
      assert.equal(d.observe(prone(), ts).candidate, false);
    }
    assert.equal(d.count, 0);
  }
});

test("reset removes candidate count and all former motion history", () => {
  const d = new LocalFallCandidateHeuristic();
  d.observe(upright(), 0);
  d.observe(prone(), 300);
  d.observe(prone(), 900);
  assert.equal(d.count, 1);
  d.reset();
  assert.equal(d.count, 0);
  for (const t of [1100, 1300, 1500, 1700]) {
    assert.equal(d.observe(prone(), t).candidate, false);
  }
});

test("overlay follows real video dimensions and never paints captured pixels", () => {
  const steps = [];
  const ctx = Object.fromEntries(
    ["clearRect", "beginPath", "moveTo", "lineTo", "stroke"]
      .map(name => [name, (...args) => steps.push([name, ...args])]),
  );
  const canvas = { width: 0, height: 0, getContext: () => ctx };
  drawTorsoOverlay(canvas, upright(), 640, 480);
  assert.equal(canvas.width, 640);
  assert.equal(canvas.height, 480);
  assert.equal(steps.filter(step => step[0] === "stroke").length, 4);
  const before = steps.length;
  drawTorsoOverlay(canvas, [upright()[0], prone()[0]], 640, 480);
  assert.equal(steps.filter(step => step[0] === "stroke").length, 4);
  assert.ok(steps.length > before);
  drawTorsoOverlay(canvas, upright(), 0, 0);
  assert.equal(steps.at(-1)[0], "clearRect");
});

test("video frames must keep advancing or the demo fails closed", () => {
  assert.equal(POSE_DEMO_STALL_MS, 3500);
  assert.equal(poseStreamStalled(1000, 0), false);
  assert.equal(poseStreamStalled(3499, 0), false);
  assert.equal(poseStreamStalled(3500, 0), true);
  assert.equal(poseStreamStalled(8000, 6000), false);
  assert.equal(poseStreamStalled(6000, 8000), true);
  assert.equal(poseStreamStalled(Infinity, 0), true);
  assert.equal(poseStreamStalled(3500, NaN), true);
});

test("only a new presented video frame proves freshness", () => {
  assert.equal(freshVideoFrameCount(0, -1), true);
  assert.equal(freshVideoFrameCount(1, 0), true);
  assert.equal(freshVideoFrameCount(5, 1), true);
  assert.equal(freshVideoFrameCount(5, 5), false);
  assert.equal(freshVideoFrameCount(4, 5), false);
  for (const invalid of [NaN, Infinity, -1, 1.5, Number.MAX_SAFE_INTEGER + 1]) {
    assert.equal(freshVideoFrameCount(invalid, 0), false);
  }
  assert.equal(freshVideoFrameCount(3, NaN), false);
  assert.equal(freshVideoFrameCount(3, -2), false);
});

test("rolling webcam metrics are bounded, numeric, and not fall accuracy", () => {
  const meter = new LocalPoseRuntimeMeter();
  assert.equal(meter.observe(NaN, 4, true), null);
  assert.equal(meter.observe(0, -1, true), null);
  assert.equal(meter.observe(0, 2, "true"), null);
  let value = meter.observe(1000, 1, true);
  assert.deepEqual(value, {
    samples: 1, sampledFps: null, inferenceP50Ms: 1,
    inferenceP95Ms: 1, singlePoseCoveragePercent: 100,
  });
  for (const [ms, costMs, valid] of [
    [1200, 2, true], [1400, 3, false],
    [1600, 4, true], [1800, 100, true],
  ]) value = meter.observe(ms, costMs, valid);
  assert.deepEqual(value, {
    samples: 5, sampledFps: 5, inferenceP50Ms: 3,
    inferenceP95Ms: 100, singlePoseCoveragePercent: 80,
  });
  assert.equal(meter.observe(1800, 999, true), null);
  assert.equal(meter.observe(1799, 999, true), null);
  assert.equal(meter.observe(2000, Infinity, true), null);
  value = meter.observe(6001, 7, true);
  assert.deepEqual(value, {
    samples: 1, sampledFps: null, inferenceP50Ms: 7,
    inferenceP95Ms: 7, singlePoseCoveragePercent: 100,
  });
  for (let i = 1; i <= 80; i++) value = meter.observe(6001 + i * 50, 2, i % 2 === 0);
  assert.ok(value.samples <= 32);
  assert.equal(value.inferenceP95Ms, 2);
  assert.ok(value.sampledFps > 0);
});

test("candidate notice is temporary and never a confirmation", () => {
  assert.equal(CANDIDATE_NOTICE_MS, 8000);
  assert.equal(candidateNoticeVisible(1000, null), false);
  assert.equal(candidateNoticeVisible(1000, 1000), true);
  assert.equal(candidateNoticeVisible(8999, 1000), true);
  assert.equal(candidateNoticeVisible(9000, 1000), false);
  assert.equal(candidateNoticeVisible(999, 1000), false);
  assert.equal(candidateNoticeVisible(Infinity, 1000), false);
});

test("browser model worker loads only local WASM and chosen File bytes", () => {
  const src = readFileSync(
    new URL("../src/localPoseEngine.ts", import.meta.url), "utf8",
  );
  assert.match(src, /file\.arrayBuffer\(\)/);
  assert.match(src, /LOCAL_VISION_WASM_ROOT/);
  assert.match(src, /runningMode: "VIDEO"/);
  assert.match(src, /numPoses: 2/);
  assert.match(src, /delegate: "CPU"/);
  assert.equal(/https?:\/\//.test(src), false);
  assert.equal(/MediaRecorder|WebSocket|sendBeacon|fetch\(/.test(src), false);
});
