import { useEffect, useState } from "react";
import {
  CAREGIVER_INBOX_SCHEMA, caregiverInboxFresh,
  fetchCaregiverInbox, presentAdvisory,
} from "./caregiverInbox";
import type { CaregiverAdvisory, CaregiverInbox } from "./caregiverInbox";

// Fictional preview only. Never presented as an actual delivered alert.
const PREVIEW: CaregiverInbox = {
  schema_version: CAREGIVER_INBOX_SCHEMA,
  generated_at: "2099-01-01T00:00:00Z",
  access_scope: "authenticated_caregiver",
  advisories: [
    {
      advisory_id: "ed76a512-508e-4afc-a716-f244012c52a1",
      source_id: "demo-wheelchair-zone",
      occurred_at: "2099-01-01T00:00:00Z",
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
    },
    {
      advisory_id: "6c34af85-f585-48c9-b6ce-1da88c269ce4",
      source_id: "demo-hallway-zone",
      occurred_at: "2099-01-01T00:00:00Z",
      stage: "edge_candidate",
      context_code: "rapid_descent",
      meta_provenance: "none",
      delivery_state: "not_sent",
      receipt_verified: false,
      review_state: "pending",
      simulated: true,
      fall_confirmed: false,
      emergency_dispatch_authorized: false,
      human_follow_up_required: true,
    },
  ],
};

type FeedState = "checking" | "available" | "unauthorized" | "invalid" | "offline";
function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    ? date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : "Unknown time";
}
function AdvisoryCard({
  advisory, selected, onClick, demo,
}: {
  advisory: CaregiverAdvisory; selected: boolean;
  onClick: () => void; demo: boolean;
}) {
  const view = presentAdvisory(advisory);
  return <button type="button" className={"caregiver-item" + (selected ? " selected" : "")}
    aria-pressed={selected} aria-label={`${advisory.source_id}: ${view.title}; ${view.review}`}
    onClick={onClick}>
    <span className="caregiver-item-top">
      <span className="caregiver-source">{advisory.source_id}</span>
      <span className={"caregiver-stage " + advisory.stage}>{advisory.stage === "informational_advisory"
        ? "INFORMATIONAL" : advisory.stage === "follow_up_required" ? "FOLLOW UP" : "CANDIDATE"}</span>
    </span>
    <strong>{view.title}</strong>
    <span className="caregiver-item-meta">{demo ? "Fictional example · " : ""}{formatDate(advisory.occurred_at)}</span>
  </button>;
}

