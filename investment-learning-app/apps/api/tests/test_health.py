from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_live_does_not_touch_db():
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_ready_succeeds_when_db_migrated():
    response = client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_health_ready_response_has_no_sensitive_fields():
    response = client.get("/health/ready")
    body_text = response.text.lower()
    assert "postgresql" not in body_text
    assert "password" not in body_text
    assert "traceback" not in body_text


def test_v1_routes_registered():
    paths = {route.path for route in app.routes}
    assert "/v1/portfolios/{portfolio_id}/orders" in paths
    assert "/v1/journals/pre-trade" in paths
