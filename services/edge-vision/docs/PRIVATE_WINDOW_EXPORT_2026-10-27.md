# VIIL Sentinel — private, consent-gated Pose-to-Window Exporter

**Member 1 | 2026-10-27 | research-only; not a deployment-ready fall detector**

## Implementation status

A `sentinel_edge.window_export` pipeline can now read **reviewed,
locally authorized videos**, run the installed official MediaPipe Pose
Landmarker Lite on the machine, and build **30 time-aligned samples × six
masked temporal motion channels** for the previously implemented NumPy
Temporal Logistic research trainer. It never sends media to a remote
service, does not display video, and keeps at most 30 sampled pose frames
per clip (instead of retaining all frames).

**Verified with real video:** the previously locally authorized IKAR
`slips_0.mp4` staged-volunteer video was processed by the actual local
MediaPipe model in RAM: 87 video frames decoded, 30×6 features generated,
30/30 sampled slots with valid pose. **No fall/ADL label was assigned,
nothing saved, and no supervised training was performed on that video.**

The IKAR pilot dataset currently contains only staged Fall recordings and
does NOT support the required Fall+ADL, subject-disjoint
Train/Validation/Test protocol. The actual classifier still has only
the earlier **fictional/synthetic** fit evidence, not real-world accuracy.

## Mandatory input files

**A. Groups manifest v2**, exactly the schema accepted by
`sentinel_edge.split_audit`. Every clip must have:

```json
{
  "clip_id": "fictional-subject-a-take-01",
  "dataset_id": "consented-study",
  "subject_id": "fictional-subject-a",
  "recording_id": "fictional-take-01",
  "split": "train",
  "expected_fall": false,
  "media_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

Use **verified** subject IDs, recording/take IDs and source SHA-256 checksums
for real media, not invented equivalents. Full manifest fields are:
`version: 2`, `permission_basis`, `clips`. Subjects/recordings/videos
must be disjoint across train/val/test, with BOTH Fall and ADL samples
in each partition. The digest above is a *fake illustrative value*.

**B. Reviewed segment manifest v1**, saved beside the actual video files
(paths relative to this manifest's directory):

```json
{
  "version": 1,
  "segments": [{
    "clip_id": "fictional-subject-a-take-01",
    "video": "some-private-sample.mp4",
    "start_ms": 1000,
    "end_ms": 4000,
    "expected_fall": false,
    "label_reviewed": true,
    "annotation_basis": "Human-reviewed continuous normal walking throughout the interval"
  }]
}
```

Every clip in groups-v2 MUST have one matching manually reviewed segment;
label must agree with the group record. The training label belongs only
to the **selected time interval**, not to the entire parent file. An
annotator must check whether a Fall-labelled interval actually contains
the fall event, and whether an ADL interval contains NO fall. The program
cannot prove the annotator's judgment or legal consent is truthful.
No automatic event-onset annotation is fabricated. Each interval must
last **900–8000 ms**; source videos are limited to 512 MiB and 6000 frames
per clip, and the entire run to 64 clips and 30,000 decoded frames.

## Run only on explicitly authorized material

Create the ignored output directory within
`D:\VIIL-Sentinel\data\private\research` first, then from
`D:\VIIL-Sentinel\services\edge-vision`:

```powershell
.\.venv\Scripts\python.exe -m sentinel_edge.window_export --groups "D:\VIIL-Sentinel\data\private\research\groups-v2.json" --segments "D:\VIIL-Sentinel\data\private\research\segments-v1.json" --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" --output "D:\VIIL-Sentinel\data\private\research\derived-30frame-windows.json" --confirm-consent --acknowledge-pose-privacy

.\.venv\Scripts\python.exe -m sentinel_edge.temporal_training --manifest "D:\VIIL-Sentinel\data\private\research\groups-v2.json" --features "D:\VIIL-Sentinel\data\private\research\derived-30frame-windows.json"
```

**Fail-closed:** without both explicit confirmations, group/segment
agreement, local media hashes, and verified 3-way group separation, the
command refuses to process the video. Output is created **exclusively**
in repo `data/private`, refuses overwrites and symlink/path escapes,
and is never auto-uploaded. **Derived landmarks/features themselves
can be biometric/sensitive**, so they remain private even though images
and raw landmark coordinate traces are not saved.

The sampler creates a 30-step uniform time grid, picks the nearest
locally observed pose to each target (within max 90ms or approximately
half the step), uses missing masks rather than repeat frames for gaps,
and requires at least 10 observed poses out of 30. It uses image-plane
kinematics, not physical speed in meters/second. No model is
trained until explicit separate training invocation.

## Remaining limitations

- Label quality and participant identity declarations require independent
  curator verification; a JSON Boolean is not evidence of consent.
- Existing IKAR eight-positive staged clips are not sufficient for the
  required binary Fall/ADL dataset and were **not relabeled** as ADL.
- Temporal Logistic is only a tiny NumPy research baseline. The window
  export and its checks do not establish classification performance,
  event latency or real-world safety.
- A future study should benchmark false alarms per verified normal
  activity exposure hour, fall onset latency, and generalization to unseen
  individuals under a pre-registered evaluation protocol.
