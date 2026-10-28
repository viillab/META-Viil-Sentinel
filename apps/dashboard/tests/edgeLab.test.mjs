import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  EDGE_CANDIDATE_SCHEMA,
  formatSourceOffset, MAX_LOCAL_CANDIDATE_BYTES, MAX_LOCAL_CANDIDATES,
  parseEdgeCandidateJsonl,
} from "../src/edgeLab.ts";

const canonical = JSON.parse(readFileSync(
  new URL("../../../services/edge-vision/examples/synthetic/candidate_v1.example.json", import.meta.url),
  "utf8",
));
const frontend = JSON.parse(readFileSync(
  new URL("../src/fixtures/edgeCandidateSynthetic.json", import.meta.url), "utf8",
));
const stringify = (o) => JSON.stringify(o) + "\n";
const parse = (o) => parseEdgeCandidateJsonl(stringify(o));

test("frontend synthetic fixture matches canonical Edge Python fixture byte values", () => {
  assert.deepEqual(frontend, canonical);
  assert.equal(canonical.schema_version, EDGE_CANDIDATE_SCHEMA);
  const result = parse(frontend);
  assert.equal(result.events.length, 1);
  assert.deepEqual(result.sourceIds, ["synthetic-clip-01"]);
  assert.equal(result.events[0].simulated, true);
  assert.equal(result.events[0].confirmed_fall, false);
  assert.equal(result.events[0].delivery_mode, "local_stdout_only");
  assert.equal(result.events[0].detector_score_type, "uncalibrated_heuristic");
  assert.equal(result.expectedNegative, false);
});

test("sitting/no-candidate has no claims of true-negative accuracy", () => {
  const result = parseEdgeCandidateJsonl("", "Synthetic sitting");
  assert.equal(result.expectedNegative, true);
  assert.equal(result.events.length, 0);
  assert.deepEqual(result.sourceIds, []);
  assert.equal(result.displayLabel, "Synthetic sitting");
});

test("Windows PowerShell UTF8 BOM and Windows newlines tolerated", () => {
  const result = parseEdgeCandidateJsonl("\uFEFF" + stringify(canonical).replace("\n", "\r\n"));
  assert.equal(result.events.length, 1);
});

test("multiple valid different sources accepted without claiming model success", () => {
  const second = { ...canonical, event_id: "00000000-0000-4000-8000-000000000002",
    source_id: "synthetic-clip-02", source_timestamp_ms: 1250 };
  const result = parseEdgeCandidateJsonl(stringify(canonical) + stringify(second));
  assert.equal(result.events.length, 2);
  assert.deepEqual(result.sourceIds, ["synthetic-clip-01", "synthetic-clip-02"]);
  assert.equal(result.events[1].source_timestamp_ms, 1250);
});

for (const [caseName, overrides] of Object.entries({
  wrongVersion: { schema_version: "viil.edge.candidate.v2" },
  confirmedFall: { confirmed_fall: true },
  calibratedClaim: { score_calibrated: true },
  falseEvidenceRefs: { evidence_refs: ["https://private/video.mp4"] },
  forgedDelivery: { delivery_mode: "http_post" },
  forgedMedical: { medical_assessment_performed: true },
  noReview: { human_review_required: false },
  wrongScoreType: { detector_score_type: "probability" },
  negativeScore: { detector_score: -0.01 },
  aboveOne: { detector_score: 1.01 },
  stringScore: { detector_score: "0.8" },
  missingSourceStart: { timestamp_basis: "unix_ms" },
  negativeTimestamp: { source_timestamp_ms: -1 },
  fractionalTimestamp: { source_timestamp_ms: 1.3 },
  textTimestamp: { source_timestamp_ms: "880" },
  privateSource: { source_id: "../user" },
  unicodeSource: { source_id: "ผู้ป่วย" },
  veryLongSource: { source_id: "A".repeat(81) },
  fakeUuid: { event_id: "not-an-uuid" },
  upperUuid: { event_id: "A0000000-0000-4000-8000-000000000001" },
  wrongModelHash: { model_sha256: "private-secret" },
  fakeSyntheticAsReal: { input_provenance: "synthetic_pose_trace", simulated: false },
  fakeRealAsSynthetic: { input_provenance: "authorized_local_camera", simulated: true },
  unknownProvenance: { input_provenance: "unlicensed_camera" },
  falseSimulationType: { simulated: "false" },
  wrongEventType: { event_type: "FALL_CONFIRMED" },
})) {
  test("rejects unsafe candidate " + caseName, () => {
    assert.throws(() => parse({ ...canonical, ...overrides }), /Invalid Edge candidate/);
  });
}

test("rejects extra raw image, landmarks, medical, URL and PII fields", () => {
  for (const extra of [
    { frames: "base64-image" }, { keyframes: ["data:image/png;..."] },
    { landmarks: { face: [0.5, 0.1] } }, { person_name: "Somebody" },
    { medical_diagnosis: "syncope" }, { user_id: "private" }, { token: "secret" },
  ]) {
    assert.throws(() => parse({ ...canonical, ...extra }), /exact metadata-only/);
  }
});

test("rejects missing required fields", () => {
  const absent = { ...canonical };
  delete absent.model_sha256;
  assert.throws(() => parse(absent), /exact metadata-only/);
});

test("rejects malformed JSONL, not an array and unsafe additional lines", () => {
  assert.throws(() => parseEdgeCandidateJsonl("{broken"), /invalid JSONL/);
  assert.throws(() => parseEdgeCandidateJsonl(JSON.stringify([canonical])), /exact metadata-only/);
  assert.throws(() => parseEdgeCandidateJsonl(stringify(canonical) + "{invalid"), /line 2/);
});

test("rejects UUID replay and source-clock going backwards", () => {
  assert.throws(() => parseEdgeCandidateJsonl(stringify(canonical) + stringify(canonical)), /duplicate event UUID/);
  const next = { ...canonical, event_id: "00000000-0000-4000-8000-000000000002",
    source_timestamp_ms: 10 };
  assert.throws(() => parseEdgeCandidateJsonl(stringify(canonical) + stringify(next)), /nondecreasing/);
});

test("bounded file length and event count", () => {
  assert.throws(() => parseEdgeCandidateJsonl("x".repeat(MAX_LOCAL_CANDIDATE_BYTES + 1)), /too large/);
  const many = Array.from({ length: MAX_LOCAL_CANDIDATES + 1 }, (_, i) =>
    stringify({ ...canonical, event_id: "00000000-0000-4000-8000-" + i.toString(16).padStart(12, "0") }),
  ).join("");
  assert.throws(() => parseEdgeCandidateJsonl(many), /Too many/);
});

test("relative source timestamp display never pretends to be wall clock", () => {
  assert.equal(formatSourceOffset(880), "+0.880 s");
  assert.equal(formatSourceOffset(1500), "+1.500 s");
  assert.equal(formatSourceOffset(0), "+0.000 s");
  assert.equal(formatSourceOffset(-2), "invalid relative offset");
});

test("label is shortened and control characters removed", () => {
  const r = parseEdgeCandidateJsonl("", "name\n" + "a".repeat(200));
  assert.ok(r.displayLabel.length <= 80);
  assert.ok(!r.displayLabel.includes("\n"));
});
