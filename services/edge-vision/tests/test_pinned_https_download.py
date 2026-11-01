"""Offline tests for exact-Git-blob HTTPS download/no-redirect enforcement.

No actual public datasets, camera network, credentials or HTTP requests.
"""
from urllib.error import HTTPError
from urllib.request import ProxyHandler
from types import SimpleNamespace as NS

import pytest

from sentinel_edge import assist_external, public_dataset_ingest
from sentinel_edge.pinned_https_download import (
    _DenyRedirect, fetch_pinned_https,
)

PINNED = ("https://raw.githubusercontent.com/publisher/repository/"
          + "a" * 40 + "/videos/synthetic.mp4")


class DummyResponse:
    def __init__(self, *, body=b"fake bytes", status=200, url=PINNED):
        self.body = body
        self.status = status
        self.url = url
        self.position = 0
        self.closed = False
        self.read_limits = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def geturl(self):
        return self.url

    def read(self, maximum):
        self.read_limits.append(maximum)
        value = self.body[self.position:self.position + maximum]
        self.position += len(value)
        return value


def fake_opener(response):
    seen = []

    def factory(*handlers):
        seen.extend(handlers)
        return NS(open=lambda request, timeout: response)

    return factory, seen


def test_valid_exact_pinned_https_download_is_bounded_and_proxy_free():
    response = DummyResponse()
    factory, handlers = fake_opener(response)
    assert fetch_pinned_https(
        PINNED, allowed_urls={PINNED}, byte_limit=64, opener_factory=factory,
    ) == b"fake bytes"
    assert response.closed
    assert response.read_limits and all(n <= 65 for n in response.read_limits)
    assert any(isinstance(h, _DenyRedirect) for h in handlers)
    assert any(isinstance(h, ProxyHandler) and not h.proxies for h in handlers)


@pytest.mark.parametrize("redirect_code", [301, 302, 303, 307, 308])
def test_redirect_handler_refuses_every_redirect(redirect_code):
    assert _DenyRedirect().redirect_request(
        None, None, redirect_code, "redirect", {},
        "https://evil.example/collect",
    ) is None


@pytest.mark.parametrize("bad_url", [
    "http://raw.githubusercontent.com/publisher/repository/" + "a" * 40 + "/videos/synthetic.mp4",
    "https://raw.githubusercontent.com.evil.example/publisher/repository/" + "a" * 40 + "/videos/synthetic.mp4",
    "https://user:password@raw.githubusercontent.com/publisher/repository/" + "a" * 40 + "/videos/synthetic.mp4",
    PINNED + "?redirect=1",
    PINNED + "#fragment",
    "file:///C:/confidential.txt",
    "https://evil.example/synthetic.mp4",
    PINNED.replace("synthetic.mp4", "other.mp4"),
])
def test_unknown_or_invalid_source_is_rejected_before_open(bad_url):
    def never_open(*_):
        pytest.fail("Rejected URL must never initialize a network opener")
    with pytest.raises(ValueError, match="source or size not authorized"):
        fetch_pinned_https(
            bad_url, allowed_urls={PINNED}, byte_limit=64, opener_factory=never_open,
        )


def test_even_allowlisted_wrong_hostname_is_rejected():
    bad = "https://evil.example/video.mp4"
    with pytest.raises(ValueError, match="source or size not authorized"):
        fetch_pinned_https(bad, allowed_urls={bad}, byte_limit=64)


@pytest.mark.parametrize("limit", [0, -1, True, 16777217, "64"])
def test_invalid_size_limit_is_rejected_without_network(limit):
    with pytest.raises(ValueError, match="source or size not authorized"):
        fetch_pinned_https(PINNED, allowed_urls={PINNED}, byte_limit=limit)


@pytest.mark.parametrize("response", [
    DummyResponse(status=302),
    DummyResponse(url="https://evil.example/redirected.mp4"),
    DummyResponse(body=b"x" * 65),
    DummyResponse(body=b"\xff" * 80),
])
def test_reject_redirect_status_changed_final_url_and_oversize_response(response):
    factory, _ = fake_opener(response)
    with pytest.raises(ValueError, match="unavailable or unsafe"):
        fetch_pinned_https(
            PINNED, allowed_urls={PINNED}, byte_limit=64, opener_factory=factory,
        )
    assert response.closed


def test_native_url_and_credentials_never_leave_redacted_error():
    def factory(*_):
        def raises(*_args, **_kwargs):
            raise HTTPError("https://user:secret@evil.example/", 302,
                            "redirect secret", {}, None)
        return NS(open=raises)
    with pytest.raises(ValueError) as caught:
        fetch_pinned_https(
            PINNED, allowed_urls={PINNED}, byte_limit=64, opener_factory=factory,
        )
    assert "secret" not in str(caught.value)
    assert "evil.example" not in str(caught.value)
    assert "unavailable or unsafe" in str(caught.value)


@pytest.mark.parametrize("module,known_url", [
    (public_dataset_ingest, public_dataset_ingest._source_url(1, "ADL", "01")),
    (assist_external, assist_external.source_url("adl", "15_stumbling.mp4")),
])
def test_each_dataset_download_is_restricted_to_frozen_catalog(monkeypatch, module, known_url):
    calls = []

    def allowlisted(url, *, allowed_urls, byte_limit):
        calls.append((url, allowed_urls, byte_limit))
        assert url in allowed_urls
        assert all(value.startswith("https://raw.githubusercontent.com/") for value in allowed_urls)
        return b"synthetic"

    monkeypatch.setattr(module, "fetch_pinned_https", allowlisted)
    download = module._fetch_binary if module is public_dataset_ingest else module._download
    assert download(known_url, 30) == b"synthetic"
    assert len(calls) == 1
    assert known_url in calls[0][1]
