import { useCallback, useEffect, useRef, useState } from "react";
import {
  hasUsableVideoTrack, LAPTOP_WEBCAM_DEMO_MAX_MS,
  requestLaptopWebcam, stopLaptopWebcam,
  webcamDemoSupported, webcamErrorLabel,
} from "./laptopWebcam";

type WebcamPhase = "idle" | "requesting" | "live" | "error";

/**
 * Manual browser getUserMedia preview for the laptop operator only.
 * No frame capture, backend calls, AI detection, recording or notifications.
 * Independent of the signed RTSP/Hikvision pipeline.
 */
export default function LaptopWebcamDemo() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const trackListener = useRef<(() => void) | null>(null);
  const stopTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const generation = useRef(0);
  const inFlight = useRef(false);
  const [phase, setPhase] = useState<WebcamPhase>("idle");
  const [message, setMessage] = useState("");
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [now, setNow] = useState(() => Date.now());

  const clearCapture = useCallback(() => {
    generation.current += 1; // invalidate permission prompts that resolve late
    inFlight.current = false;
    if (stopTimer.current !== null) clearTimeout(stopTimer.current);
    stopTimer.current = null;
    trackListener.current?.();
    trackListener.current = null;
    const stream = streamRef.current;
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.pause();
      videoRef.current.srcObject = null;
    }
    stopLaptopWebcam(stream);
  }, []);

  const stop = useCallback(() => {
    clearCapture();
    setStartedAt(null);
    setPhase("idle");
    setMessage("");
  }, [clearCapture]);

  useEffect(() => {
    const invisible = () => {
      if (document.visibilityState !== "visible") stop();
    };
    const pageExit = () => clearCapture();
    document.addEventListener("visibilitychange", invisible);
    window.addEventListener("pagehide", pageExit);
    return () => {
      document.removeEventListener("visibilitychange", invisible);
      window.removeEventListener("pagehide", pageExit);
      clearCapture(); // always release camera on navigation/unmount
    };
  }, [clearCapture, stop]);

  useEffect(() => {
    if (phase !== "live" || startedAt === null) return;
    const ticker = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(ticker);
  }, [phase, startedAt]);

  async function start() {
    if (inFlight.current || streamRef.current) return;
    if (!webcamDemoSupported(
      window.location.hostname, window.isSecureContext, navigator.mediaDevices,
    )) {
      setMessage("Laptop demo only runs on localhost / 127.0.0.1 in a secure browser context.");
      setPhase("error");
      return;
    }
    if (document.visibilityState !== "visible") return;
    const requestId = ++generation.current;
    inFlight.current = true;
    setMessage("");
    setPhase("requesting");
    let stream: MediaStream;
    try {
      stream = await requestLaptopWebcam(navigator.mediaDevices);
    } catch (error) {
      if (requestId === generation.current) {
        inFlight.current = false;
        setPhase("error");
        setMessage(webcamErrorLabel(error)); // never display native device details
      }
      return;
    }
    if (requestId !== generation.current || document.visibilityState !== "visible") {
      stopLaptopWebcam(stream); // permission completed after Stop/navigation/hidden
      return;
    }
    if (!hasUsableVideoTrack(stream)) {
      stopLaptopWebcam(stream);
      inFlight.current = false;
      setPhase("error");
      setMessage("Camera returned no active video track.");
      return;
    }
    // getUserMedia requested audio:false; reject unexpected microphones too.
    for (const audioTrack of stream.getAudioTracks()) audioTrack.stop();
    streamRef.current = stream;
    const track = stream.getVideoTracks()[0];
    const ended = () => {
      if (generation.current !== requestId) return;
      stop();
      setPhase("error");
      setMessage("Camera stopped or was disconnected.");
    };
    track.addEventListener("ended", ended);
    trackListener.current = () => track.removeEventListener("ended", ended);
    const video = videoRef.current;
    if (!video) {
      stop();
      setPhase("error");
      setMessage("Video preview unavailable.");
      return;
    }
    video.srcObject = stream;
    try {
      await video.play();
    } catch {
      if (generation.current === requestId) {
        stop();
        setPhase("error");
        setMessage("Browser could not play the local camera stream.");
      }
      return;
    }
    if (generation.current !== requestId || document.visibilityState !== "visible") {
      if (generation.current === requestId) stop();
      return;
    }
    inFlight.current = false;
    setStartedAt(Date.now());
    setNow(Date.now());
    setPhase("live");
    stopTimer.current = window.setTimeout(() => {
      if (generation.current !== requestId) return;
      stop();
      setMessage("Demo ended after 60 seconds. Click Start to open it again.");
    }, LAPTOP_WEBCAM_DEMO_MAX_MS);
  }

  const allowed = typeof window !== "undefined"
    && webcamDemoSupported(
      window.location.hostname, window.isSecureContext, navigator.mediaDevices,
    );
  const secondsRemaining = startedAt === null ? 0
    : Math.max(0, Math.ceil(
      (startedAt + LAPTOP_WEBCAM_DEMO_MAX_MS - now) / 1000,
    ));

  return <section className="laptop-webcam-demo" aria-label="Laptop webcam demo">
    <div className="laptop-webcam-info">
      <span className="integration-chip">LOCAL WEBCAM · DEMO</span>
      <h2>Laptop camera preview</h2>
      <p>Use your notebook's built-in camera instead of Hikvision. It opens only
        when you click Start and approve the browser prompt. No audio, recording,
        uploaded frames or cloud requests.</p>
      <div className="laptop-webcam-status">
        <strong>Video:</strong> {phase === "live" ? "LIVE · LOCAL DEVICE"
          : phase === "requesting" ? "REQUESTING PERMISSION" : "OFF"}
        <span>AI Fall Detection: NOT CONNECTED</span>
        <span>Caregiver alerts: DISABLED</span>
      </div>
      <div className="laptop-webcam-actions">
        {phase === "live" || phase === "requesting"
          ? <button type="button" onClick={stop}>Stop webcam</button>
          : <button type="button" disabled={!allowed}
              onClick={() => void start()}>Start laptop webcam demo</button>}
        {phase === "live" && <small role="status">
          Auto-stop in {secondsRemaining}s · stops when tab is hidden
        </small>}
        {!allowed && <small role="status">
          Open the Dashboard at http://127.0.0.1:5173 to use this demo.
        </small>}
      </div>
      {message && <small role={phase === "error" ? "alert" : "status"}
          className="laptop-webcam-message">{message}</small>}
      <small className="laptop-webcam-disclaimer">
        Preview only — this does not run MediaPipe, classify a fall or confirm
        that anyone is safe. Hikvision approval and production inference are
        separate workflows.
      </small>
    </div>
    <div className="laptop-webcam-video-box">
      <video ref={videoRef} autoPlay playsInline muted
        aria-label="Local laptop webcam live preview"
        className={phase === "live" ? "is-visible" : ""} />
      {phase !== "live" && <div className="laptop-webcam-placeholder">
        <span aria-hidden="true">◎</span>
        <strong>{phase === "requesting" ? "ALLOW CAMERA IN BROWSER" : "LOCAL CAMERA OFF"}</strong>
        <small>No image is captured until you start the demo.</small>
      </div>}
      {phase === "live" && <span className="camera-preview-watermark">
        LIVE · BROWSER LOCAL · NOT AI ANALYZED
      </span>}
    </div>
  </section>;
}
