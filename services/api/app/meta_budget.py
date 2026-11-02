"""Conservative local Meta spend reservation.

This is NOT a Meta billing dashboard or a cross-team $150 budget cap.
Each attempted paid call permanently reserves a generous maximum allowance;
failures never refund it, preventing accidental retry storms or double-spend.
SQLite BEGIN IMMEDIATE serializes local concurrent processes.
"""
import sqlite3
from pathlib import Path

# Meta Muse Spark Standard pricing as of 2026-11-02; verify before future use.
INPUT_USD_PER_MILLION = 1.25
OUTPUT_USD_PER_MILLION = 4.25
# Conservative image/text input allowance, not an observed tokenizer count.
RESERVED_INPUT_TOKENS = 100_000
MAX_OUTPUT_TOKENS = 1024
RESERVATION_MICRO_USD = (
    int(RESERVED_INPUT_TOKENS * INPUT_USD_PER_MILLION)
    + int(MAX_OUTPUT_TOKENS * OUTPUT_USD_PER_MILLION + 1)
)  # 129353 micro-USD ($0.129353) per attempt
MAX_LOCAL_MICRO_USD = 500_000  # never reserve over $0.50 on this local ledger
MAX_LOCAL_CALLS = 2
DEFAULT_LEDGER = Path(__file__).resolve().parents[3] / "data" / "private" / "meta_spend.sqlite3"


class MetaBudgetExceeded(RuntimeError):
    pass


class MetaBudget:
    def __init__(self, *, path: Path = DEFAULT_LEDGER) -> None:
        self.path = Path(path)

    def reserve_once(self) -> tuple[int, int]:
        """Durably reserve before any possible network call; never refund."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=5.0) as con:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                "CREATE TABLE IF NOT EXISTS budget ("
                "id INTEGER PRIMARY KEY CHECK (id=1), "
                "reserved_micro_usd INTEGER NOT NULL, "
                "calls INTEGER NOT NULL)"
            )
            con.execute(
                "INSERT OR IGNORE INTO budget VALUES (1, 0, 0)"
            )
            row = con.execute(
                "SELECT reserved_micro_usd, calls FROM budget WHERE id=1"
            ).fetchone()
            reserved, calls = row
            if (calls >= MAX_LOCAL_CALLS or (
                reserved + RESERVATION_MICRO_USD > MAX_LOCAL_MICRO_USD
            )):
                raise MetaBudgetExceeded("Local Meta probe cap reached; no paid call made")
            new_reserved = reserved + RESERVATION_MICRO_USD
            con.execute(
                "UPDATE budget SET reserved_micro_usd=?, calls=? WHERE id=1",
                (new_reserved, calls + 1),
            )
            con.commit()
            return calls + 1, new_reserved

    def status(self) -> tuple[int, int]:
        """Read without creating new spend or making a network request."""
        if not self.path.is_file():
            return 0, 0
        with sqlite3.connect(self.path, timeout=5.0) as con:
            try:
                row = con.execute(
                    "SELECT reserved_micro_usd, calls FROM budget WHERE id=1"
                ).fetchone()
            except sqlite3.OperationalError:
                return 0, 0
            return (row[1], row[0]) if row else (0, 0)
