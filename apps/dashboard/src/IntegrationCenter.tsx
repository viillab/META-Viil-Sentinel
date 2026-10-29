import { useEffect, useState } from "react";
import {
  fetchIntegrationOverview, snapshotIsFresh, INTEGRATION_SCHEMA,
} from "./integrationOverview";
import type { IntegrationOverview, CameraSummary } from "./integrationOverview";
import CameraLivePreview from "./CameraLivePreview";

const SAMPLE: IntegrationOverview = {
  schema_version: INTEGRATION_SCHEMA,
  generated_at: "2099-01-01T00:00:00Z", // never used as a live snapshot
  access_scope: "authenticated_operator",
  edge: { state: "degraded", last_heartbeat_at: null },
  cameras: [
    { camera_id: "zone-a", transport: "rtsp", health: "online",
      privacy: "approved", last_heartbeat_at: "2099-01-01T00:00:00Z", observed_fps: 14.8 },
    { camera_id: "zone-b", transport: "rtsp", health: "offline",
      privacy: "approved", last_heartbeat_at: null, observed_fps: null },
    { camera_id: "operator-usb", transport: "usb", health: "unknown",
      privacy: "unverified", last_heartbeat_at: null, observed_fps: null },
  ],
  meta: { provider: "mock", state: "not_configured",
    evidence_pipeline: "not_configured", last_verified_call_at: null },
  notification: { state: "not_configured" },
};
type FeedState = "loading" | "connected" | "unavailable" | "invalid" | "unauthorized";
const pretty = (value: string) => value.replaceAll("_", " ").toUpperCase();

function CameraTile({ camera, demo, permitted }: {
  camera: CameraSummary; demo: boolean; permitted: boolean;
}) {
  return <article className="integration-camera">
    <div className="integration-camera-head">
      <span className="integration-camera-icon" aria-hidden="true">▣</span>
      <span className="integration-chip">{camera.transport === "rtsp" ? "IP / RTSP" : "USB / UVC"}</span>
    </div>
    <strong>{camera.camera_id}</strong>
    <span className="integration-muted">Pseudonymous device ID · {demo ? "sample only" : "backend reported"}</span>
    <CameraLivePreview camera={camera} permitted={permitted && !demo} />
    <div className="integration-camera-footer">
      <span className={"integration-dot " + camera.health} aria-hidden="true" />
      <span>{pretty(camera.health)}</span>
      <span className="integration-camera-right">{camera.observed_fps === null
        ? "FPS —" : camera.observed_fps.toFixed(1) + " FPS"}</span>
    </div>
    <div className="integration-privacy">Privacy gate: <strong>{pretty(camera.privacy)}</strong></div>
  </article>;
}

