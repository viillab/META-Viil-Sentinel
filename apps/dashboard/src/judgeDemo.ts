/**
 * Offline competition walkthrough of EXISTING Edge v1 fixture and FUTURE
 * Member 2 orchestration. No browser network, model execution, media,
 * storage, notifications, emergency dispatch, or actual Meta responses.
 */
import syntheticCandidate from "./fixtures/edgeCandidateSynthetic.json" with { type: "json" };
import { parseEdgeCandidateJsonl, formatSourceOffset } from "./edgeLab.ts";
import type { EdgeCandidateV1 } from "./edgeLab.ts";

export type ScenarioKey =
  | "synthetic_fall" | "synthetic_sitting" | "wheelchair_context"
  | "privacy_denied" | "meta_unavailable";
export type DemoStep = Readonly<{
  id: "camera" | "edge" | "privacy" | "meta" | "policy" | "caregiver";
  title: string;
  owner: "Member 1" | "Member 2";
  state: "simulated" | "blocked" | "pending" | "not_triggered";
  detail: string;
  evidence: string;
}>;
export type DemoWalkthrough = Readonly<{
  title: string;
  challenge: string;
  intendedBenefit: string;
  scenario: ScenarioKey;
  steps: readonly DemoStep[];
  candidate: EdgeCandidateV1 | null;
  expectedHumanOutcome: string;
  disclaimer: string;
}>;

const FALL = parseEdgeCandidateJsonl(
  JSON.stringify(syntheticCandidate), "Canonical Edge synthetic fixture",
).events[0];

const descriptors: Record<ScenarioKey, {
  title: string; challenge: string; intendedBenefit: string;
}> = {
  synthetic_fall: {
    title: "Staged fall-like motion",
    challenge: "A person may be unable to reach a phone after a fall.",
    intendedBenefit: "Show how an unconfirmed Edge candidate could reach a caregiver after authorized evidence review.",
  },
  synthetic_sitting: {
    title: "Sitting · no candidate",
    challenge: "Normal posture changes should not automatically create an alert.",
    intendedBenefit: "Illustrate what a candidate-free synthetic input looks like, without claiming measured specificity.",
  },
  wheelchair_context: {
    title: "Wheelchair transfer · context ambiguity",
    challenge: "Transferring between a wheelchair and a bed may resemble a fall.",
    intendedBenefit: "Show why future Meta contextual reasoning and uncertainty handling matter for accessible care.",
  },
  privacy_denied: {
    title: "Privacy denied · fail closed",
    challenge: "No AI capability is a justification for transmitting unapproved footage.",
    intendedBenefit: "Show that unapproved imagery cannot advance through the Meta evidence gateway.",
  },
  meta_unavailable: {
    title: "Meta unavailable · safe fallback",
    challenge: "Provider or network outages must not silently erase an Edge candidate.",
    intendedBenefit: "Show the planned human follow-up when no authorized Meta assessment is available.",
  },
};

