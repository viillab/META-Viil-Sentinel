# VIIL-Sentinel — New IKAR Public Fall-Only Domain Stress (2026-10-27)

## Overview and source license

A new, previously UNUSED data source was integrated to address the
limitations of repeatedly examining the same staged Fall test videos.

- Official publication: **IKAR: Intelligent Kinetic Activity Recognition -
  Fall Detection Dataset**, AGH University of Krakow, RODBUK Dataverse.
- DOI: https://doi.org/10.58032/AGH/A1NZPE
- Published **29 September 2026**, version **1.0**. Publisher terms:
  **CC BY 4.0**, with required attribution.
- Dataset consists of **278 publisher-labeled staged Fall videos**
  made by **7 volunteers**, in four action categories:
  **92 trips**, **64 slips**, **65 faintings**, **57 blackouts**.
  Source participant identity is NOT reliably linked per filename.
- Official file API: https://agh.rodbuk.pl/api/access/datafile/16904
- Metadata API:
  https://agh.rodbuk.pl/api/datasets/:persistentId/?persistentId=doi:10.58032/AGH/A1NZPE
- Official 127,309,918 byte `IKAR_dataset.tar.gz`;
  publisher MD5 `2667661c258610c0c0aa4bc58a7fc7c2`
  and independently pinned local SHA256
  `722ec563082373213fe43af94173b8ad1273a703b32acb262b6f3d21dd1f7809`.

The official README was inspected. Annotation JSONs contain
**spatial bounding boxes over frames**, NOT independently reviewed
fall-onset times. **There are no ADL negatives in the archive.**
Do not derive fall event recall, classifier accuracy, specificity,
false alarm/hour or healthcare readiness from this dataset.

## Actual completed ingestion, privacy and provenance

The official binary was downloaded on the authorized Windows computer,
verified byte-for-byte against publisher MD5 and independent SHA256,
then inspected using Python `tarfile` in safe READ mode.
Actual archive: **278 MP4s + 278 corresponding annotation JSONs**.
Exactly 8 videos were **preselected before any scoring**:
index IDs `0,1` from each of four categories, fixed in source code.
No video was selected based on the frozen model's outputs.

Only those **8 MP4s and their 8 matching JSONs** were extracted to
`D:\VIIL-Sentinel\data\private\public-datasets\ikar-2026\selected`.
The entire remaining archive stays **compressed and unscored**.
All entries were checked for path traversal, links, file count,
categories, video-label pairing and bounded unpacked size.
The extracted files are bound into the **private manifest**:
`D:\VIIL-Sentinel\data\private\public-datasets\ikar-2026\ikar-8-source-frozen-manifest-v1.json`
with per-file SHA256/size, official archive SHA, license, and explicit
lack of actor/onset truth. Pre-existing files are checksum rechecked,
never overwritten. Directory `data/private` is Git-ignored.

No private video frames, per-frame poses, source spatial labels,
subject identities, model weights or full observation time streams
are uploaded to Git or saved into a report.

## Actual frozen original-model stress, 8 unseen new source videos

The evaluation reused the previous **unaltered** joint NumPy V1
CAUCAFall + GMDCSA-24 baseline, with **frozen SHA256**
`2e55abd9657148a5fb17c3291c96841c31d030695c18116e0da70d6489aec3ab`
and **threshold 0.53**. Model weights and threshold were neither
fit nor selected on IKAR, and the live Fall alert path was not changed.
The camera stream used the official local MediaPipe Lite model.

| Preselected publisher Fall category | Videos | Decoded frames | Torso adapter accepted | Geometry eligible | Pose windows eligible | Videos with frozen V1 candidate | Legacy heuristic events |
|---|---:|---:|---:|---:|---:|---:|---:|
| Trips | 2 | 241 | 214 | 213 | 2/2 | 0 | 0 |
| Slips | 2 | 158 | 158 | 158 | 2/2 | 2 | 1 |
| Faintings | 2 | 251 | 242 | 233 | 2/2 | 0 | 0 |
| Blackouts | 2 | 239 | 217 | 216 | 2/2 | 1 | 0 |
| **Total** | **8** | **889** | **831** | **820** | **8/8** | **3** | **1** |

