"""Bounded camera reconnection for local research, not a safety-monitoring service.

Every retry requires a NEW native pose task, NEW temporal detector, and a unique
source-relative clock namespace. The caller provides the actual capture callback.
No frames, passwords, hostnames, or pose landmarks enter this coordinator.
"""
from collections.abc import Callable
from dataclasses import dataclass
from time import sleep
from uuid import uuid4

from sentinel_edge.handoff import SOURCE_ID_PATTERN


class CameraStreamInterrupted(RuntimeError):
    """An RTSP open/read failure. Message must never contain a camera URL."""


@dataclass(frozen=True)
class ReconnectResult:
    attempts: int
    recovered_sessions: int
    completed: bool


def session_source_id(base: str, token: str, attempt: int) -> str:
    """Identify stream epochs so relative timestamps cannot cross a reconnect."""
    if SOURCE_ID_PATTERN.fullmatch(base) is None:
        raise ValueError("source_id must be a pseudonymous ASCII slug of at most 80 chars")
    if not token or any(character not in "0123456789abcdef" for character in token):
        raise ValueError("invalid session token")
    if not 1 <= attempt <= 4:
        raise ValueError("invalid RTSP attempt")
    suffix = f"-s{attempt}-{token[:8]}"
    return base[:80 - len(suffix)] + suffix


def run_bounded_sessions(
    run_session: Callable[[str], None], *,
    source_id: str,
    retries: int = 0,
    delay_seconds: float = 1.0,
    pause: Callable[[float], None] = sleep,
    status: Callable[[str], None] = lambda _: None,
    token: str | None = None,
) -> ReconnectResult:
    """Retry only capture interruptions; no retry on ML/runtime/config failures.

    The callback MUST release old capture and model resources before raising.
    There are at most four attempts. Never interpret exhausted retries as no fall.
    """
    if not 0 <= retries <= 3:
        raise ValueError("retries must be between 0 and 3")
    if not 0.25 <= delay_seconds <= 5.0:
        raise ValueError("delay_seconds must be between 0.25 and 5")
    epoch = token if token is not None else uuid4().hex[:8]
    for offset in range(retries + 1):
        source = session_source_id(source_id, epoch, offset + 1)
        try:
            run_session(source)
            return ReconnectResult(offset + 1, offset, True)
        except CameraStreamInterrupted:
            # Do not interpolate potentially sensitive exception strings.
            status(f"RTSP unavailable; attempt {offset + 1}/{retries + 1}; no monitoring")
            if offset >= retries:
                return ReconnectResult(offset + 1, offset, False)
            pause(delay_seconds)
    raise AssertionError("unreachable")
