# Meta intelligence module — live adapter pending

## Responsibilities
- Confirm current official Meta Model API model/endpoint/vision request schemas.
- Authorize and minimize keyframes (do not transmit unauthorized sensitive imagery).
- Prompt for factual visible observations and uncertainty, **not diagnosis or triage**.
- Validate schema and evidence references, reject unsupported claims and malformed responses.
- Provide retry/backoff, timeout, cost/quota guards and result provenance.

The current `services/api/app/meta.py` defines a Protocol and Mock interpreter. Real Muse Spark calls are **not** made by the foundation. A working live adapter and verified test must be added prior to any claim of Meta integration.
