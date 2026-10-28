import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import {
  INTEGRATION_SCHEMA, MAX_INTEGRATION_BYTES, fetchIntegrationOverview,
  parseIntegrationOverview, snapshotIsFresh,
} from "../src/integrationOverview.ts";

test("shared handoff JSON Schema matches the frontend's exact top-level contract", () => {
  const spec = JSON.parse(readFileSync(
    new URL("../../../handoff/team/integration_overview.v1.schema.json", import.meta.url),
    "utf8",
  ));
  assert.equal(spec.properties.schema_version.const, INTEGRATION_SCHEMA);
  assert.equal(spec.additionalProperties, false);
  assert.deepEqual([...spec.required].sort(),
    ["schema_version", "generated_at", "access_scope", "edge",
     "cameras", "meta", "notification"].sort());
  assert.equal(spec.properties.cameras.maxItems, 16);
  assert.equal(spec.properties.cameras.items.additionalProperties, false);
  assert.equal(spec.properties.meta.additionalProperties, false);
});

function valid() {
  return {
    schema_version: INTEGRATION_SCHEMA,
    generated_at: "2026-10-28T09:00:00Z",
    access_scope: "authenticated_operator",
    edge: { state: "ready", last_heartbeat_at: "2026-10-28T09:00:00Z" },
    cameras: [
      { camera_id: "lab-rtsp-01", transport: "rtsp", health: "online",
        privacy: "approved", last_heartbeat_at: "2026-10-28T09:00:00Z", observed_fps: 12.5 },
      { camera_id: "lab-usb-02", transport: "usb", health: "offline",
        privacy: "expired", last_heartbeat_at: null, observed_fps: null },
    ],
    meta: { provider: "mock", state: "not_configured",
      evidence_pipeline: "not_configured", last_verified_call_at: null },
    notification: { state: "not_configured" },
  };
}

test("accepts only small sanitized read-only metadata from backend", () => {
  const item = parseIntegrationOverview(valid());
  assert.equal(item.cameras.length, 2);
  assert.equal(item.meta.provider, "mock");
  assert.equal(item.schema_version, INTEGRATION_SCHEMA);
  assert.equal(JSON.stringify(item).includes("rtsp://"), false);
});
test("snapshot freshness blocks stale or future camera online claims", () => {
  const snap = parseIntegrationOverview(valid());
  const sourceTime = Date.parse(snap.generated_at);
  assert.equal(snapshotIsFresh(snap, sourceTime), true);
  assert.equal(snapshotIsFresh(snap, sourceTime + 30_000), true);
  assert.equal(snapshotIsFresh(snap, sourceTime + 30_001), false);
  assert.equal(snapshotIsFresh(snap, sourceTime - 5_001), false);
});

const attacks = {
  unknownMetadata: x => ({ ...x, camera_password: "sensitive" }),
  versionDowngrade: x => ({ ...x, schema_version: "v0" }),
  unauthenticated: x => ({ ...x, access_scope: "public" }),
  surplusCameras: x => ({ ...x, cameras: Array.from({ length: 17 }, (_, i) => ({
    ...x.cameras[0], camera_id: "c" + i,
  })) }),
  duplicateCamera: x => ({ ...x, cameras: [x.cameras[0], x.cameras[0]] }),
  rtspUrl: x => ({ ...x, cameras: [{ ...x.cameras[0], url: "rtsp://admin:pass@private" }] }),
  cameraIdInjection: x => ({ ...x, cameras: [{ ...x.cameras[0], camera_id: "https://host/a" }] }),
  unauthorizedOnline: x => ({ ...x, cameras: [{ ...x.cameras[0], privacy: "revoked" }] }),
  missingHeartbeat: x => ({ ...x, cameras: [{ ...x.cameras[0], last_heartbeat_at: null }] }),
  staleCameraHeartbeat: x => ({ ...x, cameras: [{ ...x.cameras[0],
    last_heartbeat_at: "2026-10-28T08:58:00Z" }] }),
  futureCameraHeartbeat: x => ({ ...x, cameras: [{ ...x.cameras[0],
    last_heartbeat_at: "2026-10-28T09:01:00Z" }] }),
  staleEdgeHeartbeat: x => ({ ...x, edge: { ...x.edge,
    last_heartbeat_at: "2026-10-28T08:58:00Z" } }),
  infiniteFPS: x => ({ ...x, cameras: [{ ...x.cameras[0], observed_fps: Infinity }] }),
  impossibleFPS: x => ({ ...x, cameras: [{ ...x.cameras[0], observed_fps: 100000 }] }),
  hiddenImage: x => ({ ...x, cameras: [{ ...x.cameras[0], image_url: "http://sensitive" }] }),
  metaDirectProviderKey: x => ({ ...x, meta: { ...x.meta, api_key: "secret" } }),
  fakeMeta: x => ({ ...x, meta: { ...x.meta, state: "ready" } }),
  metaNoEvidence: x => ({ ...x, meta: { provider: "meta_model_api",
    state: "ready", evidence_pipeline: "blocked", last_verified_call_at: null } }),
  falseNotification: x => ({ ...x, notification: { state: "alert_sent", by: "model" } }),
};
for (const [name, transform] of Object.entries(attacks)) {
  test("rejects " + name + " without reflecting secrets", () => {
    assert.throws(() => parseIntegrationOverview(transform(valid())), e => {
      assert.doesNotMatch(e.message, /secret|rtsp:\/\//i);
      return true;
    });
  });
}

test("only same-origin read-only endpoint is accessed; no browser Meta/RTSP", async () => {
  const realFetch = globalThis.fetch;
  try {
    globalThis.fetch = async (url, options) => {
      assert.equal(url, "/api/v1/integrations/overview");
      assert.equal(options.method, "GET");
      assert.equal(options.credentials, "same-origin");
      assert.equal(options.cache, "no-store");
      assert.equal(options.redirect, "error");
      assert.equal(options.headers.Accept, "application/json");
      return new Response(JSON.stringify(valid()), { status: 200,
        headers: { "Content-Type": "application/json" } });
    };
    assert.equal((await fetchIntegrationOverview()).cameras.length, 2);
  } finally { globalThis.fetch = realFetch; }
});

test("auth failure never echoes backend text or tries API tokens", async () => {
  const realFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("Bearer secret-value", { status: 401 });
    await assert.rejects(fetchIntegrationOverview(), e => {
      assert.match(e.message, /Authentication\/authorization/);
      assert.doesNotMatch(e.message, /secret-value/);
      return true;
    });
  } finally { globalThis.fetch = realFetch; }
});

test("oversize response body rejected even if server omits content-length", async () => {
  const realFetch = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("x".repeat(MAX_INTEGRATION_BYTES + 1),
      { status: 200 });
    await assert.rejects(fetchIntegrationOverview(), /too large/);
  } finally { globalThis.fetch = realFetch; }
});
