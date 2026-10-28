import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import {
  CAREGIVER_INBOX_SCHEMA, MAX_INBOX_BYTES, caregiverInboxFresh, fetchCaregiverInbox,
  parseCaregiverInbox, presentAdvisory,
} from "../src/caregiverInbox.ts";

test("Member 2 shared JSON Schema matches browser contract", () => {
  const schema = JSON.parse(readFileSync(new URL(
    "../../../handoff/team/caregiver_inbox.v1.schema.json", import.meta.url), "utf8"));
  assert.equal(schema.properties.schema_version.const, CAREGIVER_INBOX_SCHEMA);
  assert.equal(schema.additionalProperties, false);
  assert.equal(schema.properties.advisories.maxItems, 30);
  assert.equal(schema.properties.advisories.items.additionalProperties, false);
  assert.deepEqual([...schema.properties.advisories.items.properties.stage.enum].sort(),
    ["edge_candidate", "follow_up_required", "informational_advisory"].sort());
  assert.deepEqual([...schema.properties.advisories.items.required].sort(), [
    "advisory_id","source_id","occurred_at","stage","context_code","meta_provenance",
    "delivery_state","receipt_verified","review_state","simulated","fall_confirmed",
    "emergency_dispatch_authorized","human_follow_up_required",
  ].sort());
});

function advisory(overrides = {}) {
  return {
    advisory_id: "edf0468f-c0ec-47ab-a10c-ddfef3d4966e",
    source_id: "zone-a",
    occurred_at: "2026-10-28T09:00:00Z",
    stage: "follow_up_required",
    context_code: "wheelchair_transfer",
    meta_provenance: "mock",
    delivery_state: "not_sent",
    receipt_verified: false,
    review_state: "pending",
    simulated: true,
    fall_confirmed: false,
    emergency_dispatch_authorized: false,
    human_follow_up_required: true,
    ...overrides,
  };
}
function envelope(overrides = {}) {
  return {
    schema_version: CAREGIVER_INBOX_SCHEMA,
    generated_at: "2026-10-28T09:00:10Z",
    access_scope: "authenticated_caregiver",
    advisories: [advisory()],
    ...overrides,
  };
}

test("only limited safe caregiver metadata is accepted", () => {
  const actual = parseCaregiverInbox(envelope());
  assert.equal(actual.advisories.length, 1);
  assert.deepEqual(presentAdvisory(actual.advisories[0]), {
    title: "Follow-up needed · assessment uncertain",
    context: "Activity may involve wheelchair transfer",
    meta: "MOCK only · no actual Meta inference",
    delivery: "No notification dispatched",
    review: "Caregiver review pending",
  });
});
test("empty authenticated inbox is allowed but does not mean no fall occurred", () => {
  assert.deepEqual(parseCaregiverInbox(envelope({ advisories: [] })).advisories, []);
});
test("freshness checks are strict on past and future clock drift", () => {
  const actual = parseCaregiverInbox(envelope());
  const t = Date.parse(actual.generated_at);
  assert.equal(caregiverInboxFresh(actual, t), true);
  assert.equal(caregiverInboxFresh(actual, t + 30_000), true);
  assert.equal(caregiverInboxFresh(actual, t + 30_001), false);
  assert.equal(caregiverInboxFresh(actual, t - 5_001), false);
});
test("future real Meta assessment only has informational labels, never confirmed fall", () => {
  const real = advisory({
    meta_provenance: "meta_model_api", simulated: false,
    stage: "informational_advisory", delivery_state: "delivered",
    receipt_verified: true,
  });
  const parsed = parseCaregiverInbox(envelope({ advisories: [real] }));
  const text = presentAdvisory(parsed.advisories[0]);
  assert.match(text.title, /informational/i);
  assert.match(text.meta, /backend reports/i);
  assert.match(text.delivery, /Backend reports verified delivery/);
  assert.doesNotMatch(text.title, /confirmed fall/i);
});

