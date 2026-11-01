/**
 * Strictly invented torso landmarks for the in-browser research heuristic.
 * Independent of the Python Edge v1 emitter, real MediaPipe inference, and
 * actual cameras. Never export or retain landmarks in UI result objects.
 */
import { LocalFallCandidateHeuristic } from "./localPoseDemo.ts";
import type { LocalPoseLandmark, PoseObservation } from "./localPoseDemo.ts";

export const SYNTHETIC_POSE_SCENARIOS = [
  "fall_motion", "sitting", "horizontal_first", "tracking_lost", "multiple_people",
] as const;
export type SyntheticPoseScenario = typeof SYNTHETIC_POSE_SCENARIOS[number];

export const SYNTHETIC_POSE_LABELS: Record<SyntheticPoseScenario, string> = {
  fall_motion: "Upright → descending horizontal",
  sitting: "Sitting · no candidate",
  horizontal_first: "Horizontal without prior upright",
  tracking_lost: "Pose lost mid-transition",
  multiple_people: "Two poses during transition",
};

export type SyntheticPoseStep = Readonly<{
  sourceMs: number;
  input: "upright" | "horizontal" | "sitting" | "lost" | "two_people";
  result: PoseObservation["status"];
  angleDeg: number | null;
  hipY: number | null;
  emittedCandidate: boolean;
}>;

export type SyntheticPoseReplay = Readonly<{
  scenario: SyntheticPoseScenario;
  synthetic: true;
  usesRealCamera: false;
  usesMediaPipeModel: false;
  backendRequests: 0;
  verifiedFalls: 0;
  candidateCount: number;
  steps: ReadonlyArray<SyntheticPoseStep>;
}>;

type TraceInput = SyntheticPoseStep["input"];

function oneBody(posture: "upright" | "horizontal" | "sitting"): LocalPoseLandmark[] {
  const points: LocalPoseLandmark[] = Array.from({ length: 33 }, () =>
    ({ x: 0.5, y: 0.5, visibility: 0.99, presence: 0.99 }));
  const horizontal = posture === "horizontal";
  const hipY = horizontal || posture === "sitting" ? 0.82 : 0.64;
  const shoulderY = horizontal ? 0.82 : posture === "sitting" ? 0.45 : 0.24;
  points[11] = { x: horizontal ? 0.2 : 0.45, y: shoulderY, visibility: 0.99, presence: 0.99 };
  points[12] = { x: horizontal ? 0.3 : 0.55, y: shoulderY, visibility: 0.99, presence: 0.99 };
  points[23] = { x: horizontal ? 0.7 : 0.45, y: hipY, visibility: 0.99, presence: 0.99 };
  points[24] = { x: horizontal ? 0.8 : 0.55, y: hipY, visibility: 0.99, presence: 0.99 };
  return points;
}

function inputToPoses(input: TraceInput): ReadonlyArray<ReadonlyArray<LocalPoseLandmark>> {
  if (input === "lost") return [];
  if (input === "two_people") return [oneBody("horizontal"), oneBody("horizontal")];
  return [oneBody(input)];
}

function traceFor(scenario: SyntheticPoseScenario): readonly TraceInput[] {
  switch (scenario) {
    case "fall_motion":
      return ["upright", "upright", "horizontal", "horizontal", "horizontal",
        "horizontal", "horizontal"];
    case "sitting":
      return ["sitting", "sitting", "sitting", "sitting", "sitting", "sitting", "sitting"];
    case "horizontal_first":
      return ["horizontal", "horizontal", "horizontal", "horizontal",
        "horizontal", "horizontal", "horizontal"];
    case "tracking_lost":
      return ["upright", "horizontal", "lost", "horizontal", "horizontal",
        "horizontal", "horizontal"];
    case "multiple_people":
      return ["upright", "horizontal", "two_people", "horizontal",
        "horizontal", "horizontal", "horizontal"];
  }
}

export function runSyntheticPoseReplay(scenario: SyntheticPoseScenario): SyntheticPoseReplay {
  if (!SYNTHETIC_POSE_SCENARIOS.includes(scenario)) {
    throw new Error("Unknown synthetic pose scenario");
  }
  const heuristic = new LocalFallCandidateHeuristic();
  const steps: SyntheticPoseStep[] = traceFor(scenario).map((input, index) => {
    const observation = heuristic.observe(inputToPoses(input), index * 200);
    return Object.freeze({
      sourceMs: index * 200,
      input,
      result: observation.status,
      angleDeg: observation.angleDeg,
      hipY: observation.hipY,
      emittedCandidate: observation.candidate,
    });
  });
  return Object.freeze({
    scenario,
    synthetic: true,
    usesRealCamera: false,
    usesMediaPipeModel: false,
    backendRequests: 0,
    verifiedFalls: 0,
    candidateCount: heuristic.count,
    steps: Object.freeze(steps),
  });
}
