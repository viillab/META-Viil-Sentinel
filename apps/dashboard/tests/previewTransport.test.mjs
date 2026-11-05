import assert from "node:assert/strict";
import { test } from "node:test";
import {
  PREVIEW_TRANSPORT_SCHEMA, fetchPreviewTransportStatus, parsePreviewTransportStatus,
} from "../src/previewTransport.ts";
import { CAMERA_PREVIEW_SCHEMA } from "../src/cameraPreview.ts";

const session = {
  schema_version: CAMERA_PREVIEW_SCHEMA,
  camera_id: "staged-camera-01",
  session_id: "Xx9_abcDefGhIjKlMnOpQr",
  expires_at: "2099-01-01T00:00:20.000Z",
};
const sample = () => ({
  schema_version: PREVIEW_TRANSPORT_SCHEMA,
  camera_id: session.camera_id,
  session_id: session.session_id,
  edge_first_jpeg_verified: true,
  edge_preflight_started: true,
  browser_image_display_verified: false,
});

test("Edge decoded a JPEG is NOT proof the browser displayed it", () => {
  const result = parsePreviewTransportStatus(sample(), session);
  assert.equal(result.edge_first_jpeg_verified, true);
  assert.equal(result.browser_image_display_verified, false);
  assert.doesNotMatch(JSON.stringify(result), /rtsp:\/\/|password|credential/i);
});

for (const [name, mutate] of Object.entries({
  extraCredentials: x => ({ ...x, rtsp_url: "rtsp://admin:secret@camera" }),
  wrongCamera: x => ({ ...x, camera_id: "other" }),
  wrongSession: x => ({ ...x, session_id: "different-session-12345" }),
  fakeBrowser: x => ({ ...x, browser_image_display_verified: true }),
  unsupportedSchema: x => ({ ...x, schema_version: "untrusted.v0" }),
  invalidFirstFrame: x => ({ ...x, edge_first_jpeg_verified: "true" }),
  impossiblePreflight: x => ({ ...x, edge_preflight_started: false }),
})) {
  test("strict preview status refuses " + name, () => {
    assert.throws(() => parsePreviewTransportStatus(mutate(sample()), session),
      /Invalid local preview transport status/);
  });
}

test("preflight not started is not a decoded frame", () => {
  const result = parsePreviewTransportStatus({
    ...sample(), edge_first_jpeg_verified: false, edge_preflight_started: false,
  }, session);
  assert.equal(result.edge_first_jpeg_verified, false);
});

test("status request is same-origin, scoped to current opaque session", async () => {
  const old = globalThis.fetch;
  let calls = 0;
  try {
    globalThis.fetch = async (url, options) => {
      calls++;
      assert.equal(url, "/api/v1/cameras/staged-camera-01/preview-sessions/Xx9_abcDefGhIjKlMnOpQr/status");
      assert.equal(options.method, "GET");
      assert.equal(options.credentials, "same-origin");
      assert.equal(options.mode, "same-origin");
      assert.equal(options.cache, "no-store");
      assert.equal(options.redirect, "error");
      assert.doesNotMatch(JSON.stringify({url, options}), /rtsp:\/\/|password/i);
      return new Response(JSON.stringify(sample()), { status: 200 });
    };
    assert.equal(calls, 0);
    const result = await fetchPreviewTransportStatus(session);
    assert.equal(result.edge_first_jpeg_verified, true);
    assert.equal(calls, 1);
  } finally { globalThis.fetch = old; }
});

test("missing Member2 production endpoint cannot imply Edge frames", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("rtsp://secret", { status: 404 });
    await assert.rejects(fetchPreviewTransportStatus(session), e => {
      assert.equal(e.message, "Local preview transport status unavailable");
      assert.doesNotMatch(e.message, /rtsp|secret/i);
      return true;
    });
  } finally { globalThis.fetch = old; }
});

test("unbounded local preview status body is rejected", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("x".repeat(4000), { status: 200 });
    await assert.rejects(fetchPreviewTransportStatus(session),
      /Invalid local preview transport status/);
  } finally { globalThis.fetch = old; }
});

test("untrusted session IDs are rejected before network access", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = async () => { throw new Error("Unexpected fetch"); };
    await assert.rejects(fetchPreviewTransportStatus({
      ...session, session_id: "../../credentials",
    }), /Invalid local preview transport status/);
  } finally { globalThis.fetch = old; }
});
