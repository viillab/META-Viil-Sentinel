# VIIL-Sentinel Member 1 — NumPy Tiny MLP Real Public-Video Training
27 October 2026 · Research-only, never a deployed fall alarm

## Objective

The original CAUCAFall+GMDCSA-24 joint NumPy V1 logistic classifier
was compact, but it did not detect any publisher-staged Fall videos
in the already-exposed third-source ASSIST-IoT frozen stress suite.
A more expressive learner may model nonlinear combinations of
torso position and motion more effectively. This experiment is
an **ACTUALLY TRAINED**, CPU-only, bounded, **12-hidden-unit MLP**,
not a TCN/CNN/RNN and **not a guarantee of better Fall detection**.

It consumes the **same 30 x 6 masked frame motion windows**, pools
into the existing **30-D input** (5 ordered time bins × 6 channels),
learns a 30×12 tanh hidden transformation and a 12×1 sigmoid output
by balanced full-batch gradient descent entirely in NumPy.
It retains train-only scaler and VAL-only threshold.
An existing linear NumPy research baseline is refitted on the
**identical TRAIN** data and compared on the **same VAL** clips.
**The MLP wins selection ONLY if VAL balanced accuracy improves
by more than 0.02**; otherwise the simpler linear candidate remains
recommended. The already-exposed old TEST subjects are loaded after
candidate choice, purely as historical diagnostics. No result on
ASSIST-IoT may be used to choose hyperparameters or threshold.

### Frozen architecture (before scoring source clips)

- `input=30`, `hidden=12`, `tanh`, sigmoid binary classifier
- Seed `407`, train-only mean/std, limited `[-12,12]` standardized
  numerical features, 800 full batch steps, learning rate `0.15`,
  `L2=0.02`, class-balanced Fall/ADL gradient
- threshold candidates `0.95` down to `0.05` in 0.01 increments;
  choose highest threshold on tied VAL balanced accuracy
- Tiny-only numerical artifact includes mean/scale, `w1`,
  `b1`, `w2`, `bias`, selected VAL threshold, source SHA
  commitment, architecture and explicit research flag.
- No raw video pixels, pose samples, individual clip IDs,
  video filenames, participant identifiers, or person tracks
  are written to the learned model file. The model remains in
  Git-ignored `data/private`. The report emitted to stdout
  contains aggregate score summaries and private-source hash only.
- Requires explicit publisher-label uncertainty and sensitive
  pose processing acknowledgements. Original SHA-pinned videos
  are verified with the preexisting `publisher_label_pilot`
  before any fit; the source manifests are rehashed after training.
  No `torch` or TensorFlow installation or API spending.

## Real source data and limitations

Two original public research sources: CAUCAFall (publisher-designated
actions, reported CC BY 4.0) and GMDCSA-24 (public MIT repository
source) in the previously pinned local private media roots.
Declared source/subject/recording split isolation is reaudited
both per source and after merge. **Declared source actors are NOT
independently identity-verified** and **publisher labels are NOT
independently human-reviewed**.

Original CAUCAFall + GMDCSA-24 former `test` actor results were
already exposed in previous VIIL-Sentinel development, as were all
11 ASSIST-IoT reference videos. Any metrics on those sources
are **diagnostic and NOT fresh unbiased generalization**. The
VAL numbers are also optimistically biased by using VAL to choose
a candidate and threshold.

This implementation **does not** train from independent reviewed
Fall-event-onset labels. The real third-source Event Reviewer
template remains **blank**, awaiting two actual human reviewers;
it is not silently accepted as ground truth. A fresh completely
unseen participant/camera independent test is required before
any performance or medical-device readiness claims. No live
camera, deployment, automatic alert, emergency action, or original
research V1 weights are modified.

## Exact real Windows command

```powershell
cd D:\VIIL-Sentinel\services\edge-vision
$py = ".\.venv\Scripts\python.exe"
$p = "D:\VIIL-Sentinel\data\private"
& $py -m sentinel_edge.tiny_mlp_training `
  --cauca-root "$p\public-datasets\caucafall-omnifall\extracted\Cauca_fall" `
  --gmdcsa-root "$p\public-datasets\gmdcsa24-mini" `
  --pose-task "D:\VIIL-Sentinel\models\pose_landmarker_lite.task" `
  --output "$p\joint-cauca-gmdcsa-tiny-mlp-research-20261027.json" `
  --acknowledge-publisher-labels --acknowledge-pose-privacy

