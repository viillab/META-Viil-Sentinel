from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def client() -> TestClient:
    return TestClient(create_app(Settings(meta_provider="mock", demo_mode=True)))


def test_health_and_empty_feed():
    with client() as api:
        assert api.get("/health").json()["status"] == "ok"
        assert api.get("/api/v1/incidents").json() == []


def test_end_to_end_simulated_review_flow():
    with client() as api:
        response = api.post("/api/v1/incidents/demo", json={"source_id": "staged-01", "confidence": 0.7})
        assert response.status_code == 201
        incident = response.json()
        assert incident["simulated"] is True
        assert incident["status"] == "NOTIFIED"
        assert incident["notification_sent"] is True
        assert incident["observation"]["generated_by"] == "mock"
        incident_id = incident["id"]
        assert len(api.get(f"/api/v1/incidents/{incident_id}").json()["history"]) == 3
        for action, status in [
            ("ACKNOWLEDGE", "ACKNOWLEDGED"),
            ("VERIFY", "VERIFIED"),
            ("RESOLVE", "RESOLVED"),
        ]:
            result = api.post(
                f"/api/v1/incidents/{incident_id}/review",
                json={"action": action, "actor": "Test Caregiver"},
            )
            assert result.status_code == 200
            assert result.json()["status"] == status
        assert api.get("/api/v1/incidents").json()[0]["status"] == "RESOLVED"


def test_incorrect_transition_returns_conflict():
    with client() as api:
        incident_id = api.post("/api/v1/incidents/demo", json={}).json()["id"]
        response = api.post(
            f"/api/v1/incidents/{incident_id}/review",
            json={"action": "VERIFY", "actor": "Caregiver"},
        )
        assert response.status_code == 409


def test_false_alert_path():
    with client() as api:
        incident_id = api.post("/api/v1/incidents/demo", json={}).json()["id"]
        for action in ("ACKNOWLEDGE", "MARK_FALSE_ALERT", "RESOLVE"):
            response = api.post(
                f"/api/v1/incidents/{incident_id}/review",
                json={"action": action, "actor": "Caregiver"},
            )
            assert response.status_code == 200
        assert response.json()["status"] == "RESOLVED"


def test_no_unauthenticated_actions_outside_demo():
    with TestClient(create_app(Settings(meta_provider="mock", demo_mode=False))) as api:
        assert api.post("/api/v1/incidents/demo", json={}).status_code == 403


def test_invalid_input_validation():
    with client() as api:
        assert api.post("/api/v1/incidents/demo", json={"confidence": 99}).status_code == 422
