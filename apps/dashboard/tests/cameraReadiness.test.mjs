import assert from "node:assert/strict";
import { test } from "node:test";
import {
  CAMERA_READINESS_SCHEMA, fetchCameraReadiness, parseCameraReadiness,
} from "../src/cameraReadiness.ts";

const CAM = "staged-camera-01";
const valid = () => ({
  schema_version: CAMERA_READINESS_SCHEMA,
  camera_id: CAM,
  signed_privacy_approval_verified: false,
  private_rtsp_configured: true,
  pyav_decoder_installed: true,
  opencv_jpeg_encoder_installed: true,
  eligible_for_supervised_trial: false,
  real_camera_frame_verified: false,
});

test("valid local readiness is not proof of video and never carries credentials", () => {
  const ready = parseCameraReadiness(valid());
  assert.equal(ready.real_camera_frame_verified, false);
  assert.equal(ready.eligible_for_supervised_trial, false);
  assert.doesNotMatch(JSON.stringify(ready), /rtsp:\/\/|password|secret/i);
});

for (const [name, make] of Object.entries({
  foreignSchema: v => ({ ...v, schema_version: "malicious.v0" }),
  foreignCamera: v => ({ ...v, camera_id: "https://camera.example" }),
  remoteUrl: v => ({ ...v, rtsp_url: "rtsp://login:secret@camera" }),
  cameraPassword: v => ({ ...v, password: "secret" }),
  fakeLiveVideo: v => ({ ...v, real_camera_frame_verified: true }),
  incorrectReadiness: v => ({ ...v, eligible_for_supervised_trial: true }),
  malformedBoolean: v => ({ ...v, pyav_decoder_installed: "yes" }),
})) {
  test("readiness contract refuses " + name, () => {
    assert.throws(() => parseCameraReadiness(make(valid())),
      /Invalid local camera readiness response/);
  });
}

test("diagnostic GET requires same origin credentials, no session secrets", async () => {
  const old = globalThis.fetch;
  let hits = 0;
  try {
    globalThis.fetch = async (url, options) => {
      hits++;
      assert.equal(url, "/api/v1/operator/camera-readiness");
      assert.equal(options.method, "GET");
      assert.equal(options.credentials, "same-origin");
      assert.equal(options.mode, "same-origin");
      assert.equal(options.cache, "no-store");
      assert.equal(options.redirect, "error");
      assert.doesNotMatch(JSON.stringify({url, options}), /password|rtsp:\/\/|token/i);
      return new Response(JSON.stringify(valid()), {status: 200});
    };
    assert.equal(hits, 0); // no camera or HTTP request on module import
    const check = await fetchCameraReadiness();
    assert.equal(check.signed_privacy_approval_verified, false);
    assert.equal(hits, 1);
  } finally { globalThis.fetch = old; }
});

test("Member2 endpoint not supporting local diagnostic fails closed", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("sensitive data", {status: 404});
    await assert.rejects(fetchCameraReadiness(), e => {
      assert.equal(e.message, "Local camera readiness unavailable");
      assert.doesNotMatch(e.message, /sensitive/);
      return true;
    });
  } finally { globalThis.fetch = old; }
});

test("unbounded local readiness response rejected during streaming", async () => {
  const old = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("x".repeat(4096), {status: 200});
    await assert.rejects(fetchCameraReadiness(), /Invalid local camera readiness response/);
  } finally { globalThis.fetch = old; }
});
