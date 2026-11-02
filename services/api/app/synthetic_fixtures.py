"""Single source of truth for the frozen, fictional Member 1 pose fixtures.

No imports of FastAPI, live provider adapters, or orchestration scripts.
"""
from pathlib import Path

EDGE_ROOT = Path(__file__).resolve().parents[2] / "edge-vision"
SYNTHETIC_ROOT = EDGE_ROOT / "examples" / "synthetic"
SYNTHETIC_SOURCE = "synthetic-clip-01"

# Frozen source-owned mathematical traces, not real camera footage.
EXPECTED_TRACE_HASHES = {
    "fall": "ce4eba83088d4a9728002c87a7ace082debdf48d6c12bf3be8277fec9c2155e1",
    "sitting": "29d11e019e698647bf5d5348747c1c0f7985d02a277efebf32f5f5b836b5f468",
}
