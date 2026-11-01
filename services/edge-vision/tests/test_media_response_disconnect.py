"""ASGI disconnect lifecycle tests, fully synthetic, no camera/network."""
import anyio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from sentinel_edge.local_media_bridge import (
    PreflightMediaParts, RevocableMediaResponse, SynchronizedMediaParts,
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


def test_preflighted_decoder_closed_when_asgi_headers_fail_before_first_body():
    state = {"preflighted": 0, "closed": 0, "revoked": 0, "released": 0}

    def camera():
        try:
            state["preflighted"] += 1
            yield b"synthetic-first-jpeg"
            yield b"should-not-be-observed"
        finally:
            state["closed"] += 1

    native = camera()
    first = next(native)  # 12/12 preflight and first JPEG already completed
    parts = PreflightMediaParts(first, native, authorized=lambda: True)
    response = RevocableMediaResponse(
        parts,
        revoke=lambda: state.__setitem__("revoked", state["revoked"] + 1),
        released=lambda: state.__setitem__("released", state["released"] + 1),
    )

    async def send(message):
        if message["type"] == "http.response.start":
            raise OSError("simulated browser disconnect before MJPEG body")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def exercise():
        with pytest.raises(Exception) as error:
            await response(_scope(), receive, send)
        # Starlette ASGI 2.4 translates network OSError to ClientDisconnect.
        assert type(error.value).__name__ in ("ClientDisconnect", "OSError")

    anyio.run(exercise)
    assert state == {
        "preflighted": 1, "closed": 1, "revoked": 1, "released": 1,
    }
    with pytest.raises(StopIteration):
        next(parts)


def test_preflighted_decoder_not_sent_if_viewer_revoked_after_preflight():
    state = {"closed": 0}

    def native():
        try:
            yield b"prepared-jpeg"
        finally:
            state["closed"] += 1

    source = native()
    first = next(source)
    parts = PreflightMediaParts(first, source, authorized=lambda: False)
    with pytest.raises(StopIteration):
        next(parts)
    parts.close()
    assert state["closed"] == 1


def test_native_close_exception_redacted_and_global_capacity_not_released():
    state = {"revoked": 0, "released": 0}

    class FailingDecoder:
        def __iter__(self):
            return self

        def __next__(self):
            return b"synthetic"

        def close(self):
            raise RuntimeError("rtsp://private:TOP-SECRET@192.168.1.2/live")

    response = RevocableMediaResponse(
        FailingDecoder(),
        revoke=lambda: state.__setitem__("revoked", state["revoked"] + 1),
        released=lambda: state.__setitem__("released", state["released"] + 1),
    )

    async def send(message):
        if message["type"] == "http.response.start":
            raise OSError("synthetic send failure")

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def exercise():
        with pytest.raises(RuntimeError) as raised:
            await response(_scope(), receive, send)
        assert str(raised.value) == "Protected media cleanup unavailable (redacted)"
        assert raised.value.__cause__ is None

    anyio.run(exercise)
    assert state == {"revoked": 1, "released": 0}


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
