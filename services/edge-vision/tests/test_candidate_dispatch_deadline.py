"""Synthetic-only live candidate handoff tests across blocking callbacks.

A revoked/expired gate must not serialize stale fall-candidate metadata.
No real camera, image, model weights, remote callbacks or patient data.
"""
from io import StringIO

import pytest

from sentinel_edge.detector import TemporalFallDetector
from sentinel_edge.privacy_gate import PrivacyGateDenied
from sentinel_edge.runner import process_capture
from test_runner_integration import FakeCapture, FakeCv2, FakeLandmarker, FakeMp


class ManualClock:
    def __init__(self):
        self.value = 0.0

    def __call__(self):
        return self.value


class CallbackDetector:
    def __init__(self, callback=None):
        self.inner = TemporalFallDetector()
        self.callback = callback
        self.count = 0

    def process(self, frame):
        self.count += 1
        event = self.inner.process(frame)
        if self.callback is not None and self.count == 9:
            self.callback()
        return event


@pytest.mark.parametrize("slow_step", [
    "on_frame", "detector", "on_event", "event_encoder",
])
def test_expired_callback_does_not_serialize_candidate(slow_step):
    clock = ManualClock()
    output = StringIO()
    emitted = []
    count = 0

    def slow():
        clock.value = 2.0  # Beyond the 1s approved epoch.

    def on_frame(_frame):
        nonlocal count
        count += 1
        if count == 9 and slow_step == "on_frame":
            slow()

    def on_event(event):
        emitted.append(event)
        if slow_step == "on_event":
            slow()

    def encode(event):
        if slow_step == "event_encoder":
            slow()
        return {"type": "FALL_CANDIDATE", "id": event.id}

    detector = CallbackDetector(slow if slow_step == "detector" else None)
    stats = process_capture(
        FakeCapture(range(9)), cv2=FakeCv2, mp=FakeMp,
        landmarker=FakeLandmarker(), detector=detector,
        webcam=False, source_id="staged-test", output=output,
        max_duration_seconds=1.0, clock=clock,
        on_frame=on_frame, on_event=on_event, event_encoder=encode,
    )
    assert output.getvalue() == ""
    assert stats.candidate_events == 0
    assert stats.frames_processed == 8
    if slow_step == "on_frame":
        assert detector.count == 8
        assert not emitted
    elif slow_step in ("detector", "event_encoder"):
        assert detector.count == 9
        assert (len(emitted) == 1) == (slow_step == "event_encoder")
    else:
        # on_event was already invoked when the expiry happened; the
        # callback's external effects cannot be rolled back, but output
        # serialization must still be suppressed.
        assert len(emitted) == 1


@pytest.mark.parametrize("revocation_step", [
    "on_frame", "detector", "on_event", "event_encoder",
])
def test_revoked_callback_never_exports_stale_candidate(revocation_step):
    revoked = [False]
    output = StringIO()
    emitted = []
    frame_calls = 0

    def revoke():
        revoked[0] = True

    def check():
        if revoked[0]:
            raise PrivacyGateDenied("Synthetic approval revoked")

    def on_frame(_frame):
        nonlocal frame_calls
        frame_calls += 1
        if frame_calls == 9 and revocation_step == "on_frame":
            revoke()

    def on_event(event):
        emitted.append(event)
        if revocation_step == "on_event":
            revoke()

    def encode(event):
        if revocation_step == "event_encoder":
            revoke()
        return {"id": event.id}

    detector = CallbackDetector(revoke if revocation_step == "detector" else None)
    with pytest.raises(PrivacyGateDenied, match="revoked"):
        process_capture(
            FakeCapture(range(9)), cv2=FakeCv2, mp=FakeMp,
            landmarker=FakeLandmarker(), detector=detector,
            webcam=False, source_id="staged-test", output=output,
            max_duration_seconds=1.0, clock=ManualClock(),
            privacy_check=check, on_frame=on_frame,
            on_event=on_event, event_encoder=encode,
        )
    assert output.getvalue() == ""
    if revocation_step == "on_frame":
        assert detector.count == 8 and not emitted
    if revocation_step == "detector":
        assert detector.count == 9 and not emitted


def test_fast_callbacks_keep_normal_nonclinical_candidate_event():
    output = StringIO()
    received = []
    clock = ManualClock()
    stats = process_capture(
        FakeCapture(range(9)), cv2=FakeCv2, mp=FakeMp,
        landmarker=FakeLandmarker(),
        webcam=False, source_id="staged-test", output=output,
        max_duration_seconds=1.0, clock=clock,
        on_frame=lambda frame: None,
        on_event=received.append,
        event_encoder=lambda event: {"type": "FALL_CANDIDATE", "id": event.id},
        privacy_check=lambda: None,
    )
    assert stats.candidate_events == 1
    assert stats.frames_processed == 9
    assert len(received) == 1
    assert '"type": "FALL_CANDIDATE"' in output.getvalue()
