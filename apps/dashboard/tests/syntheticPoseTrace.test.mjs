import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  runSyntheticPoseReplay, SYNTHETIC_POSE_LABELS, SYNTHETIC_POSE_SCENARIOS,
} from "../src/syntheticPoseTrace.ts";

test("real browser heuristic emits one UNCONFIRMED event for invented motion", () => {
  const result = runSyntheticPoseReplay("fall_motion");
  assert.equal(result.synthetic, true);
  assert.equal(result.usesMediaPipeModel, false);
  assert.equal(result.usesRealCamera, false);
  assert.equal(result.backendRequests, 0);
  assert.equal(result.verifiedFalls, 0);
  assert.equal(result.candidateCount, 1);
  assert.deepEqual(result.steps.map(x => x.sourceMs), [0, 200, 400, 600, 800, 1000, 1200]);
  assert.deepEqual(result.steps.filter(x => x.emittedCandidate).map(x => x.sourceMs), [1000]);
  assert.equal(result.steps[5].result, "candidate");
  assert.ok(Object.isFrozen(result));
  assert.ok(Object.isFrozen(result.steps));
  assert.ok(Object.isFrozen(result.steps[5]));
  assert.equal(JSON.stringify(result).includes('"landmarks"'), false);
});

test("sitting, horizontal-first, tracking-loss, multi-person all abstain", () => {
  for (const scenario of ["sitting","horizontal_first","tracking_lost","multiple_people"]) {
    const result = runSyntheticPoseReplay(scenario);
    assert.equal(result.steps.length, 7);
    assert.equal(result.candidateCount, 0, scenario);
    assert.equal(result.steps.some(x => x.emittedCandidate), false);
    assert.ok(SYNTHETIC_POSE_LABELS[scenario]);
  }
  assert.equal(runSyntheticPoseReplay("tracking_lost").steps[2].result, "unknown");
  assert.equal(runSyntheticPoseReplay("multiple_people").steps[2].result, "unknown");
  assert.equal(runSyntheticPoseReplay("horizontal_first").steps[0].result, "observing");
});

test("trace generator is deterministic, bounded, local-only, and rejects unknown scenarios", () => {
  for (const scenario of SYNTHETIC_POSE_SCENARIOS) {
    const a = runSyntheticPoseReplay(scenario);
    const b = runSyntheticPoseReplay(scenario);
    assert.deepEqual(a,b);
    assert.ok(a.steps.length <= 7);
    assert.equal(a.steps.every(x => x.sourceMs >= 0 && x.sourceMs <= 1200), true);
    assert.equal(a.steps.every(x => x.angleDeg === null || Number.isFinite(x.angleDeg)), true);
  }
  assert.throws(() => runSyntheticPoseReplay("../private-camera"), /Unknown/);
  assert.throws(() => runSyntheticPoseReplay("test;fetch()"), /Unknown/);
});

test("offline UI cannot connect to a camera, Meta, backend or send an alert", () => {
  const src = readFileSync(new URL("../src/SyntheticPoseTraceLab.tsx", import.meta.url), "utf8");
  const generator = readFileSync(new URL("../src/syntheticPoseTrace.ts", import.meta.url), "utf8");
  const lab = readFileSync(new URL("../src/EdgeTestLab.tsx", import.meta.url), "utf8");
  assert.match(src, /SIMULATION ONLY/);
  assert.match(src, /UNCONFIRMED CANDIDATE/);
  assert.match(src, /runSyntheticPoseReplay/);
  assert.match(lab, /<SyntheticPoseTraceLab\s*\/>/);
  assert.match(generator, /new LocalFallCandidateHeuristic/);
  for (const forbidden of [
    /\bfetch\s*\(/, /getUserMedia/, /MediaRecorder/, /navigator\.mediaDevices/,
    /WebSocket\s*\(/, /XMLHttpRequest/, /sendBeacon/, /localStorage/, /sessionStorage/,
    /new Worker/, /import\s*\(/,
  ]) {
    assert.equal(forbidden.test(src), false, String(forbidden));
    assert.equal(forbidden.test(generator), false, String(forbidden));
  }
});
