"""Periodic, fail-closed privacy approval revalidation during live capture.

Approval may be removed/changed or the verification key rotated after a
session begins. Recheck without storing frames. This is a bounded-delay check,
not an immediate distributed revocation or a legal compliance guarantee.
"""
from pathlib import Path
from time import monotonic
from typing import Callable

from sentinel_edge.privacy_gate import verify_privacy_approval


class LiveApprovalGuard:
    """Verify at construction and no less frequently than a short interval."""

    def __init__(
        self, path: Path, *, camera_id: str,
        clock: Callable[[], float] = monotonic,
        interval_seconds: float = 1.0,
        verifier: Callable[..., dict] = verify_privacy_approval,
    ) -> None:
        if type(interval_seconds) not in (float, int) or not 0 < interval_seconds <= 10:
            raise ValueError("Privacy recheck interval must be in (0, 10] seconds")
        self._path = path
        self._camera_id = camera_id
        self._clock = clock
        self._interval_seconds = interval_seconds
        self._verifier = verifier
        self._last_checked = clock()
        verifier(path, camera_id=camera_id)

    def check(self) -> None:
        """Called before and after each blocking camera read."""
        now = self._clock()
        if now - self._last_checked >= self._interval_seconds or now < self._last_checked:
            self._verifier(self._path, camera_id=self._camera_id)
            self._last_checked = now
