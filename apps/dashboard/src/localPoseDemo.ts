/** In-memory, session-only research heuristic ported from Edge Python threshold rules.
 * NOT a validated fall classifier or a medical alarm. No events/landmarks leave JS.
 */
export type LocalPoseLandmark = {
  x: number; y: number; visibility?: number; presence?: number;
};
export type PoseObservation = {
  status: "unknown" | "upright" | "observing" | "candidate";
  angleDeg: number | null;
  hipY: number | null;
  quality: number | null;
  candidate: boolean;
};
type Features = { angleDeg: number; hipY: number; quality: number };
const UPRIGHT_MAX_DEG = 32;
const HORIZONTAL_MIN_DEG = 56;
const MIN_HIP_DROP = 0.13;
const LOOKBACK_MS = 1600;
const HOLD_MS = 450;
const COOLDOWN_MS = 4000;
const GAP_MS = 700;
const MIN_VISIBILITY = 0.55;

export const POSE_DEMO_INTERVAL_MS = 200; // <=5Hz, no second camera capture
export const POSE_DEMO_STALL_MS = 3500; // no fresh video frames => stop instead of implying live AI
export const CANDIDATE_NOTICE_MS = 8000; // ephemeral, unconfirmed local notice
export const MAX_LOCAL_TASK_BYTES = 16 * 1024 * 1024;

/** Valid monotonic RAF timings only. Bad clocks also fail closed. */
export function poseStreamStalled(nowMs: number, lastFrameMs: number): boolean {
  return !Number.isFinite(nowMs) || !Number.isFinite(lastFrameMs)
    || nowMs < lastFrameMs || nowMs - lastFrameMs >= POSE_DEMO_STALL_MS;
}

/** Do not leave an unconfirmed candidate banner visible indefinitely. */
export function candidateNoticeVisible(nowMs: number, candidateAtMs: number | null): boolean {
  return candidateAtMs !== null
    && Number.isFinite(nowMs) && Number.isFinite(candidateAtMs)
    && nowMs >= candidateAtMs && nowMs - candidateAtMs < CANDIDATE_NOTICE_MS;
}
export const LOCAL_VISION_WASM_ROOT = "/vendor/mediapipe/wasm";

export function validLocalPoseTask(file: Pick<File, "name" | "size"> | null): boolean {
  return file !== null
    && typeof file.name === "string"
    && file.name.toLowerCase().endsWith(".task")
    && Number.isSafeInteger(file.size)
    && file.size >= 1024 && file.size <= MAX_LOCAL_TASK_BYTES;
}

export function torsoFeatures(
  poses: ReadonlyArray<ReadonlyArray<LocalPoseLandmark>>,
): Features | null {
  if (!Array.isArray(poses) || poses.length !== 1) return null;
  const points = poses[0];
  if (!Array.isArray(points) || points.length <= 24) return null;
  const required = [points[11], points[12], points[23], points[24]];
  for (const p of required) {
    if (p === null || typeof p !== "object") return null;
    if (!Number.isFinite(p.x) || !Number.isFinite(p.y)
        || p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1) return null;
    if (!Number.isFinite(p.visibility)
        || (p.visibility ?? 0) < MIN_VISIBILITY
        || (p.visibility ?? 0) > 1) return null;
    if (p.presence !== undefined && (p.presence === null
        || !Number.isFinite(p.presence)
        || p.presence < MIN_VISIBILITY || p.presence > 1)) return null;
  }
  const [ls, rs, lh, rh] = required;
  const sx = (ls.x + rs.x) / 2;
  const sy = (ls.y + rs.y) / 2;
  const hx = (lh.x + rh.x) / 2;
  const hy = (lh.y + rh.y) / 2;
  const dx = sx - hx;
  const dy = sy - hy;
  if (Math.hypot(dx, dy) < 0.04) return null;
  return {
    angleDeg: Math.atan2(Math.abs(dx), Math.abs(dy)) * 180 / Math.PI,
    hipY: hy,
    quality: Math.min(...required.map(point => point.visibility ?? 0)),
  };
}