Additional original strict adapter reasons across the new 8 videos:
**36** frames returned multiple MediaPipe poses and **22** had no
usable person, giving 58 total rejected frames. All 8 clips
had at least one pose-eligible frozen video window. The frozen
baseline thus emitted a video-level candidate in 3/8 preselected
publisher-labeled staged Fall clips. **THIS IS NOT a 3/8 FALL RECALL
OR ACCURACY** because source labels do not independently establish
event onset or reviewed per-video fall-event counts.

The publisher's fainting and trip types did not trigger candidate
videos within this very small deterministic source subset.
That is only a **descriptive** clue for future independent
annotation and training. Do **not** retrospectively tune thresholds
against the same 8 now-exposed videos. Only newly collected,
independently reviewed and actor/camera-disjoint data can establish
improvements or eligibility for safety use.

Private aggregate JSON:
`D:\VIIL-Sentinel\data\private\ikar-public-frozen-8-video-stress-20261027.json`
(no scores, frames, joint coordinates, per-person information).
The unused archive clips still have unknown subject/view disjointness
and MUST NOT be claimed as an untouched, person-disjoint test cohort.

## Reproduce on authorized Windows machine

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$root = "D:\VIIL-Sentinel\data\private\public-datasets\ikar-2026"
$p = "D:\VIIL-Sentinel\data\private"

# Root is created once inside Git-ignored data/private.
New-Item -ItemType Directory -Force -Path $root | Out-Null

# 1. Check Dataverse license/version, download 127MB, MD5+SHA256.
& $py -m sentinel_edge.ikar_domain_stress --mode download `
  --root $root --acknowledge-publisher-labels --acknowledge-pose-privacy

# 2. Inspect official source tar, reject unsafe members, extract
#    ONLY predetermined IDs 0 and 1 from each fall category.
& $py -m sentinel_edge.ikar_domain_stress --mode prepare `
  --root $root --archive "$root\IKAR_dataset.tar.gz" `
  --acknowledge-publisher-labels --acknowledge-pose-privacy

# 3. Evaluate completely FROZEN V1, no model/threshold changes.
& $py -m sentinel_edge.ikar_domain_stress --mode evaluate `
  --root $root `
  --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --frozen-model "$p\joint-cauca-gmdcsa-v1-publisher-research-20261027.json" `
  --report "$p\ikar-public-frozen-8-video-stress-20261027.json" `
  --acknowledge-publisher-labels --acknowledge-pose-privacy

& $py -m pytest -q
& $py -m ruff check .
```

Reports use exclusive-create `open("x")` and never silently overwrite.
Choose a new private output filename on future runs. The downloader
will only reuse an archive that passes full pin verification; metadata
license and version must still match the original official publication.

## Next developer research work

1. With organizationally approved permission, annotate independently
   verified frame-accurate fall onsets for fresh, **not previously seen**
   video scenes; this source provides spatial boxes, not onset ground truth.
2. Obtain ADL hard negatives and verified actor/session groups;
   never treat IKAR's 278 fall-only videos as both positive and negative
   or assign unique-person IDs from sequential file indexes.
3. Build a completely independent source+subject+camera heldout
   corpus before selecting a newly trained model. Current IKAR
   8-video results are now exposed external diagnostics.
4. Report complete long-stream false candidates per reviewed ADL hour,
   event-level recall/detection delay and target Edge CPU/RAM/FPS.
   Maintain human confirmation and the existing production
   multi-person/low-pose abstentions pending robust validation.

Member1 code: `sentinel_edge/ikar_domain_stress.py` and
`tests/test_ikar_domain_stress.py`.
Work only on `member1/feature/*`; integrate tested work into
`member/feature/preprod` and do not touch shared `preprod` or `main`.
