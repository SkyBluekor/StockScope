from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_reports_read_only_service() -> None:
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    assert payload["real_trading"] is False


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
