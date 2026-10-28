import assert from "node:assert/strict";
import { test } from "node:test";
import { buildJudgeDemo, JUDGE_SCENARIOS } from "../src/judgeDemo.ts";
import { readFileSync } from "node:fs";
import { parseEdgeCandidateJsonl } from "../src/edgeLab.ts";

test("all competition stories have exactly six owner-marked stages", () => {
  for (const name of JUDGE_SCENARIOS) {
    const demo = buildJudgeDemo(name);
    assert.equal(demo.scenario, name);
    assert.deepEqual(demo.steps.map(x => x.id),
      ["camera", "edge", "privacy", "meta", "policy", "caregiver"]);
    assert.deepEqual(demo.steps.map(x => x.owner),
      ["Member 1", "Member 1", "Member 2", "Member 2", "Member 2", "Member 1"]);
    assert.match(demo.disclaimer, /SIMULATED/);
    assert.ok(demo.expectedHumanOutcome);
    for (const phase of demo.steps) {
      assert.notEqual(phase.state, "ready");
      assert.ok(phase.evidence);
      assert.ok(phase.detail);
    }
  }
});
test("synthetic fall uses the real canonical frontend/Edge fixture, not invented output", () => {
  const source = JSON.parse(readFileSync(new URL(
    "../src/fixtures/edgeCandidateSynthetic.json", import.meta.url), "utf8"));
  const fixtureEvent = parseEdgeCandidateJsonl(JSON.stringify(source)).events[0];
  const fall = buildJudgeDemo("synthetic_fall");
  assert.deepEqual(fall.candidate, fixtureEvent);
  assert.equal(fall.candidate.confirmed_fall, false);
  assert.equal(fall.candidate.score_calibrated, false);
  assert.equal(fall.candidate.simulated, true);
  assert.equal(fall.candidate.delivery_mode, "local_stdout_only");
  assert.equal(fall.steps[3].state, "blocked");
  assert.match(fall.steps[3].evidence, /No images/);
});
test("synthetic sitting cannot imply sensitivity, specificity or a notification", () => {
  const sitting = buildJudgeDemo("synthetic_sitting");
  assert.equal(sitting.candidate, null);
  for (const s of sitting.steps.slice(1)) {
    assert.equal(s.state, "not_triggered");
  }
  assert.match(sitting.expectedHumanOutcome, /not proof/i);
});
test("wheelchair story never claims actual classifier recognition of disability", () => {
  const story = buildJudgeDemo("wheelchair_context");
  assert.match(story.steps[1].detail, /does not prove/);
  assert.match(story.steps[3].detail, /FUTURE/);
  assert.match(story.expectedHumanOutcome, /rather than assume/i);
});
test("privacy denial blocks Meta image transmission", () => {
  const story = buildJudgeDemo("privacy_denied");
  assert.equal(story.steps[2].state, "blocked");
  assert.equal(story.steps[3].state, "not_triggered");
  assert.equal(story.steps[4].state, "blocked");
  assert.match(story.steps[2].detail, /MUST be denied/);
});
test("Meta outage does not erase a candidate or mark a real delivery", () => {
  const story = buildJudgeDemo("meta_unavailable");
  assert.ok(story.candidate);
  assert.equal(story.steps[3].state, "blocked");
  assert.match(story.steps[3].detail, /follow-up/i);
  assert.match(story.steps[5].evidence, /No sent notification/);
});
test("unrecognized scenario does not show made-up data", () => {
  assert.throws(() => buildJudgeDemo("__unknown__"), /Unsupported/);
});
test("no actual network operations in the pure storyboard", () => {
  const original = globalThis.fetch;
  globalThis.fetch = () => { throw new Error("Unexpected internet access"); };
  try {
    for (const scenario of JUDGE_SCENARIOS) {
      assert.equal(buildJudgeDemo(scenario).steps.length, 6);
    }
  } finally { globalThis.fetch = original; }
});
