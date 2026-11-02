# VIIL-Sentinel — Evidence Quality & Abstention (research v1)

**2026-11-02 • Member 2 • offline/read-only • real staged noncommercial research dataset + fictional poses • no new Meta API usage**

## What actually changed

Added `services/api/app/review_evidence_abstention.py` as a separate, **local research-only** consumer of the existing Member 1 V1 TemporalFallDetector and Member 2 V2 ExperimentalReviewMotionDetector.

An audit of the actual Member 1 Edge runner and pose reader confirms that the production trace keeps exactly **four torso points** (landmark IDs 11/12 shoulders, 23/24 hips), not knees, ankles, fall direction, floor contact, context or subject identity. **This increment does NOT claim to implement multi-joint motion tracking or to improve the actual fall detector.** Additional joints would require a separately reviewed privacy-scoped extractor and a genuinely new dataset.

The new tool makes a bounded, explicit **evidence sufficiency** assessment (not a diagnosis):
- minimum 20 frames and 700 ms temporal span
- ≥75% of frames have sufficient torso visibility and geometric quality
- at most 12 consecutive unusable frames
- timestamp gaps must stay ≤700 ms
- same source ID and strictly increasing timestamps on all frames
- two detector candidates count as temporally aligned only within 1200 ms, and **are not treated as independent sources of truth**

These numbers are engineering guardrails only, **not calibrated safety thresholds** and have not been validated on an actor-independent dataset.

### Possible outcomes

| Internal state | Meaning | Actual authorized action |
| --- | --- | --- |
| `abstain_insufficient_pose` | Short clip, missing/occluded landmarks, poor pose fraction or timing discontinuity | Do not interpret candidate; investigate quality |
| `single_heuristic_review_only` | Exactly one uncorroborated heuristic (or unaligned events) | Human review may be requested |
| `dual_heuristic_review_only` | V1 and V2 detected a similar-time signal | Human review only; **correlated evidence, not confirmation** |
| `no_candidate_not_clearance` | Neither detector emitted an event | **Never means no fall occurred** |

Across every outcome: `fall_confirmed=false`, `no_fall_confirmed=false`,
`automatic_notification_permitted=false`, `emergency_dispatch_permitted=false`,
`meta_upload_permitted=false`, `provider_called=false`,
`calibrated_fall_probability_available=false`.

The policy **fails closed** on mixed source IDs, reordered timestamps,
empty streams, oversized streams, invalid quality thresholds or unsupported
inputs. It emits only fixed reason codes and aggregate numbers, never
images or raw pose coordinates. Invalid/short evidence may be withheld
even when the two heuristics report a candidate; this is not a statement
that such a candidate was false.

## Actual retrospective local test — 12 known research videos

All **12 distinct publicly licensed staged MP4s** from earlier work:
6 publisher-labeled Fall and 6 ADL. All twelve had already been inspected
in earlier milestones: five initial clips, five development clips and two
negative-challenge clips. They may share actors and camera setups.
This audit reuses source-hash-verified local JSONL traces, reruns both
existing detectors and checks original V1 candidate counts for exact
agreement. **This is NOT a blind/actor-disjoint accuracy or safety test.**

| Decision | Fall-labeled clips | ADL clips | Total |
| --- | ---: | ---: | ---: |
| Dual-heuristic human review | 2 | 0 | 2 |
| Single-heuristic human review | 3 | 0 | 3 |
| No candidate, not clearance | 1 | 6 | 7 |
| Abstain due to quality | 0 | 0 | 0 |
| **Total** | **6** | **6** | **12** |

The fall-labeled clip `FD0012` still produces **no candidate**; the
quality gate cannot solve it. All 12 retrospective clips met the current
basic pose coverage and temporal thresholds, so the new policy **did not
repair fall recall**. There were no real-person notifications or Meta calls.

The private report is written to
`data/private/adl_negative_challenge_v1/review-abstention-retrospective.json`.
This file and all derived pose traces and videos are Git-ignored.

## Synthetic negative tests expose remaining ambiguity

The eight fictional four-point ADL scenarios from
`app.synthetic_adl_stress` still generate **two V2 false review signals**
(rapid voluntary sitting and fast bed repositioning), plus one V1
false event in the fast-sitting scenario. The new quality policy abstains
on these **short** synthetic clips (all eight fail the minimum frame
threshold), but **this is NOT a fix** for the ambiguity.

Two additional *longer*, high-quality fictional scenarios explicitly show
that **voluntary fast sitting and bed shifting can still pass the quality
policy and cause human-review proposals**. Such results must never be
promoted to automatic emergency alerts. The quality checker does not
infer intention, injury, fall onset or floor contact.

The synthetic camera-source-switch case fails closed with
`abstain_mixed_source` at the research stress harness layer; the
underlying evidence assessor itself rejects mixed-source streams.

## Reproduce

From `D:\VIIL-Sentinel\services\api` with Edge V1 and
Member 2 research extras installed:

```powershell
# Local replay of 12 ALREADY-KNOWN research traces (no downloads, no Meta):
.\.venv\Scripts\python.exe -m app.review_evidence_abstention_report --evaluate-known --acknowledge-noncommercial-license

# Purely fictional 8-scenario ADL stress with new quality-state annotations:
.\.venv\Scripts\python.exe -m app.synthetic_adl_stress

# Full backend/Edge test suites and lint:
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
cd ..\edge-vision
..\api\.venv\Scripts\python.exe -m pytest -q
```

The new Pytest module `tests/test_review_evidence_abstention.py` uses
**fictional pose fixtures**, including long fake normal fast-sitting and
bed-shifting scenarios, a 19-frame occlusion, time gaps, mixed source IDs,
reordered timestamps, malformed policy parameters, and a stubbed
12-record manifest (no private video needed for CI).

## Safety / release and subsequent project work

**Release decision: NO-GO** for automated fall confirmation, autonomous
emergency notification, camera/person safety monitoring, or sending these
publicly licensed identifiable subjects to Meta.

This research branch leaves **Member 1 Edge source**, production incident
ingest, signed evidence/consent rules, FastAPI Caregiver endpoints, Mobile
and Dashboard untouched. No live media is exposed through an API.

The **next genuine engineering dependency** is authorization to construct
a *separately permissioned* extended Pose pipeline (e.g. shoulders, hips,
knees and ankles) with lawful data/retention handling, multi-person
association, perspective calibration, explicit tracking identity and
independently annotated actor-disjoint real ADL/fall datasets. These are
needed to study whether voluntary sitting, bed motion, ground contact and
actual falls can be distinguished reliably. Freeze preprocessing and
thresholds on a development cohort before any blind field evaluation;
report uncertain/abstained rate, recall, actual false review candidates
per hour and onset-aligned latency rather than a tiny sample F1.

Existing Meta local ledger is **4/4** authorized test attempts; the
new module and replay run **zero** paid Meta calls.
