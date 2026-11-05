# Member 1 — Versioned Private V1 Linear Research Artifact

28 October 2026 — Research only, no automated fall alerts.

## Why versioning matters

The 28 October correctness repair aligned NumPy logistic V1/V2
inference with training-only Z-score clipping to [-12,+12]. Older
private V1 weight JSONs did not identify their preprocessing contract.
Identical numeric parameters could therefore give different outlier
scores under older and newer source commits. Versioned metadata fixes
traceability for future training, NOT historical scores.

## Strict numeric schema

- Version 2 (new output): finite 30D arrays mean, scale, weights,
  bias, threshold, source SHA256 digests and explicit key
  inference_preprocessing = train_only_zscore_clamp_minus12_plus12.
- Version 1 (legacy): accepted ONLY with the exact old key set and all
  original numeric limits and research-only flags. Old bytes are
  unchanged. The frozen shadow separately requires its original
  exact SHA256 and threshold before loading old weights.
- Unknown version (including Boolean), missing/wrong preprocessing,
  extra/missing keys, nonfinite coefficients, zero scales, altered
  research flags or wrong dimensions are rejected.
- Model architecture is still 30D trained Linear V1, NOT a 40D V2,
  2-second trained model, GRU, or production incident detector.

Private source videos, derived windows, person identities and numeric
weights remain inside ignored data/private, never committed.

## Reproduce locally

From D:\VIIL-Sentinel\services\edge-vision:

~~~powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .

$root = "D:\VIIL-Sentinel\data\private\public-datasets\caucafall-omnifall\extracted\Cauca_fall"
$private = "D:\VIIL-Sentinel\data\private"
$args = @("--root",$root,"--groups","$root\caucafall-research-groups-v2.json","--proposals","$root\caucafall-review-proposals-v1.json","--pose-model","D:\VIIL-Sentinel\models\pose_landmarker_lite.task","--output","$private\caucafall-linear-v1-new-artifact-v2-20261028.json","--acknowledge-publisher-labels","--acknowledge-pose-privacy")
.\.venv\Scripts\python.exe -m sentinel_edge.private_model_training @args
~~~

The private output is exclusive-create: use a NEW filename for
another experiment. Original source hashes and the fixed
train/validation/held-out subject split remain checked. Do not tune
using repeatedly viewed publisher-labeled test results.

## Verified execution

**COMPLETED real local private retrain, not synthetic:** ran the already
source-pinned CAUCAFall 40 publisher-staged Fall/ADL video pipeline
using the original fixed group split and 30D Linear V1 algorithm.
The NEW private artifact was written under ignored data/private by
exclusive creation, strict version=2 and the exact preprocessing
tag. It was read back immediately; 736 bytes of numeric NumPy
parameters and its validation-selected threshold **0.95** checked.

**Reproducibility check:** Independently loaded the previously fitted
real CAUCAFall V1 artifact from 27 October and compared its complete
three 30D arrays mean, scale, weights, its bias and threshold against
the new V2-format artifact. **ALL numeric fit parameters were bitwise
identical** and both files remained unchanged. This is a deterministic
train/serialization evidence result, NOT an accuracy improvement.

**Legacy frozen shadow compatibility:** loaded the actual existing
SHA256-pinned 30D legacy V1 shadow model from private storage through
load_verified_linear_shadow; its exact SHA, frozen threshold and
finite score check all succeeded. It still cannot send alerts.

**Privacy:** No original video, pose arrays, frame paths, people,
reviewer IDs or model weights entered Git, docs or stdout. Both
artifacts remain private. Labels are publisher-staged and not
independently reviewed, and the old test subjects are repeatedly
exposed: no legitimate new fall event accuracy or clinical claims.

**Local validation on this implementation:** Edge Vision **557 pytest cases passed**;
Edge Ruff passed; Backend **6 pytest cases passed** and Ruff passed;
Dashboard TypeScript/Vite production build passed. No patient images,
videos, motion window vectors or model weights were committed. Hosted
GitHub Actions must additionally pass on BOTH the topic commit and the
team integration merge commit before reporting the merge as verified.


## Next developer

Pin the source Git SHA, model architecture, artifact version and
preprocessing contract before presenting research metrics. Previously
exposed staged publisher labels are NOT independently reviewed fall
onsets or real-world accuracy. An actual low-latency 2-second trained
model still requires independent human event annotation, untouched
actor/camera-separated test sources and long ADL negative hours.
