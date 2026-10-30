"""Local Edge bridge security regression tests (synthetic images ONLY)."""
import pytest
from fastapi.testclient import TestClient

from privacy_approval_fixture import make_policy
from sentinel_edge.local_media_bridge import (
    BridgeConfig, create_bridge_app, COOKIE_NAME, MEDIA_SCHEMA,
    SESSION_SECONDS,
)

CAMERA = "staged-camera-01"
SECRET = "TEST-ONLY-local-operator-separate-from-camera-2026"
ORIGIN = "http://127.0.0.1:5173"
PRIVATE_CAMERA_URL = "rtsp://synthetic-viewer:fake-only@192.168.100.8:554/Streaming/Channels/102"
POST_PATH = f"/api/v1/cameras/{CAMERA}/preview-sessions"


class FakeTime:
    value = 10_000.0

    def __call__(self):
        return self.value


def setup(tmp_path, monkeypatch, *, valid=True, fake=None, clock=None,
          client_ip="127.0.0.1", configured=True):
    policy = make_policy(tmp_path, monkeypatch)
    monkeypatch.setenv("VIIL_CAMERA_RTSP", PRIVATE_CAMERA_URL)
    if not valid:
        policy.unlink()
    config = BridgeConfig(
        enabled=configured, camera_id=CAMERA,
        source_env="VIIL_CAMERA_RTSP", approval_path=policy,
        operator_password=SECRET,
    )
    calls = []
    def synthetic_parts(_cv2, **kwargs):
        calls.append(kwargs)
        assert kwargs["source_id"] == CAMERA
        assert kwargs["viewer_check"]() is True
        assert kwargs["source_env"] == "VIIL_CAMERA_RTSP"
        assert kwargs["privacy_approval"] == policy
        yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 8\r\n\r\n\xff\xd8FAKE\xff\xd9\r\n"
    app = create_bridge_app(config, media_factory=fake or synthetic_parts,
                            cv2_loader=lambda: object(), clock=clock or FakeTime())
    client = TestClient(
        app, base_url="http://127.0.0.1:8001",
        client=(client_ip, 33912),
    )
    return client, calls, policy


def login(client, *, password=SECRET, origin=ORIGIN):
    return client.post("/api/v1/operator/login", json={"password": password},
                       headers={"Origin": origin})


def start(client):
    return client.post(POST_PATH, headers={"Origin": ORIGIN})


def test_disabled_by_default_does_not_accept_login(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch, configured=False)
    with client:
        assert login(client).status_code == 503
        assert client.get("/api/v1/integrations/overview").status_code == 503
    assert not calls


def test_non_loopback_rejected_before_login(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch, client_ip="198.51.100.7")
    with client:
        assert login(client).status_code == 403
        assert client.get("/api/v1/integrations/overview").status_code == 403
    assert not calls


@pytest.mark.parametrize("origin", [None, "https://outside.example", "http://localhost:8000"])
def test_login_denies_missing_or_wrong_origin(tmp_path, monkeypatch, origin):
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        res = client.post("/api/v1/operator/login", json={"password": SECRET},
                          headers={"Origin": origin} if origin else {})
        assert res.status_code == 403
    assert not calls


