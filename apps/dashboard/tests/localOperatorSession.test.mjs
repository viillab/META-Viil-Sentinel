import assert from "node:assert/strict";
import { test } from "node:test";
import { loginLocalOperator, logoutLocalOperator } from "../src/localOperatorSession.ts";

test("operator session login sends password only to same-origin local path", async () => {
  const original = globalThis.fetch;
  const separatePassword = "synthetic-local-operator-very-private";
  let callCount = 0;
  try {
    globalThis.fetch = async (url, options) => {
      callCount++;
      assert.equal(url, "/api/v1/operator/login");
      assert.equal(options.method, "POST");
      assert.equal(options.credentials, "same-origin");
      assert.equal(options.mode, "same-origin");
      assert.equal(options.redirect, "error");
      assert.equal(options.cache, "no-store");
      assert.deepEqual(JSON.parse(options.body), { password: separatePassword });
      assert.doesNotMatch(url, /rtsp:|hikvision|password/);
      return new Response(JSON.stringify({ authenticated: true }), { status: 200 });
    };
    await loginLocalOperator(separatePassword);
    assert.equal(callCount, 1);
  } finally {
    globalThis.fetch = original;
  }
});

test("operator sign-in failures never reflect backend passwords", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("RTSP: admin/private-secret", { status: 401 });
    await assert.rejects(loginLocalOperator("bad"), e => {
      assert.match(e.message, /sign-in denied/);
      assert.doesNotMatch(e.message, /private-secret|admin/);
      return true;
    });
  } finally { globalThis.fetch = original; }
});

test("invalid operator password cannot trigger network request", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => { throw new Error("Unexpected login request"); };
    await assert.rejects(loginLocalOperator(""), /separate local operator/);
    await assert.rejects(loginLocalOperator("x".repeat(257)), /separate local operator/);
  } finally { globalThis.fetch = original; }
});

test("logout requests server revocation without bearer key", async () => {
  const original = globalThis.fetch;
  let count = 0;
  try {
    globalThis.fetch = async (url, options) => {
      count++;
      assert.equal(url, "/api/v1/operator/logout");
      assert.equal(options.method, "POST");
      assert.equal(options.credentials, "same-origin");
      assert.equal(options.mode, "same-origin");
      assert.equal(options.redirect, "error");
      assert.equal(options.cache, "no-store");
      assert.equal(options.body, undefined);
      return new Response(null, { status: 204 });
    };
    await logoutLocalOperator();
    assert.equal(count, 1);
  } finally { globalThis.fetch = original; }
});
