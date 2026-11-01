import { useState } from "react";
import {
  runSyntheticPoseReplay, SYNTHETIC_POSE_LABELS, SYNTHETIC_POSE_SCENARIOS,
} from "./syntheticPoseTrace";
import type { SyntheticPoseReplay, SyntheticPoseScenario } from "./syntheticPoseTrace";

/**
 * Synthetic landmarks go through the very same browser-local heuristic as
 * LaptopWebcamDemo. This is NOT MediaPipe detection, Python Edge v1, a real
 * fall, incident creation or backend/Meta/caregiver delivery.
 */
export default function SyntheticPoseTraceLab() {
  const [replay, setReplay] = useState<SyntheticPoseReplay | null>(null);
  const [selectedStep, setSelectedStep] = useState(0);

  function run(scenario: SyntheticPoseScenario) {
    const next = runSyntheticPoseReplay(scenario);
    setReplay(next);
    setSelectedStep(next.steps.length - 1);
  }
  const step = replay?.steps[selectedStep];
  const emittedThroughStep = replay
    ? replay.steps.slice(0, selectedStep + 1).filter(s => s.emittedCandidate).length
    : 0;

  return <section className="panel synthetic-pose-lab"
    aria-label="Synthetic browser Pose heuristic trace">
    <div className="panel-head">
      <h2>04 / Browser heuristic · synthetic Pose trace</h2>
      <span>GENERATED LANDMARKS · NO CAMERA / NO AI MODEL</span>
    </div>
    <div className="synthetic-pose-body">
      <p className="synthetic-pose-disclaimer" role="note">
        <strong>SIMULATION ONLY — NO REAL FALL OR LIVE INFERENCE.</strong>
        {" "}Seven invented posture samples are evaluated by the same
        LocalFallCandidateHeuristic as Laptop Webcam Demo. The Python Edge
        candidate fixture above is a separate pipeline. Nothing is sent to
        a backend, Meta AI, caregiver, or emergency service.
      </p>
      <div className="lab-actions" role="group"
        aria-label="Choose synthetic Pose motion scenario">
        {SYNTHETIC_POSE_SCENARIOS.map(scenario =>
          <button type="button" className={replay?.scenario === scenario
            ? "lab-button-primary" : "lab-button"} key={scenario}
            aria-pressed={replay?.scenario === scenario}
            onClick={() => run(scenario)}>
            {scenario === "fall_motion" ? "Run synthetic fall trace"
              : scenario === "sitting" ? "Run synthetic sitting trace"
                : scenario === "horizontal_first" ? "Run no-baseline trace"
                  : scenario === "tracking_lost" ? "Run lost-pose trace"
                    : "Run multi-person trace"}
          </button>)}
        <button type="button" className="lab-button"
          onClick={() => { setReplay(null); setSelectedStep(0); }}>
          Clear synthetic trace
        </button>
      </div>
      {!replay ? <p className="synthetic-pose-empty">
        Select a generated scenario to inspect the actual browser heuristic.
        This exercise is independent of the camera and does not create
        real events.
      </p> : <div className="synthetic-pose-results">
        <div role="status" aria-live="polite"
          className="synthetic-pose-result" aria-label="Synthetic heuristic result">
          <strong>{SYNTHETIC_POSE_LABELS[replay.scenario]}</strong>
          <span>Synthetic possible-fall candidates: {emittedThroughStep}
            {" "}· Confirmed falls: {replay.verifiedFalls}
            {" "}· Backend / Meta / alerts: OFF</span>
          <span>{emittedThroughStep > 0
            ? "UNCONFIRMED CANDIDATE · HUMAN REVIEW REQUIRED"
            : "NO CANDIDATE IN THIS GENERATED TRACE · NOT PROOF OF ACCURACY"}</span>
        </div>
        <div className="synthetic-pose-steps" role="group"
          aria-label="Select synthetic pose trace frame">
          {replay.steps.map((s, i) => <button type="button"
            key={s.sourceMs} aria-pressed={i === selectedStep}
            className={i === selectedStep ? "selected" : ""}
            onClick={() => setSelectedStep(i)}>
            <strong>{s.sourceMs} ms</strong>
            <small>{s.emittedCandidate ? "CANDIDATE" : s.result.toUpperCase()}</small>
          </button>)}
        </div>
        {step && <div className="synthetic-pose-inspect"
          aria-label="Selected synthetic pose step">
          <div><small>GENERATED INPUT</small><strong>{step.input.replaceAll("_", " ")}</strong></div>
          <div><small>ACTUAL HEURISTIC STATE</small><strong>{step.result.toUpperCase()}</strong></div>
          <div><small>TORSO ANGLE</small><strong>{step.angleDeg === null
            ? "Unknown" : `${step.angleDeg.toFixed(1)}°`}</strong></div>
          <div><small>HIP Y (NORMALIZED)</small><strong>{step.hipY === null
            ? "Unknown" : step.hipY.toFixed(2)}</strong></div>
          <div><small>EMITTED HERE</small><strong>{step.emittedCandidate
            ? "1 UNCONFIRMED CANDIDATE" : "NO CANDIDATE"}</strong></div>
        </div>}
        <p className="synthetic-pose-foot">
          Only derived numerical states are displayed. No photo, video,
          identity, network calls, Pose model load, incident creation or
          confirmed-fall claim. Any detection-quality estimate requires
          independently labeled real-world test data.
        </p>
      </div>}
    </div>
  </section>;
}
