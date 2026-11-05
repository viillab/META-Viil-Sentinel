import { useState } from "react";
import SyntheticPoseTraceLab from "./SyntheticPoseTraceLab";
import syntheticCandidate from "./fixtures/edgeCandidateSynthetic.json" with { type: "json" };
import {
  formatSourceOffset, MAX_LOCAL_CANDIDATE_BYTES, parseEdgeCandidateJsonl,
} from "./edgeLab";
import type { EdgeCandidateV1, LocalReplay } from "./edgeLab";

/**
 * MEMBER 1 only. Replays Python Edge metadata and separately exercises a
 * synthetic browser-only torso heuristic. Neither path loads real media or
 * MediaPipe; no API requests, notifications, storage or emergency response.
 */
export default function EdgeTestLab() {
  const [replay, setReplay] = useState<LocalReplay | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function useSample() {
    try {
      setReplay(parseEdgeCandidateJsonl(JSON.stringify(syntheticCandidate), "Synthetic Fall candidate · fixture"));
      setSelectedIndex(0);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Sample load failed");
    }
  }

  function useNonfall() {
    setReplay(parseEdgeCandidateJsonl("", "Synthetic Sitting · no candidate"));
    setSelectedIndex(0);
    setError(null);
  }

  function reset() {
    setReplay(null);
    setError(null);
    setSelectedIndex(0);
  }

  async function loadLocalFile(file: File | undefined) {
    if (!file) return;
    setBusy(true);
    setError(null);
    // If validation fails, clear previous results to prevent stale claims.
    setReplay(null);
    setSelectedIndex(0);
    try {
      if (file.size > MAX_LOCAL_CANDIDATE_BYTES) {
        throw new Error("Only metadata-only JSONL files up to 256 KiB are accepted.");
      }
      if (!/\.(jsonl|json)$/i.test(file.name)) {
        throw new Error("Select the local Edge .jsonl or .json metadata output, not a video.");
      }
      const loaded = parseEdgeCandidateJsonl(await file.text(), file.name);
      setReplay(loaded);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "File validation failed");
    } finally {
      setBusy(false);
    }
  }

  const selected: EdgeCandidateV1 | undefined = replay?.events[selectedIndex];

  return (
    <div className="lab-page">
      <div className="lab-hero">
        <div>
          <div className="eyebrow blue">MEMBER 1 · PHASE 1 / EDGE AI TEST LAB</div>
          <h1>Fall candidate lab</h1>
          <p>Inspect Python Edge metadata and test a separate synthetic Pose heuristic locally. No upload, API, or automatic alert.</p>
        </div>
        <div className="lab-mode">OFFLINE METADATA REPLAY</div>
      </div>
      <div className="warning" role="note">
        <span>RESEARCH / DEMO ONLY</span>
        These events are <strong>uncalibrated candidates</strong>, not verified falls.
        Score 0–1 is not a fall probability. This viewer cannot measure accuracy, latency or FPS.
      </div>
      <section className="lab-input panel" aria-label="Local candidate replay controls">
        <div className="panel-head"><h2>01 / Select test input</h2><span>LOCAL BROWSER MEMORY ONLY</span></div>
        <div className="lab-input-content">
          <div className="lab-actions">
            <button type="button" className="lab-button-primary" onClick={useSample} disabled={busy}>
              Load synthetic fall
            </button>
            <button type="button" className="lab-button" onClick={useNonfall} disabled={busy}>
              Load synthetic sitting (no candidate)
            </button>
            <button type="button" className="lab-button" onClick={reset} disabled={busy}>
              Clear
            </button>
          </div>
          <div className="lab-file-picker">
            <label htmlFor="local-edge-jsonl"><strong>Open Edge candidate JSONL</strong><span>Generated with the Python Edge handoff CLI; max 256 KiB / 100 candidates. Files are not uploaded.</span></label>
            <input id="local-edge-jsonl" type="file" accept=".jsonl,.json,application/json,text/plain"
              disabled={busy} onChange={(event) => {
                const file = event.target.files?.[0];
                void loadLocalFile(file);
                event.currentTarget.value = "";
              }} />
          </div>
          {error && <div className="error" role="alert">{error}</div>}
        </div>
      </section>
      <section className="lab-stats" aria-label="Metadata replay summary">
        <div className="stat"><small>CANDIDATES</small><strong>{replay?.events.length ?? "—"}</strong><span>Observed v1 metadata events</span></div>
        <div className="stat"><small>SOURCES</small><strong>{replay?.sourceIds.length ?? "—"}</strong><span>Declared pseudonymous source IDs</span></div>
        <div className="stat"><small>MODEL VALIDATION</small><strong className="lab-not-validated">NOT PROVEN</strong><span>No real ground-truth labels loaded</span></div>
        <div className="stat"><small>META / BACKEND</small><strong className="lab-not-validated">OFF</strong><span>Zero external incident dispatch</span></div>
      </section>
      <div className="lab-results">
        <section className="panel">
          <div className="panel-head"><h2>02 / Candidate replay</h2><span>{replay?.displayLabel ?? "NO FILE LOADED"}</span></div>
          {!replay
            ? <div className="empty"><div className="empty-icon">◎</div><strong>Choose a synthetic fixture or local JSONL</strong><p>First run the Edge detector in Python, then load its metadata-only stdout here.</p></div>
            : replay.expectedNegative
              ? <div className="empty"><div className="empty-icon">✓</div><strong>No candidates in this input</strong><p>This is an empty replay, not proof of a true negative or recall.</p></div>
              : <div className="lab-candidate-list">
                {replay.events.map((event, index) =>
                  <button type="button" key={event.event_id} className={"lab-candidate " + (selectedIndex === index ? "is-selected" : "")}
                    onClick={() => setSelectedIndex(index)}>
                    <div><strong>Candidate {index + 1} <span className="lab-unverified">UNCONFIRMED</span></strong>
                      <small>{event.source_id} · {formatSourceOffset(event.source_timestamp_ms)}</small></div>
                    <span className="lab-score">{event.detector_score.toFixed(3)}</span>
                  </button>,
                )}
              </div>}
        </section>
        <section className="panel">
          <div className="panel-head"><h2>03 / Detection details</h2><span>SAFE METADATA ONLY</span></div>
          {!selected ? <div className="empty"><div className="empty-icon">⌁</div><strong>No candidate selected</strong><p>No raw frames, landmarks or private recordings are loaded in this lab.</p></div> :
            <div className="lab-detail">
              <div className="lab-detail-row"><small>LOCAL SOURCE TIME</small><strong>{formatSourceOffset(selected.source_timestamp_ms)}</strong></div>
              <div className="lab-detail-row"><small>DETECTOR</small><strong>{selected.detector}</strong></div>
              <div className="lab-detail-row"><small>PROVENANCE (SELF-DECLARED)</small><strong>{selected.input_provenance.replaceAll("_", " ")}</strong></div>
              <div className="lab-detail-row"><small>SYNTHETIC</small><strong>{selected.simulated ? "YES · GENERATED TRACE" : "NO · UNVERIFIED REAL SOURCE"}</strong></div>
              <div className="lab-score-meter" aria-label="Uncalibrated heuristic score"><div className="lab-meter-head"><small>UNCALIBRATED DETECTOR SCORE</small><strong>{selected.detector_score.toFixed(3)} / 1</strong></div>
                <div className="lab-meter-track"><div className="lab-meter-bar" style={{ width: `${selected.detector_score * 100}%` }} /></div>
                <p>Not confidence calibration, a diagnosis, or a verified fall probability.</p>
              </div>
              <div className="lab-info">Event ID <code>{selected.event_id}</code></div>
              <div className="lab-info">Model digest <code>{selected.model_sha256 ?? "not declared"}</code></div>
              <div className="lab-restriction">Fall confirmed: NO · Medical assessment: NO · Network delivery: NO</div>
            </div>}
        </section>
      </div>
      <SyntheticPoseTraceLab />
      <div className="lab-footer-note">
        <strong>Next test:</strong> run <code>python -m sentinel_edge.handoff_cli</code> with the synthetic traces and
        redirect stdout to a local <code>.jsonl</code> file. Load it here to inspect the
        real Edge emitter output. Do not upload video or patient data. Backend/Meta integration belongs to Member 2.
      </div>
    </div>
  );
}
