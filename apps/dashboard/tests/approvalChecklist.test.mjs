import assert from "node:assert/strict";
import { test } from "node:test";
import {
  APPROVAL_CHECKLIST_SCHEMA, fetchApprovalChecklist, parseApprovalChecklist,
} from "../src/approvalChecklist.ts";

const safe = () => ({
  schema_version: APPROVAL_CHECKLIST_SCHEMA,
  draft_available: true,
  draft_fields_structurally_complete: false,
  issues: ["notice_ref", "validity_window", "site_authorization_confirmed"],
  genuine_site_permission_confirmed_by_tool: false,
  signed_policy_verified: false,
  camera_access_granted: false,
});

test("private unsigned draft issues are only field names, not authorization", () => {
  const result = parseApprovalChecklist(safe());
  assert.deepEqual(result.issues, ["notice_ref", "validity_window",
    "site_authorization_confirmed"]);
  assert.equal(result.signed_policy_verified, false);
  assert.equal(result.camera_access_granted, false);
  assert.doesNotMatch(JSON.stringify(result), /rtsp:\/\/|password|private-reference/i);
});

for (const [name, change] of Object.entries({
  illegalExtra: v => ({ ...v, camera_url: "rtsp://secret" }),
  privateRef: v => ({ ...v, issues: ["notice_ref=PRIVATE-SECRET"] }),
  pathDisclosure: v => ({ ...v, issues: ["C:\\Private\\approval.json"] }),
  fakeApproved: v => ({ ...v, signed_policy_verified: true }),
  fakeAuthority: v => ({ ...v, genuine_site_permission_confirmed_by_tool: true }),
  fakeAccess: v => ({ ...v, camera_access_granted: true }),
  duplicate: v => ({ ...v, issues: ["notice_ref", "notice_ref"] }),
  malformedAvailable: v => ({ ...v, draft_available: false }),
  inconsistentComplete: v => ({ ...v, draft_fields_structurally_complete: true }),
  wrongSchema: v => ({ ...v, schema_version: "untrusted.v0" }),
})) {
  test("approval checklist rejects " + name, () => {
    assert.throws(() => parseApprovalChecklist(change(safe())),
      /Invalid unsigned approval checklist/);
  });
}

test("missing draft may be displayed but never interpreted as approval", () => {
  assert.deepEqual(parseApprovalChecklist({
    ...safe(), draft_available: false, issues: [],
  }), {
    ...safe(), draft_available: false, issues: [],
  });
});

test("GET is authenticated same origin, no POST, key or camera URL", async () => {
  const original = globalThis.fetch;
  let calls = 0;
  try {
    globalThis.fetch = async (url, opts) => {
      calls++;
      assert.equal(url, "/api/v1/operator/approval-checklist");
      assert.equal(opts.method, "GET");
      assert.equal(opts.credentials, "same-origin");
      assert.equal(opts.mode, "same-origin");
      assert.equal(opts.cache, "no-store");
      assert.equal(opts.redirect, "error");
      assert.doesNotMatch(JSON.stringify({url, opts}), /rtsp:\/\/|password|token/);
      return new Response(JSON.stringify(safe()), { status: 200 });
    };
    assert.equal(calls, 0);
    const result = await fetchApprovalChecklist();
    assert.equal(result.draft_fields_structurally_complete, false);
    assert.equal(calls, 1);
  } finally { globalThis.fetch = original; }
});

test("unavailable endpoint redacts response and fails closed", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("PRIVATE_REFERENCE", { status: 404 });
    await assert.rejects(fetchApprovalChecklist(), e => {
      assert.equal(e.message, "Local approval review unavailable");
      assert.doesNotMatch(e.message, /PRIVATE_REFERENCE/);
      return true;
    });
  } finally { globalThis.fetch = original; }
});

test("oversized checklist response rejected even without content-length", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("S".repeat(5000), { status: 200 });
    await assert.rejects(fetchApprovalChecklist(), /Invalid unsigned approval checklist/);
  } finally { globalThis.fetch = original; }
});