export default function IntegrationCenter() {
  const [snapshot, setSnapshot] = useState<IntegrationOverview | null>(null);
  const [feedState, setFeedState] = useState<FeedState>("loading");
  const [preview, setPreview] = useState(false);
  // Use the actual browser clock, not the timestamp of the last successful poll.
  const [nowMs, setNowMs] = useState(() => Date.now());
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    if (preview) return;
    const clock = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(clock);
  }, [preview]);

  useEffect(() => {
    if (preview) return;
    let alive = true;
    let controller: AbortController | null = null;
    async function poll() {
      if (!alive || controller || document.visibilityState === "hidden") return;
      const running = new AbortController();
      controller = running;
      const deadline = window.setTimeout(() => running.abort(), 7_000);
      try {
        const data = await fetchIntegrationOverview(running.signal);
        if (!alive || document.visibilityState !== "visible") return;
        const fresh = snapshotIsFresh(data);
        setNowMs(Date.now());
        setSnapshot(fresh ? data : null);
        setFeedState(fresh ? "connected" : "invalid");
      } catch (err) {
        if (!alive) return;
        setSnapshot(null); // do not show stale "online" devices after an error
        const message = err instanceof Error ? err.message : "";
        setFeedState(message.startsWith("Authentication/authorization")
          ? "unauthorized" : message.includes("Invalid integration")
            || message.includes("snapshot too large") ? "invalid" : "unavailable");
      } finally {
        window.clearTimeout(deadline);
        if (controller === running) controller = null;
        if (alive) setNowMs(Date.now());
      }
    }
    void poll();
    const timer = window.setInterval(() => void poll(), 10_000);
    const visible = () => {
      if (document.visibilityState === "visible") {
        setNowMs(Date.now());
        void poll();
      } else {
        // An unseen tab must not retain an allegedly online camera snapshot.
        setSnapshot(null);
        setFeedState("loading");
        controller?.abort();
      }
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      alive = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", visible);
      controller?.abort();
    };
  }, [preview, refreshToken]);

  const isLive = !preview && feedState === "connected" && !!snapshot
    && snapshotIsFresh(snapshot, nowMs);
  const data = preview ? SAMPLE : isLive ? snapshot : null;
  const cameras = data?.cameras ?? [];
  const readyCameras = isLive ? cameras.filter(c => c.health === "online" && c.privacy === "approved").length : 0;
  // A server report is not independently verified by the browser.
  const metaLabel = preview ? "MOCK / NOT CONFIGURED"
    : !isLive ? "NOT CONNECTED"
    : data?.meta.provider === "meta_model_api" ? "BACKEND REPORT" : "MOCK / UNAVAILABLE";

  return <div className="integration-page">
    <div className="integration-heading">
      <div>
        <div className="eyebrow blue">MEMBER 1 · CAMERA & META INTEGRATION WORKSPACE</div>
        <h1>Integration center</h1>
        <p>One place to review camera adapters, privacy gates and the Member 2 AI handoff.</p>
      </div>
      <div className="integration-controls">
        <button type="button" className="lab-button" onClick={() => {
          setPreview(v => !v);
          setSnapshot(null);
          setFeedState("loading");
        }}>{preview ? "Return to backend status" : "Preview sample layout"}</button>
        <button type="button" className="lab-button-primary" disabled={preview}
          onClick={() => setRefreshToken(n => n + 1)}>Refresh connections</button>
      </div>
    </div>
    <div role="status" aria-live="polite" className={"integration-notice" + (preview ? " sample" : "")}>
      <span className="integration-signal" aria-hidden="true">●</span>
      <strong>{preview ? "SAMPLE UI — NOT LIVE DATA" : isLive
        ? "BACKEND-REPORTED SNAPSHOT · NOT INDEPENDENTLY VERIFIED"
        : feedState === "unauthorized" ? "AUTHENTICATION REQUIRED"
          : feedState === "invalid" ? "INVALID OR EXPIRED SNAPSHOT"
            : feedState === "loading" ? "CHECKING LOCAL BACKEND" : "INTEGRATION ENDPOINT NOT CONNECTED"}</strong>
      <span>{preview
        ? "Illustrative devices are in-memory examples only. No camera or Meta call is made."
        : "Camera preview requires an explicit click and an authenticated backend media session. No direct RTSP or camera passwords in browser."}</span>
    </div>

    <section className="integration-kpis" aria-label="Connection summary">
      <div className="integration-kpi"><small>REGISTERED SOURCES</small><strong>{data ? cameras.length : "—"}</strong><span>{preview ? "Sample devices" : isLive ? "Backend-reported only" : "Waiting for Member 2 API"}</span></div>
      <div className="integration-kpi"><small>APPROVED + REPORTED ONLINE</small><strong>{preview ? "1*" : isLive ? readyCameras : "—"}</strong><span>{preview ? "* Fictional example" : "Never inferred from model events"}</span></div>
      <div className="integration-kpi"><small>META AI</small><strong className="integration-text-value">{metaLabel}</strong><span>{isLive ? "No browser-side provider credentials" : "Awaiting verified backend handoff"}</span></div>
      <div className="integration-kpi"><small>CAREGIVER DELIVERY</small><strong className="integration-text-value">{isLive && data ? pretty(data.notification.state) : "NOT VERIFIED"}</strong><span>No emergency dispatch enabled</span></div>
    </section>

    <div className="integration-section-head"><div><h2>Camera sources</h2><p>Vendor-neutral RTSP / USB adapters · local capture stays on the Edge worker</p></div><span>{data ? cameras.length : "0"} sources {preview ? "· SAMPLE" : ""}</span></div>
    {cameras.length
      ? <div className="integration-camera-grid">{cameras.map(c =>
        <CameraTile key={c.camera_id} camera={c} demo={preview}
          permitted={isLive && c.health === "online" && c.privacy === "approved"} />)}</div>
      : <div className="integration-empty">
        <span className="integration-empty-mark" aria-hidden="true">▣</span>
        <div><strong>No authorized camera metadata available</strong>
          <p>Member 2 must expose the authenticated metadata-only overview endpoint. Camera credentials and registration remain on the trusted Edge/backend side.</p>
          <small>Do not enter an RTSP URL, password, or raw video here.</small></div>
      </div>}

    <div className="integration-panels">
      <section className="integration-card">
        <div className="integration-panel-title"><span className="integration-step">01</span><div><strong>Edge camera adapter</strong><small>Member 1 · implemented</small></div><span className="integration-tag">LOCAL</span></div>
        <p>RTSP-compatible IP cameras and USB/UVC, with signed privacy approval, bounded sessions, camera isolation and revocation checks.</p>
        <div className="integration-rule"><span>Edge heartbeat</span><strong>{isLive && data ? pretty(data.edge.state) : "NOT VERIFIED"}</strong></div>
        <div className="integration-rule"><span>Browser live preview</span><strong>BACKEND MEDIA SESSION REQUIRED</strong></div>
      </section>
      <section className="integration-card">
        <div className="integration-panel-title"><span className="integration-step">02</span><div><strong>Meta AI assessment</strong><small>Member 2 · backend-only adapter</small></div><span className="integration-tag">HANDOFF</span></div>
        <p>Only the backend can authenticate evidence, call Meta AI and produce a validated informational assessment. Model output is not medical confirmation.</p>
        <div className="integration-rule"><span>Provider</span><strong>{isLive && data ? pretty(data.meta.provider) : "NOT VERIFIED"}</strong></div>
        <div className="integration-rule"><span>Evidence pipeline</span><strong>{isLive && data ? pretty(data.meta.evidence_pipeline) : "NOT VERIFIED"}</strong></div>
      </section>
      <section className="integration-card">
        <div className="integration-panel-title"><span className="integration-step">03</span><div><strong>Caregiver workflow</strong><small>Member 1 UI + Member 2 authorized API</small></div><span className="integration-tag">REVIEW</span></div>
        <p>Incident review is handled in the Operations demo. Human approval, backend RBAC, audit logs and delivery receipts are required before real use.</p>
        <div className="integration-rule"><span>Automatic emergency action</span><strong>NOT AUTHORIZED</strong></div>
        <div className="integration-rule"><span>Cloud image transfer</span><strong>DISABLED BY DEFAULT</strong></div>
      </section>
    </div>
    <div className="integration-handoff">
      <div><strong>Member 2 integration contract</strong><p>GET <code>/api/v1/integrations/overview</code> · schema <code>{INTEGRATION_SCHEMA}</code> · authenticated metadata only. HTTP 401/403/404, stale data and malformed fields all fail closed.</p></div>
      <div className="integration-handoff-status">AUTH + RBAC REQUIRED</div>
    </div>
  </div>;
}
