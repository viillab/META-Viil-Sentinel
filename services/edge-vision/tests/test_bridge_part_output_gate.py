"""Offline bridge defense-in-depth tests; no real camera or image transport."""
from threading import Event, Thread

import pytest

from sentinel_edge.local_media_bridge import MAX_PREVIEW_PARTS, PreflightMediaParts

FRAME = (
    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 8"
    b"\r\n\r\n\xff\xd8FAKE\xff\xd9\r\n"
)


def test_valid_multipart_first_and_followup_frames_pass():
    state = {"closed": 0}

    def source():
        try:
            yield FRAME
            yield FRAME
        finally:
            state["closed"] += 1

    original = source()
    parts = PreflightMediaParts(next(original), original, authorized=lambda: True)
    assert list(parts) == [FRAME, FRAME]
    parts.close()
    assert state["closed"] == 1


@pytest.mark.parametrize("bad", [
    b"not an MJPEG frame",
    b"--frame\r\nContent-Type: text/html\r\nContent-Length: 8\r\n\r\n"
    b"not-jpeg\r\n",
    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 99"
    b"\r\n\r\n\xff\xd8FAKE\xff\xd9\r\n",
    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 262145"
    b"\r\n\r\n" + b"X" * 262145 + b"\r\n",
], ids=["not-mjpeg", "wrong-content-type", "length-mismatch", "oversized-jpeg"])
def test_invalid_subsequent_mjpeg_part_is_never_forwarded(bad):
    state = {"closed": 0, "after_bad": 0}

    def source():
        try:
            yield FRAME
            yield bad
            state["after_bad"] += 1
            yield FRAME
        finally:
            state["closed"] += 1

    original = source()
    parts = PreflightMediaParts(next(original), original, authorized=lambda: True)
    assert list(parts) == [FRAME]
    parts.close()
    assert state == {"closed": 1, "after_bad": 0}


def test_revocation_before_second_read_never_touches_producer():
    approved = [True]
    state = {"reads": 0, "closed": 0}

    def source():
        try:
            yield FRAME
            state["reads"] += 1
            yield FRAME
        finally:
            state["closed"] += 1

    source_iterator = source()
    parts = PreflightMediaParts(
        next(source_iterator), source_iterator, authorized=lambda: approved[0],
    )
    assert next(parts) == FRAME
    approved[0] = False
    with pytest.raises(StopIteration):
        next(parts)
    parts.close()
    assert state == {"reads": 0, "closed": 1}


def test_revocation_during_blocking_next_drops_already_decoded_part():
    approved = [True]
    started = Event()
    proceed = Event()
    received = []
    state = {"closed": 0}

    def source():
        try:
            yield FRAME
            started.set()
            if not proceed.wait(timeout=5):
                raise AssertionError("synthetic decoder hung")
            yield FRAME
        finally:
            state["closed"] += 1

    iterator = source()
    parts = PreflightMediaParts(next(iterator), iterator, authorized=lambda: approved[0])
    assert next(parts) == FRAME

    def read():
        try:
            received.append(next(parts))
        except StopIteration:
            received.append(None)

    worker = Thread(target=read)
    worker.start()
    try:
        assert started.wait(timeout=3)
        approved[0] = False
    finally:
        proceed.set()
        worker.join(timeout=5)
    assert not worker.is_alive()
    assert received == [None]
    parts.close()
    assert state["closed"] == 1


def test_authorization_callback_error_fails_closed_without_leaking_secret():
    class FailingAuthorization:
        def __call__(self):
            raise RuntimeError("rtsp://user:SECRET@127.0.0.2/camera")

    def source():
        yield FRAME
        raise AssertionError("no second read on denied access")

    original = source()
    parts = PreflightMediaParts(next(original), original, authorized=FailingAuthorization())
    with pytest.raises(StopIteration):
        next(parts)
    parts.close()


def test_http_bridge_caps_frames_even_if_producer_ignores_limits():
    state = {"generated": 0, "closed": 0}

    def source():
        try:
            while True:
                state["generated"] += 1
                yield FRAME
        finally:
            state["closed"] += 1

    original = source()
    parts = PreflightMediaParts(next(original), original, authorized=lambda: True)
    assert len(list(parts)) == MAX_PREVIEW_PARTS
    assert state["generated"] == MAX_PREVIEW_PARTS
    parts.close()
    assert state["closed"] == 1
