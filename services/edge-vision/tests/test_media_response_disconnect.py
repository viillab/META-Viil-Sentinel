"""ASGI disconnect lifecycle tests, fully synthetic, no camera/network."""
import anyio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from sentinel_edge.local_media_bridge import (
    RevocableMediaResponse, SynchronizedMediaParts,
)


def _scope():
    return {
        "type": "http", "http_version": "1.1",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "method": "GET", "scheme": "http", "path": "/synthetic-mjpeg",
        "raw_path": b"/synthetic-mjpeg", "query_string": b"",
        "root_path": "", "headers": [], "client": ("127.0.0.1", 3001),
        "server": ("127.0.0.1", 8001),
    }


@pytest.mark.parametrize("failure_point", ["headers", "first_frame", "none"])
def test_network_disconnect_releases_synthetic_decoder(failure_point):
    state = {"revoke": 0, "released": 0, "closed": 0, "starts": 0}

    def parts():
        state["starts"] += 1
        try:
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\nsynthetic\r\n"
            yield b"second-synthetic-frame"
        finally:
            state["closed"] += 1

    response = RevocableMediaResponse(
        parts(),
        revoke=lambda: state.__setitem__("revoke", state["revoke"] + 1),
        released=lambda: state.__setitem__("released", state["released"] + 1),
    )

    async def send(message):
        if failure_point == "headers" and message["type"] == "http.response.start":
            raise OSError("synthetic browser disconnected before stream")
        if failure_point == "first_frame" and message["type"] == "http.response.body":
            raise OSError("synthetic browser disconnected mid-stream")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def exercise():
        try:
            await response(_scope(), receive, send)
        except Exception as err:
            if failure_point == "none":
                raise
            assert type(err).__name__ in ("ClientDisconnect", "OSError")

    anyio.run(exercise)
    assert state["revoke"] == 1
    assert state["released"] == 1
    assert state["closed"] == (0 if failure_point == "headers" else 1)
    assert state["starts"] == (0 if failure_point == "headers" else 1)


def test_synchronized_close_joins_inflight_worker_before_release():
    began = Event()
    resume = Event()
    finally_closed = Event()

    def native_generator():
        try:
            began.set()
            if not resume.wait(timeout=5):
                raise AssertionError("synthetic decoder hung")
            yield b"synthetic-jpeg"
        finally:
            finally_closed.set()

    parts = SynchronizedMediaParts(native_generator())
    with ThreadPoolExecutor(max_workers=2) as workers:
        pending_next = workers.submit(next, parts)
        assert began.wait(timeout=3)
        pending_close = workers.submit(parts.close)
        # If closing raced without a lock, close() would raise ValueError:
        # generator already executing. Releasing the blocked decoder allows
        # the serialized close to finish safely.
        resume.set()
        assert pending_next.result(timeout=5) == b"synthetic-jpeg"
        assert pending_close.result(timeout=5) is None
    assert finally_closed.is_set()


def test_synchronized_close_idempotent_after_stream_end():
    released = Event()

    def frames():
        try:
            yield b"frame"
        finally:
            released.set()

    parts = SynchronizedMediaParts(frames())
    assert next(parts) == b"frame"
    with pytest.raises(StopIteration):
        next(parts)
    parts.close()
    parts.close()
    assert released.is_set()
