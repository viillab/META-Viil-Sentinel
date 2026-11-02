# VIIL-Sentinel — Experimental Review-only Motion Detector V2 (2026-11-02)

**Actual local research run, 10 human-performed staged MP4 clips across two small cohorts. NOT clinically valid. NOT live safety detection. NO Meta API calls.**

## Why

On the original 5 video diagnostic cohort, Member 1's temporal heuristic missed 3/3 fall-labeled clips despite MediaPipe having extracted usable torso poses from 660/667 frames. Review-only V2 tests **two bounded motion hypotheses** rather than requiring an upright posture:
- `rapid_descent_rotation`: significant normalized hip descent together with a torso angular change, followed by a briefly sustained semi-horizontal posture.
- `horizontal_descent`: hip descent while already broadly horizontal, followed by a briefly sustained horizontal posture.

**Important:** V2 is *not* deployed into Member 1's Edge runtime, Core API event ingest or notification routes. Its outputs are internal `ReviewMotionCandidate` objects with strict `review_only=true`, `fall_confirmed=false`, `notification_authorized=false`, `meta_upload_authorized=false` and `probability_calibrated=false`.

The parameters were defined as engineering hypotheses **before** running the new development comparison. After observing the development result, they were not adjusted to pass individual clips. The original 5 examples were previously inspected in detail before any V2 coding; their later evaluation is explicitly labeled **non-blind, leakage-prone regression**, not true held-out verification.

## Sources, license, privacy

