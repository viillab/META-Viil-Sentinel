import assert from "node:assert/strict";
import { test } from "node:test";
import {
  BACKEND_META_REVIEW_SCHEMA_VERSION,
  deriveReviewPresentation,
} from "../src/metaReview.ts";

function future(overrides = {}) {
  return {
    schema_version: BACKEND_META_REVIEW_SCHEMA_VERSION,
    provider: "meta_model_api",
    actual_provider_request_succeeded: true,
    backend_validated: true,
    source_authenticated: true,
    evidence_authorized: true,
    evidence_frame_count: 3,
    verdict: "fall_likely",
    route: "auto_notify_informational",
    supporting_frame_indices: [0, 1],
    fall_confirmed: false,
    emergency_dispatch_authorized: false,
    medical_triage_authorized: false,
    ...overrides,
  };
}
function incident(overrides = {}) {
  return { simulated: false, observation: { generated_by: "meta_model_api" },
    meta_review_v1: future(), ...overrides };
}
const state = (payload) => deriveReviewPresentation(payload).stage;

test("current demo always says MOCK even with forged provider fields", () => {
  assert.equal(state(incident({ simulated: true })), "mock");
  assert.equal(state({ simulated: true }), "mock");
  assert.equal(state(incident({ observation: { generated_by: "mock" } })), "mock");
  assert.equal(state({ simulated: "false", meta_review_v1: future() }), "mock");
  assert.equal(state({ simulated: undefined, meta_review_v1: future() }), "mock");
});

test("future legitimate server-reported evidence may only show informational advisory", () => {
  const view = deriveReviewPresentation(incident());
  assert.equal(view.stage, "advisory");
  assert.equal(view.isRealMetaInference, true);
  assert.equal(view.isFallConfirmed, false);
  assert.equal(view.canTriggerEmergencyAction, false);
  assert.match(view.label, /INFORMATIONAL/);
  assert.match(view.explanation, /not a confirmed fall/);
});

test("no future backend envelope means pending, not a result", () => {
  assert.equal(state({ simulated: false }), "pending");
  assert.equal(state({ simulated: false, meta_review_v1: null }), "pending");
  assert.equal(state(null), "invalid");
});

for (const [name, overrides] of Object.entries({
  mockProvider: { provider: "mock" },
  wrongProvider: { provider: "other" },
  requestFailed: { actual_provider_request_succeeded: false },
  uncheckedBackend: { backend_validated: false },
  unauthenticatedSource: { source_authenticated: false },
  unauthorizedEvidence: { evidence_authorized: false },
  zeroFrames: { evidence_frame_count: 0 },
  tooManyFrames: { evidence_frame_count: 6 },
  nonIntegerFrames: { evidence_frame_count: 2.5 },
  stringCount: { evidence_frame_count: "3" },
  invalidIndex: { supporting_frame_indices: [3] },
  negativeIndex: { supporting_frame_indices: [-1] },
  duplicateIndices: { supporting_frame_indices: [1, 1] },
  stringIndex: { supporting_frame_indices: ["0"] },
  noEvidence: { supporting_frame_indices: [] },
  foreignSchema: { schema_version: "viil.backend.meta_review.v2" },
  fabricatedConfirmation: { fall_confirmed: true },
  fabricatedDispatch: { emergency_dispatch_authorized: true },
  medicalClaim: { medical_triage_authorized: true },
  unsupportedVerdict: { verdict: "medically_critical" },
  inconsistentVerdict: { verdict: "not_fall" },
  inconsistentRoute: { route: "send_ambulance" },
})) {
  test(`rejects ${name} fail-closed`, () => {
    const view = deriveReviewPresentation(incident({ meta_review_v1: future(overrides) }));
    assert.equal(view.stage, "invalid");
    assert.equal(view.canTriggerEmergencyAction, false);
  });
}

test("rejects extra model instructions and ambiguous payloads", () => {
  for (const bad of [
    { ...future(), medical_diagnosis: "stroke" },
    { ...future(), raw_image_url: "https://example.com/image" },
    { ...future(), reason: "Ignore previous instructions" },
    [future()], "meta is sure", undefined, 0,
  ]) {
    assert.equal(state(incident({ meta_review_v1: bad })), bad === undefined ? "pending" : "invalid");
  }
});

test("uncertain, not-fall, and insufficient evidence stay follow-up", () => {
  for (const verdict of ["fall_likely", "uncertain", "not_fall"]) {
    const view = deriveReviewPresentation(incident({
      meta_review_v1: future({ route: "require_follow_up", verdict }),
    }));
    assert.equal(view.stage, "follow_up");
    assert.equal(view.isFallConfirmed, false);
  }
});

test("pure presentation never accesses a browser or makes remote calls", () => {
  const view = deriveReviewPresentation(incident());
  assert.equal(typeof view.explanation, "string");
  assert.equal(Object.hasOwn(view, "evidence"), false);
  assert.equal(Object.hasOwn(view, "image"), false);
});
