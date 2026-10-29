import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import {
  CAMERA_PREVIEW_SCHEMA, MAX_PREVIEW_JSON_BYTES, MAX_PREVIEW_LIFETIME_MS,
  parseCameraPreviewSession, previewBasePath, previewImagePath,
  openCameraPreview, closeCameraPreview,
} from "../src/cameraPreview.ts";

const CAMERA = "staged-camera-01";
const SESSION = "Xx9_abcDefGhIjKlMnOpQr";
const clock = Date.parse("2026-10-29T10:00:00Z");
const valid = (now = clock) => ({
  schema_version: CAMERA_PREVIEW_SCHEMA,
  camera_id: CAMERA,
  session_id: SESSION,
  expires_at: new Date(now + 20_000).toISOString(),
});

test("Member 2 camera session JSON schema agrees on all exact keys and ID constraints", () => {
  const spec = JSON.parse(readFileSync(
    new URL("../../../handoff/team/camera_preview_session.v1.schema.json", import.meta.url),
    "utf8",
  ));
  assert.equal(spec.additionalProperties, false);
  assert.deepEqual(spec.required.sort(), ["schema_version", "camera_id", "session_id",
    "expires_at"].sort());
  assert.equal(spec.properties.schema_version.const, CAMERA_PREVIEW_SCHEMA);
  assert.ok(new RegExp(spec.properties.camera_id.pattern).test(CAMERA));
  assert.ok(new RegExp(spec.properties.session_id.pattern).test(SESSION));
  assert.ok(new RegExp(spec.properties.expires_at.pattern).test(valid().expires_at));
});

test("strict verified camera-scoped one-session contract and local path only", () => {
  assert.equal(previewBasePath(CAMERA), "/api/v1/cameras/staged-camera-01/preview-sessions");
  const session = parseCameraPreviewSession(valid(), CAMERA, clock);
  assert.equal(previewImagePath(session),
    "/api/v1/cameras/staged-camera-01/preview-sessions/Xx9_abcDefGhIjKlMnOpQr/mjpeg");
  assert.equal(MAX_PREVIEW_LIFETIME_MS, 30_000);
});

const malicious = {
  mismatchedCamera: x => ({ ...x, camera_id: "other" }),
  remoteMedia: x => ({ ...x, url: "rtsp://admin:secret@192.168.10.10" }),
  maliciousMedia: x => ({ ...x, url: "https://outside.example/x" }),
  noExpiry: x => ({ ...x, expires_at: null }),
  expired: x => ({ ...x, expires_at: new Date(clock - 1).toISOString() }),
  tooLong: x => ({ ...x, expires_at: new Date(clock + MAX_PREVIEW_LIFETIME_MS + 1).toISOString() }),
  badSessionId: x => ({ ...x, session_id: "../../admin?token=secret" }),
  shortSessionId: x => ({ ...x, session_id: "123" }),
  rtspCameraId: x => ({ ...x, camera_id: "rtsp://bad/cam" }),
  wrongSchema: x => ({ ...x, schema_version: "viil.preview.insecure.v0" }),
  extraKey: x => ({ ...x, token: "secret" }),
};
for (const [name, change] of Object.entries(malicious)) {
  test("camera preview rejects " + name + " without reflecting private data", () => {
    assert.throws(() => parseCameraPreviewSession(change(valid()), CAMERA, clock),
      e => {
        assert.doesNotMatch(e.message, /rtsp|secret|192\.168|token/i);
        return true;
      });
  });
}

test("invalid camera and session identifiers never create arbitrary URLs", () => {
  for (const id of ["", "https://evil", "../other", "a?x=1", "rtsp://name:secret@local"]) {
    assert.throws(() => previewBasePath(id), /Invalid preview camera ID/);
  }
  assert.throws(() => previewImagePath({ ...valid(), session_id: "//evil" }), /Invalid/);
});

test("one explicit session POST and cleanup DELETE are same-origin, no RTSP/password", async () => {
  const old = globalThis.fetch;
  let count = 0;
  try {
    globalThis.fetch = async (url, options) => {
      count++;
      assert.match(url, /^\/api\/v1\/cameras\/staged-camera-01\/preview-sessions/);
      assert.equal(options.credentials, "same-origin");
      assert.equal(options.mode, "same-origin");
      assert.equal(options.redirect, "error");
      assert.equal(options.cache, "no-store");
      assert.doesNotMatch(JSON.stringify({ url, options }), /password|cameraSecret|rtsp:/);
      if (count === 1) {
        assert.equal(options.method, "POST");
        return new Response(JSON.stringify(valid(Date.now())), { status: 200 });
      }
      assert.equal(options.method, "DELETE");
      assert.equal(url, `/api/v1/cameras/${CAMERA}/preview-sessions/${SESSION}`);
      return new Response(null, { status: 204 });
    };
    // Importing the module never calls fetch or opens a camera.
    assert.equal(count, 0);
    const session = await openCameraPreview(CAMERA);
    assert.equal(count, 1);
    await closeCameraPreview(session);
    assert.equal(count, 2);
  } finally {
    globalThis.fetch = old;
  }
});

test("backend auth denial never leaks raw response or retries", async () => {
  const original = globalThis.fetch;
  let count = 0;
  try {
    globalThis.fetch = async () => {
      count++;
      return new Response("SENSITIVE camera credentials", { status: 403 });
    };
    await assert.rejects(openCameraPreview(CAMERA), e => {
      assert.match(e.message, /authentication|access denied/i);
      assert.doesNotMatch(e.message, /SENSITIVE/);
      return true;
    });
    assert.equal(count, 1);
  } finally { globalThis.fetch = original; }
});

test("404 means backend media gateway unavailable, never camera streaming", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("rtsp://secret", { status: 404 });
    await assert.rejects(openCameraPreview(CAMERA), /gateway unavailable/);
  } finally { globalThis.fetch = original; }
});

test("refuse unbounded JSON body even without content-length", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("X".repeat(MAX_PREVIEW_JSON_BYTES + 1),
      { status: 200 });
    await assert.rejects(openCameraPreview(CAMERA), /Invalid camera preview session/);
  } finally { globalThis.fetch = original; }
});

test("server-expired approval cannot be replayed as a browser image", () => {
  assert.throws(() => parseCameraPreviewSession(valid(clock - 40_000), CAMERA, clock),
    /not current/);
});
