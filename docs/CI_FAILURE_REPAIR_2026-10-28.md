# VIIL-Sentinel CI recovery — 28 October 2026

## Reproduced GitHub Actions failure

[GitHub Actions failed run #40552989462](https://github.com/viillab/META-Viil-Sentinel/actions/runs/40552989462)
on `member/feature/preprod` at `e45e076`, Python 3.12, Node 22.

| Job | Previous failure verified from actual job logs | Repair |
|---|---|---|
| backend | 9 Ruff diagnostics `I001`, `UP017`, `BLE001` during lint; pytest was skipped | Sort imports in production and API tests; use Python 3.11+ `datetime.UTC`; preserve broad fail-closed third-party interpreter isolation and document its explicit `# noqa: BLE001` |
| edge-vision | `ModuleNotFoundError: No module named 'numpy'` during Pytest collection in 5 training-related test modules; Ruff passed | Include `numpy>=1.26,<3.0` in Edge `[dev]` extra, so **unchanged** GitHub `pip install -e ".[dev]"` works in a brand-new environment |
| dashboard | Vite/TypeScript build succeeded | No changes needed |

The original workstation's Edge virtual environment had NumPy already
installed and the local API environment was not configured, hiding the
difference between developer tests and fresh GitHub dependency resolution.

## Commands reproducing each GitHub CI job

```bash
cd services/api
python -m pip install -e ".[dev]"
python -m ruff check .
python -m pytest -q

cd ../edge-vision
python -m pip install -e ".[dev]"
python -c "import numpy; print(numpy.__version__)"
python -m ruff check .
python -m pytest -q

cd ../../apps/dashboard
npm ci
npm run build
```

Use **Python 3.12** for the two Python projects and **Node.js 22**
for the dashboard to match `.github/workflows/ci.yml`.

The API's `except Exception` handles **untrusted optional external
provider failures** to prevent a fabricated AI report and keep the
human-review event flow; this is intentionally not narrowed or silently
removed to satisfy lint. Other changes are import organization only
and using the standard UTC alias, which maintains equivalent timestamps.

Do not copy any model weights, private datasets or health information
into CI. This repair changes only lint hygiene and development package
metadata, not the runtime inference, shadow threshold, fall alerts,
provider behavior or incident routing.

## Validation and final GitHub result

API: installed a **new Python 3.12 virtual environment** with
`pip install -e ".[dev]"`; Ruff passed and **6 Pytests passed**
(only a deprecation warning from an upstream TestClient dependency).

Edge before fresh install: **484 local Pytests passed**, Ruff passed.
GitHub results must be inspected after the fix branch is pushed,
rather than inferred from passing developer tests.