& $py -m pytest -q
& $py -m ruff check .
```

The output is created **only if it does not already exist**, under
ignored private storage. Choose a new path for a new iteration,
never silently overwrite another model. The artifact is checked
with strict schema, dimensional, finite-value and threshold validation,
and all numeric arrays/threshold are reloaded and compared byte
equivalent to the fitted model.

## Guidance to future developers

Only train a new version after defining fresh development-set classes,
subjects, source rights and evaluation protocol. The original
publisher action label does not prove independent onset annotation.
Use actual two-reviewer completed event labels when they exist.
Compare new model on source- and subject-disjoint VAL, keep the
old external ASSIST results as explicitly exposed regressions,
and reserve a genuinely never-seen TEST corpus for promotion.
Prioritize ambiguity/abstention and long negative-camera footage
false alarms per hour and CPU/FPS/RAM budgets. Avoid deploying
this MLP or turning its window probability into a high-stakes
fall alert without a separately calibrated event policy.

Only work under `member1/feature/*` and integrate to
`member/feature/preprod`; main/shared preprod human-only.

## Executed real on-device training — measured results

**Completed real, source-hash-reverified CAUCAFall + GMDCSA-24 video
pose extraction and TWO independent TRAIN-only NumPy fits** in the
authorized Windows Edge Vision virtual environment.
This did not involve Torch/GPU/API calls and did not change the
live fall detector.

| Measured split or metric | Re-fitted linear V1 | Trained Tiny MLP |
|---|---:|---:|
| Declared TRAIN | 31 clips, 8 subjects | same 31 |
| Declared VAL | 10 clips, 3 subjects | same 10 |
| OLD, already-exposed TEST | 10 clips, 3 subjects | same 10 |
| VAL balanced accuracy | **0.90** | 0.80 |
| VAL Fall hits / all Fall | **5/5** | **5/5** |
| VAL ADL correct / all ADL | **4/5** | 3/5 |
| VAL threshold (chosen by VAL alone) | **0.53** | 0.43 |
| OLD TEST Fall detected | 3/6 | **4/6** |
| OLD TEST ADL correctly rejected | 4/4 | 4/4 |
| Fitted parameters+scaler RAM | **736 bytes** | 3,568 bytes |
| Approx model numeric count including scale/mean | 92 | 446 |

**Predeclared model-selection result: `linear_v1`, NOT Tiny MLP.**
The nonlinear model performed worse on the only declared validation
split and has 5× the RAM parameter size. Its apparent better OLD
TEST Fall count **cannot override VAL selection** because these
TEST cohorts have previously been inspected. Neither metric is
independent clinical/field reliability evidence. The old TEST here
was never used to alter the model architecture, select a threshold,
or choose the winner. Original production alerts remain unchanged.

The independently trained Tiny MLP candidate is kept privately for
reproducibility, *not deployment*, at
`D:\VIIL-Sentinel\data\private\joint-cauca-gmdcsa-tiny-mlp-research-20261027.json`.
It is **9,478 bytes** JSON on disk and has file SHA-256:

`6e9db54f2ef987096a3f631eab660c12e6ce23a4d61cf6e8dd0516ae82939526`

The strict research-only loader reloaded mean, scale, hidden/output
weight arrays, biases and chosen VAL threshold and verified exact
equality against the freshly trained in-memory parameters. No raw
video, human landmarks, subjects or per-video predictions are
contained in that artifact. This MLP is independent of and did
not overwrite the previous frozen private V1 artifact.

### CPU inference-only microbenchmark

On the existing Windows developer CPU, direct Python/NumPy
repeated 30-D single-window inference, `N=10,000` calls:

- Linear baseline ≈ **9.09 microseconds per call**
- Tiny MLP ≈ **19.93 microseconds per call**

These are illustrative local microbenchmarks measured after the
actual video training run, **not** end-to-end frame inference,
MediaPipe FPS, GPU throughput or real-world response latency.
The full video pose extraction generally dominates runtime.
The MLP is lightweight but neither more accurate on VAL nor
faster than the existing linear research baseline.

### What is STILL missing

No actual two-person reviewed event-onset labels were available.
Previously exposed actor splits and the already-viewed ASSIST
videos are unsuitable for a new unbiased final generalization
claim. Future model improvement requires additional publisher-
licensed video scenes with independently verified actor IDs,
reviewed event onset segments, long ADL hard negatives and
camera/subject-isolated unseen TEST sources. Do not choose Tiny
MLP, adjust 0.43/0.53 thresholds, or enable automatic incidents
because of outcomes on the exposed old TEST subjects.
