import { useMemo, useState } from "react";
import { buildJudgeDemo, JUDGE_SCENARIOS } from "./judgeDemo";
import type { ScenarioKey, DemoStep } from "./judgeDemo";

const stepCopy: Record<DemoStep["state"], string> = {
  simulated: "SIMULATED",
  blocked: "BLOCKED / NOT RUN",
  pending: "FUTURE CONTRACT",
  not_triggered: "NOT TRIGGERED",
};
const names: Record<ScenarioKey, string> = {
  synthetic_fall: "01 · Fall-like motion",
  wheelchair_context: "02 · Wheelchair transfer",
  synthetic_sitting: "03 · Normal sitting",
  privacy_denied: "04 · Privacy blocks Meta",
  meta_unavailable: "05 · Meta API outage",
};
export default function JudgeDemoView() {
  const [scenario, setScenario] = useState<ScenarioKey>("synthetic_fall");
  const [activeIndex, setActiveIndex] = useState(0);
  const current = useMemo(() => buildJudgeDemo(scenario), [scenario]);
  const selected = current.steps[activeIndex];
  const next = () => setActiveIndex(idx => Math.min(idx + 1, current.steps.length - 1));
  const previous = () => setActiveIndex(idx => Math.max(0, idx - 1));

  return <section className="judge-page" aria-labelledby="judge-title">
    <div className="judge-heading">
      <div>
        <div className="eyebrow blue">VIIL SENTINEL · MEMBER 1 / JUDGE WALKTHROUGH</div>
        <h1 id="judge-title">The journey from detection to care</h1>
        <p>A reproducible, privacy-safe walkthrough of how the Edge signal could
          become a Meta-assisted caregiver experience.</p>
      </div>
      <span className="judge-offline">100% OFFLINE STORYBOARD</span>
    </div>
    <div className="judge-important" role="note">
      <strong>SIMULATION — NOT LIVE META, CAMERA OR NOTIFICATIONS</strong>
      <p>{current.disclaimer} The actual synthetic Edge candidate is parsed from
        the canonical fixture; later stages are illustrations, not successful API calls.</p>
    </div>

    <div className="judge-layout">
      <section className="judge-scenario" aria-labelledby="judge-scenarios-title">
        <h2 id="judge-scenarios-title">1. Choose a story</h2>
        <p className="judge-muted">Try failures as well as success-path expectations.</p>
        <div className="judge-tabs" role="group" aria-label="Choose an offline demo scenario">
          {JUDGE_SCENARIOS.map(id => <button key={id} type="button"
            aria-pressed={id === scenario} className={id === scenario ? "selected" : ""}
            onClick={() => { setScenario(id); setActiveIndex(0); }}>
            {names[id]}
          </button>)}
        </div>
        <div className="judge-case">
          <strong>{current.title}</strong>
          <p>{current.challenge}</p>
          <div><small>ASSISTIVE VALUE</small><p>{current.intendedBenefit}</p></div>
        </div>
        <div className="judge-facts">
          <div><small>EDGE OUTPUT</small><strong>{current.candidate ? "1 FIXTURE EVENT" : "0 EVENTS"}</strong></div>
          <div><small>MODEL CONFIDENCE</small><strong>NOT CALIBRATED</strong></div>
          <div><small>META API CALLS</small><strong>0 · NONE</strong></div>
          <div><small>REAL ALERTS SENT</small><strong>0 · NONE</strong></div>
        </div>
      </section>

      <section className="judge-walkthrough" aria-labelledby="judge-engine-title">
        <div className="judge-section-title">
          <div>
            <h2 id="judge-engine-title">2. Walk through the core engine</h2>
            <p className="judge-muted">Select any stage or use Previous / Next.</p>
          </div>
          <span>{activeIndex + 1} / {current.steps.length}</span>
        </div>
        <div className="judge-stage-list" aria-label="Core engine stages">
          {current.steps.map((step, index) => <button key={step.id}
            type="button" onClick={() => setActiveIndex(index)}
            aria-current={index === activeIndex ? "step" : undefined}
            className={"judge-stage" + (index === activeIndex ? " current" : "")}>
            <span className="judge-stage-index">{index + 1}</span>
            <span className="judge-stage-name">{step.title}<small>{step.owner}</small></span>
            <span className={"judge-stage-state " + step.state}>{stepCopy[step.state]}</span>
          </button>)}
        </div>
        <div className="judge-focus" aria-live="polite" aria-atomic="true">
          <div className="judge-focus-top">
            <span>SELECTED ENGINE STAGE</span>
            <strong>{stepCopy[selected.state]}</strong>
          </div>
          <h3>{selected.title}</h3>
          <p>{selected.detail}</p>
          <div className="judge-evidence">
            <small>WHAT WE CAN ACTUALLY SHOW</small>
            <p>{selected.evidence}</p>
          </div>
        </div>
        <div className="judge-navigation">
          <button type="button" onClick={previous} disabled={activeIndex === 0}>Previous stage</button>
          <button type="button" onClick={next} disabled={activeIndex === current.steps.length - 1}>Next stage</button>
        </div>
      </section>
    </div>

    <div className="judge-takeaway">
      <div><small>EXPECTED HUMAN-CENTERED OUTCOME</small><strong>{current.expectedHumanOutcome}</strong></div>
      <div className="judge-explain">
        <strong>Why Meta matters:</strong> The proposed multimodal role is to reason over
        authorized scene evidence and its uncertainty — especially ambiguous
        actions such as transferring from a wheelchair. Edge stays on-device
        for continuous screening. The backend must prove privacy, model
        provenance and delivery before any real caregiver advisory.
      </div>
    </div>
    <p className="judge-bottom">
      <strong>To show actual executable evidence:</strong> open AI Detect Test Lab and
      load its canonical Edge synthetic fall and empty sitting samples.
      To test a physical camera, use the privacy-approved Edge Python runner.
      For real Meta inference and authenticated caregiver messages, Member 2
      must complete the backend integration. This demo deliberately makes no
      clinical or emergency guarantees.
    </p>
  </section>;
}
