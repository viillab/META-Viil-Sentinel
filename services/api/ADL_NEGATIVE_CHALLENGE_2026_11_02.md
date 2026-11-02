# VIIL-Sentinel — ADL Negative Challenge + Synthetic Stress (2026-11-02)

**Member 2 | executed locally | real staged licensed video, frozen review-only V2 |
no Meta API calls, image uploads, caregiver alerts or automatic dispatch**

## Why this check matters

On five research development videos the experimental V2 returned 3/3
fall-labeled *review* candidates; on five previously inspected videos it
returned 2/3. Neither is blind/actor-disjoint validation. The biggest known
danger is mistaking **voluntary sitting** or **bed repositioning** for a fall.
This milestone tests the *two remaining* unused ADL videos from the same
dataset, and separately exercises eight purely fictional ADL motion patterns.

We **did not tune thresholds** based on these two negative challenge clips;
the frozen `ReviewMotionConfig()` remains:
rapid window 650 ms, minimum hip descent 0.16 normalized, minimum angular
change 20°, semi-horizontal final angle 38°, horizontal gate 60°, hold 280 ms,
event window 1100 ms, cooldown 4000 ms, visibility ≥0.55. The V1
`TemporalFallDetector` and Member 1 runtime were not modified.

## Data origin, license and privacy

