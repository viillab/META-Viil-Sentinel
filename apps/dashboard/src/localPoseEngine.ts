/** MediaPipe WASM and user-supplied private .task only. No CDN, upload or model persistence. */
import type { PoseLandmarker } from "@mediapipe/tasks-vision";
import { LOCAL_VISION_WASM_ROOT, validLocalPoseTask } from "./localPoseDemo";

export async function loadLocalPoseLandmarker(file: File): Promise<PoseLandmarker> {
  if (!validLocalPoseTask(file)) {
    throw new Error("Choose a local .task pose model file (1 KiB–16 MiB).");
  }
  // Package imported only after the operator chooses a model.
  const { FilesetResolver, PoseLandmarker } = await import("@mediapipe/tasks-vision");
  const wasm = await FilesetResolver.forVisionTasks(LOCAL_VISION_WASM_ROOT);
  // File arrayBuffer() is local File API. Never URL.createObjectURL or upload.
  const bytes = new Uint8Array(await file.arrayBuffer());
  if (bytes.byteLength !== file.size) {
    throw new Error("Model file changed while loading.");
  }
  return PoseLandmarker.createFromOptions(wasm, {
    baseOptions: { modelAssetBuffer: bytes, delegate: "CPU" },
    runningMode: "VIDEO",
    numPoses: 2, // more than one person => abstain, not an alert
    minPoseDetectionConfidence: 0.55,
    minPosePresenceConfidence: 0.55,
    minTrackingConfidence: 0.55,
    outputSegmentationMasks: false,
  });
}
