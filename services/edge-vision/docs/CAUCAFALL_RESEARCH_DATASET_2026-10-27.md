# Member 1 — Real CAUCAFall annotation curation and pilot (27 Oct 2026)

**Local research, not clinical fall detection or a deployment release.**

## Source and licensing

The already-downloaded CAUCAFall *OmniFall-format derivative* comes from
[Zenodo record 17170592](https://zenodo.org/records/17170592), whose
record declares CC BY 4.0; the original CAUCAFall is hosted by
[Mendeley Data](https://data.mendeley.com/datasets/7w7fccy7ky/4),
also described under CC BY 4.0. Maintain source/author attribution,
preserve original annotations, respect participant privacy and independently
review commercialization/public redistribution rights.

Private local files (NOT in Git):
`D:\VIIL-Sentinel\data\private\public-datasets\caucafall-omnifall\extracted\Cauca_fall\`

- Downloaded archive 173,504,611 bytes, official MD5 verified
  `5a1899fe0022c9c4c0d37ce64ac0c986`, full ZIP CRC clean.
- 516 AVI clips in extracted repack; 258 lines of *MMAction2 annotations*
  and 258 rows of `caucafall.csv`. **Only the 258 annotated crop paths
  are eligible**; the 258 other AVI files are not separately labeled.
- Subject.1 through Subject.10 present; the publisher's 10-class labels
  are: 0 walk (47), 1 fall motion (50), 2 fallen (48), 3 sit_down (10),
  4 sitting (20), 5 lie_down (1), 6 lying (1), 7 stand_up (16),
  8 standing (32), 9 other (33).
- Both the original CSV and the MMAction2 annotation file are parsed.
  Each clip's label/subject, original source take, and original start/end
  interval must match before curating it; a filename alone cannot
  establish a normal-activity label.

## Conservative binary pilot definitions

Fall = **publisher class 1 fall motion only**, with original source
category `side`, `forward` or `backwards`.

No-fall/ADL = publisher classes **0, 3, 4, 7, 8** **only when the
original CSV source group is `adl/`**.

This explicitly excludes class 2 `fallen` (post-fall state), classes
5/6 (lying/moving down), class 9 `other`, and apparent normal
pre-fall/post-fall segments cut out of *Fall* source recordings.
This is a narrow research taxonomy, not proof that every sampled
interval has been independently visually checked.

## Deterministic subject-disjoint selection

Fixed participants (not chosen using model scores):

| Split | Publisher subject IDs | Fall-motion | ADL | Total |
|---|---|---:|---:|---:|
| Train | 1–6 | 12 | 12 | 24 |
| Validation | 7–8 | 4 | 4 | 8 |
| Held-out test | 9–10 | 4 | 4 | 8 |
| Total | 10 unique people | 20 | 20 | 40 |

For each subject, choose two separate valid original fall takes
(preference Forward then Right) and two distinct valid original ADL
takes (preference SitDown then Walk). All proposals require a decodable
AVI duration of 900–8000 ms, an on-disk SHA-256, and matching publisher
CSV / MMAction2 annotations. The named `recording_id` groups any crops
from the same original take. This dataset's labels are **publisher
annotations, NOT labels reviewed by the project user or assistant**.

The version-2 group manifest passes existing `split_audit.py`.
The proposal file deliberately uses **`label_reviewed=false`**:
the strict reviewed `window_export.py` will refuse it until each
segment is independently reviewed/accepted.

## Actual local private proposal files

Generated from the downloaded dataset without publishing/committing media:

- `caucafall-research-groups-v2.json` (SHA256 media and fixed split)
- `caucafall-review-proposals-v1.json` (video-relative segments,
  publisher source text, **review false**)

Both are saved in the extracted dataset root under `data/private`.
The curation CLI creates files exclusively (refuses overwrite) and
never uploads frames or derived pose.

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
.\.venv\Scripts\python.exe -m sentinel_edge.caucafall_curator --root "D:\VIIL-Sentinel\data\private\public-datasets\caucafall-omnifall\extracted\Cauca_fall" --groups-out "D:\VIIL-Sentinel\data\private\public-datasets\caucafall-omnifall\extracted\Cauca_fall\caucafall-research-groups-v2.json" --segments-out "D:\VIIL-Sentinel\data\private\public-datasets\caucafall-omnifall\extracted\Cauca_fall\caucafall-review-proposals-v1.json"
```

The above curation command is repeatable in an **empty** private destination;
it will refuse to overwrite the existing two outputs (delete/rename only after
explicit operator review).

## Publisher-labeled *research-only* pilot

The code also provides `publisher_label_pilot(...)` which:
- runs real MediaPipe PoseLandmarker locally on a 30×6 in-memory sequence,
- uses **only publisher class annotations** with explicitly unreviewed
  `label_reviewed=false`; never falsely marks external human verification,
- enforces the predeclared minimum **10/30 valid poses per clip**, recording
  exclusions by split and label,
- re-validates both classes remain in each split after exclusions,
- trains existing lightweight NumPy Temporal Logistic only on train
  subjects; selects threshold using validation subjects and tests on two
  unseen publisher subjects,
- returns aggregate metrics only; **does not persist trained weights,
  derived features or source video** and does not touch production alerts.

**The sample is tiny and volunteer-staged, selected with a pose-coverage
filter. Even good held-out scores cannot establish real-world accuracy,
false alarms per surveillance hour, fall-onset latency or safety.**
Any filtered test clips make the estimate conditional on successful pose
tracking; missing-pose rates must be reported, never silently omitted.

Manual video review of event boundaries, verification of actual subject
IDs and device-target multi-person testing remain necessary before
subsequent product development.

## Actual local publisher-labeled classifier pilot (not synthetic)

An actual MediaPipe Pose Landmarker Lite model (stored outside Git)
processed all **40** curated real-human *staged action* videos in-memory.
The fixed predeclared pose-quality gate requires >=10 observed pose slots
in each 30-slot window.

| Measurement | Train | Validation | Held-out test |
|---|---:|---:|---:|
| Initially selected Fall | 12 | 4 | 4 |
| Initially selected ADL | 12 | 4 | 4 |
| Pose-quality failures Fall | 0 | 1 | 0 |
| Pose-quality failures ADL | 1 | 1 | 2 |
| Eligible Fall | 12 | 3 | 4 |
| Eligible ADL | 11 | 3 | 2 |

**35 of 40** clips pass pose quality. The frozen two-subject test group has
only **6 eligible clips**, and two of its four ADL examples were excluded.
This severely limits claims about false alarms.

The trained baseline is the existing **five-bin 30-channel NumPy
Temporal Logistic** (NOT a TCN/GRU). Train-only normalization, validation-
only threshold calibration, and held-out test were executed for real
publisher-labeled videos. On this specific tiny test subset:

- Classifier threshold chosen using validation: **0.95**
- Held-out fall recall: **2/4 = 50%** (TP=2, FN=2)
- Held-out nonfall specificity: **2/2 = 100%** (TN=2, FP=0)
- Held-out precision: **2/2 = 100%** (but only two predicted positives)
- Validation: TP=2, FN=1, FP=0, TN=3
- **Original unmodified temporal heuristic**, on the EXACT SAME 6 eligible
  held-out videos: TP=0, FN=4, FP=0, TN=2; recall 0%. This is a fairer
  *in-sample-pilot* side-by-side comparison than using the unrelated IKAR
  clips, but six cherry-limited/pose-filtered cases remain insufficient
  for population-level inference.
- Train/validation/test subjects remain disjoint by publisher IDs.

**These figures are not deployable fall detection accuracy.** The
publisher's coarse per-clip labels were not independently reviewed;
pose-quality selection excludes 5 clips and biases the measured
population; ten volunteers staging movements do not represent accidental
falls or daily life in deployment. In particular **0 false alerts among
only 2 test ADLs is not evidence of a low false-alert rate**.
No exposure hours, real fall onset times, real-world sensitivity or
calibration bounds are established. The model remains in RAM only.
Human review, held-out uncertainty analysis, more ADL examples and
repeated cross-subject folds remain essential.

## Quality and privacy

- Only this source code, unit tests and instructions belong in Git.
- Private video, annotation files, group manifests and per-person features
  stay under Git-ignored `data/private`.
- No alert policy, false emergency dispatch or live Meta inference is
  modified.
