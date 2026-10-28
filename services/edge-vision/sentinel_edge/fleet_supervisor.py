"""Fail-closed lifecycle supervisor for bounded experimental camera workers.

No camera data or secrets are inspected. A single worker failure stops its
siblings; a wall-time budget prevents unattended demo capture after a hang.
Not a high-availability service or a substitute for OS job objects.
"""
import subprocess
from time import monotonic, sleep
from typing import Callable


MAX_FLEET_TIMEOUT_SECONDS = 3600
POLL_SECONDS = 0.1


def _status(child) -> int | None:
    poll = getattr(child, "poll", None)
    if callable(poll):
        return poll()
    # Compatibility for in-memory fake workers in unit tests. Real Popen
    # always implements poll(), so this never blocks on an OS child.
    try:
        return child.wait(timeout=0)
    except subprocess.TimeoutExpired:
        return None


def stop_workers(children: list) -> None:
    """Reap all workers without including their sensitive native stderr."""
    for child in children:
        try:
            if _status(child) is None:
                child.terminate()
        except OSError:
            pass
    for child in children:
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                child.kill()
                child.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        except OSError:
            pass


def supervise_camera_workers(
    children: list, *,
    timeout_seconds: int = 900,
    clock: Callable[[], float] = monotonic,
    pause: Callable[[float], None] = sleep,
) -> int:
    """Return nonzero and stop siblings on first failed/overlong worker."""
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= MAX_FLEET_TIMEOUT_SECONDS:
        raise ValueError("Fleet timeout must be an integer in 1..3600 seconds")
    if not children:
        raise ValueError("At least one camera worker must be running")
    pending = list(children)
    started = clock()
    try:
        while pending:
            for child in tuple(pending):
                status = _status(child)
                if status is None:
                    continue
                pending.remove(child)
                if status != 0:
                    stop_workers(children)
                    return 2
            if pending and clock() - started >= timeout_seconds:
                stop_workers(children)
                return 2
            if pending:
                pause(POLL_SECONDS)
    except (OSError, KeyboardInterrupt):
        stop_workers(children)
        return 2
    return 0
