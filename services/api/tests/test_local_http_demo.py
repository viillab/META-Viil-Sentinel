"""Loopback TCP-only synthetic demo and remote demo-route isolation tests."""
import json
import socket
from urllib.parse import urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.local_http_demo import loopback_http_server, run_local_http_demo
from app.main import create_app

REMOTE = ("203.0.113.77", 54321)
INCIDENT = "00000000-0000-4000-8000-000000000000"


def test_real_local_tcp_edge_to_sqlite_to_caregiver_inbox(monkeypatch):
    # The HTTP demo must use fresh ephemeral demo-only keys, not existing .env.
    monkeypatch.setenv("META_MODEL_API_KEY", "fake-parent-meta-key-never-use")
    monkeypatch.setenv("EDGE_CANDIDATE_HMAC_SECRET", "fake-parent-hmac-key-never-use")
    monkeypatch.setenv("CAREGIVER_INBOX_TOKEN", "fake-parent-caregiver-key-never-use")
    result = run_local_http_demo()
    assert result["result"] == "LOCAL_TCP_HTTP_EDGE_TO_INBOX_PASS"
    assert result["transport"] == "ephemeral 127.0.0.1 TCP HTTP"
    assert result["actual_edge_python_emitter"] is True
    assert result["sitting_emits_zero_candidates"] is True
    assert result["signed_edge_candidate_accepted"] is True
    assert result["deduplication_verified"] is True
    assert result["caregiver_read_only_inbox_verified"] is True
    assert result["unsigned_and_forged_requests_rejected"] is True
    assert result["untrusted_browser_origin_rejected_by_cors"] is True
    assert result["server_stopped"] is True
    assert result["temporary_sqlite_removed"] is True
    assert result["meta_api_called"] is False
    assert result["notifications_sent"] is False
    assert result["real_camera_used"] is False
    assert result["caregiver_production_login_enabled"] is False
    assert "fake-parent" not in json.dumps(result)


def test_loopback_server_uses_real_socket_and_closes_after_success():
    settings = Settings(_env_file=None, meta_provider="mock", demo_mode=False)
    with loopback_http_server(create_app(settings)) as base_url:
        assert base_url.startswith("http://127.0.0.1:")
        port = urlsplit(base_url).port
        assert port is not None
        with httpx.Client(base_url=base_url, trust_env=False, timeout=3) as client:
            assert client.get("/health").status_code == 200
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)


def test_loopback_server_closes_after_exception():
    settings = Settings(_env_file=None, meta_provider="mock", demo_mode=False)
    port = None
    with (
        pytest.raises(RuntimeError, match="synthetic test error"),
        loopback_http_server(create_app(settings)) as base_url,
    ):
        port = urlsplit(base_url).port
        raise RuntimeError("synthetic test error")
    assert port is not None
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)


@pytest.mark.parametrize("headers", [
    {},
    {"Host": "localhost:5173"},
    {"X-Forwarded-For": "127.0.0.1"},
    {"X-Real-IP": "127.0.0.1"},
    {"Forwarded": "for=127.0.0.1"},
])
def test_remote_clients_cannot_read_create_or_review_unsecured_demo_incidents(headers):
    config = Settings(_env_file=None, meta_provider="mock", demo_mode=True)
    with TestClient(create_app(config), client=REMOTE) as remote:
        assert remote.get("/health", headers=headers).status_code == 200
        assert remote.get("/api/v1/incidents", headers=headers).status_code == 403
        assert remote.get(
            f"/api/v1/incidents/{INCIDENT}", headers=headers
        ).status_code == 403
        assert remote.post(
            "/api/v1/incidents/demo",
            json={"source_id": "staged-remote", "confidence": 0.6},
            headers=headers,
        ).status_code == 403
        assert remote.post(
            f"/api/v1/incidents/{INCIDENT}/review",
            json={"action": "ACKNOWLEDGE", "actor": "remote attacker"},
            headers=headers,
        ).status_code == 403


def test_local_testclient_demo_flow_remains_opt_in_and_simulated():
    config = Settings(_env_file=None, meta_provider="mock", demo_mode=True)
    with TestClient(create_app(config)) as client:
        new = client.post(
            "/api/v1/incidents/demo",
            json={"source_id": "staged-01", "confidence": 0.6},
        )
        assert new.status_code == 201
        assert new.json()["simulated"] is True
        assert new.json()["observation"]["generated_by"] == "mock"
        incident_id = new.json()["id"]
        assert client.get(f"/api/v1/incidents/{incident_id}").status_code == 200
        assert len(client.get("/api/v1/incidents").json()) == 1
        assert client.post(
            f"/api/v1/incidents/{incident_id}/review",
            json={"action": "ACKNOWLEDGE", "actor": "local demo"},
        ).status_code == 200