def test_login_credentials_not_echoed_and_cookie_is_http_only(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        bad = login(client, password="wrong-pass")
        assert bad.status_code == 401
        assert SECRET not in bad.text
        assert client.get("/api/v1/integrations/overview").status_code == 401
        good = login(client)
        assert good.status_code == 200
        cookie = good.headers["set-cookie"].lower()
        assert "httponly" in cookie and "samesite=strict" in cookie
        assert COOKIE_NAME in good.headers["set-cookie"]
        assert SECRET not in good.text
        snap = client.get("/api/v1/integrations/overview")
        assert snap.status_code == 200
        payload = snap.json()
        assert payload["cameras"][0]["health"] == "unknown"
        assert payload["cameras"][0]["privacy"] == "approved"
        assert payload["cameras"][0]["observed_fps"] is None
        assert "rtsp:" not in snap.text and SECRET not in snap.text
    assert not calls


def test_preview_requires_signed_scope_and_verified_session(tmp_path, monkeypatch):
    client, calls, policy = setup(tmp_path, monkeypatch)
    with client:
        assert start(client).status_code == 401
        assert login(client).status_code == 200
        assert client.post(POST_PATH).status_code == 403
        created = start(client)
        assert created.status_code == 201
        session = created.json()
        assert set(session) == {"schema_version", "camera_id", "session_id", "expires_at"}
        assert session["schema_version"] == MEDIA_SCHEMA
        assert "rtsp:" not in created.text
        path = f"{POST_PATH}/{session['session_id']}/mjpeg"
        streamed = client.get(path)
        assert streamed.status_code == 200
        assert streamed.headers["content-type"].startswith("multipart/x-mixed-replace")
        assert "no-store" in streamed.headers["cache-control"]
        assert b"FAKE" in streamed.content
        assert client.get(path).status_code == 403
        policy.unlink()
        assert client.get("/api/v1/integrations/overview").json()["cameras"][0]["privacy"] == "unverified"
        assert start(client).status_code == 403
    assert len(calls) == 1


def test_logout_and_delete_revoke_camera_sessions(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        assert login(client).status_code == 200
        sid = start(client).json()["session_id"]
        path = f"{POST_PATH}/{sid}"
        assert client.delete(path).status_code == 403
        assert client.delete(path, headers={"Origin": ORIGIN}).status_code == 204
        assert client.get(path + "/mjpeg").status_code == 403
        sid2 = start(client).json()["session_id"]
        logout = client.post("/api/v1/operator/logout", headers={"Origin": ORIGIN})
        assert logout.status_code == 204
        assert client.get(f"{POST_PATH}/{sid2}/mjpeg").status_code == 401
        assert client.get("/api/v1/integrations/overview").status_code == 401
    assert not calls


def test_session_expiry_blocks_media_even_with_cookie(tmp_path, monkeypatch):
    clock = FakeTime()
    client, calls, _ = setup(tmp_path, monkeypatch, clock=clock)
    with client:
        assert login(client).status_code == 200
        sid = start(client).json()["session_id"]
        clock.value += 26
        assert client.get(f"{POST_PATH}/{sid}/mjpeg").status_code == 403
        sid = start(client).json()["session_id"]
        clock.value += SESSION_SECONDS + 1
        assert client.get(f"{POST_PATH}/{sid}/mjpeg").status_code == 401
    assert not calls


def test_origin_and_fetch_site_restrictions(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        assert client.post("/api/v1/operator/login", json={"password": SECRET},
                           headers={"Origin": ORIGIN,
                                    "Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert login(client).status_code == 200
        assert client.get("/api/v1/integrations/overview",
                          headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert client.post(POST_PATH, headers={"Origin": "https://other.test"}).status_code == 403
    assert not calls


def test_wrong_camera_and_invalid_rtsp_fail_closed(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        assert login(client).status_code == 200
        assert client.post("/api/v1/cameras/foreign/preview-sessions",
                           headers={"Origin": ORIGIN}).status_code == 403
        monkeypatch.setenv("VIIL_CAMERA_RTSP", "rtsp://public.example/live")
        assert start(client).status_code == 503
    assert not calls


def test_password_failures_are_rate_limited(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        for _ in range(5):
            assert login(client, password="wrong").status_code == 401
        assert login(client, password=SECRET).status_code == 429
    assert not calls


def test_no_signed_policy_no_video(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch, valid=False)
    with client:
        assert login(client).status_code == 200
        snap = client.get("/api/v1/integrations/overview").json()
        assert snap["cameras"][0]["privacy"] == "unverified"
        assert start(client).status_code == 403
    assert not calls

def test_empty_decoder_returns_503_not_fake_live_video(tmp_path, monkeypatch):
    def no_frames(_cv2, **_kwargs):
        if False:
            yield b"never"
    client, _, _ = setup(tmp_path, monkeypatch, fake=no_frames)
    with client:
        assert login(client).status_code == 200
        sid = start(client).json()["session_id"]
        response = client.get(f"{POST_PATH}/{sid}/mjpeg")
        assert response.status_code == 503
        assert "no-store" in response.headers["cache-control"]
        assert "rtsp://" not in response.text
        # Preflight must revoke the failed session and release its global slot.
        assert start(client).status_code == 201


def test_native_decoder_exception_redacted_and_503(tmp_path, monkeypatch):
    def bad_camera(_cv2, **_kwargs):
        raise RuntimeError("rtsp://synthetic:TOP-SECRET@192.168.1.2/stream")
        yield b"never"
    client, _, _ = setup(tmp_path, monkeypatch, fake=bad_camera)
    with client:
        assert login(client).status_code == 200
        sid = start(client).json()["session_id"]
        response = client.get(f"{POST_PATH}/{sid}/mjpeg")
        assert response.status_code == 503
        assert "TOP-SECRET" not in response.text
        assert "192.168" not in response.text
        assert start(client).status_code == 201


@pytest.mark.parametrize("first", [
    b"not a jpeg",
    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 7\r\n\r\n\xff\xd8FAKE\xff\xd9\r\n",
    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 8\r\n\r\n\xff\xd8FAKE\xff\xd9",
    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 8\r\n\r\nhello!!!\r\n",
    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 999999\r\n\r\n\xff\xd8\xff\xd9\r\n",
])
def test_malformed_first_frame_does_not_receive_http_200(tmp_path, monkeypatch, first):
    def fake_frames(_cv2, **_kwargs):
        yield first
    client, _, _ = setup(tmp_path, monkeypatch, fake=fake_frames)
    with client:
        assert login(client).status_code == 200
        sid = start(client).json()["session_id"]
        assert client.get(f"{POST_PATH}/{sid}/mjpeg").status_code == 503


def test_only_one_active_camera_session_even_across_logins(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        assert login(client).status_code == 200
        first = start(client).json()["session_id"]
        assert start(client).status_code == 409
        # Logging in from another tab changes the cookie but not the
        # camera's global single-decoder budget.
        assert login(client).status_code == 200
        assert start(client).status_code == 409
        assert client.delete(f"{POST_PATH}/{first}", headers={"Origin": ORIGIN}).status_code == 204
        # A different owner cannot revoke another owner's session.
        assert start(client).status_code == 409
    assert not calls


def test_per_process_operator_session_capacity_capped(tmp_path, monkeypatch):
    client, _, _ = setup(tmp_path, monkeypatch)
    with client:
        for _ in range(8):
            assert login(client).status_code == 200
        assert login(client).status_code == 429


def test_revoked_policy_blocks_queued_stream_without_decoder(tmp_path, monkeypatch):
    client, calls, policy = setup(tmp_path, monkeypatch)
    with client:
        assert login(client).status_code == 200
        sid = start(client).json()["session_id"]
        policy.unlink()
        assert client.get(f"{POST_PATH}/{sid}/mjpeg").status_code == 403
    assert not calls

@pytest.mark.parametrize("available_frames, expected_status", [(11, 503), (13, 200)])
def test_real_edge_producer_is_connected_to_http_preflight(
    tmp_path, monkeypatch, available_frames, expected_status,
):
    """No camera device: exercise the actual Edge 12/12 gate over FastAPI."""
    from types import SimpleNamespace as NS

    from sentinel_edge import pyav_capture
    from sentinel_edge.edge_mjpeg import iter_authorized_mjpeg_parts

    class FakeCamera:
        reads = 0
        released = False

        def isOpened(self):
            return True

        def read(self):
            self.reads += 1
            if self.reads > available_frames:
                return False, None
            return True, NS(
                shape=(432, 768, 3), size=432 * 768 * 3, dtype="uint8",
            )

        def release(self):
            self.released = True

    class FakeCodec:
        IMWRITE_JPEG_QUALITY = 1

        def imencode(self, _ext, _frame, _options):
            return True, NS(tobytes=lambda: b"\xff\xd8MOCK\xff\xd9")

    camera = FakeCamera()
    monkeypatch.setattr(pyav_capture, "open_pyav_capture", lambda _cv2, _url: camera)
    _, _, policy = setup(tmp_path, monkeypatch)
    app = create_bridge_app(
        BridgeConfig(enabled=True, camera_id=CAMERA,
                     source_env="VIIL_CAMERA_RTSP", approval_path=policy,
                     operator_password=SECRET),
        media_factory=iter_authorized_mjpeg_parts, cv2_loader=FakeCodec,
    )
    with TestClient(app, base_url="http://127.0.0.1:8001",
                    client=("127.0.0.1", 33912)) as api:
        assert login(api).status_code == 200
        sid = start(api).json()["session_id"]
        response = api.get(f"{POST_PATH}/{sid}/mjpeg")
        assert response.status_code == expected_status
        assert camera.released
        if expected_status == 200:
            assert b"MOCK" in response.content
            assert camera.reads >= 13
        else:
            assert b"MOCK" not in response.content
            assert camera.reads == 12
