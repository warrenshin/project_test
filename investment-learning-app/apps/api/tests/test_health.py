from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_v1_routes_registered():
    paths = {route.path for route in app.routes}
    assert "/v1/portfolios/{portfolio_id}/orders" in paths
    assert "/v1/journals/pre-trade" in paths
