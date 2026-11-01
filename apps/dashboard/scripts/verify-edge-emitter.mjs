/**
 * Executes the actual Python Edge v1 handoff emitter and validates its output
 * using the exact TypeScript parser loaded by the Dashboard.
 *
 * All input is invented numeric pose data. This script performs no network
 * requests, model loading, video access, storage, or incident delivery.
 */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { parseEdgeCandidateJsonl } from "../src/edgeLab.ts";

const args = process.argv.slice(2);
if (args.length !== 0 && (args.length !== 2 || args[0] !== "--python" || !args[1])) {
  throw new Error("Usage: node --experimental-strip-types scripts/verify-edge-emitter.mjs [--python PATH]");
}
const python = args.length === 2 ? args[1] : (process.env.VIIL_EDGE_PYTHON || "python");
const edgeRoot = fileURLToPath(new URL("../../../services/edge-vision/", import.meta.url));
const canonical = JSON.parse(readFileSync(new URL(
  "../../../services/edge-vision/examples/synthetic/candidate_v1.example.json",
  import.meta.url,
), "utf8"));
const dashboardFixture = JSON.parse(readFileSync(new URL(
  "../src/fixtures/edgeCandidateSynthetic.json", import.meta.url,
), "utf8"));
assert.deepEqual(dashboardFixture, canonical, "Dashboard fixture differs from Edge fixture");

function emit(trace, options = []) {
  const child = spawnSync(python, [
    "-m", "sentinel_edge.handoff_cli",
    "--trace", `examples/synthetic/${trace}.jsonl`,
    "--source-id", "synthetic-clip-01",
    "--provenance", "synthetic_pose_trace", ...options,
  ], {
    cwd: edgeRoot, encoding: "utf8", windowsHide: true,
    timeout: 30_000, maxBuffer: 128 * 1024, shell: false,
  });
  if (child.error) throw new Error("Python Edge emitter could not execute");
  return child;
}

const fall = emit("fall");
assert.equal(fall.status, 0, "Synthetic fall Python Edge command failed");
const parsed = parseEdgeCandidateJsonl(fall.stdout, "Fresh Python synthetic fall output");
assert.equal(parsed.events.length, 1, "Actual Edge emitter must produce one synthetic candidate");
assert.equal(parsed.expectedNegative, false);
assert.deepEqual(parsed.sourceIds, ["synthetic-clip-01"]);

const candidate = parsed.events[0];
assert.match(candidate.event_id,
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
assert.deepEqual(
  { ...candidate, event_id: canonical.event_id }, canonical,
  "Python emitter changed candidate semantics but canonical UI fixture was not updated",
);
assert.equal(candidate.simulated, true);
assert.equal(candidate.confirmed_fall, false);
assert.equal(candidate.human_review_required, true);
assert.equal(candidate.score_calibrated, false);
assert.equal(candidate.delivery_mode, "local_stdout_only");
assert.deepEqual(candidate.evidence_refs, []);

const sitting = emit("sitting");
assert.equal(sitting.status, 0, "Synthetic sitting Python Edge command failed");
assert.equal(sitting.stdout, "", "Synthetic sitting should never emit a candidate");
assert.equal(parseEdgeCandidateJsonl(sitting.stdout).events.length, 0);

const forged = emit("fall", ["--authorized-staged-data"]);
assert.notEqual(forged.status, 0, "Synthetic data must not be marked as authorized media");
assert.equal(forged.stdout, "", "Invalid authorization must never emit candidate JSONL");

const invalidSource = spawnSync(python, [
  "-m", "sentinel_edge.handoff_cli",
  "--trace", "examples/synthetic/fall.jsonl",
  "--source-id", "../private-camera",
], {
  cwd: edgeRoot, encoding: "utf8", windowsHide: true,
  timeout: 30_000, maxBuffer: 128 * 1024, shell: false,
});
assert.equal(invalidSource.error, undefined, "Invalid source check could not run");
assert.notEqual(invalidSource.status, 0, "Private path source identifiers must be rejected");
assert.equal(invalidSource.stdout, "", "Rejected input must not leak a partial event");

console.log(
  "OFFLINE CROSS-LANGUAGE CONTRACT PASS: Python Edge fall=1; sitting=0; " +
  "Dashboard TypeScript parser=valid; canonical fixture=matched; " +
  "forged authorization/path=rejected; network=none; real-world accuracy=not tested",
);
