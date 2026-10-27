# VIIL-Sentinel — Real ASSIST-IoT Pose Rejection Root-Gate Audit (Member 1)
27 October 2026 · Public publisher-labeled reference clips · RESEARCH ONLY

## Scope and privacy

This work diagnoses the *original unchanged* MediaPipe torso adapter
when it returns no valid body landmarks. It adds a categorical
`pose_reason_consumer` **only to opt-in offline video research**.
The production `extract_torso_landmarks`, default camera/edge event
stream, 0.55 threshold and multi-person abstention are unchanged.
Raw video, human landmarks, joint coordinates, face pixels, individual
probabilities and per-frame timestamps **are not saved**; report includes
only public activity names and aggregate integer counters.

The extra reason names are `accepted`, `no_person`,
`multiple_people`, `malformed_result`, `malformed_torso`,
`missing_visibility`, `invalid_numeric`, `out_of_frame`,
`low_visibility`, `low_presence`. They match the same first
strict rejection gate as the original adapter; tests check parity.
Exactly one category must account for each decoded frame, and
`accepted` must match the actual accepted torso frame count. Any
mismatch aborts. **'Multiple people' means MediaPipe returned
more than one pose; it does NOT prove several real human beings.**
No policy change to select one pose is authorized or made.

## Immutable input and model

Source ASSIST-IoT: https://github.com/ASSIST-IoT-SRIPAS/multimodal-fall-detection-dataset
(CC BY 4.0; pinned commit `7a11c96b9a3576cef92f0795a19b3786c69a3335`).
11 source-Git-hash verified MP4 reference videos:
8 hard-negative ADL and 3 staged Fall examples.

The existing private joint CAUCAFall/GMDCSA-24 research V1 model
is frozen to SHA256
`2e55abd9657148a5fb17c3291c96841c31d030695c18116e0da70d6489aec3ab`
and threshold 0.53, previously chosen from separate development
Validation. This round did **not train**, change any weights, tune
thresholds or wire an automatic alert. These external reference
videos have been seen before and are **exposed diagnostics**, NOT
untouched human-subject-disjoint test data. Class labels and
event onset are not independently human-reviewed.

## Actual result — all 11 real MP4s

| Frozen torso adapter category | ADL 8 videos | Fall 3 videos |
|---|---:|---:|
| Decoded frames | **1,838** | **1,558** |
| Accepted torso frames | 1,520 | 698 |
| Total rejected | 318 | **860** |
| `no_person` | 252 | 0 |
| `multiple_people` | 51 | **860** |
| `out_of_frame` | 15 | 0 |
| Low visibility / low presence | 0 | 0 |
| All other rejection categories | 0 | 0 |

Fall videos by source activity:
- Forward fall walking: **395** multi-pose rejected, 121/516
  accepted frames, 2/3 windows pose-eligible, no fall candidate.
- Backward fall: **465** multi-pose rejected, 124/589 accepted,
  1/3 windows pose-eligible, no fall candidate.
- Vertical fall/faint: **0** rejected; 453/453 accepted,
  2/2 windows pose-eligible, STILL no fall candidate.
- Neither the original temporal heuristic nor the frozen joint V1
  signaled any of these 3 publisher-labeled Fall references.

**Observed engineering gap:** 860/860 frames rejected in the Fall
class were rejected because MediaPipe returned >1 pose. The next
investigation must differentiate real nearby people from duplicate
detections/foreground-background confusion on new approved footage.
It is **unsafe to select the most confident pose automatically**
without new validation. A distinct gap remains in temporal fall
recognition: the completely pose-covered fainting clip was missed.

## Reproduce locally; no webcam / cloud uploads

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$private = "D:\VIIL-Sentinel\data\private"

& $py -m sentinel_edge.assist_external --mode reason-audit `
  --root "$private\public-datasets\assist-iot-external" `
  --model "$private\joint-cauca-gmdcsa-v1-publisher-research-20261027.json" `
  --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --report "$private\assist-pose-rejection-reason-audit-20261027.json" `
  --acknowledge-publisher-labels --acknowledge-pose-privacy

& $py -m pytest -q
& $py -m ruff check .
```

The report is exclusively created at the private path above and
never overwritten. Choose another private filename for another run.
No private data or model weights may be pushed to Git.

## Next developer action

1. Evaluate strict multi-person detection on **newly licensed,
   consented, independently reviewed development footage**:
   count genuine multi-person scenes versus duplicate detections;
   use privacy-minimized labels and never suppress a real second person.
2. Explore a *research-only* bounded tracking/association proposal
   with explicit ambiguity abstention, without altering live
   detector until new Train/Validation, scene and person-disjoint
   tests support it.
3. Address 453/453 fully visible fainting Fall missed by BOTH
   heuristics and classifier through actual fall-onset annotations
   and new temporal training data, NOT threshold tuning against
   this already inspected external set.
4. Collect properly annotated long ADL sequences and event-level
   false alarms/hour, detection latency and target-device resource
   metrics before any production safety or alarm claims.

Member1 topic integration allowed only in `member/feature/preprod`;
`preprod` and `main` are protected and human-controlled.
