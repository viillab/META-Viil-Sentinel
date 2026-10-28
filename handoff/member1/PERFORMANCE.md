# Member 1 — performance, RAM, storage, speed and decisions

28 October 2026 · Read-only hardware facts + measured prior experiments
**Not hardware-independent guarantees; NOT verified fall-onset latency.**

## Actual local disk sizes (measured this turn)

Read-only inspection on authorized Windows developer machine:

| Component | Actual size | Meaning |
|---|---:|---|
| Official MediaPipe Pose Landmarker Lite .task | **5,777,746 bytes (5.51 MiB)** | Dominant runtime *model file*; requires lawful local asset |
| Edge Python .venv | **372,087,360 bytes (354.85 MiB)** | Installed full developer environment, *NOT a release binary* |
| Linear 30D model (90 float64 coefficients + bias and threshold) | **736 bytes of numeric parameters** | 30 mean + 30 scale + 30 weights + 2 scalars; does not include Python, OpenCV, MediaPipe, metadata or RAM overhead |
| New 1500ms private research weight JSON | **2,654 bytes (2.59 KiB)** | Real newly fitted CAUCAFall weight file; strict schema, source digests and 736B numeric coefficients; Git-ignored |

**Small classifier weights do NOT imply the camera application needs
736 bytes of memory.** The MediaPipe runtime and video decoding dominate
RSS. Never conflate numeric model size, disk deployment size, entire
Python environment or native process working set. No Torch or CUDA
runtime has been added.

## Real prior Windows video replay (already source-verified, 27 Oct)

The prior repeatable-protocol reports are:
- [Real Edge Replay Resource Profile](../../services/edge-vision/docs/REAL_EDGE_REPLAY_RESOURCE_PROFILE_2026-10-27.md)
- [Persistent Pose Session Profile](../../services/edge-vision/docs/PERSISTENT_POSE_SESSION_RESOURCE_HANDOFF_2026-10-27.md)
- [Streaming Evaluation Efficiency](../../services/edge-vision/docs/PERFORMANCE_EFFICIENCY_2026-10-27.md)

These are actual 8 already-exposed IKAR staged-Fall clips on a Windows
development workstation (NOT live webcam, NOT unseen ADL negatives).

| Measured run | Complete frames | End-to-end replay FPS | Max sampled process RSS |
|---|---:|---:|---:|
| Original per-file MediaPipe, native video | 889 | **24.62** | **248.24 MiB** |
| One persistent PoseLandmarker across 8 staged files | 889 | **28.62** | **241.82 MiB** |
| Per-file experimental 512px cap | 889 | **24.99** | **245.20 MiB** |

Persistent session reuses one native model instance but accepted 823
torso frames versus 831 for per-file initialization. Therefore its
apparent speed gain is **not proof of better detection** and shared
tracking can leak across independent clip boundaries. These measurements
were not repeated/paired to eliminate CPU, disk cache and temperature
variance. 512px changed original heuristic event counts from 1 to 2;
**DO NOT promote 512px to production** without proper validation.

The 1500ms model and shadow added recently have no claim of better
full decode FPS. Prior 1500ms research trained from 40 source-pinned
CAUCAFall videos: only 31 eligible, old staged publisher test detected
1/3 eligible staged Falls, missed 2/3, with 2/2 available ADLs
scored negative; 2 other test ADLs abstained. **NOT field accuracy.**
A full streaming round trip plus real trained short weights is a
research-only integration check, not an event-onset response benchmark.

## New real TRAINED 1500ms artifact to shadow smoke (this turn)

Successfully trained a new genuine 1500ms logistic classifier in memory
on 40 original CAUCAFall publisher-labeled staged videos and exported
a **2,654-byte private JSON artifact**. The loader checked all fields
and bitwise reload parity of all 30D mean/scale/weights, bias and
threshold. Git ignore was independently checked: data/private/ is
excluded by .gitignore line 26. No video, pose or weight was pushed.

