# Evaluation protocol (no fabricated scores)

Record dataset consent/license, split by participant/video, test conditions, model version, prompt version, code commit and hardware.

- Detection: TP/FP/TN/FN, precision, recall, F1, fall-event latency, false alerts during bending/sitting/lying.
- Report: schema-valid %, evidence-grounding human review %, unsupported claims, uncertainty completeness, p50/p95 latency.
- Operations: notification delivery latency, idempotency, state-transition validity, audit completeness, failure recovery.
- Compare the same staged conditions with detection-only and full Meta-enhanced incident workflow.
- No claims about clinical sensitivity, real elderly population validity, or diagnosis.

Keep private/copyrighted videos outside public git.
