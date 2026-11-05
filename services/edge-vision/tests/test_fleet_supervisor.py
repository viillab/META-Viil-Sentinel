"""Synthetic fail-closed worker supervisor tests; no processes or cameras started."""
from itertools import count

import pytest

from sentinel_edge.fleet_supervisor import (
    MAX_FLEET_TIMEOUT_SECONDS, stop_workers, supervise_camera_workers,
)


class FakeChild:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.last = None
        self.terminated = False
        self.killed = False
        self.reaped = False

    def poll(self):
        if self.terminated or self.killed:
            return 2
        try:
            self.last = next(self.responses)
        except StopIteration:
            pass
        return self.last

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        self.reaped = True
        return 2 if self.terminated else (self.last or 0)


def test_supervisor_all_children_done_successfully():
    a = FakeChild([None, 0])
    b = FakeChild([None, None, 0])
    assert supervise_camera_workers(
        [a, b], timeout_seconds=10, clock=lambda: 0.0, pause=lambda _: None,
    ) == 0
    assert not a.terminated and not b.terminated


def test_one_worker_failure_stops_pending_camera_workers():
    failed = FakeChild([2])
    running = FakeChild([None, None])
    assert supervise_camera_workers(
        [failed, running], timeout_seconds=10, clock=lambda: 0.0,
        pause=lambda _: None,
    ) == 2
    assert running.terminated
    assert running.reaped


def test_hard_timeout_stops_unresponsive_workers():
    worker = FakeChild([None] * 12)
    ticks = count(0)
    assert supervise_camera_workers(
        [worker], timeout_seconds=2, clock=lambda: next(ticks),
        pause=lambda _: None,
    ) == 2
    assert worker.terminated
    assert worker.reaped


@pytest.mark.parametrize("invalid", [True, None, 0, -1, 3601])
def test_supervisor_rejects_invalid_deadlines(invalid):
    with pytest.raises(ValueError):
        supervise_camera_workers([FakeChild([0])], timeout_seconds=invalid)
    assert MAX_FLEET_TIMEOUT_SECONDS == 3600


def test_supervisor_refuses_empty_worker_set():
    with pytest.raises(ValueError):
        supervise_camera_workers([], timeout_seconds=10)


def test_stop_workers_only_terminates_live_children():
    already_done = FakeChild([0])
    still_running = FakeChild([None])
    stop_workers([already_done, still_running])
    assert not already_done.terminated
    assert still_running.terminated
    assert already_done.reaped and still_running.reaped