One original source SHA256-pinned **TRAIN ADL** clip was replayed into
the **ACTUAL trained** private 1500ms predictor through the new
Causal1500msModelShadow. This is an end-to-end research wiring test,
not a human-reviewed event accuracy test:

| Actual measurement from ONE source on this Windows PC | Value |
|---|---:|
| Source frames fully decoded / verified | **115/115** |
| Wall time including MediaPipe and video decode | **6.013 seconds** |
| End-to-end one-clip file replay throughput | **19.12 FPS** |
| Trained 1500ms shadow windows scored | **12** |
| Pose abstention windows | **5** |
| Max PoseFrame objects in rolling shadow | **32** |
| Process RSS before clip run | **45.21 MiB** |
| Process RSS after clip run | **108.58 MiB** |
| Verified numeric classifier parameters | **736 bytes** |
| Private model JSON footprint | **2,654 bytes** |

RSS values are two point-in-time process samples; **neither is peak
RSS**, and they cannot be compared to different processes or MediaPipe
sessions without an equivalent protocol. There is no measured p95
capture latency or proof of meeting a steady-state 30 FPS camera
target. This original clip contains publisher ADL labels only and is
already part of the research training set; it is NOT an independent
accuracy/FPR test. Zero *incidents dispatched* is a code guarantee of
the shadow output contract, not the model's false-positive rate.

## Practical model/runtime budget

1. **One pose model instance per genuine continuous camera session.**
   Avoid per-frame MediaPipe initialization or repeated OpenCV/video
   decoder opens. Explicit source reset/gap policy for rolling
   model state. Across unrelated prerecorded clips, sharing MediaPipe
   may carry hidden tracker state: use a fresh session or verify.
2. **On-device processing**: original BGR -> RGB -> MediaPipe Lite,
   keep only the four torso landmark joints for original heuristic
   and minimal 30x6/1500ms rolling features for research. No image
   retention, no whole video or entire person keypoint history.
3. **Bounded memory**: 1500ms shadow limits PoseFrames to 256; source
   and >700ms gaps reset. With 250ms score hop (4 candidate
   evaluations/second MAX after warmup), tiny logistic matrix math
   should not be the dominant runtime cost, but p50/p95 must be
   measured on the actual target device.
4. **No new heavyweight libraries**: NumPy numeric training extra;
   lean local JSON wrapper only. No TensorFlow/PyTorch dependency or
   GPU assumption in this Member 1 release.
5. **Resolution/subsample optimization is NOT free**: before any
   lower resolution/FPS policy, measure how Pose availability,
   ambiguous multi-person abstention, 30 timestamp slots and
   event detection change on **human-reviewed** independent Fall/ADL
   samples. Never quietly promote from one favorable speed run.
6. **No unnecessary files**: store only source manifest hashes and
   tiny numeric parameters in ignored data/private. Do not store raw
   frames, pose buffers, per-event scores, photo evidence or
   reviewer identities in Git. No automatic deletion of private
   datasets or already existing weights.

## Remaining before claiming "fast, lightweight and accurate"

- Cold-start and 30+ minutes steady-state webcam/video capture on
  target machine; capture-to-frame, decode/pose, feature/smoothing,
  last-hop and backend notification timing separately.
- Compare at least 3 repeat runs under matched video set and
  measured CPU load. Record wall FPS p50/p95, process RSS p95 and
  max sampled, actual package sizes, disk and power/thermals.
- Independently human-reviewed fall onset/offset, unseen subjects
  and cameras, long ADL/no-fall negatives and multi-person cases.
  Report event recall, false alarms per verified no-fall hour,
  abstention rates, event-onset delay p50/p95, and uncertainty.
- Demonstrate Member 2 authenticated ingestion + rate limiting/
  idempotency and Member 3 human-confirmed notification workflow;
  until then, no real-time operational readiness.
