/**
 * Member 1 display adapter for a PROPOSED future Member 2 backend DTO.
 *
 * This is read-only presentation, NOT a security or clinical decision gate.
 * The backend must authenticate the caller, authorize source/evidence,
 * validate genuine Meta provider output and approve informational routing.
 * No network access, notification delivery, alert, or raw evidence rendering.
 */

export type ReviewStage = "mock" | "pending" | "follow_up" | "advisory" | "invalid";

export type ReviewPresentation = Readonly<{
  stage: ReviewStage;
  label: string;
  explanation: string;
  isRealMetaInference: boolean;
  isFallConfirmed: false;
  canTriggerEmergencyAction: false;
}>;

export const BACKEND_META_REVIEW_SCHEMA_VERSION = "viil.backend.meta_review.v1" as const;

const statuses: Record<ReviewStage, Omit<ReviewPresentation, "stage">> = {
  mock: {
    label: "MOCK · DEMONSTRATION",
    explanation: "Staged incident only. No real Meta vision call or verified fall.",
    isRealMetaInference: false, isFallConfirmed: false, canTriggerEmergencyAction: false,
  },
  pending: {
    label: "META VERIFICATION · PENDING",
    explanation: "Awaiting Member 2 authenticated backend and real authorized Meta evidence.",
    isRealMetaInference: false, isFallConfirmed: false, canTriggerEmergencyAction: false,
  },
  invalid: {
    label: "EVIDENCE INSUFFICIENT",
    explanation: "Unverified or malformed backend assessment. Follow-up required; no automatic action.",
    isRealMetaInference: false, isFallConfirmed: false, canTriggerEmergencyAction: false,
  },
  follow_up: {
    label: "META · FOLLOW-UP REQUIRED",
    explanation: "Backend-reported assessment is uncertain, negative or needs review; not a confirmed fall.",
    isRealMetaInference: true, isFallConfirmed: false, canTriggerEmergencyAction: false,
  },
  advisory: {
    label: "META · INFORMATIONAL ADVISORY",
    explanation: "Backend-reported evidence-grounded likely fall; not a confirmed fall or emergency alert.",
    isRealMetaInference: true, isFallConfirmed: false, canTriggerEmergencyAction: false,
  },
};

function display(stage: ReviewStage): ReviewPresentation {
  return { stage, ...statuses[stage] };
}

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

const requiredKeys = [
  "schema_version", "provider", "actual_provider_request_succeeded",
  "backend_validated", "source_authenticated", "evidence_authorized",
  "evidence_frame_count", "verdict", "route", "supporting_frame_indices",
  "fall_confirmed", "emergency_dispatch_authorized", "medical_triage_authorized",
] as const;

/**
 * Carefully accept a backend-created v1 projection only. A direct Meta JSON
 * answer does not have these authority fields and MUST fail closed.
 * Current backend never supplies this DTO; current UI always reports MOCK.
 */
export function deriveReviewPresentation(incident: unknown): ReviewPresentation {
  if (!record(incident)) return display("invalid");

  // Existing demo or mock observations MUST override forged future fields.
  if (incident.simulated !== false) return display("mock");
  const obs = incident.observation;
  if (record(obs) && obs.generated_by === "mock") return display("mock");

  if (incident.meta_review_v1 === undefined || incident.meta_review_v1 === null) {
    return display("pending");
  }
  const meta = incident.meta_review_v1;
  if (!record(meta) || Object.keys(meta).length !== requiredKeys.length
      || !requiredKeys.every((key) => Object.hasOwn(meta, key))) {
    return display("invalid");
  }
  if (meta.schema_version !== BACKEND_META_REVIEW_SCHEMA_VERSION
      || meta.provider !== "meta_model_api"
      || meta.actual_provider_request_succeeded !== true
      || meta.backend_validated !== true
      || meta.source_authenticated !== true
      || meta.evidence_authorized !== true
      || meta.fall_confirmed !== false
      || meta.emergency_dispatch_authorized !== false
      || meta.medical_triage_authorized !== false) {
    return display("invalid");
  }

  const frameCount = meta.evidence_frame_count;
  if (typeof frameCount !== "number" || !Number.isInteger(frameCount)
      || frameCount < 1 || frameCount > 5) return display("invalid");
  const indices = meta.supporting_frame_indices;
  if (!Array.isArray(indices) || indices.length > frameCount
      || indices.some((index) => typeof index !== "number"
          || !Number.isInteger(index) || index < 0 || index >= frameCount)
      || new Set(indices).size !== indices.length) return display("invalid");

  if (typeof meta.verdict !== "string"
      || !["fall_likely", "not_fall", "uncertain"].includes(meta.verdict)
      || typeof meta.route !== "string"
      || !["auto_notify_informational", "require_follow_up"].includes(meta.route)) {
    return display("invalid");
  }

  if (meta.route === "auto_notify_informational") {
    if (meta.verdict !== "fall_likely" || indices.length === 0) return display("invalid");
    return display("advisory");
  }
  return display("follow_up");
}