const fake = "IN-MEMORY STORYBOARD ONLY · not a model run";
function step(
  id: DemoStep["id"], title: string, owner: DemoStep["owner"],
  state: DemoStep["state"], detail: string, evidence = fake,
): DemoStep {
  return { id, title, owner, state, detail, evidence };
}
/** No live conditions can be inferred from this deterministic storyboard. */
export function buildJudgeDemo(scenario: ScenarioKey): DemoWalkthrough {
  const descriptor = descriptors[scenario];
  if (!descriptor) throw new Error("Unsupported fictional scenario");
  const noCandidate = scenario === "synthetic_sitting";
  const wheelchair = scenario === "wheelchair_context";
  const privacyDenied = scenario === "privacy_denied";
  const metaUnavailable = scenario === "meta_unavailable";
  const candidate = noCandidate ? null : FALL;
  const candidateExists = !noCandidate;
  const canRequestEvidence = candidateExists && !privacyDenied;
  const steps: DemoStep[] = [
    step("camera", "1 · Authorized input", "Member 1", "simulated",
      wheelchair
        ? "Fictional wheelchair transfer; no actual wheelchair footage or person was processed."
        : "Synthetic pose-trace test input; no connected CCTV, webcam, or video playback.",
      "Only an offline synthetic pose trace is represented."),
    step("edge", "2 · Temporal Edge candidate", "Member 1",
      candidateExists ? "simulated" : "not_triggered",
      candidateExists
        ? wheelchair
          ? "Reusing the canonical synthetic Edge fixture ONLY to illustrate ambiguity; this does not prove the model recognized a wheelchair transfer."
          : "Canonical Python Edge v1 fixture contains an unconfirmed FALL_CANDIDATE. Score is an uncalibrated heuristic, not fall probability."
        : "The canonical synthetic sitting case yields an empty JSONL; that is not a measured true-negative rate.",
      candidateExists && FALL
        ? `Synthetic event ${FALL.event_id}; source-relative offset ${formatSourceOffset(FALL.source_timestamp_ms)}`
        : "0 synthetic candidates in this input"),
    step("privacy", "3 · Privacy / evidence gate", "Member 2",
      !candidateExists ? "not_triggered" : privacyDenied ? "blocked" : "pending",
      !candidateExists ? "No event: evidence review is not requested."
        : privacyDenied ? "POLICY BLOCK: image, keyframes and third-party API calls MUST be denied; do not bypass with model instructions."
          : "Permission would be verified server-side before selecting 2–5 authorized frames. No images are available or transmitted in this storyboard.",
      privacyDenied ? "Cloud image transfer = denied" : "Backend authorization not connected"),
    step("meta", "4 · Meta multimodal reasoning", "Member 2",
      !canRequestEvidence ? "not_triggered" : "blocked",
      !candidateExists ? "No candidate means no Meta call requested."
        : privacyDenied ? "Blocked upstream by privacy rules; no Meta request."
          : metaUnavailable ? "Provider unavailable: a candidate stays unconfirmed and MUST retain a human follow-up route."
            : wheelchair ? "FUTURE: Meta should examine the sequence, wheelchair, bed and posture context; a model is not permitted to infer disability or medical severity."
              : "FUTURE: Meta would interpret consented keyframes, scene sequence and ambiguity, using structured JSON with actual provider provenance.",
      metaUnavailable ? "Simulated provider outage · no real Meta call"
        : "No images, live Meta API key, or genuine provider response"),
    step("policy", "5 · Validated routing", "Member 2",
      !candidateExists ? "not_triggered" : privacyDenied ? "blocked" : "pending",
      !candidateExists ? "Nothing is sent. An empty synthetic input cannot prove no real fall."
        : privacyDenied ? "No Meta call or image transfer. An event may only enter policy-approved local follow-up."
          : "Desired rule: verified informational Meta advisory OR human follow-up for uncertain, invalid or unavailable results. Never auto-confirm fall or dispatch rescue.",
      "No authenticated ingestion, idempotent event store, or caregiver delivery is running"),
    step("caregiver", "6 · Caregiver support", "Member 1",
      candidateExists ? "pending" : "not_triggered",
      candidateExists
        ? "FUTURE: accessible text, high-contrast review and authenticated acknowledgement from Member 2. No actual caregiver was contacted."
        : "No new advisory in this example. A working system still needs alternate ways to request help.",
      "No sent notification, delivery receipt, acknowledgement or emergency call"),
  ];
  return {
    ...descriptor, scenario, steps, candidate,
    expectedHumanOutcome: !candidateExists
      ? "No synthetic candidate; not proof of safety"
      : privacyDenied ? "Block evidence transfer; follow local consent policy"
        : metaUnavailable ? "Follow-up required, even without Meta"
          : wheelchair ? "Request human clarification rather than assume a fall"
            : "Unconfirmed event awaits authorized evidence and human follow-up",
    disclaimer: "SIMULATED END-TO-END STORYBOARD · only Edge fixture validation is executable; privacy, Meta, backend, and caregiver steps are future contracts.",
  };
}
export const JUDGE_SCENARIOS: readonly ScenarioKey[] = [
  "synthetic_fall", "wheelchair_context", "synthetic_sitting",
  "privacy_denied", "meta_unavailable",
];