export default function CaregiverInbox() {
  const [snapshot, setSnapshot] = useState<CaregiverInbox | null>(null);
  const [feedState, setFeedState] = useState<FeedState>("checking");
  const [preview, setPreview] = useState(false);
  const [largeText, setLargeText] = useState(false);
  const [highContrast, setHighContrast] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (preview) return;
    const clock = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(clock);
  }, [preview]);

  useEffect(() => {
    if (preview) return;
    let alive = true;
    let controller: AbortController | null = null;
    const poll = async () => {
      if (!alive || controller || document.visibilityState !== "visible") return;
      const request = new AbortController();
      controller = request;
      const timer = window.setTimeout(() => request.abort(), 7_000);
      try {
        const result = await fetchCaregiverInbox(request.signal);
        if (!alive || document.visibilityState !== "visible") return;
        const fresh = caregiverInboxFresh(result);
        setSnapshot(fresh ? result : null);
        setNowMs(Date.now());
        setFeedState(fresh ? "available" : "invalid");
      } catch (error) {
        if (!alive) return;
        setSnapshot(null);
        setSelectedId(null);
        const message = error instanceof Error ? error.message : "";
        setFeedState(message.includes("authentication") ? "unauthorized"
          : message.startsWith("Invalid") || message.includes("too large")
            || message.startsWith("Malformed") ? "invalid" : "offline");
      } finally {
        window.clearTimeout(timer);
        if (controller === request) controller = null;
      }
    };
    void poll();
    const periodic = window.setInterval(() => void poll(), 10_000);
    const visibility = () => {
      if (document.visibilityState === "hidden") {
        controller?.abort();
        setSnapshot(null);
        setSelectedId(null);
        setFeedState("checking");
      } else {
        setNowMs(Date.now());
        void poll();
      }
    };
    document.addEventListener("visibilitychange", visibility);
    return () => {
      alive = false;
      window.clearInterval(periodic);
      document.removeEventListener("visibilitychange", visibility);
      controller?.abort();
    };
  }, [preview, refreshToken]);

  const current = !preview && feedState === "available" && snapshot
    && caregiverInboxFresh(snapshot, nowMs) ? snapshot : null;
  const data = preview ? PREVIEW : current;
  const advisories = data?.advisories ?? [];
  const selected = advisories.find(item => item.advisory_id === selectedId) ?? advisories[0];
  const needingFollowUp = advisories.filter(item => item.review_state === "pending").length;
  const presentation = selected ? presentAdvisory(selected) : null;
  const stateLabel = preview ? "EXAMPLE ONLY · NO ALERTS SENT"
    : current ? "AUTHENTICATED BACKEND REPORT · NOT INDEPENDENTLY VERIFIED"
      : feedState === "unauthorized" ? "LOGIN / PERMISSIONS REQUIRED"
        : feedState === "invalid" ? "INVALID OR STALE ADVISORY DATA"
          : feedState === "checking" ? "CHECKING CAREGIVER ACCESS"
            : "CAREGIVER API NOT CONNECTED";

  return <div className={"caregiver-page" + (highContrast ? " caregiver-contrast" : "")
    + (largeText ? " caregiver-large" : "")}>
    <div className="caregiver-heading">
      <div>
        <div className="eyebrow blue">MEMBER 1 · ACCESSIBLE CAREGIVER EXPERIENCE</div>
        <h1>Caregiver inbox</h1>
        <p>Understand possible incidents and follow-up needs without requiring video or audio.</p>
      </div>
      <div className="caregiver-toolbar">
        <button className="lab-button" type="button" onClick={() => {
          setPreview(p => !p);
          setSelectedId(null);
          setSnapshot(null);
          setFeedState("checking");
        }}>{preview ? "Exit sample preview" : "Preview accessible sample"}</button>
        <button type="button" className="lab-button-primary" disabled={preview}
          onClick={() => setRefreshToken(t => t + 1)}>Refresh status</button>
      </div>
    </div>

    <section className="caregiver-preferences" aria-label="Accessibility display options">
      <strong>Display accessibility</strong>
      <label><input type="checkbox" checked={largeText}
        onChange={event => setLargeText(event.target.checked)} />
        Larger text and controls</label>
      <label><input type="checkbox" checked={highContrast}
        onChange={event => setHighContrast(event.target.checked)} />
        Higher contrast</label>
      <small>Changes apply only to this view, in memory. No identity or preference data is uploaded.</small>
    </section>

    <div className={"caregiver-banner" + (preview ? " sample" : "")} role="status" aria-live="polite">
      <strong>{stateLabel}</strong>
      <span>{preview
        ? "Everything below is fictional. No camera, Meta provider or notification was contacted."
        : "Only backend-authorized metadata may appear here. No images, person identification or emergency dispatch."}</span>
    </div>

    <div className="caregiver-summary" aria-label="Advisory summary">
      <div><small>AVAILABLE ADVISORIES</small><strong>{data ? advisories.length : "—"}</strong><span>{preview ? "Synthetic example records" : "Backend-authorized records only"}</span></div>
      <div><small>REQUIRE FOLLOW-UP</small><strong>{data ? needingFollowUp : "—"}</strong><span>Not a medical urgency score</span></div>
      <div><small>MESSAGE DELIVERY</small><strong className="caregiver-summary-text">RECEIPT-BASED</strong><span>Backend proof required; no browser-side send</span></div>
    </div>

    <div className="caregiver-layout">
      <section className="caregiver-panel" aria-labelledby="caregiver-queue-heading">
        <div className="caregiver-panel-header"><h2 id="caregiver-queue-heading">Advisories</h2><span>{preview ? "SAMPLE" : current ? "BACKEND REPORT" : "NOT CONNECTED"}</span></div>
        {advisories.length
          ? <div className="caregiver-queue">{advisories.map(item =>
            <AdvisoryCard key={item.advisory_id} advisory={item}
              selected={selected?.advisory_id === item.advisory_id}
              onClick={() => setSelectedId(item.advisory_id)} demo={preview} />)}</div>
          : <div className="caregiver-empty"><strong>No authorized advisory data to show</strong>
              <p>Member 2 must enable the authenticated caregiver inbox. An empty or offline inbox does not mean that no fall occurred.</p></div>}
      </section>
      <section className="caregiver-panel" aria-labelledby="caregiver-detail-heading">
        <div className="caregiver-panel-header"><h2 id="caregiver-detail-heading">Incident context</h2><span>READ ONLY</span></div>
        {!selected || !presentation
          ? <div className="caregiver-empty"><strong>No advisory selected</strong>
              <p>No data was loaded. This page will not generate a notification or bypass caregiver review.</p></div>
          : <div className="caregiver-detail">
            <div className="caregiver-detail-label">SOURCE (PSEUDONYMOUS)</div>
            <strong className="caregiver-detail-source">{selected.source_id}</strong>
            <div className="caregiver-context">
              <small>OBSERVED CONTEXT</small><p>{presentation.context}</p>
            </div>
            <div className="caregiver-context"><small>ASSESSMENT STATUS</small>
              <p>{presentation.title}</p><p className="caregiver-secondary">{presentation.meta}</p></div>
            <div className="caregiver-context"><small>NOTIFICATION DELIVERY</small>
              <p>{preview ? "SAMPLE ONLY — no notification dispatched" : presentation.delivery}</p></div>
            <div className="caregiver-context"><small>REVIEW STATE</small>
              <p>{preview ? "SAMPLE — no real acknowledgement recorded" : presentation.review}</p></div>
            <div className="caregiver-safety"><strong>Unconfirmed event — human follow-up</strong>
              <p>AI cannot determine whether a person needs emergency assistance. Follow your organization's approved human care and emergency procedures. Never rely on this demo as the only way to request help.</p>
            </div>
            <small className="caregiver-endnote">Viewing is not acknowledgement. Delivery, review and closure actions must be implemented by Member 2 with authentication, audit and source permissions.</small>
          </div>}
      </section>
    </div>
    <div className="caregiver-next">
      <strong>For Member 2:</strong> <code>GET /api/v1/caregiver/inbox</code> must return schema <code>{CAREGIVER_INBOX_SCHEMA}</code> only after authenticated caregiver-scoped authorization. This release does not request notification permissions, play audio, or send alerts.
    </div>
  </div>;
}
