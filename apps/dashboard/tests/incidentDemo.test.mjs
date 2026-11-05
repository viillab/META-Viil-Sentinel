import assert from "node:assert/strict";
import { test } from "node:test";
import {
  allowLocalDemo, parseDemoIncident, parseDemoIncidentList,
  listLocalDemoIncidents, createLocalDemoIncident, reviewLocalDemoIncident,
} from "../src/incidentDemo.ts";

function staged(overrides = {}) {
  return {
    id: "cbb6b9cf-2c74-42a5-aadd-d1e7b699e3d2",
    source_id: "STAGED-CAMERA-01",
    status: "REVIEW_REQUIRED",
    confidence: 0.82,
    simulated: true,
    notification_sent: false,
    created_at: "2026-10-28T09:00:00+00:00",
    updated_at: "2026-10-28T09:00:00+00:00",
    observation: {
      posture: "uncertain fall candidate",
      surroundings: "staged scene",
      uncertainty: ["Synthetic demo only"],
      evidence_refs: [],
      generated_by: "mock",
      medical_severity: null,
    },
    history: [{ time: "2026-10-28T09:00:00+00:00",
      event: "mock", actor: "demo", from_status: "DETECTED",
      to_status: "REVIEW_REQUIRED" }],
    ...overrides,
  };
}

test("local incident demo can only be enabled on a developer's loopback browser", () => {
  assert.equal(allowLocalDemo("localhost", true), true);
  assert.equal(allowLocalDemo("127.0.0.1", true), true);
  assert.equal(allowLocalDemo("localhost", false), false);
  for (const name of ["example.com", "192.168.1.50", "localhost.evil.test",
    "127.0.0.2", "[::1]", "LOCALHOST", ""]) {
    assert.equal(allowLocalDemo(name, true), false);
  }
});

test("accepts mock-only Pydantic-like incident contract", () => {
  assert.equal(parseDemoIncident(staged()).simulated, true);
  assert.equal(parseDemoIncident(staged()).observation.generated_by, "mock");
  assert.equal(parseDemoIncidentList([staged()]).length, 1);
});

for (const [caseName, transform] of Object.entries({
  realEvent: x => ({ ...x, simulated: false }),
  pii: x => ({ ...x, email: "protected@example.com" }),
  metaField: x => ({ ...x, meta_review_v1: { provider: "fake" } }),
  unknownPhoto: x => ({ ...x, photo: "raw_image" }),
  cameraURL: x => ({ ...x, source_id: "rtsp://name:pass@192.168.1.1/stream" }),
  falseSchema: x => ({ ...x, notification_sent: "true" }),
  badConfidence: x => ({ ...x, confidence: Infinity }),
  medicalSeverity: x => ({ ...x, observation: {
    ...x.observation, medical_severity: "critical" } }),
  evidence: x => ({ ...x, observation: { ...x.observation, evidence_refs: ["private"] } }),
  unsafeObservation: x => ({ ...x, observation: {
    ...x.observation, posture: "<img src=x onerror=alert(1)>" } }),
  unsafeActor: x => ({ ...x, history: [
    { ...x.history[0], actor: "<script>alert(1)</script>" }] }),
  unknownStatus: x => ({ ...x, status: "EMERGENCY_DISPATCHED" }),
  enormousHistory: x => ({ ...x, history: Array(41).fill(x.history[0]) }),
  emptyUUID: x => ({ ...x, id: "not-a-uuid" }),
})) {
  test("fail closed on " + caseName, () => {
    assert.throws(() => parseDemoIncident(transform(staged())), e => {
      assert.doesNotMatch(e.message, /private|pass@|protected@example/i);
      return true;
    });
  });
}
test("list length and duplicate IDs are bounded", () => {
  assert.throws(() => parseDemoIncidentList(Array(51).fill(staged())), /oversized/);
  assert.throws(() => parseDemoIncidentList([staged(), staged()]), /Duplicate/);
});

test("GET never leaks token to Meta/RTSP or accepts redirect", async () => {
  const saved = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, "/api/v1/incidents");
      assert.equal(options.method, "GET");
      assert.equal(options.credentials, "same-origin");
      assert.equal(options.redirect, "error");
      assert.equal(options.cache, "no-store");
      return new Response(JSON.stringify([staged()]), { status: 200 });
    };
    assert.equal((await listLocalDemoIncidents()).length, 1);
  } finally { globalThis.fetch = saved; }
});

test("local demo mutation paths and typed body have no secrets", async () => {
  const saved = globalThis.fetch;
  const paths = [];
  try {
    globalThis.fetch = async (url, options) => {
      paths.push(url);
      assert.equal(options.method, "POST");
      assert.equal(options.redirect, "error");
      assert.equal(options.credentials, "same-origin");
      assert.equal(options.headers["Content-Type"], "application/json");
      assert.doesNotMatch(options.body, /api_key|rtsp:\/\//);
      return new Response(JSON.stringify(staged()), { status: 200 });
    };
    assert.equal((await createLocalDemoIncident()).simulated, true);
    assert.equal((await reviewLocalDemoIncident(staged().id, "ACKNOWLEDGE", "Tester")).simulated, true);
    assert.deepEqual(paths, [
      "/api/v1/incidents/demo",
      `/api/v1/incidents/${staged().id}/review`,
    ]);
  } finally { globalThis.fetch = saved; }
});

test("dangerous actor names and unrecognized operations never make a request", async () => {
  const saved = globalThis.fetch;
  globalThis.fetch = () => { throw new Error("Network call not permitted"); };
  try {
    await assert.rejects(reviewLocalDemoIncident(
      staged().id, "DELETE_ALL", "Tester"), /Invalid local demo/);
    await assert.rejects(reviewLocalDemoIncident(
      staged().id, "ACKNOWLEDGE", "<script>"), /Invalid local demo/);
  } finally { globalThis.fetch = saved; }
});

test("401 response is redacted and list must not fall back to fake data", async () => {
  const saved = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(
      "Bearer PRIVATE_SECRET", { status: 401 });
    await assert.rejects(listLocalDemoIncidents(), e => {
      assert.match(e.message, /authentication\/authorization/i);
      assert.doesNotMatch(e.message, /PRIVATE_SECRET/);
      return true;
    });
  } finally { globalThis.fetch = saved; }
});

test("too-large response is refused even when missing content-length", async () => {
  const saved = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("a".repeat(128 * 1024 + 1));
    await assert.rejects(listLocalDemoIncidents(), /too large/);
  } finally { globalThis.fetch = saved; }
});
