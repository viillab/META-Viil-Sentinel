"""RTSP runtime security integration with fake captures and fake models only.

The tests deliberately supply an invented credential in synthetic exception
strings; no camera, network, RTSP transport, real key or media is touched.
"""
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from sentinel_edge import runner
from sentinel_edge.privacy_gate import PrivacyGateDenied


FAKE_SECRET = "invented-rtsp-password"
FAKE_URL = f"rtsp://test:{FAKE_SECRET}@192.168.88.10:554/Streaming/Channels/102"


class FakeCapture:
    def __init__(self, *, on_opened=None, fail_on_release=True):
        self.released = False
        self.opened_calls = 0
        self.on_opened = on_opened
        self.fail_on_release = fail_on_release

    def isOpened(self):
        self.opened_calls += 1
        if self.on_opened is not None:
            self.on_opened()
        return True

    def release(self):
        self.released = True
        if self.fail_on_release:
            raise RuntimeError("Native decoder cleanup failed: " + FAKE_URL)


class FakePose:
    def __init__(self, on_enter=None):
        self.closed = False
        self.on_enter = on_enter

    def __enter__(self):
        if self.on_enter is not None:
            self.on_enter()
        return self

    def __exit__(self, *_):
        self.closed = True


class FakeMp:
    def __init__(self, *, on_model=None):
        self.pose = FakePose(on_enter=on_model)
        self.created = 0

        def create(_):
            self.created += 1
            return self.pose

        self.tasks = NS(
            BaseOptions=lambda **kwargs: kwargs,
            vision=NS(
                PoseLandmarkerOptions=lambda **kwargs: kwargs,
                RunningMode=NS(VIDEO="video"),
                PoseLandmarker=NS(create_from_options=create),
            ),
        )


def params(tmp_path: Path):
    model = tmp_path / "test.task"
    model.write_bytes(b"synthetic test model path; no actual model inference")
    return NS(
        model=model, profile_rtsp=False, max_frames=1,
        rtsp_session_seconds=2, rtsp_retries=0, rtsp_retry_delay_ms=250,
        source_id="synthetic-camera",
    )


@pytest.mark.parametrize(("deny_check", "expected_opened", "expected_model"), [
    (2, 0, 0),  # Native opening completed, approval revoked before isOpened
    (3, 1, 0),  # Revoked after native isOpened
    (4, 1, 1),  # Revoked during native model initialization
])
def test_live_approval_revocation_aborts_and_closes_without_secret_leak(
    tmp_path, monkeypatch, capsys, deny_check, expected_opened, expected_model,
):
    cap = FakeCapture()
    mp = FakeMp()
    monkeypatch.setattr(runner, "open_rtsp_capture", lambda *_: cap)
    monkeypatch.setattr(
        runner, "process_capture",
        lambda *_args, **_kwargs: pytest.fail("Revoked RTSP must never infer"),
    )
    checks = []

    def verify():
        checks.append(True)
        if len(checks) == deny_check:
            raise PrivacyGateDenied("Approval was revoked: " + FAKE_URL)

    with pytest.raises(PrivacyGateDenied):
        runner._run_rtsp_retry_mode(
            params(tmp_path), NS(), mp, FAKE_URL, privacy_check=verify,
        )

    assert len(checks) == deny_check
    assert cap.released is True
    assert cap.opened_calls == expected_opened
    assert mp.created == expected_model
    stderr = capsys.readouterr().err
    assert FAKE_URL not in stderr and FAKE_SECRET not in stderr


def test_rtsp_native_release_failure_never_changes_successful_trial(
    tmp_path, monkeypatch, capsys,
):
    cap = FakeCapture()
    mp = FakeMp()
    monkeypatch.setattr(runner, "open_rtsp_capture", lambda *_: cap)
    monkeypatch.setattr(
        runner, "process_capture",
        lambda *_a, **_kw: runner.StreamStats(1, 1, 0),
    )
    result = runner._run_rtsp_retry_mode(
        params(tmp_path), NS(), mp, FAKE_URL, privacy_check=lambda: None,
    )
    assert result == 0
    assert cap.released
    assert mp.pose.closed
    result_text = capsys.readouterr()
    assert FAKE_URL not in result_text.err + result_text.out
    assert FAKE_SECRET not in result_text.err + result_text.out
    assert "1 frames" in result_text.err


def test_uncaught_native_processing_exception_is_redacted_and_no_retry(
    tmp_path, monkeypatch, capsys,
):
    cap = FakeCapture()
    mp = FakeMp()
    attempts = []
    monkeypatch.setattr(
        runner, "open_rtsp_capture",
        lambda *_: (attempts.append(True), cap)[1],
    )

    def fail_after_open(*_a, **_kw):
        raise RuntimeError("Native capture failure: " + FAKE_URL)

    monkeypatch.setattr(runner, "process_capture", fail_after_open)
    args = params(tmp_path)
    args.rtsp_retries = 1
    result = runner._run_rtsp_retry_mode(
        args, NS(), mp, FAKE_URL, privacy_check=lambda: None,
    )
    assert result == 2
    assert len(attempts) == 1
    assert cap.released
    assert mp.pose.closed
    stderr = capsys.readouterr().err
    assert "details redacted" in stderr
    assert FAKE_URL not in stderr and FAKE_SECRET not in stderr


def test_capture_release_helper_is_best_effort_without_raw_tracebacks():
    cap = FakeCapture()
    assert runner._release_capture_redacted(cap) is None
    assert cap.released is True
