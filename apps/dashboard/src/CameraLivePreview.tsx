import { useCallback, useEffect, useRef, useState } from "react";
import type { CameraSummary } from "./integrationOverview";
import {
  closeCameraPreview, openCameraPreview, previewImagePath,
} from "./cameraPreview";
import type { CameraPreviewSession } from "./cameraPreview";

type PreviewPhase = "idle" | "connecting" | "waiting_frame" | "first_frame" | "error";

/**
 * Browser presentation only. The image is fetched only with an explicit click,
 * from a same-origin, authenticated backend session, NEVER a direct RTSP URL.
 * Backend must verify per-camera RBAC, signed Edge approval and every frame.
 */
export default function CameraLivePreview({
  camera, permitted,
}: { camera: CameraSummary; permitted: boolean }) {
  const [phase, setPhase] = useState<PreviewPhase>("idle");
  const [session, setSession] = useState<CameraPreviewSession | null>(null);
  const [message, setMessage] = useState("");
  const currentSession = useRef<CameraPreviewSession | null>(null);
  const pending = useRef<AbortController | null>(null);
  const expiryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = useCallback(() => {
    pending.current?.abort();
    pending.current = null;
    if (expiryTimer.current !== null) clearTimeout(expiryTimer.current);
    expiryTimer.current = null;
    const active = currentSession.current;
    currentSession.current = null;
    setSession(null); // detach live <img> immediately on revoke/stop
    setPhase("idle");
    setMessage("");
    if (active) void closeCameraPreview(active);
  }, []);

  useEffect(() => {
    return () => { stop(); };
  }, [stop]);

  useEffect(() => {
    if (!permitted) stop();
  }, [permitted, stop]);

  useEffect(() => {
    const hidden = () => {
      if (document.visibilityState !== "visible") stop();
    };
    document.addEventListener("visibilitychange", hidden);
    return () => document.removeEventListener("visibilitychange", hidden);
  }, [stop]);

  async function start() {
    if (!permitted || pending.current || currentSession.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setMessage("");
    setPhase("connecting");
    try {
      const issued = await openCameraPreview(camera.camera_id, controller.signal);
      if (pending.current !== controller || controller.signal.aborted) {
        void closeCameraPreview(issued);
        return;
      }
      pending.current = null;
      // Never rely on the frontend timer as the privacy/security boundary.
      currentSession.current = issued;
      setSession(issued);
      setPhase("waiting_frame");
      const milliseconds = Date.parse(issued.expires_at) - Date.now();
      if (milliseconds <= 0) {
        stop();
        return;
      }
      expiryTimer.current = setTimeout(stop, milliseconds);
    } catch (e) {
      if (pending.current !== controller) return;
      pending.current = null;
      setPhase("error");
      setMessage(e instanceof Error && (
        e.message === "Operator authentication or camera access denied"
        || e.message === "Protected camera media gateway unavailable"
      ) ? e.message : "Unable to start authorized camera preview");
    }
  }

  const imageVisible = permitted && session !== null;
  const active = imageVisible && (phase === "waiting_frame" || phase === "first_frame");
  return <div className="camera-preview-panel">
    {active && session ? <div className="camera-preview-frame">
      <img
        key={session.session_id}
        src={previewImagePath(session)}
        alt="Operator-authorized live camera preview"
        referrerPolicy="no-referrer"
        onLoad={() => {
          if (currentSession.current?.session_id === session.session_id) {
            setPhase("first_frame");
          }
        }}
        onError={() => {
          stop();
          setPhase("error");
          setMessage("Protected media failed or was revoked");
        }}
      />
      <span className="camera-preview-watermark">
        {phase === "first_frame" ? "FRAME RECEIVED · SUPERVISED" : "WAITING FOR FIRST FRAME"}
      </span>
    </div> : <div className="integration-dark-preview">
      <div aria-hidden="true" className="integration-crosshair">◎</div>
      <span>{permitted ? "PROTECTED LIVE VIEW · OFF" : "VIDEO PREVIEW LOCKED"}</span>
      <small>{permitted
        ? "Requires authenticated, per-camera backend media session"
        : "Camera requires fresh authorized backend status and privacy approval"}</small>
    </div>}
    <div className="camera-preview-controls">
      {phase === "connecting" ? <span role="status">Requesting protected session…</span>
        : active ? <button type="button" onClick={stop}>Stop preview</button>
          : <button type="button" disabled={!permitted} onClick={() => void start()}>
            Open live preview
          </button>}
      {phase === "error" && <small role="alert">{message}</small>}
    </div>
  </div>;
}
