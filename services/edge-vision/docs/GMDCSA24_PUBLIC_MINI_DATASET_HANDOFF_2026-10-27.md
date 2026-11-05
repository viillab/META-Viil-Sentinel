# VIIL-Sentinel Member 1 — Public GMDCSA-24 Mini-Dataset Handoff
27 October 2026 · *Real publisher-labeled staged videos, unreviewed; research only*

## Why this fast path

We did **not** create additional private people videos. We found and
selected a fixed small set of public GMDCSA-24 recordings (Ekram Alam
et al., *GMDCSA-24: A dataset for human fall detection in videos*,
Data in Brief 57 (2024) 110892,
https://doi.org/10.1016/j.dib.2024.110892). Publisher's original
repository and declared MIT `LICENSE`:
https://github.com/ekramalam/GMDCSA24-A-Dataset-for-Human-Fall-Detection-in-Videos

**Immutable upstream revision:** `5abac7693229900cf80f722e878fbb119211fc1c`

Selection decided by fixed source filenames and provenance **before**
inspecting model predictions. The mini set contains **16 actual MP4s**,
8 staged Falls and 8 ADL clips across four distinct declared subjects,
**87,718,186 source bytes (~83.65 MiB)**. Class labels are directly
from the publisher's `Subject N/{Fall,ADL}` folders and descriptions
in `Subject N/{Fall,ADL}.csv`, **not independently reviewed**.
A published action interval can contain preparation, falling, aftermath
or sitting: binary `Fall` means that the video includes a staged
fall action, not that every 30-frame segment is falling. The private
manifest uses a single whole-video sampling window where possible,
so exact event onset still requires human verification.

## Exact split and scope

| Declared subject | Split | Fall / ADL |
|---|---|---|
| Subject 1 | train | 2 / 2 |
| Subject 2 | train | 2 / 2 |
| Subject 3 | validation | 2 / 2 |
| Subject 4 | test | 2 / 2 |

The chosen activities include sit-to-fall, walking-to-fall, forward/back/
sideways falls, lying/sitting, and daily activities under different
lighting/rooms. Actual scene and event properties remain publisher
descriptions; do not infer older-adult or real-accident coverage.

Data **must not** be mixed with prior CAUCAFall held-out test subjects
to tune model choice. If experimenting with new training hyperparameters,
freeze another never-seen subject/domain group first. Four subjects are
not sufficient to establish reliable field performance.

## Repeatable data acquisition

Source files and hashes are pinned in
`sentinel_edge/public_dataset_ingest.py` as a **hard allowlist of 16 paths**.
For each download it enforces the official Git blob SHA-1 object identity,
expected byte count and MP4 header; computes local SHA-256; refuses corrupt
existing files or manifest drift. Source is exactly the immutable upstream
GitHub commit; no arbitrary URLs or shell downloads accepted.
Only selected files are transferred; no full 1+ GB archive required.

Run in the normal repository, after the Member 1 merge:

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$root = "D:\VIIL-Sentinel\data\private\public-datasets\gmdcsa24-mini"

# Download or verify (idempotent if files and private manifests unchanged).
& $py -m sentinel_edge.public_dataset_ingest `
  --mode download --root "$root" --acknowledge-publisher-labels

# Offline REAL MediaPipe inference, NUMPY baseline and experimental V2.
# Do NOT add --dev-crossval: this mini has only three dev subjects,
# fewer than the predeclared eight-person CV prerequisite.
& $py -m sentinel_edge.public_dataset_ingest `
  --mode pilot --root "$root" `
  --model "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --acknowledge-publisher-labels

& $py -m pytest -q
& $py -m ruff check .
```

The importer creates only Git-ignored local data:
`data/private/public-datasets/gmdcsa24-mini/clips/subject-*/...`,
`gmdcsa-research-groups-v2.json`, and
`gmdcsa-publisher-proposals-v1.json`. Group IDs are pseudonymous
declared publisher subjects, record IDs are unique, SHA256 is computed
for each source file, and all splits contain both classes.

The pilot reuses exactly the streaming MediaPipe + nearest-sample
pose window implementation and the existing train-only normalization,
validation-only threshold and **held-out only diagnostic** model comparison.
Existing production alert routes, emergency dispatch, external APIs and
thresholds do **not** change. Outputs expose aggregate eligible/abstained
counts and a tiny held-out confusion matrix, *never* raw videos, images,
landmarks, training features, reviewer identities or fitted weights.
No cloud upload is performed.

## Measured original, newly downloaded GMDCSA pilot

This was executed on the **16 real MP4s** from source commit
`5abac7693229900cf80f722e878fbb119211fc1c` with the isolated
MediaPipe environment and unchanged local Lite task model.

- Verified downloads: **16 / 16**, source content exactly matches Git blob
  identity and expected length; **87,718,186 bytes** total.
- Pose-readable clips: **16 / 16**; 0 abstentions at 10-of-30 threshold.
- Training: Subjects 1–2 (4 Fall / 4 ADL); validation: Subject 3
  (2 Fall / 2 ADL); **held-out: Subject 4** (2 Fall / 2 ADL).
- Baseline V1 on held-out Subject 4: TP 0, FN 2, FP 0, TN 2;
  **Fall recall 0/2** and ADL specificity 2/2.
- Experimental V2 on the *same* held-out subject: also TP 0, FN 2,
  FP 0, TN 2; **Fall recall 0/2**.
- Validation-only selection chose V1, not V2; this does **not**
  authorize field monitoring or a threshold change based on this test.

**Critical:** The real GMDCSA experiment found that both candidate models
missed both labeled fall videos from a new person/room. This exposes a
strong domain/generalization gap despite success on some CAUCAFall clips.
Only two staged held-out Fall clips is far too small for general accuracy.
This exposed Subject 4 is **no longer an untouched test cohort** for
subsequent tuning. A new external cohort must be selected and frozen
before using GMDCSA results to choose a future candidate.

## Attribution, security, caveats

- **Dataset source**: Ekram Alam et al., DOI above. Preserve a reference
  to the original repo and its MIT license. Publisher source describes
  controlled volunteers, not unconsented surveillance.
- The repository license is public MIT. The final application still needs
  to verify any distinct personality/model/likeness and redistribution
  restrictions before packaging copies of the clips. We only keep them
  locally for research and **do not commit or redistribute third-party MP4s**.
- A license statement does not prove human consent for all intended uses.
  Manual label review and ethical/rights checks remain separate gates.
- **No model is deployed.** The public 16-video pilot can reveal bugs and
  domain variation; it is too small for trustworthy sensitivity, false
  alarms per hour or accuracy guarantees. Always report denominator and
  excluded-pose cases.

## Future public additions (do not blindly ingest)

- **ASSIST-IoT-SRIPAS**:
  https://github.com/ASSIST-IoT-SRIPAS/multimodal-fall-detection-dataset
  has several small direct MP4 ADL hard-negatives (collapsing onto chair,
  lying down, bending, stumbling) and staged falls. CC BY 4.0 repository
  license; **participant identity details may be insufficient** for honest
  subject-disjoint training. Good external negative stress tests after
  provenance verification.
- **Ursul Video Fall Dataset**: https://doi.org/10.6084/m9.figshare.28596332.v2
  is CC BY 4.0 with 2,017 activities / 29 subjects; ~2.36 GiB ZIP.
  Better broad extension than our four-actor mini, but requires a
  disk/network budget and inspection of subject IDs and action windows.
- **IKAR**: https://doi.org/10.58032/AGH/A1NZPE (CC BY 4.0)
  contains 278 staged Falls from 7 people, **no ADL negatives**. Pair
  with independently obtained negatives for model research only; test
  domain shift before reporting a binary classifier.
- **OmniFall**: https://dsch.ai/omnifall/ supplies strong cross-dataset
  annotation protocol. Individual sub-datasets have **different licenses**;
  several are noncommercial or permission-gated. No blanket redistribution.

## Next Developer acceptance checklist

1. Run the 16-video real pose pilot and inspect abstentions.
2. Select/verify additional **independent public ADL** recordings and
   maintain source, immutable Git revision, exact bytes and license.
3. Do not calibrate using the test subject or old CAUCA test.
4. If more data can be obtained, freeze subject/camera-disjoint
   train/validation/**new untouched test** before tuning.
5. Continue to measure false alarms per hour on long ADL recordings,
   misses per real fall, onset delay, actual FPS/CPU/RAM and model bytes.
6. Only then consider a tiny TCN/GRU versus V1 and V2; promotion requires
   repeated held-out improvement and review of participant rights/labels.
7. Deliver further code in `member1/feature/*`; merge validated changes
   only to `member/feature/preprod`. Leave shared `preprod` and human-only
   `main` unchanged.

**Model quality status:** exploratory research, **not production-ready**.
