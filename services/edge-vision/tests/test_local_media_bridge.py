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
