"""Read-only Hikvision ISAPI metadata audit tests: zero camera/network I/O."""
import json
from types import SimpleNamespace as NS

import pytest

from sentinel_edge import hikvision_isapi_audit as audit


SECRET = "FAKE_SECRET_NEVER_OUTPUT"
XML = """<?xml version="1.0" encoding="UTF-8"?>
<StreamingChannel xmlns="http://www.hikvision.com/ver20/XMLSchema" version="2.0">
<id>{id}</id><serialNumber>SECRET_SERIAL</serialNumber>
<Video>
<videoCodecType>{codec}</videoCodecType>
<videoResolutionWidth>{width}</videoResolutionWidth>
<videoResolutionHeight>{height}</videoResolutionHeight>
<maxFrameRate>{fps}</maxFrameRate>
<vbrUpperCap>{bitrate}</vbrUpperCap>
<videoQualityControlType>VBR</videoQualityControlType>
<h264Profile>Main</h264Profile>
</Video></StreamingChannel>"""


def xml(channel="101", codec="H.264", width="2560", height="1440",
        fps="1500", bitrate="3994"):
    return XML.format(id=channel, codec=codec, width=width, height=height,
                      fps=fps, bitrate=bitrate).encode()


class Response:
    def __init__(self, data, content_type="application/xml"):
        self.headers = {"Content-Type": content_type}
        self._data = data
        self.closed = False
        self.read_limit = None

    def read(self, maximum):
        self.read_limit = maximum
        return self._data[:maximum]

    def close(self):
        self.closed = True


def make_opener(responses, visited, handlers_seen):
    def factory(*handlers):
        handlers_seen.extend(handlers)
        def open_url(request, timeout):
            visited.append((request.full_url, request.get_method(), timeout))
            return responses.pop(0)
        return NS(open=open_url)
    return factory


def test_read_only_digest_audit_prefers_real_h264_substream():
    a = Response(xml())
    b = Response(xml("102", width="768", height="432", fps="1000", bitrate="512"))
    visited, handlers = [], []
    report = audit.audit_camera(
        "192.168.10.204", username="reader", password=SECRET,
        opener_factory=make_opener([a, b], visited, handlers),
    )
    assert report["result"] == "read_only_metadata"
    assert report["recommended_edge_channel"] == "102"
    assert report["http_mjpeg_substream_configured"] is False
    assert report["mjpeg_frames_verified"] is False
    assert report["rtsp_frames_decoded"] is False
    assert report["camera_settings_modified"] is False
    assert report["authorization_for_video_granted"] is False
    assert report["channels"][0]["codec"] == "H.264"
    assert report["channels"][0]["configured_fps"] == 15.0
    assert report["channels"][1]["configured_fps"] == 10.0
    assert report["channels"][1]["width"] == 768
    assert report["channels"][1]["height"] == 432
    assert report["channels"][1]["bitrate_kbps"] == 512
    assert report["channels"][1]["h264_profile"] == "MAIN"
    assert report["channels"][1]["bitrate_control"] == "VBR"
    assert visited == [
        ("http://192.168.10.204:80/ISAPI/Streaming/channels/101", "GET", 3.0),
        ("http://192.168.10.204:80/ISAPI/Streaming/channels/102", "GET", 3.0),
    ]
    assert all(r.closed for r in [a, b])
    assert all(r.read_limit == audit.MAX_XML_BYTES + 1 for r in [a, b])
    assert len(handlers) == 3
    assert any(isinstance(h, audit.HTTPDigestAuthHandler) for h in handlers)
    assert any(isinstance(h, audit._NoRedirect) for h in handlers)
    assert any(isinstance(h, audit.ProxyHandler) and not h.proxies for h in handlers)
    assert SECRET not in str(report)
    assert "SECRET_SERIAL" not in str(report)
    assert "192.168.10.204" not in str(report)


def test_isapi_parser_defuses_dtd_entities_and_external_references(monkeypatch):
    original = audit.safe_xml_fromstring
    observed = []

    def guarded_parse(payload, **kwargs):
        observed.append(kwargs)
        return original(payload, **kwargs)

    monkeypatch.setattr(audit, "safe_xml_fromstring", guarded_parse)
    result = audit.parse_stream_xml(xml(), "101")
    assert result["codec"] == "H.264"
    assert observed == [{
        "forbid_dtd": True,
        "forbid_entities": True,
        "forbid_external": True,
    }]


def test_parser_library_failures_are_redacted(monkeypatch):
    from defusedxml.common import DefusedXmlException

    def malicious_parser(*_args, **_kwargs):
        raise DefusedXmlException("secret XML native parser information")

    monkeypatch.setattr(audit, "safe_xml_fromstring", malicious_parser)
    with pytest.raises(audit.CameraAuditUnavailable) as caught:
        audit.parse_stream_xml(xml(), "101")
    assert "secret" not in str(caught.value).lower()
    assert "invalid hikvision channel metadata" in str(caught.value).lower()


def test_mjpeg_codec_report_is_configuration_only():
    a, b = Response(xml()), Response(xml("102", codec="MJPEG"))
    report = audit.audit_camera(
        "192.168.10.204", username="reader", password=SECRET,
        opener_factory=make_opener([a, b], [], []),
    )
    assert report["recommended_edge_channel"] == "101"
    assert report["http_mjpeg_substream_configured"] is True
    assert report["mjpeg_frames_verified"] is False