- Upstream: [samruddhi-2308/FallDetectionDataset](https://github.com/samruddhi-2308/FallDetectionDataset);
  source [index](https://github.com/samruddhi-2308/FallDetectionDataset/blob/main/metadata/clips_index.csv).
- License: [CC BY-NC 4.0](https://github.com/samruddhi-2308/FallDetectionDataset/blob/main/LICENSE);
  attribution required and noncommercial use only. Staged videos include identifiable people.
- Source Git tree: `2ea3acbb74db88a4c2d584b3b5a631f180b490f6`.
- Media download used pinned source paths and verified exact file sizes,
  upstream Git blob IDs and **independently pinned SHA-256**. All images
  and the derived torso pose traces stay in
  `D:\VIIL-Sentinel\data\private\adl_negative_challenge_v1\` (Git ignored).
- Subject identities are **not confirmed independent** across any clips.
  Shared actors and settings can make results easier than deployment.
- No clip or person-derived pose was uploaded to Meta, any model provider,
  GitHub or external telemetry. MediaPipe ran **locally on the full MP4**.
  Only aggregate, pseudonymous IDs and public source file hashes are committed.

## Actual two-new-video challenge

| Clip ID | Original public ADL MP4 | Decoded frames | Duration | V1 false candidate(s) | V2 false review(s) |
| --- | --- | ---: | ---: | ---: | ---: |
| FD0001 | `video_20260216_151903.mp4` | 326 | 5.432 s | 0 | 0 |
| FD0005 | `video_20260223_151242.mp4` | 448 | 7.481 s | 0 | 0 |
| **Total** | ADL, nonfall label | **774** | **12.913 s** | **0** | **0** |

Actual video SHA-256:
- FD0001: `737ce8f78042fe166fff8d64de7372fb2d8c44ef19945f27f40046e499746000`
- FD0005: `eaacb0bc568de95547d302b711ad7f4d69115b7beb11084d5c1748d8221174a8`

The false-candidate rate estimate of 0 events in *12.879 seconds of
analyzed first-to-last frame span* provides **no reliable estimate** of
the false alerts per hour in a hospital or residence.

### All six real ADL clips from this source

The previous two diagnostic ADL clips plus the prior two development
ADL clips and the two fresh challenge clips were replayed from
hash-checked private source videos and local poses, **without re-uploading
media**.

| ID | Cohort | Frames | Observed trace span | V1 | V2 review |
| --- | --- | ---: | ---: | --- | --- |
| FD0002 | Previously inspected | 101 | 1.699 s | 0 | 0 |
| FD0003 | Previously inspected | 93 | 1.839 s | 0 | 0 |
| FD0004 | Previously inspected dev | 166 | 2.749 s | 0 | 0 |
| FD0006 | Previously inspected dev | 223 | 4.439 s | 0 | 0 |
| FD0001 | Fresh challenge | 326 | 5.415 s | 0 | 0 |
| FD0005 | Fresh challenge | 448 | 7.464 s | 0 | 0 |
| **Total** | **6 distinct clip IDs** | **1,357** | **23.605 s** | **0** | **0** |

**Critical limit:** all six come from the same source dataset and total
only about 24 seconds. Zero FP on this minuscule selected collection
is **not proof** the model avoids false alerts. The two fresh samples
are not subject-disjoint, and the previous four were already seen.

## Eight fictional ADL scenarios reveal unaddressed false alerts

The new `app.synthetic_adl_stress` generates only original four-landmark
**fictional geometry**, not people, photos, hidden faces or acquired video.
It runs the actual V1 and actual experimental V2 code with untouched
thresholds.

| Synthetic *nonfall* movement | V1 candidate(s) | V2 review candidate(s) |
| --- | ---: | ---: |
| Stationary standing | 0 | 0 |
| Stationary lying | 0 | 0 |
| Gradual controlled sitting | 0 | 0 |
| **Rapid voluntary sitting** | **1** | **1** |
| Quick bend without hip descent | 0 | 0 |
| **Rapid voluntary bed shift** | 0 | **1** |
| Low-visibility interruption | 0 | 0 |
| Camera/source identity change | 0 | 0 |
| **Total 8 synthetic nonfall cases** | **1** | **2** |

These two V2 false review flags prove an ambiguity in the chosen
normalized 2D torso geometry, *despite* the result of 0/6 observed
negative video clips. The eight fictional cases are not sampled real-world
movements and cannot be converted to a population-level false alarm rate.

**V2 is still strictly REVIEW-ONLY.** A review proposal has
`fall_confirmed=false`, `notification_authorized=false`,
`meta_upload_authorized=false`. No auto alarm, medical diagnosis,
actual emergency dispatch or live Meta tool action was added.

## Reproduction

In `D:\VIIL-Sentinel\services\api`:

```powershell
# Public research dataset download only, CC BY-NC terms acknowledged:
.\.venv\Scripts\python.exe -m app.adl_negative_challenge --download --acknowledge-noncommercial-license

# FIRST RUN ONLY: actual local MediaPipe MP4 extraction to ignored private pose traces:
.\.venv\Scripts\python.exe -m app.adl_negative_challenge --extract --acknowledge-noncommercial-license

# Re-evaluate two new negative clips from already extracted pose traces:
.\.venv\Scripts\python.exe -m app.adl_negative_challenge --evaluate --acknowledge-noncommercial-license

# Replay all six known ADL clips, including the previously inspected cases:
.\.venv\Scripts\python.exe -m app.adl_negative_challenge --summarize-six --acknowledge-noncommercial-license

# Original fictional, negative motion stress; NO video, camera or network:
.\.venv\Scripts\python.exe -m app.synthetic_adl_stress

# Offline CI tests (fixtures only, no dataset download):
.\.venv\Scripts\python.exe -m pytest -q tests/test_adl_negative_challenge.py
.\.venv\Scripts\python.exe -m ruff check .
```

Private machine-readable outputs:
`data/private/adl_negative_challenge_v1/negative-challenge-report.json`
and `.../all-six-adl-summary.json`.

The two extracted MP4s and their `*.pose.jsonl` are ignored; do not
run `git add -f` on them or share raw media. Extraction refuses to
overwrite previous pose traces. The evaluator refuses missing traces,
mismatched SHA-256/size/Git blob, symlinked media, unexpected clip IDs
or altered frame counts. CI synthetic scenarios are self-contained and
do not access any private file or provider.

## Release decision and next research work

**NO-GO for unattended automatic fall alarms**. Current positives remain
missable (the V2 regression still misses FD0012), and synthetic rapid
sitting/bed-repositioning demonstrate known false positive risks.

For the next milestone, acquire/label **actor-disjoint and genuinely new**
long-form negative recordings of fast sitting, lying down, bed shifts,
bending, kneeling, camera movement and occlusions; require clear
per-subject privacy permission and source licenses. Evaluate review
burden per video-hour and fall onset latency on a *separate* blind set,
with frozen preprocessing and thresholds. Consider multi-joint
temporal tracking and explicit abstention states. Do not authorize
production alerts or Meta uploads on these results alone.

Original Member 1 Edge source files and unrelated Flutter/dashboard
directories are untouched. The local Meta test budget remains exhausted
at 4/4 approved attempts, and this milestone made 0 paid Meta calls.
