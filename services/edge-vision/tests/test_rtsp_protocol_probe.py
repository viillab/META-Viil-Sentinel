"""Credential-free RTSP OPTIONS probe tests; no real network connection."""
import json

import pytest

from sentinel_edge import rtsp_protocol_probe as probe


class FakeSocket:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.request = None
        self.timeout = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def settimeout(self, seconds):
        self.timeout = seconds

    def sendall(self, request):
        self.request = request

    def recv(self, _max_bytes):
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


@pytest.mark.parametrize(("status", "auth"), [
    (200, False), (401, True), (404, False), (501, False),
])
def test_rtsp_server_status_but_no_decoded_video_or_login(monkeypatch, status, auth):
    fake = FakeSocket([f"RTSP/1.0 {status} OK\r\nPublic: PLAY\r\n\r\n".encode()])
    called = []

    def connect(address, timeout):
        called.append((address, timeout))
        return fake

    monkeypatch.setattr(probe.socket, "create_connection", connect)
    result = probe.probe_options("192.168.50.25")
    assert called == [(("192.168.50.25", 554), 2.5)]
    assert fake.request == (
        b"OPTIONS rtsp://192.168.50.25:554/ RTSP/1.0\r\nCSeq: 1\r\n\r\n"
    )
    assert b"Authorization" not in fake.request
    assert b"DESCRIBE" not in fake.request
    assert b"PLAY" not in fake.request
    assert fake.timeout == 2.5
    assert result["result"] == "rtsp_server_responded"
    assert result["rtsp_status_code"] == status
    assert result["authentication_challenge"] is auth
    assert result["video_decoded"] is False
    assert result["privacy_approval_verified"] is False
    assert not result["credentials_used"]
    assert "Public" not in str(result)


def test_fragmented_rtsp_line_supported(monkeypatch):
    fake = FakeSocket([b"RTS", b"P/1.0 401 Unauthorized\r\n"])
    monkeypatch.setattr(probe.socket, "create_connection", lambda *_a, **_k: fake)
    assert probe.probe_options("10.2.3.4")["authentication_challenge"] is True


@pytest.mark.parametrize("payload", [
    b"HTTP/1.1 200 OK\r\n\r\n",
    b"SSH-2.0-OpenSSH\r\n",
    b"",
    b"RTSP/1.0 999 Anything\r\n",
])
def test_non_rtsp_response_is_not_claimed_as_camera(monkeypatch, payload):
    fake = FakeSocket([payload])
    monkeypatch.setattr(probe.socket, "create_connection", lambda *_a, **_k: fake)
    report = probe.probe_options("172.22.1.10")
    assert report["result"] == "non_rtsp_or_invalid_response"
    assert report["video_decoded"] is False


def test_timeout_fails_closed_without_leaking_native_error(monkeypatch):
    def fail(*_args, **_kw):
        raise OSError("synthetic_secret_rtsp_url")

    monkeypatch.setattr(probe.socket, "create_connection", fail)
    result = probe.probe_options("192.168.20.10")
    assert result["result"] == "transport_or_protocol_timeout"
    assert "synthetic_secret_rtsp_url" not in str(result)


@pytest.mark.parametrize("ip,port,timeout", [
    ("8.8.8.8", 554, 1.0),
    ("127.0.0.1", 554, 1.0),
    ("169.254.169.254", 554, 1.0),
    ("fe80::1", 554, 1.0),
    ("camera.example", 554, 1.0),
    ("192.168.1.2", 9554, 1.0),
    ("192.168.1.2", True, 1.0),
    ("192.168.1.2", 554, 0.01),
    ("192.168.1.2", 554, 10.0),
])
def test_unsafe_target_rejected_before_opening_socket(monkeypatch, ip, port, timeout):
    def forbidden(*_a, **_k):
        raise AssertionError("network call not permitted")

    monkeypatch.setattr(probe.socket, "create_connection", forbidden)
    with pytest.raises(ValueError):
        probe.probe_options(ip, port=port, timeout_seconds=timeout)


def test_cli_reports_only_sanitized_metadata(monkeypatch, capsys):
    fake = FakeSocket([b"RTSP/1.0 401 Unauthorized\r\nWWW-Authenticate: Digest secret\r\n"])
    monkeypatch.setattr(probe.socket, "create_connection", lambda *_a, **_k: fake)
    assert probe.main(["--camera-ip", "192.168.10.25"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out)["authentication_challenge"] is True
    assert "Digest" not in out
    assert "192.168.10.25" not in out
