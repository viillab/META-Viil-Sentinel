/**
 * Member 1 local Edge candidate lab: BOUNDED, metadata-only, untrusted JSONL.
 * No model is run in the browser. No network, persistence, screenshots or alerts.
 * This is a UI sanity contract, not an authenticated backend security check.
 */

export const EDGE_CANDIDATE_SCHEMA = "viil.edge.candidate.v1" as const;
export const MAX_LOCAL_CANDIDATE_BYTES = 256 * 1024;
export const MAX_LOCAL_CANDIDATES = 100;
export const MAX_LINE_CHARACTERS = 6_000;

const FIELDS = [
  "schema_version", "event_type", "event_id", "source_id",
  "source_timestamp_ms", "timestamp_basis", "detector", "model_sha256",
  "input_provenance", "detector_score", "detector_score_type",
  "score_calibrated", "confirmed_fall", "human_review_required",
  "medical_assessment_performed", "simulated", "evidence_refs", "delivery_mode",
] as const;

const FIELD_SET: ReadonlySet<string> = new Set(FIELDS);
const SLUG_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$/;
const SHA_RE = /^[0-9a-f]{64}$/;
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export type EdgeCandidateV1 = {
  schema_version: typeof EDGE_CANDIDATE_SCHEMA;
  event_type: "FALL_CANDIDATE";
  event_id: string;
  source_id: string;
  source_timestamp_ms: number;
  timestamp_basis: "relative_to_source_start";
  detector: string;
  model_sha256: string | null;
  input_provenance: "synthetic_pose_trace" | "consented_staged_video" | "authorized_local_camera";
  detector_score: number;
  detector_score_type: "uncalibrated_heuristic";
  score_calibrated: false;
  confirmed_fall: false;
  human_review_required: true;
  medical_assessment_performed: false;
  simulated: boolean;
  evidence_refs: [];
  delivery_mode: "local_stdout_only";
};

export type LocalReplay = Readonly<{
  events: EdgeCandidateV1[];
  sourceIds: string[];
  expectedNegative: boolean;
  displayLabel: string;
}>;

function isRecord(obj: unknown): obj is Record<string, unknown> {
  return typeof obj === "object" && obj !== null && !Array.isArray(obj);
}

function reject(message: string, row: number): never {
  throw new Error(`Invalid Edge candidate at line ${row}: ${message}`);
}

function validated(value: unknown, row: number): EdgeCandidateV1 {
  if (!isRecord(value) || Object.keys(value).length !== FIELDS.length
      || Object.keys(value).some((k) => !FIELD_SET.has(k))) {
    return reject("expected the exact metadata-only v1 fields", row);
  }
  const e = value;
  if (e.schema_version !== EDGE_CANDIDATE_SCHEMA
      || e.event_type !== "FALL_CANDIDATE"
      || typeof e.event_id !== "string" || !UUID_RE.test(e.event_id)
      || typeof e.source_id !== "string" || !SLUG_RE.test(e.source_id)
      || typeof e.detector !== "string" || !SLUG_RE.test(e.detector)
      || typeof e.source_timestamp_ms !== "number"
      || !Number.isSafeInteger(e.source_timestamp_ms) || e.source_timestamp_ms < 0
      || e.timestamp_basis !== "relative_to_source_start"
      || !(e.model_sha256 === null
        || (typeof e.model_sha256 === "string" && SHA_RE.test(e.model_sha256)))
      || typeof e.input_provenance !== "string"
      || !["synthetic_pose_trace", "consented_staged_video", "authorized_local_camera"]
        .includes(e.input_provenance)
      || typeof e.detector_score !== "number"
      || !Number.isFinite(e.detector_score)
      || e.detector_score < 0 || e.detector_score > 1
      || e.detector_score_type !== "uncalibrated_heuristic"
      || e.score_calibrated !== false
      || e.confirmed_fall !== false
      || e.human_review_required !== true
      || e.medical_assessment_performed !== false
      || typeof e.simulated !== "boolean"
      || !Array.isArray(e.evidence_refs) || e.evidence_refs.length !== 0
      || e.delivery_mode !== "local_stdout_only") {
    return reject("invalid version, provenance, timestamp, score or safety flags", row);
  }
  if ((e.input_provenance === "synthetic_pose_trace") !== e.simulated) {
    return reject("simulated flag and declared input provenance disagree", row);
  }
  // Object returned only contains the canonical safe contract, never extra fields.
  return e as EdgeCandidateV1;
}

/**
 * Text must come from an explicit local File picker (or the synthetic fixture).
 * The browser stores only this parsed metadata in React memory until Reset.
 * Empty JSONL is a valid NO CANDIDATE event stream, NOT a true-negative metric.
 */
export function parseEdgeCandidateJsonl(
  raw: string,
  displayLabel = "Local candidate file",
): LocalReplay {
  if (typeof raw !== "string" || raw.length > MAX_LOCAL_CANDIDATE_BYTES
      || new TextEncoder().encode(raw).byteLength > MAX_LOCAL_CANDIDATE_BYTES) {
    throw new Error("Local candidate file too large (maximum 256 KiB)");
  }
  const cleaned = raw.replace(/^\uFEFF/, "");
  const lines = cleaned.split(/\r?\n/);
  if (lines.length > MAX_LOCAL_CANDIDATES + 2) {
    throw new Error("Too many candidate lines (maximum 100)");
  }
  const events: EdgeCandidateV1[] = [];
  const seenEvents = new Set<string>();
  const sourceTimes = new Map<string, number>();
  lines.forEach((line, i) => {
    if (!line.trim()) return;
    if (line.length > MAX_LINE_CHARACTERS) {
      reject("event record is too long", i + 1);
    }
    let decoded: unknown;
    try {
      decoded = JSON.parse(line) as unknown;
    } catch {
      reject("invalid JSONL (one JSON object per line)", i + 1);
    }
    const entry = validated(decoded, i + 1);
    if (seenEvents.has(entry.event_id)) reject("duplicate event UUID", i + 1);
    seenEvents.add(entry.event_id);
    const previousTime = sourceTimes.get(entry.source_id);
    if (previousTime !== undefined && entry.source_timestamp_ms < previousTime) {
      reject("timestamps must be nondecreasing per source", i + 1);
    }
    sourceTimes.set(entry.source_id, entry.source_timestamp_ms);
    events.push(entry);
  });
  if (events.length > MAX_LOCAL_CANDIDATES) {
    throw new Error("Too many events for local replay");
  }
  const label = typeof displayLabel === "string"
    ? displayLabel.slice(0, 80).replace(/[\x00-\x1F]/g, "")
    : "Local candidate file";
  return {
    events,
    sourceIds: [...sourceTimes.keys()],
    expectedNegative: events.length === 0,
    displayLabel: label,
  };
}

export function formatSourceOffset(ms: number): string {
  if (!Number.isSafeInteger(ms) || ms < 0) return "invalid relative offset";
  const seconds = Math.floor(ms / 1_000);
  const remainder = ms % 1_000;
  return `+${seconds}.${String(remainder).padStart(3, "0")} s`;
}
