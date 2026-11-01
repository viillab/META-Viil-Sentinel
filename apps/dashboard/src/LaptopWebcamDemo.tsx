import { useCallback, useEffect, useRef, useState } from "react";
import type { PoseLandmarker } from "@mediapipe/tasks-vision";
import {
  candidateNoticeVisible, drawTorsoOverlay, freshVideoFrameCount,
  LocalFallCandidateHeuristic, LOCAL_VISION_WASM_ROOT,
  poseStreamStalled, POSE_DEMO_INTERVAL_MS, validLocalPoseTask,
} from "./localPoseDemo";
import type { PoseObservation } from "./localPoseDemo";
import { loadLocalPoseLandmarker } from "./localPoseEngine";
import {
  hasUsableVideoTrack, LAPTOP_WEBCAM_DEMO_MAX_MS,
  requestLaptopWebcam, stopLaptopWebcam,
  webcamDemoSupported, webcamErrorLabel,
} from "./laptopWebcam";

type WebcamPhase = "idle" | "requesting" | "live" | "error";
type PosePhase = "unloaded" | "loading" | "ready" | "error";

/**
 * Manual browser getUserMedia preview for the laptop operator only.
 * Optional in-browser MediaPipe pose heuristic (unconfirmed candidate only).
 * No backend calls, upload, recording or notifications.
 * Independent of the signed RTSP/Hikvision pipeline.
 */