@pytest.mark.parametrize("payload", [
    b"",
    b"<!DOCTYPE StreamingChannel><StreamingChannel/>",
    b"<!ENTITY injected 'secret'><StreamingChannel/>",
    b"<StreamingChannel>",
    b"<WrongRoot><Video><videoCodecType>H.264</videoCodecType></Video></WrongRoot>",
    xml("101", codec="malicious"),
    xml("102"),
    b"x" * (audit.MAX_XML_BYTES + 1),
], ids=["empty", "doctype", "entity", "incomplete", "wrong-root",
        "unknown-codec", "wrong-channel", "oversize"])
def test_malformed_or_mismatched_metadata_is_rejected_without_echo(payload):
    with pytest.raises(audit.CameraAuditUnavailable) as caught:
        audit.parse_stream_xml(payload, "101")
    assert "secret" not in str(caught.value).lower()
    assert "malicious" not in str(caught.value)


@pytest.mark.parametrize("ip,port", [
    ("8.8.8.8", 80), ("127.0.0.1", 80), ("169.254.169.254", 80),
    ("fe80::1", 80), ("camera.example", 80), ("192.168.10.204", 443),
    ("192.168.10.204", True), ("192.168.10.204", 0),
])
def test_unsafe_ip_and_port_refused_before_auth_or_network(ip, port):
    called = []
    def factory(*_):
        called.append(True)
        raise AssertionError("Should never connect to unsafe IP")
    with pytest.raises(audit.CameraAuditUnavailable):
        audit.audit_camera(ip, port=port, username="reader", password=SECRET,
                           opener_factory=factory)
    assert not called


@pytest.mark.parametrize("timeout", [0, -1, 0.01, 6, float("inf"), float("nan")])
def test_timeout_is_bounded_before_network(timeout):
    with pytest.raises(audit.CameraAuditUnavailable):
        audit.audit_camera("192.168.10.204", username="reader", password=SECRET,
                           timeout_seconds=timeout, opener_factory=lambda *_: 1)


def test_no_basic_fallback_and_deny_redirect():
    handler = audit._NoRedirect()
    assert handler.redirect_request(
        None, None, 302, "Redirect", {},
        "http://external.example.com/credentials",
    ) is None


def test_invalid_content_type_or_native_error_is_redacted():
    for response in [
        Response(xml(), "text/html"),
        Response(b"a" * (audit.MAX_XML_BYTES + 1)),
    ]:
        with pytest.raises(audit.CameraAuditUnavailable):
            audit.audit_camera(
                "192.168.10.204", username="reader", password=SECRET,
                opener_factory=make_opener([response], [], []),
            )
        assert response.closed
    def failing(*_):
        return NS(open=lambda *_a, **_kw: (_ for _ in ()).throw(
            OSError("rtsp://reader:" + SECRET + "@192.168.10.204"),
        ))
    with pytest.raises(audit.CameraAuditUnavailable) as caught:
        audit.audit_camera("192.168.10.204", username="reader",
                           password=SECRET, opener_factory=failing)
    assert SECRET not in str(caught.value)


def test_cli_outputs_only_allowlisted_values(monkeypatch, capsys):
    monkeypatch.setenv("VIIL_HIK_HTTP_USER", "test-reader")
    monkeypatch.setenv("VIIL_HIK_HTTP_PASS", SECRET)
    def fake_audit(ip, **kw):
        assert ip == "192.168.10.204"
        assert kw["password"] == SECRET
        return {"type": "viil.camera.hikvision_stream_audit.v1",
                "result": "read_only_metadata", "channels": []}
    monkeypatch.setattr(audit, "audit_camera", fake_audit)
    assert audit.main(["--camera-ip", "192.168.10.204"]) == 0
    output = capsys.readouterr().out
    assert json.loads(output)["result"] == "read_only_metadata"
    assert SECRET not in output
    monkeypatch.setattr(audit, "audit_camera", lambda *_a, **_kw: (
        _ for _ in ()).throw(audit.CameraAuditUnavailable(SECRET)),
    )
    assert audit.main(["--camera-ip", "192.168.10.204"]) == 2
    assert SECRET not in capsys.readouterr().out


def test_empty_credentials_fail_before_network():
    with pytest.raises(audit.CameraAuditUnavailable):
        audit.audit_camera("192.168.10.204", username="", password="")


def test_recommendation_not_given_without_rtsp_compatible_codec():
    a, b = Response(xml("101", codec="MJPEG")), Response(xml("102", codec="MJPEG"))
    result = audit.audit_camera(
        "192.168.10.204", username="reader", password=SECRET,
        opener_factory=make_opener([a, b], [], []),
    )
    assert result["recommended_edge_channel"] is None
    assert result["http_mjpeg_substream_configured"] is True
    assert result["rtsp_frames_decoded"] is False


def test_windows_operator_wrapper_avoids_camera_capture_and_secrets():
    import sys
    import subprocess
    from pathlib import Path

    path = Path(__file__).resolve().parents[3] / "scripts" / "inspect-hikvision-streams.ps1"
    contents = path.read_text(encoding="utf-8")
    assert "Read-Host 'Hikvision password (masked, never saved)' -AsSecureString" in contents
    assert "VIIL_HIK_HTTP_PASS" in contents
    assert "SetEnvironmentVariable('VIIL_HIK_HTTP_PASS', $oldPass" in contents
    assert "sentinel_edge.hikvision_isapi_audit" in contents
    assert "VideoCapture" not in contents
    assert "start-hikvision-staged.ps1" not in contents
    if sys.platform == "win32":
        args = [
            "powershell.exe", "-NoProfile", "-File", str(path),
            "-CameraIp", "8.8.8.8",
        ]
        result = subprocess.run(
            args, text=True, capture_output=True, timeout=20, check=False,
        )
        assert result.returncode == 2
        assert "READ ONLY: Inspecting Hikvision ISAPI" not in result.stdout
        assert SECRET not in result.stdout + result.stderr
