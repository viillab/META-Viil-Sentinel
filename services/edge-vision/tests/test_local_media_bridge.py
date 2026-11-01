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



def test_transport_status_never_claims_browser_render_or_exposes_camera_secret(
    tmp_path, monkeypatch,
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    second_requested = Event()
    release = Event()
    frame = (
        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 8"
        b"\r\n\r\n\xff\xd8FAKE\xff\xd9\r\n"
    )

    def staged_frames(_cv2, **kwargs):
        assert kwargs["viewer_check"]()
        yield frame
        second_requested.set()
        assert release.wait(timeout=6), "synthetic stream was not released"
        if kwargs["viewer_check"]():
            yield frame

    client, calls, policy = setup(tmp_path, monkeypatch, fake=staged_frames)
    with client:
        assert client.get(f"{POST_PATH}/Xx9_abcDefGhIjKlMnOpQr/status").status_code == 401
        assert login(client).status_code == 200
        sid = start(client).json()["session_id"]
        status_path = f"{POST_PATH}/{sid}/status"
        pending = client.get(status_path)
        assert pending.status_code == 200
        assert pending.json() == {
            "schema_version": "viil.local.preview_transport_status.v1",
            "camera_id": CAMERA, "session_id": sid,
            "edge_first_jpeg_verified": False,
            "edge_preflight_started": False,
            "browser_image_display_verified": False,
        }
        assert "rtsp://" not in pending.text and SECRET not in pending.text
        assert client.get(
            f"/api/v1/cameras/foreign/preview-sessions/{sid}/status"
        ).status_code == 403
        assert client.get(f"{POST_PATH}/Xx9_abcDefGhIjKlMnOpQr/status").status_code == 403

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(client.get, f"{POST_PATH}/{sid}/mjpeg")
            try:
                assert second_requested.wait(timeout=4), "first JPEG not handed to ASGI"
                active = client.get(status_path)
                assert active.status_code == 200
                assert active.json()["edge_first_jpeg_verified"] is True
                assert active.json()["edge_preflight_started"] is True
                assert active.json()["browser_image_display_verified"] is False
                assert SECRET not in active.text and "rtsp://" not in active.text
                assert start(client).status_code == 409
                # The owner may revoke without exposing image or metadata.
                assert client.delete(
                    f"{POST_PATH}/{sid}", headers={"Origin": ORIGIN}
                ).status_code == 204
                assert client.get(status_path).status_code == 403
                assert start(client).status_code == 409
            finally:
                release.set()
            completed = future.result(timeout=8)
            assert completed.status_code == 200
        assert start(client).status_code == 201
        # A missing/invalid signed approval revokes status immediately.
        policy.unlink()
        assert client.get(status_path).status_code == 403
    assert len(calls) == 0  # custom fake source was used, never a camera


def test_preview_status_requires_current_owner_session(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        assert login(client).status_code == 200
        sid = start(client).json()["session_id"]
        endpoint = f"{POST_PATH}/{sid}/status"
        assert client.get(endpoint).status_code == 200
        assert login(client).status_code == 200  # new cookie, not the old owner
        assert client.get(endpoint).status_code == 403
        assert client.get(endpoint, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert not calls


def test_completed_camera_stream_releases_global_session_slot(tmp_path, monkeypatch):
    """A finished stream must permit a new session, without manual DELETE."""
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        assert login(client).status_code == 200
        first = start(client)
        assert first.status_code == 201
        first_sid = first.json()["session_id"]
        assert client.get(f"{POST_PATH}/{first_sid}/mjpeg").status_code == 200
        assert client.get(f"{POST_PATH}/{first_sid}/mjpeg").status_code == 403
        second = start(client)
        assert second.status_code == 201
        assert second.json()["session_id"] != first_sid
        assert client.get(f"{POST_PATH}/{second.json()['session_id']}/mjpeg").status_code == 200
    assert len(calls) == 2

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


def test_failed_native_preflight_close_is_redacted_and_fail_closed(
    tmp_path, monkeypatch,
):
    """A native close failure may leave an active handle: never reopen it."""
    def unsafe_source(_cv2, **_kwargs):
        try:
            yield b"invalid synthetic MJPEG frame"
        finally:
            raise RuntimeError("rtsp://private:TOP-SECRET@192.168.1.2/live")

    client, _, _ = setup(tmp_path, monkeypatch, fake=unsafe_source)
    with client:
        assert login(client).status_code == 200
        sid = start(client).json()["session_id"]
        result = client.get(f"{POST_PATH}/{sid}/mjpeg")
        assert result.status_code == 503
        assert "TOP-SECRET" not in result.text
        assert "192.168" not in result.text
        assert "no-store" in result.headers["cache-control"]
        # Native resource disposal is not proven. A new decoder would
        # exceed the one-handle privacy and memory budget.
        assert start(client).status_code == 409


@pytest.mark.parametrize("second", [
    b"unexpected second frame",
    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 99"
    b"\r\n\r\n\xff\xd8FAKE\xff\xd9\r\n",
    b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 262145"
    b"\r\n\r\n" + b"X" * 262145 + b"\r\n",
], ids=["non-mjpeg", "wrong-length", "oversize"])
def test_bridge_drops_invalid_followup_without_leaking_and_releases_slot(
    tmp_path, monkeypatch, second,
):
    """Actual HTTP bridge, fake inner producer deliberately lacks validation."""
    frame = (
        b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 8"
        b"\r\n\r\n\xff\xd8FAKE\xff\xd9\r\n"
    )
    state = {"closed": 0, "after_bad": 0}

    def untrusted_media(_cv2, **_kwargs):
        try:
            yield frame
            yield second
            state["after_bad"] += 1
            yield frame
        finally:
            state["closed"] += 1

    client, _, _ = setup(tmp_path, monkeypatch, fake=untrusted_media)
    with client:
        assert login(client).status_code == 200
        sid = start(client).json()["session_id"]
        response = client.get(f"{POST_PATH}/{sid}/mjpeg")
        assert response.status_code == 200  # First valid JPEG already streamed.
        assert response.content == frame  # Invalid second JPEG is never sent.
        assert state == {"closed": 1, "after_bad": 0}
        assert "no-store" in response.headers["cache-control"]
        # Healthy cleanup must permit a new preview and avoid wedging capacity.
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

def test_slow_authorized_edge_preflight_returns_503_and_reopens_slot(
    tmp_path, monkeypatch,
):
    """FastAPI uses actual MJPEG Edge preflight with a controlled monotonic clock."""
    from types import SimpleNamespace as NS

    from sentinel_edge.edge_mjpeg import iter_authorized_mjpeg_parts

    class SlowFakeClock:
        value = 0.0

        def now(self):
            return self.value

        def sleep(self, seconds):
            self.value += seconds

    timer = SlowFakeClock()

    class SlowCamera:
        reads = 0
        released = False

        def isOpened(self):
            return True

        def read(self):
            self.reads += 1
            timer.value += 1.5
            return True, NS(shape=(432, 768, 3), size=432 * 768 * 3, dtype="uint8")

        def release(self):
            self.released = True

    class FakeCV2:
        IMWRITE_JPEG_QUALITY = 1

        def imencode(self, *_args, **_kwargs):
            raise AssertionError("Preflight over budget must never encode a JPEG")

    camera = SlowCamera()

    def slow_media(cv2, **kwargs):
        yield from iter_authorized_mjpeg_parts(
            cv2, **kwargs, open_capture=lambda _cv2, _url: camera,
            clock=timer.now, sleeper=timer.sleep,
        )

    _, _, policy = setup(tmp_path, monkeypatch)
    app = create_bridge_app(
        BridgeConfig(enabled=True, camera_id=CAMERA,
                     source_env="VIIL_CAMERA_RTSP", approval_path=policy,
                     operator_password=SECRET),
        media_factory=slow_media, cv2_loader=FakeCV2,
    )
    with TestClient(app, base_url="http://127.0.0.1:8001",
                    client=("127.0.0.1", 33912)) as api:
        assert login(api).status_code == 200
        sid = start(api).json()["session_id"]
        response = api.get(f"{POST_PATH}/{sid}/mjpeg")
        assert response.status_code == 503
        assert "no-store" in response.headers["cache-control"]
        assert PRIVATE_CAMERA_URL not in response.text
        assert camera.released and camera.reads < 12
        # An expired preflight must not leak a camera-wide decoder slot.
        assert start(api).status_code == 201


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


@pytest.mark.parametrize("revocation", ["delete", "logout"])
def test_revoke_while_decoder_preflight_busy_releases_global_slot(
    tmp_path, monkeypatch, revocation,
):
    """Never allow a second decoder while the first preflight is unwinding."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    started = Event()
    release = Event()
    cleanup = Event()

    def blocked_camera(_cv2, **kwargs):
        try:
            started.set()
            assert release.wait(timeout=6), "synthetic decoder never released"
            # Real Edge checks this both before reads and after each frame.
            if kwargs["viewer_check"]():
                yield b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: 8\r\n\r\n\xff\xd8FAKE\xff\xd9\r\n"
        finally:
            cleanup.set()

    client, _, _ = setup(tmp_path, monkeypatch, fake=blocked_camera)
    with client:
        assert login(client).status_code == 200
        sid = start(client).json()["session_id"]
        path = f"{POST_PATH}/{sid}/mjpeg"
        with ThreadPoolExecutor(max_workers=1) as pool:
            task = pool.submit(client.get, path)
            try:
                assert started.wait(timeout=4)
                if revocation == "delete":
                    assert client.delete(f"{POST_PATH}/{sid}",
                                         headers={"Origin": ORIGIN}).status_code == 204
                else:
                    assert client.post("/api/v1/operator/logout",
                                       headers={"Origin": ORIGIN}).status_code == 204
                    assert login(client).status_code == 200
                # Even with original preview revoked, native capture has
                # not been released yet. A new POST must NOT open a decoder.
                assert start(client).status_code == 409
            finally:
                release.set()
            result = task.result(timeout=7)
            assert result.status_code == 503
            assert cleanup.wait(timeout=2)
            assert start(client).status_code == 201


def test_approval_checklist_requires_authenticated_local_operator(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        assert client.get("/api/v1/operator/approval-checklist").status_code == 401
        assert login(client).status_code == 200
        assert client.get("/api/v1/operator/approval-checklist",
                          headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        result = client.get("/api/v1/operator/approval-checklist")
        assert result.status_code == 200
        assert result.json() == {
            "schema_version": "viil.local.unsigned_approval_checklist.v1",
            "draft_available": False,
            "draft_fields_structurally_complete": False,
            "issues": [],
            "genuine_site_permission_confirmed_by_tool": False,
            "signed_policy_verified": False,
            "camera_access_granted": False,
        }
    assert not calls


def test_approval_checklist_only_reports_safe_field_names(tmp_path, monkeypatch):
    import json

    from sentinel_edge.local_media_bridge import BridgeConfig, create_bridge_app
    from sentinel_edge.privacy_approval_operator import unsigned_template

    _, _, policy = setup(tmp_path, monkeypatch)
    draft = tmp_path / "operator-unsigned-draft.json"
    specimen = unsigned_template(CAMERA)
    specimen["notice_ref"] = "PRIVATE_OWNER_NOTICE_REFERENCE_DO_NOT_EXPOSE"
    draft.write_text(json.dumps(specimen), encoding="utf-8")
    app = create_bridge_app(
        BridgeConfig(enabled=True, camera_id=CAMERA,
                     source_env="VIIL_CAMERA_RTSP", approval_path=policy,
                     unsigned_draft_path=draft, operator_password=SECRET),
        cv2_loader=lambda: (_ for _ in ()).throw(
            AssertionError("Read-only checklist must not open camera")
        ),
    )
    with TestClient(app, base_url="http://127.0.0.1:8001",
                    client=("127.0.0.1", 32112)) as client:
        assert login(client).status_code == 200
        result = client.get("/api/v1/operator/approval-checklist")
        assert result.status_code == 200
        payload = result.json()
        assert payload["draft_available"] is True
        assert payload["draft_fields_structurally_complete"] is False
        assert "approval_ref" in payload["issues"]
        assert "validity_window" in payload["issues"]
        assert "site_authorization_confirmed" in payload["issues"]
        assert "notices_confirmed" in payload["issues"]
        assert payload["signed_policy_verified"] is False
        assert payload["genuine_site_permission_confirmed_by_tool"] is False
        assert payload["camera_access_granted"] is False
        assert "PRIVATE_OWNER_NOTICE_REFERENCE" not in result.text
        assert str(draft) not in result.text
        assert SECRET not in result.text
        assert "rtsp://" not in result.text


def test_approval_checklist_malformed_draft_fails_closed(tmp_path, monkeypatch):
    from sentinel_edge.local_media_bridge import BridgeConfig, create_bridge_app

    _, _, policy = setup(tmp_path, monkeypatch)
    draft = tmp_path / "broken-private-policy.json"
    draft.write_text('{"notice_ref":"DO_NOT_EXPOSE","notice_ref":"duplicate"}',
                     encoding="utf-8")
    config = BridgeConfig(enabled=True, camera_id=CAMERA,
                          source_env="VIIL_CAMERA_RTSP", approval_path=policy,
                          operator_password=SECRET, unsigned_draft_path=draft)
    with TestClient(create_bridge_app(config), base_url="http://127.0.0.1:8001",
                    client=("127.0.0.1", 32112)) as client:
        assert login(client).status_code == 200
        response = client.get("/api/v1/operator/approval-checklist")
        assert response.status_code == 200
        assert response.json()["draft_available"] is False
        assert response.json()["issues"] == []
        assert "DO_NOT_EXPOSE" not in response.text


def test_camera_readiness_requires_operator_and_is_metadata_only(tmp_path, monkeypatch):
    import sentinel_edge.local_media_bridge as local_bridge
    # CI need not install optional camera/video dependencies.
    monkeypatch.setattr(local_bridge, "find_spec", lambda _name: object())
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        assert client.get("/api/v1/operator/camera-readiness").status_code == 401
        assert login(client).status_code == 200
        response = client.get("/api/v1/operator/camera-readiness")
        assert response.status_code == 200
        result = response.json()
        assert result == {
            "schema_version": "viil.local.camera_readiness.v1",
            "camera_id": CAMERA,
            "signed_privacy_approval_verified": True,
            "private_rtsp_configured": True,
            "pyav_decoder_installed": True,
            "opencv_jpeg_encoder_installed": True,
            "eligible_for_supervised_trial": True,
            "real_camera_frame_verified": False,
        }
        assert "rtsp://" not in response.text
        assert SECRET not in response.text
    assert calls == []  # GET cannot try any camera or decode


def test_camera_readiness_missing_policy_or_private_rtsp_reports_not_ready(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch, valid=False)
    with client:
        assert login(client).status_code == 200
        result = client.get("/api/v1/operator/camera-readiness").json()
        assert result["signed_privacy_approval_verified"] is False
        assert result["eligible_for_supervised_trial"] is False
        monkeypatch.setenv("VIIL_CAMERA_RTSP", "rtsp://public.example/live")
        result = client.get("/api/v1/operator/camera-readiness").json()
        assert result["private_rtsp_configured"] is False
        assert result["eligible_for_supervised_trial"] is False
    assert not calls


def test_readiness_missing_optional_decoder_does_not_claim_video(tmp_path, monkeypatch):
    import sentinel_edge.local_media_bridge as local_bridge

    installed = local_bridge.find_spec
    monkeypatch.setattr(
        local_bridge, "find_spec",
        lambda name: None if name == "av" else installed(name),
    )
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        assert login(client).status_code == 200
        result = client.get("/api/v1/operator/camera-readiness").json()
        assert result["pyav_decoder_installed"] is False
        assert result["eligible_for_supervised_trial"] is False
        assert result["real_camera_frame_verified"] is False
    assert not calls


def test_readiness_denies_cross_site_request(tmp_path, monkeypatch):
    client, calls, _ = setup(tmp_path, monkeypatch)
    with client:
        assert login(client).status_code == 200
        assert client.get("/api/v1/operator/camera-readiness",
                          headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert not calls