export default function LaptopWebcamDemo() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const overlayRef = useRef<HTMLCanvasElement | null>(null);
  const modelRef = useRef<PoseLandmarker | null>(null);
  const modelLoadGeneration = useRef(0);
  const [posePhase, setPosePhase] = useState<PosePhase>("unloaded");
  const [poseObservation, setPoseObservation] = useState<PoseObservation["status"]>("unknown");
  const [candidateCount, setCandidateCount] = useState(0);
  const [lastCandidateAt, setLastCandidateAt] = useState<number | null>(null);
  const [poseFrames, setPoseFrames] = useState(0);
  const [poseMessage, setPoseMessage] = useState("");
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
    modelLoadGeneration.current += 1;
    const model = modelRef.current;
    modelRef.current = null;
    try { model?.close(); } catch { /* native errors stay private */ }
    const canvas = overlayRef.current;
    canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
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
    setPosePhase("unloaded");
    setPoseObservation("unknown");
    setCandidateCount(0);
    setLastCandidateAt(null);
    setPoseFrames(0);
    setPoseMessage("");
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

  async function loadPoseModel(file: File | undefined) {
    if (!file || !validLocalPoseTask(file)) {
      setPosePhase("error");
      setPoseMessage("Choose the local pose_landmarker_lite.task file (1 KiB–16 MiB).");
      return;
    }
    const requestId = ++modelLoadGeneration.current;
    setPosePhase("loading");
    setPoseMessage("");
    let engine: PoseLandmarker;
    try {
      engine = await loadLocalPoseLandmarker(file);
    } catch {
      if (requestId === modelLoadGeneration.current) {
        setPosePhase("error");
        setPoseMessage("Local MediaPipe model could not load. Confirm the .task file and WASM assets.");
      }
      return;
    }
    if (requestId !== modelLoadGeneration.current
        || document.visibilityState !== "visible") {
      try { engine.close(); } catch { /* no native error disclosure */ }
      return;
    }
    try { modelRef.current?.close(); } catch { /* redacted */ }
    modelRef.current = engine;
    setPosePhase("ready");
    setPoseObservation("unknown");
    setCandidateCount(0);
    setLastCandidateAt(null);
    setPoseFrames(0);
  }

  useEffect(() => {
    if (phase !== "live" || posePhase !== "ready") return;
    const engine = modelRef.current;
    const video = videoRef.current;
    if (!engine || !video) return;
    // Chrome/Edge guarantee a decoded/presented video frame callback.
    // currentTime can advance while a live MediaStream picture is frozen.
    if (typeof video.requestVideoFrameCallback !== "function"
        || typeof video.cancelVideoFrameCallback !== "function") {
      stop();
      setPhase("error");
      setMessage("Browser cannot verify fresh camera frames. Local Pose demo disabled.");
      return;
    }
    const session = generation.current;
    const detector = new LocalFallCandidateHeuristic();
    let frameId = 0;
    let callbackId = 0;
    let cancelled = false;
    let previousMs = -1;
    let latestPresentedFrames = -1;
    let analyzedPresentedFrames = -1;
    let firstWatchMs: number | null = null;
    let lastRenderedMs: number | null = null;
    const framePresented = (ms: number, metadata: VideoFrameCallbackMetadata) => {
      if (cancelled || generation.current !== session) return;
      if (freshVideoFrameCount(metadata.presentedFrames, latestPresentedFrames)) {
        latestPresentedFrames = metadata.presentedFrames;
        lastRenderedMs = ms;
      }
      callbackId = video.requestVideoFrameCallback(framePresented);
    };
    callbackId = video.requestVideoFrameCallback(framePresented);
    const tick = (ms: number) => {
      if (cancelled || generation.current !== session
          || document.visibilityState !== "visible") return;
      frameId = window.requestAnimationFrame(tick);
      if (firstWatchMs === null) firstWatchMs = ms;
      if (poseStreamStalled(ms, lastRenderedMs ?? firstWatchMs)) {
        stop();
        setPhase("error");
        setMessage("Webcam frames stopped arriving. Local inference halted; no alert was sent.");
        return;
      }
      if (previousMs >= 0 && ms - previousMs < POSE_DEMO_INTERVAL_MS) return;
      if (video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA
          || latestPresentedFrames <= analyzedPresentedFrames) return;
      previousMs = ms;
      analyzedPresentedFrames = latestPresentedFrames;
      try {
        // Same browser-owned video element: no second webcam capture, upload
        // or video snapshot. Inference is synchronous and at most 5Hz.
        const result = engine.detectForVideo(video, ms);
        if (cancelled || generation.current !== session) return;
        const observation = detector.observe(result.landmarks, ms);
        const overlay = overlayRef.current;
        if (overlay) drawTorsoOverlay(
          overlay, result.landmarks, video.videoWidth, video.videoHeight,
        );
        setPoseFrames(n => n + 1);
        setPoseObservation(observation.status);
        if (observation.candidate) {
          const candidateAt = Date.now();
          setCandidateCount(detector.count);
          setLastCandidateAt(candidateAt);
          setNow(candidateAt);
        }
      } catch {
        if (!cancelled && generation.current === session) {
          stop();
          setPosePhase("error");
          setPoseMessage("Local inference stopped unexpectedly. No alert was sent.");
        }
      }
    };
    frameId = window.requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(frameId);
      video.cancelVideoFrameCallback(callbackId);
      const canvas = overlayRef.current;
      canvas?.getContext("2d")?.clearRect(0, 0, canvas.width, canvas.height);
    };
  }, [phase, posePhase, stop]);

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
      <h2>Laptop camera + on-device Pose Demo</h2>
      <p>Use one laptop camera for video and optional local MediaPipe Pose analysis.
        First select your own .task model, then click Start and approve the browser
        permission prompt. No audio, recorded frames, uploaded video or alerts.</p>
      <div className="laptop-webcam-status">
        <strong>Video:</strong> {phase === "live" ? "LIVE · LOCAL DEVICE"
          : phase === "requesting" ? "REQUESTING PERMISSION" : "OFF"}
        <span>Pose AI: {posePhase === "ready"
          ? phase === "live"
            ? poseFrames > 0 ? "LOCAL HEURISTIC · EXPERIMENTAL"
              : "MODEL READY · WAITING FOR FIRST FRAME"
            : "MODEL READY"
          : posePhase === "loading" ? "LOADING LOCAL MODEL" : "NOT LOADED"}</span>
        <span>Caregiver alerts: DISABLED</span>
      </div>
      <div className="laptop-pose-controls">
        <label htmlFor="viil-local-pose-model">Select local MediaPipe .task model
          (never uploaded)</label>
        <input id="viil-local-pose-model" type="file" accept=".task"
          disabled={posePhase === "loading"}
          onChange={event => {
            const file = event.currentTarget.files?.[0];
            event.currentTarget.value = "";
            void loadPoseModel(file);
          }} />
        <small>On this laptop: D:\VIIL-Sentinel\models\pose_landmarker_lite.task</small>
        <small>Local WASM: <code>{LOCAL_VISION_WASM_ROOT}</code> · up to 5 analyses/sec</small>
        {posePhase === "ready" && <strong>Pose model loaded into browser memory</strong>}
        {posePhase === "loading" && <small role="status">Loading local Pose Landmarker…</small>}
        {poseMessage && <small role={posePhase === "error" ? "alert" : "status"}>
          {poseMessage}</small>}
      </div>
      {phase === "live" && posePhase === "ready" && <div
          className="laptop-pose-feedback" role="status" aria-live="polite">
        <strong>{poseFrames === 0
          ? "WAITING FOR FIRST LOCAL POSE INFERENCE"
          : poseObservation === "candidate"
          ? "POSSIBLE FALL CANDIDATE · HUMAN REVIEW REQUIRED"
          : poseObservation === "unknown"
            ? "NO RELIABLE SINGLE-PERSON POSE"
            : poseObservation === "upright"
              ? "UPRIGHT BASELINE OBSERVED"
              : "OBSERVING BODY MOTION · NO CONFIRMED EVENT"}</strong>
        {candidateNoticeVisible(now, lastCandidateAt) && <strong
          className="laptop-pose-candidate">RECENT POSSIBLE FALL CANDIDATE ·
          UNCONFIRMED · HUMAN REVIEW REQUIRED</strong>}
        <span>Frames analyzed locally: {poseFrames} · Session-only candidate count: {candidateCount}</span>
        <small>Experimental torso-motion heuristic, not a fall confirmation,
          calibrated model probability or emergency monitoring.</small>
      </div>}
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
        Pose landmarks and heuristic results stay in browser memory; nothing
        is recorded or sent to the incident backend. This research demo cannot
        confirm a fall or anyone's safety. Hikvision authorization, real-world
        model validation and Meta provider work are separate.
      </small>
    </div>
    <div className="laptop-webcam-video-box">
      <video ref={videoRef} autoPlay playsInline muted
        aria-label="Local laptop webcam live preview"
        className={phase === "live" ? "is-visible" : ""} />
      <canvas ref={overlayRef} aria-hidden="true" className="laptop-pose-overlay" />
      {phase !== "live" && <div className="laptop-webcam-placeholder">
        <span aria-hidden="true">◎</span>
        <strong>{phase === "requesting" ? "ALLOW CAMERA IN BROWSER" : "LOCAL CAMERA OFF"}</strong>
        <small>No image is captured until you start the demo.</small>
      </div>}
      {phase === "live" && <span className="camera-preview-watermark">
        {posePhase === "ready" && poseFrames > 0
          ? "LIVE · LOCAL POSE HEURISTIC · NOT CONFIRMED"
          : "LIVE · BROWSER LOCAL · NOT AI ANALYZED"}
      </span>}
    </div>
  </section>;
}
