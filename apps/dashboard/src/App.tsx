import { useCallback, useEffect, useState } from "react";
import { deriveReviewPresentation } from "./metaReview";
import EdgeTestLab from "./EdgeTestLab";
import IntegrationCenter from "./IntegrationCenter";

const API = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
// Demo API writes are unauthenticated in Member 2's current local foundation.
// They must never be enabled by default or on non-loopback browser origins.
const LOCAL_DEMO_WRITES = import.meta.env.VITE_ENABLE_LOCAL_DEMO_MUTATIONS === "true"
  && ["localhost", "127.0.0.1"].includes(window.location.hostname);

type Status =
  | "DETECTED" | "ANALYZING" | "REVIEW_REQUIRED" | "NOTIFIED"
  | "ACKNOWLEDGED" | "VERIFIED" | "FALSE_ALERT" | "RESOLVED";

type Incident = {
  id: string;
  source_id: string;
  status: Status;
  confidence: number;
  simulated: boolean;
  notification_sent: boolean;
  /** Future optional DTO: only Member 2 authorized backend may populate. */
  meta_review_v1?: unknown;
  created_at: string;
  observation: {
    posture: string;
    surroundings: string;
    uncertainty: string[];
    evidence_refs: string[];
    generated_by: string;
  } | null;
  history: { time: string; actor: string; from_status: string | null; to_status: string }[];
};

const actionOptions: Record<string, Array<[string, string]>> = {
  NOTIFIED: [["Acknowledge", "ACKNOWLEDGE"]],
  ACKNOWLEDGED: [["Verify incident", "VERIFY"], ["Mark false alert", "MARK_FALSE_ALERT"]],
  VERIFIED: [["Resolve", "RESOLVE"]],
  FALSE_ALERT: [["Resolve", "RESOLVE"]],
};

function displayTime(s: string) {
  return new Date(s).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" });
}

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options);
  if (!response.ok) {
    let message = `HTTP ${response.status}`;
    try {
      const parsed = await response.json();
      if (typeof parsed.detail === "string") message = parsed.detail;
    } catch { /* Keep status message for non-JSON errors */ }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export default function App() {
  const [view, setView] = useState<"lab" | "integrations" | "operations">("integrations");
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [reviewer, setReviewer] = useState("Demo Caregiver");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [online, setOnline] = useState(false);
  const selectedIncident = incidents.find((incident) => incident.id === selected) ?? incidents[0];
  const metaReview = selectedIncident ? deriveReviewPresentation(selectedIncident) : null;

  const refresh = useCallback(async () => {
    try {
      const data = await fetchJson<Incident[]>(`${API}/api/v1/incidents`);
      setIncidents(data);
      setOnline(true);
      setError(null);
    } catch (e) {
      setOnline(false);
      setError(e instanceof Error ? e.message : "Unable to connect to API");
    }
  }, []);

  useEffect(() => {
    // The offline lab never contacts or polls Member 2 backend.
    if (view !== "operations") return;
    void refresh();
    const timer = window.setInterval(() => void refresh(), 5000);
    return () => window.clearInterval(timer);
  }, [refresh, view]);

  async function run<T>(task: () => Promise<T>) {
    setBusy(true);
    setError(null);
    try {
      await task();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }

  function createDemo() {
    if (!LOCAL_DEMO_WRITES) return;
    void run(async () => {
      const incident = await fetchJson<Incident>(`${API}/api/v1/incidents/demo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source_id: "STAGED-CAMERA-01", confidence: 0.82 }),
      });
      setSelected(incident.id);
    });
  }

  function update(action: string, id: string) {
    if (!LOCAL_DEMO_WRITES) return;
    void run(() =>
      fetchJson(`${API}/api/v1/incidents/${id}/review`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, actor: reviewer }),
      }),
    );
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
        <header className="topbar"><div className="eyebrow">MEMBER 1 / {view === "lab" ? "AI DETECT TEST LAB" : view === "integrations" ? "INTEGRATION CENTER" : "INCIDENT OPERATIONS"}</div>{view === "lab" ? <span className="connection ok">● Browser-local · no API</span> : view === "integrations" ? <span className="connection">● Read-only connection status</span> : <span className={online ? "connection ok" : "connection"}>● {online ? "Local API reachable · demo only" : "API offline"}</span>}</header>
        {view === "lab" ? <EdgeTestLab /> : view === "integrations" ? <IntegrationCenter /> : <>
        <div className="hero"><div><div className="eyebrow blue">OPERATIONAL OVERVIEW</div><h1>Incident intelligence</h1><p>Meta-first visual verification is planned. Current events are MOCK; caregiver review and response tracking remain manual in this demo.</p></div><button className="primary" onClick={createDemo} disabled={!LOCAL_DEMO_WRITES || busy || !online}>+ Generate staged incident</button></div>
        <div className="warning"><span>SIMULATION ONLY</span> This foundation uses mock incident interpretation. It does not detect a real fall, query Meta Muse Spark, provide medical advice, or contact emergency services. {LOCAL_DEMO_WRITES ? "Local-only demo write actions explicitly enabled (NOT authenticated)." : "Unauthenticated demo write actions disabled by default; local opt-in required."}</div>
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
            {incidents.length === 0 ? <div className="empty"><div className="empty-icon">◉</div><strong>No staged incidents yet</strong><p>Generate a simulated incident to test the notification and review state machine.</p></div> :
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
                <div className="actions">{(actionOptions[selectedIncident.status] ?? []).map(([label, action]) => <button key={action} disabled={!LOCAL_DEMO_WRITES || busy || !reviewer.trim()} onClick={() => update(action, selectedIncident.id)}>{label}</button>)}</div>
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
