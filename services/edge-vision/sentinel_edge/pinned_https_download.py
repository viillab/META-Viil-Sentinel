"""Small pinned HTTPS downloader for published public research datasets.

This is NOT for camera URLs, internal hosts, credentials or arbitrary websites.
A caller supplies a frozen per-dataset URL inventory; any redirect is denied,
including redirects to another raw.githubusercontent.com path. This reduces
cross-origin metadata leakage and keeps publisher commit pinning meaningful.
Payload integrity and license still require separate independent checks.
"""
from collections.abc import Collection, Callable
from urllib.parse import urlsplit
from urllib.request import (
    HTTPRedirectHandler, ProxyHandler, Request, build_opener,
)

MAX_PINNED_DOWNLOAD_BYTES = 16 * 1024 * 1024
PINNED_DOWNLOAD_TIMEOUT_SECONDS = 45


class _DenyRedirect(HTTPRedirectHandler):
    """Refuse all 30x responses, including same-host and protocol changes."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_pinned_https(
    url: str,
    *,
    allowed_urls: Collection[str],
    byte_limit: int,
    opener_factory: Callable = build_opener,
) -> bytes:
    """Download a single allowlisted public Git blob with bounded reads.

    Do not return urllib exceptions because they may contain URL/path details.
    No environment-configured proxy, HTTP redirect or unapproved URL is used.
    """
    if (type(url) is not str
            or url not in allowed_urls
            or type(byte_limit) is not int
            or not 0 < byte_limit <= MAX_PINNED_DOWNLOAD_BYTES):
        raise ValueError("Pinned HTTPS source or size not authorized")
    parsed = urlsplit(url)
    if (parsed.scheme != "https"
            or parsed.netloc != "raw.githubusercontent.com"
            or parsed.query or parsed.fragment
            or not parsed.path.startswith("/")
            or "//" in parsed.path
            or "%2f" in parsed.path.lower()
            or "%5c" in parsed.path.lower()):
        raise ValueError("Pinned HTTPS source or size not authorized")

    try:
        opener = opener_factory(_DenyRedirect(), ProxyHandler({}))
        with opener.open(
            Request(url, headers={"User-Agent": "VIIL-Sentinel-research/1.0"}, method="GET"),
            timeout=PINNED_DOWNLOAD_TIMEOUT_SECONDS,
        ) as response:
            if (response.status != 200
                    or response.geturl() != url):
                raise ValueError("Unapproved HTTPS response")
            pieces: list[bytes] = []
            length = 0
            while True:
                chunk = response.read(min(65536, byte_limit + 1 - length))
                if not chunk:
                    break
                if type(chunk) is not bytes:
                    raise ValueError("Unexpected HTTPS response type")
                length += len(chunk)
                if length > byte_limit:
                    raise ValueError("Pinned HTTPS response too large")
                pieces.append(chunk)
            return b"".join(pieces)
    except (OSError, ValueError, TypeError, AttributeError):
        # urllib HTTPError/URLError contain user-provided URL content.
        raise ValueError("Pinned HTTPS download unavailable or unsafe (redacted)") from None