Same source repository: [samruddhi-2308/FallDetectionDataset](https://github.com/samruddhi-2308/FallDetectionDataset), noncommercial **CC BY-NC 4.0** with attribution. Source class labels appear in [clips_index.csv](https://github.com/samruddhi-2308/FallDetectionDataset/blob/main/metadata/clips_index.csv). Upstream Git tree object: `2ea3acbb74db88a4c2d584b3b5a631f180b490f6`.

New development set **has five different clip IDs** from the original five; participant identity equivalence or actual subject-independent separation **cannot be proven** from this metadata alone. This is not evidence of generalization.

Videos may contain identifiable individuals. Five new MP4s, pose JSONLs and both comparison reports are under Git-ignored `data/private/public_fall_devset_v1`; the original cohort stays in `data/private/public_fall_video_probe_v1`. **No video, pose landmark, screenshots, biometric data or MediaPipe model asset is committed to Git, sent to Meta, or used for alerts.** Original dataset files are externally downloaded only from the cited research repository; model execution is offline.

Each newly downloaded video has been size-checked, matched to upstream Git blob SHA-1 and *also* pinned to its locally verified SHA-256. All five were processed through the unchanged local OpenCV + MediaPipe PoseLandmarker runner and converted to private JSONL traces with full-frame counts.

## Development-only cohort: actual output

| ID | Publisher's category | Video frames | V1 candidate | Review V2 candidate |
| --- | --- | ---: | --- | --- |
| FD0034 | standing_to_fall | 133 | Yes | Yes (rapid_descent_rotation) |
| FD0011 | sitting_to_fall | 216 | Yes | Yes (rapid_descent_rotation) |
| FD0024 | sleeping_to_fall | 346 | **No** | Yes (horizontal_descent) |
| FD0004 | adl_no_fall | 166 | No | No |
| FD0006 | adl_no_fall | 223 | No | No |
| **Total** | 3 Fall + 2 ADL | **1,084** | **TP2/FN1/FP0/TN2** | **TP3/FN0/FP0/TN2** |

For these five selected clips only, V1 **Recall 2/3 (66.7%) and F1 0.8**, while the V2 review proposal **selected 3/3 fall-labeled clips and no ADL clips** (conventional clip-label F1 1.0). These are **NOT** actual fall-confirmation accuracy, calibrated probabilities, independent validation or expected field performance. No onset timestamps are available for these five; latency was not measured.

## Previously inspected 5-clip non-blind regression

**This was NOT a valid blind test set:** the three specific failure types of these clips were documented *before* V2 was designed. This regression is useful for testing code behavior and nothing more.

| ID | Publisher category | V1 | V2 Review-only |
| --- | --- | --- | --- |
| FD0033 | standing_to_fall | No | Yes (rapid_descent_rotation) |
| FD0012 | sitting_to_fall | No | **No (still missed)** |
| FD0032 | sleeping_to_fall | No | Yes (horizontal_descent) |
| FD0002 | adl_no_fall | No | No |
| FD0003 | adl_no_fall | No | No |
| **Total** | 3 Fall + 2 ADL | **TP0/FN3/FP0/TN2** | **TP2/FN1/FP0/TN2** |

Observed V2 recall on these inspected clips = 2/3 (66.7%); **NOT** a generalization estimate.

## Key risks, unresolved failure and deliberately preserved safeguards

- Synthetic safety tests demonstrate that **rapid voluntary sitting can trigger V2**, because four torso landmarks cannot reliably tell intentional sitting apart from falling. Every flagged result requires human review. **Do not deploy V2 as an unattended alarm.**
- Original ID FD0012 remains a missed fall even after V2. Do not silently lower thresholds to fit this already-inspected case. Instead inspect independently annotated motion timing, camera view and person tracking.
- A sample of four total ADL clips covers only a few seconds of benign movement, so **FP=0/4 says almost nothing about false alarms per hour**. Future negative data should include brisk sitting, lying down, bending, kneeling, rolling in bed and occlusions.
- This is a **small, convenience-selected, single-dataset experiment**, not a randomized, subject-disjoint study. Possible participant overlap, camera correlation and annotation uncertainty are unresolved.
- Model does not estimate injuries, medical severity, consciousness, or safe action. Camera access, caregiver notifications and Meta inference remain unchanged/disabled.

## Reproduce the development result locally

From `D:\VIIL-Sentinel\services\api` with Python Edge video extras installed:

```powershell
# Acquires *five separate* development clips; validates pinned Git and SHA-256.
.\.venv\Scripts\python.exe -m app.dev_video_research --download --acknowledge-noncommercial-license

# First time only; produces private five-clip pose traces and manifest.
# Refuses to overwrite private traces.
.\.venv\Scripts\python.exe -m app.dev_video_research --extract --acknowledge-noncommercial-license

# Offline original heuristic baseline, without running video/Meta models.
.\.venv\Scripts\python.exe -m app.dev_video_research --baseline --acknowledge-noncommercial-license

# V1 vs V2 review proposals using only development poses.
.\.venv\Scripts\python.exe -m app.review_dev_comparison --compare-dev --acknowledge-noncommercial-license

# Nonblind regression on previously inspected five clips ONLY.
.\.venv\Scripts\python.exe -m app.review_dev_comparison --compare-inspected --acknowledge-noncommercial-license

.\.venv\Scripts\python.exe -m pytest -q tests/test_experimental_review_motion.py tests/test_dev_video_research.py
.\.venv\Scripts\python.exe -m ruff check .
```

The comparison writes privacy-scoped, **aggregate-only** JSON under the two `data/private` folders. The default Edge runtime and caregiver backend are not modified. All model calls are local MediaPipe or trace replay. The previous paid Meta ledger remains 4/4 exhausted, with no billable calls made here.

## Recommended next milestone

1. Establish independently annotated **actor-disjoint** development and blind test sets with an expanded ADL denominator, explicit fall-onset times and license/consent audit.
2. Add an uncertainty/abstention policy, camera-geometry adaptation, multi-person tracking and a *human-approved* case-review workflow before any real use.
3. Introduce calibration only on designated development data, freeze thresholds and validate on a genuinely unseen independent dataset. Report recall, false alerts per video-hour and time-to-first-candidate.
4. Do not merge experimental review V2 into Member 1's production Edge path until Member 1 and project maintainers review tests, ground truth and limitations.

**Development owner:** Member 2 research tooling under `services/api/app`. No Member 1 detector or mobile/dashboard files were changed.
