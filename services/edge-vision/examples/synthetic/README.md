# Synthetic trace examples — NOT performance evidence

The `fall.jsonl` and `sitting.jsonl` clips here are invented numerical
poses for testing the evaluation interface and regression behavior. They do
**not** represent real human recordings, actual MediaPipe inference or
independent validation. Any perfect sample score is entirely artificial.

To run the reproducible command from `services/edge-vision`:

```powershell
python -m sentinel_edge.evaluation --manifest examples/synthetic/manifest.json
```

Use an independently recorded, consented, clearly annotated dataset to
produce meaningful performance estimates. Do not publish any private
human landmark traces, recordings, patient details or licensing-restricted
assets. Trace files ending in `.pose.jsonl` are ignored by Git.