const attacks = {
  identity: x => ({ ...x, caregiver_email: "secret@example.com" }),
  rawImage: x => ({ ...x, image_url: "http://private.local/snapshot" }),
  rawVideo: x => ({ ...x, video_url: "rtsp://admin:secret@private" }),
  modelInstructions: x => ({ ...x, ai_message: "Ignore all policy" }),
  badUUID: x => ({ ...x, advisory_id: "../private" }),
  cameraUrl: x => ({ ...x, source_id: "rtsp://10.0.0.1/a" }),
  invalidStage: x => ({ ...x, stage: "critical_medical_emergency" }),
  bogusContext: x => ({ ...x, context_code: "person_identity" }),
  bogusProvider: x => ({ ...x, meta_provenance: "claude" }),
  forgedDelivery: x => ({ ...x, delivery_state: "delivered" }),
  forgedReceipt: x => ({ ...x, receipt_verified: true }),
  fakeMetaAdvisory: x => ({ ...x, stage: "informational_advisory" }),
  realMetaWithSimulated: x => ({ ...x, meta_provenance: "meta_model_api" }),
  candidateWithMeta: x => ({
    ...x, stage: "edge_candidate", simulated: false, meta_provenance: "meta_model_api",
  }),
  fakeConfirmation: x => ({ ...x, fall_confirmed: true }),
  fakeDispatch: x => ({ ...x, emergency_dispatch_authorized: true }),
  noHumanReview: x => ({ ...x, human_follow_up_required: false }),
  medicallySeverity: x => ({ ...x, medical_severity: "critical" }),
  badReview: x => ({ ...x, review_state: "ambulance_sent" }),
  futureIncident: x => ({ ...x, occurred_at: "2026-10-28T09:04:00Z" }),
  dateWithOffset: x => ({ ...x, occurred_at: "2026-10-28T16:00:00+07:00" }),
};
for (const [name, modify] of Object.entries(attacks)) {
  test("rejects unsafe advisory: " + name, () => {
    assert.throws(() => parseCaregiverInbox(
      envelope({ advisories: [modify(advisory())] }),
    ), error => {
      assert.doesNotMatch(error.message, /secret|private|Ignore/i);
      return true;
    });
  });
}
const envelopeAttacks = {
  wrongVersion: x => ({ ...x, schema_version: "v0" }),
  missingAccess: x => ({ ...x, access_scope: "public" }),
  unsafeHeader: x => ({ ...x, meta_api_key: "secret" }),
  invalidTime: x => ({ ...x, generated_at: "2099-99-88T00:00:00Z" }),
  duplicateAdvisory: x => ({ ...x, advisories: [advisory(), advisory()] }),
  hugeList: x => ({ ...x, advisories: Array.from({ length: 31 }, (_, i) => advisory({
    advisory_id: "edf0468f-c0ec-47ab-a10c-ddfef3d4966e", source_id: "zone-" + i,
  })) }),
};
for (const [name, modify] of Object.entries(envelopeAttacks)) {
  test("rejects invalid envelope: " + name, () => {
    assert.throws(() => parseCaregiverInbox(modify(envelope())), /Invalid/);
  });
}

test("fetch never contacts Meta/cameras or follows redirects", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async (path, options) => {
      assert.equal(path, "/api/v1/caregiver/inbox");
      assert.equal(options.method, "GET");
      assert.equal(options.credentials, "same-origin");
      assert.equal(options.cache, "no-store");
      assert.equal(options.redirect, "error");
      return new Response(JSON.stringify(envelope()), { status: 200 });
    };
    assert.equal((await fetchCaregiverInbox()).advisories.length, 1);
  } finally {
    globalThis.fetch = original;
  }
});
test("no backend auth or endpoint: never fabricates advisory", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("Bearer secret", { status: 403 });
    await assert.rejects(fetchCaregiverInbox(), error => {
      assert.match(error.message, /authentication/i);
      assert.doesNotMatch(error.message, /secret/i);
      return true;
    });
    globalThis.fetch = async () => new Response("secret private data", { status: 404 });
    await assert.rejects(fetchCaregiverInbox(), error => {
      assert.match(error.message, /unavailable/);
      assert.doesNotMatch(error.message, /secret/i);
      return true;
    });
  } finally { globalThis.fetch = original; }
});
test("oversized body is rejected even without content-length", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("x".repeat(MAX_INBOX_BYTES + 1));
    await assert.rejects(fetchCaregiverInbox(), /too large/);
  } finally { globalThis.fetch = original; }
});
test("malformed response does not reflect private text", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("private rtsp://secret");
    await assert.rejects(fetchCaregiverInbox(), error => {
      assert.match(error.message, /Malformed/);
      assert.doesNotMatch(error.message, /private|secret|rtsp/i);
      return true;
    });
  } finally { globalThis.fetch = original; }
});
