import { useCallback, useEffect, useState } from "react";
import { deriveReviewPresentation } from "./metaReview";
import EdgeTestLab from "./EdgeTestLab";
import IntegrationCenter from "./IntegrationCenter";
import {
  allowLocalDemo, listLocalDemoIncidents, createLocalDemoIncident,
  reviewLocalDemoIncident,
} from "./incidentDemo";
import type { DemoAction, DemoIncident } from "./incidentDemo";

// Demo incident endpoints have NO authentication in Member 2's foundation.
// Never contact them unless explicitly opted in on loopback.
const LOCAL_DEMO_WRITES = allowLocalDemo(
  window.location.hostname, import.meta.env.VITE_ENABLE_LOCAL_DEMO_MUTATIONS === "true",
);

const actionOptions: Record<string, Array<[string, string]>> = {
  NOTIFIED: [["Acknowledge", "ACKNOWLEDGE"]],
  ACKNOWLEDGED: [["Verify incident", "VERIFY"], ["Mark false alert", "MARK_FALSE_ALERT"]],
  VERIFIED: [["Resolve", "RESOLVE"]],
  FALSE_ALERT: [["Resolve", "RESOLVE"]],
};

function displayTime(s: string) {
  return new Date(s).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

export default function App() {
  const [view, setView] = useState<"lab" | "integrations" | "operations">("integrations");
  const [incidents, setIncidents] = useState<DemoIncident[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState("Demo Caregiver");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [online, setOnline] = useState(false);
  const selectedIncident = incidents.find((incident) => incident.id === selected) ?? incidents[0];
  const metaReview = selectedIncident ? deriveReviewPresentation(selectedIncident) : null;

  const refresh = useCallback(async (signal?: AbortSignal) => {
    if (!LOCAL_DEMO_WRITES) return;
    try {
      const data = await listLocalDemoIncidents(signal);
      if (signal?.aborted) return;
      setIncidents(data);
      setOnline(true); // local demo endpoint reachable, NOT verified authentication
      setError(null);
    } catch (e) {
      if (signal?.aborted) return;
      // Never keep old "online" demo incidents after an API/auth/validation failure.
      setIncidents([]);
      setSelected(null);
      setOnline(false);
      setError(e instanceof Error ? e.message : "Local demo API unavailable");
    }
  }, []);

  useEffect(() => {
    // Offline lab and Integration Center must not fetch demo incident records.
    if (view !== "operations" || !LOCAL_DEMO_WRITES) return;
    const controller = new AbortController();
    let pending = false;
    const poll = () => {
      if (document.visibilityState !== "visible") {
        setIncidents([]);
        setSelected(null);
        setOnline(false);
        return;
      }
      if (pending) return;
      pending = true;
      void refresh(controller.signal).finally(() => { pending = false; });
    };
    poll();
    const timer = window.setInterval(poll, 5000);
    document.addEventListener("visibilitychange", poll);
    return () => {
      controller.abort();
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", poll);
      setIncidents([]);
      setSelected(null);
      setOnline(false);
    };
  }, [refresh, view]);

  async function run<T>(task: () => Promise<T>) {
    setBusy(true);
    setError(null);
    try {
      await task();
      await refresh();
    } catch (e) {
      // Do not retain a seemingly actionable incident after a failed write.
      setIncidents([]);
      setSelected(null);
      setOnline(false);
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  function createDemo() {
    if (!LOCAL_DEMO_WRITES || !online) return;
    void run(async () => {
      const incident = await createLocalDemoIncident();
      setSelected(incident.id);
    });
  }

  function update(action: DemoAction, id: string) {
    if (!LOCAL_DEMO_WRITES || !online) return;
    void run(() => reviewLocalDemoIncident(id, action, reviewer));
  }

  const active = incidents.filter((i) => !["RESOLVED", "FALSE_ALERT"].includes(i.status)).length;
  const resolved = incidents.filter((i) => i.status === "RESOLVED").length;
  const stagedFeedCount = incidents.filter((i) => i.simulated && i.notification_sent).length;

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span className="brand-mark">V</span><div><strong>VIIL SENTINEL</strong><small>INCIDENT INTELLIGENCE</small></div></div>
        <div className="nav-label">WORKSPACE</div>
        <button type="button" className={view === "integrations" ? "nav-active" : "nav-muted"} onClick={() => setView("integrations")} aria-current={view === "integrations" ? "page" : undefined}>▦ <span>Integration center</span></button>
        <button type="button" className={view === "lab" ? "nav-active" : "nav-muted"} onClick={() => setView("lab")} aria-current={view === "lab" ? "page" : undefined}>◎ <span>AI Detect Test Lab</span></button>
        <button type="button" className={view === "operations" ? "nav-active" : "nav-muted"} onClick={() => setView("operations")} aria-current={view === "operations" ? "page" : undefined}>◈ <span>Incident operations (demo)</span></button>
        <div className="nav-muted">◇ <span>Meta / camera links · backend-owned</span></div>
        <div className="side-bottom"><strong>HACKATHON FOUNDATION</strong><p>Local development environment — not connected to live cameras or rescue services.</p></div>
      </aside>
      <main className="main">
        <header className="topbar"><div className="eyebrow">MEMBER 1 / {view === "lab" ? "AI DETECT TEST LAB" : view === "integrations" ? "INTEGRATION CENTER" : "INCIDENT OPERATIONS"}</div>{view === "lab" ? <span className="connection ok">● Browser-local · no API</span> : view === "integrations" ? <span className="connection">● Read-only connection status</span> : <span className={online ? "connection ok" : "connection"}>● {!LOCAL_DEMO_WRITES ? "Local demo API disabled" : online ? "Local demo API reachable · no auth" : "Local demo API offline"}</span>}</header>
        {view === "lab" ? <EdgeTestLab /> : view === "integrations" ? <IntegrationCenter /> : <>
        <div className="hero"><div><div className="eyebrow blue">OPERATIONAL OVERVIEW</div><h1>Incident intelligence</h1><p>Meta-first visual verification is planned. Current events are MOCK; caregiver review and response tracking remain manual in this demo.</p></div><button className="primary" onClick={createDemo} disabled={!LOCAL_DEMO_WRITES || busy || !online}>+ Generate staged incident</button></div>
        <div className="warning"><span>SIMULATION ONLY</span> This foundation uses mock incident interpretation. It does not detect a real fall, query Meta AI, provide medical advice, or contact emergency services. {LOCAL_DEMO_WRITES ? "Local-only demo read/write actions explicitly enabled (NOT authenticated)." : "Unauthenticated demo API reads and writes are disabled by default. Developers can opt in only on localhost with VITE_ENABLE_LOCAL_DEMO_MUTATIONS=true. This is not backend authorization."}</div>
        {error && <div className="error" role="alert">Connection / action error: {error}</div>}
        <section className="stats">
          <div className="stat"><small>INCIDENTS LOGGED</small><strong>{incidents.length}</strong><span>Staged development events</span></div>
          <div className="stat"><small>ACTIVE / OPEN</small><strong>{active}</strong><span>Awaiting closure</span></div>
          <div className="stat"><small>RESOLVED</small><strong>{resolved}</strong><span>Human-reviewed workflows</span></div>
          <div className="stat"><small>MODEL PROVIDER</small><strong className="provider">MOCK</strong><span>Muse Spark integration pending</span></div>
        </section>
        <section className="pipeline-readiness" aria-label="Member 1 integration readiness">
          <div className="pipeline-step"><small>01 · MEMBER 1</small><strong>EDGE CANDIDATE</strong><span>Contract ready · offline handoff only</span></div>
          <div className="pipeline-step"><small>02 · MEMBER 2</small><strong>META VERIFICATION</strong><span>Pending live authorized integration</span></div>
          <div className="pipeline-step"><small>03 · MEMBER 1</small><strong>CAREGIVER DASHBOARD</strong><span>Demo feed: {stagedFeedCount} · no push delivery</span></div>
        </section>
        <div className="content">
          <section className="panel incident-list">
            <div className="panel-head"><h2>Incident feed</h2><span>{incidents.length} events</span></div>
            {incidents.length === 0 ? <div className="empty"><div className="empty-icon">◉</div><strong>{LOCAL_DEMO_WRITES ? "No staged incidents yet" : "Local demo access disabled"}</strong><p>{LOCAL_DEMO_WRITES ? "Generate a simulated incident to test the notification and review state machine." : "Incident data is deliberately not fetched until the local-only developer opt-in is enabled. The authenticated Member 2 incident API is not yet integrated."}</p></div> :
              incidents.map((item) => <button key={item.id} className={"incident-item " + (selectedIncident?.id === item.id ? "is-selected" : "")} onClick={() => setSelected(item.id)}>
                <div><strong>{item.source_id}</strong><small>{displayTime(item.created_at)}</small></div>
                <span className={"status " + item.status.toLowerCase()}>{item.status.replaceAll("_", " ")}</span>
              </button>)}
          </section>
          <section className="panel details">
            <div className="panel-head"><h2>Incident inspection</h2><span>META-FIRST PROPOSED · MOCK NOW</span></div>
            {!selectedIncident ? <div className="empty"><div className="empty-icon">◎</div><strong>Select an incident</strong><p>Evidence, uncertainty, state transitions, and reviewer controls will appear here.</p></div> :
              <div className="inspection">
                <div className="inspection-row"><div><small>EVENT ID</small><code>{selectedIncident.id.slice(0, 12)}…</code></div><span className="pill">STAGED EVENT</span></div>
                <div className="inspection-row"><div><small>DEMO DETECTOR SCORE · NOT A FALL PROBABILITY</small><strong>{Math.round(selectedIncident.confidence * 100)}% (simulated)</strong></div><div><small>STATUS</small><strong>{selectedIncident.status}</strong></div></div>
                <div className="evidence"><span className="evidence-badge">NO REAL VIDEO INPUT</span><div className="evidence-symbol">⌁</div><p>Authorized keyframes not connected. Raw video or pose is never displayed in this demo.</p></div>
                <div className="section-label">META-FIRST ASSESSMENT</div>
                <div className={"meta-assessment " + (metaReview?.stage ?? "pending")} role="status" aria-live="polite">
                  <strong>{metaReview?.label ?? "META VERIFICATION · PENDING"}</strong>
                  <p>{metaReview?.explanation ?? "No incident selected."}</p>
                  <small>Display status only · no confirmed fall, automatic emergency action, or real notification</small>
                </div>
                <div className="section-label">INTERPRETATION</div>
                <p className="observation">{selectedIncident.observation?.posture ?? "No report available"}</p>
                <div className="uncertainty"><strong>Uncertainty & limits</strong>{selectedIncident.observation?.uncertainty.map((line, index) => <p key={index}>• {line}</p>)}</div>
                <div className="section-label">CAREGIVER REVIEW / ACKNOWLEDGEMENT (DEMO)</div>
                <label htmlFor="reviewer" className="reviewer-label">Reviewer name</label>
                <input id="reviewer" value={reviewer} maxLength={80} onChange={(event) => setReviewer(event.target.value)} />
                <div className="actions">{(actionOptions[selectedIncident.status] ?? []).map(([label, action]) => <button key={action} disabled={!LOCAL_DEMO_WRITES || !online || busy || !reviewer.trim()} onClick={() => update(action as DemoAction, selectedIncident.id)}>{label}</button>)}</div>
                <div className="section-label">LOCAL DEMO AUDIT TRAIL</div>
                <div className="audit">{selectedIncident.history.slice().reverse().map((entry, index) => <div className="audit-item" key={index}><span className="audit-dot" /><div><strong>{entry.to_status.replaceAll("_", " ")}</strong><small>{entry.actor} · {displayTime(entry.time)}</small></div></div>)}</div>
              </div>}
          </section>
        </div>
        </>}
        <footer>VIIL Sentinel · Meta Global AI Developer Hackathon 2026 · Non-clinical research demonstration</footer>
      </main>
    </div>
  );
}