const UNKNOWN: PoseObservation = Object.freeze({
  status: "unknown", angleDeg: null, hipY: null, quality: null, candidate: false,
});

export class LocalFallCandidateHeuristic {
  private history: Array<{ t: number; value: Features }> = [];
  private lastMs = -1;
  private pendingSince: number | null = null;
  private lastCandidateMs: number | null = null;
  private candidateCount = 0;

  reset(): void {
    this.history = [];
    this.lastMs = -1;
    this.pendingSince = null;
    this.lastCandidateMs = null;
    this.candidateCount = 0;
  }

  get count(): number { return this.candidateCount; }

  observe(poses: ReadonlyArray<ReadonlyArray<LocalPoseLandmark>>, ms: number): PoseObservation {
    if (!Number.isFinite(ms) || ms < 0 || ms <= this.lastMs) {
      this.reset();
      return UNKNOWN;
    }
    if (this.lastMs >= 0 && ms - this.lastMs > GAP_MS) {
      this.history = [];
      this.pendingSince = null;
    }
    this.lastMs = ms;
    const features = torsoFeatures(poses);
    if (!features) {
      this.history = [];
      this.pendingSince = null;
      return UNKNOWN;
    }
    this.history = this.history.filter(({ t }) => t >= ms - LOOKBACK_MS);
    const uprightY = this.history
      .filter(({ value }) => value.angleDeg <= UPRIGHT_MAX_DEG)
      .map(({ value }) => value.hipY);
    this.history.push({ t: ms, value: features });
    const descent = uprightY.length ? features.hipY - Math.min(...uprightY) : 0;
    const horizontal = features.angleDeg >= HORIZONTAL_MIN_DEG;
    const enoughDrop = descent >= MIN_HIP_DROP;
    const cooled = this.lastCandidateMs === null || ms - this.lastCandidateMs >= COOLDOWN_MS;
    if (!horizontal || !enoughDrop || !cooled) {
      this.pendingSince = null;
      return {
        status: features.angleDeg <= UPRIGHT_MAX_DEG ? "upright" : "observing",
        angleDeg: features.angleDeg, hipY: features.hipY,
        quality: features.quality, candidate: false,
      };
    }
    if (this.pendingSince === null) {
      this.pendingSince = ms;
    } else if (ms - this.pendingSince >= HOLD_MS) {
      this.pendingSince = null;
      this.lastCandidateMs = ms;
      this.candidateCount += 1;
      return {
        status: "candidate", angleDeg: features.angleDeg, hipY: features.hipY,
        quality: features.quality, candidate: true,
      };
    }
    return {
      status: "observing", angleDeg: features.angleDeg, hipY: features.hipY,
      quality: features.quality, candidate: false,
    };
  }
}

/** Draw only ephemeral normalized joints/torso lines, never raw pixels. */
export function drawTorsoOverlay(
  canvas: HTMLCanvasElement,
  poses: ReadonlyArray<ReadonlyArray<LocalPoseLandmark>>,
  frameWidth: number,
  frameHeight: number,
): void {
  const context = canvas.getContext("2d");
  if (!context) return;
  // Same aspect ratio as the actual MediaStream; 640x360 is only ideal.
  if (!Number.isFinite(frameWidth) || !Number.isFinite(frameHeight)
      || frameWidth < 1 || frameHeight < 1
      || frameWidth > 1920 || frameHeight > 1080) {
    context.clearRect(0, 0, canvas.width, canvas.height);
    return;
  }
  const width = Math.floor(frameWidth);
  const height = Math.floor(frameHeight);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  context.clearRect(0, 0, canvas.width, canvas.height);
  if (!torsoFeatures(poses)) return;
  const points = poses[0];
  context.lineWidth = 3;
  context.lineCap = "round";
  context.strokeStyle = "#46e5b6";
  const connections: ReadonlyArray<readonly [number, number]> = [
    [11, 12], [11, 23], [12, 24], [23, 24],
  ];
  for (const [a, b] of connections) {
    context.beginPath();
    context.moveTo(points[a].x * canvas.width, points[a].y * canvas.height);
    context.lineTo(points[b].x * canvas.width, points[b].y * canvas.height);
    context.stroke();
  }
}
