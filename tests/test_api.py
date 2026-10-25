import sys
from pathlib import Path

from fastapi.testclient import TestClient

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from app.main import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_shipment_lookup_success():
    response = client.get("/shipments/SHP-00001")
    assert response.status_code == 200
    assert response.json()["shipment_id"] == "SHP-00001"

def test_unknown_shipment_returns_404():
    response = client.get("/shipments/DOES-NOT-EXIST-999")
    assert response.status_code == 404
    assert "error" in response.json()

def test_shipment_list_supports_pagination():
    response = client.get("/shipments?page=1&page_size=5")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) <= 5
    assert data["page"] == 1
    assert "total" in data

def test_data_quality_report():
    response = client.get("/data-quality/report")
    assert response.status_code == 200
    data = response.json()
    assert "issues" in data
    assert len(data["issues"]) >= 12

def test_predict_delay_success_uses_fake_model(monkeypatch):
    import app.main as main_module

    feature_columns = [
        "origin_port",
        "destination_port",
        "cargo_type",
        "weight_tons",
        "container_count",
        "transit_days_planned",
    ]

    class FakeModel:
        def __init__(self):
            self.feature_columns = feature_columns

        def predict(self, rows):
            return [0]

        def predict_proba(self, rows):
            return [[0.9, 0.1]]

    monkeypatch.setattr(main_module, "MODEL", FakeModel())

    response = client.post(
        "/predict-delay",
        json={"shipment_id": "SHP-00001"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["shipment_id"] == "SHP-00001"
    assert data["predicted_more_than_24h_late"] is False
    assert data["probability_more_than_24h_late"] == 0.1
    assert data["model_version"] == "1.0.0"


def test_predict_delay_uses_fallback_when_model_missing(monkeypatch):
    import app.main as main_module

    monkeypatch.setattr(main_module, "MODEL", None)
    response = client.post(
        "/predict-delay",
        json={"shipment_id": "SHP-00001"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["shipment_id"] == "SHP-00001"
    assert isinstance(body["predicted_more_than_24h_late"], bool)
    assert 0.0 <= body["probability_more_than_24h_late"] <= 1.0

def test_predict_unknown_shipment_returns_404():
    response = client.post(
        "/predict-delay",
        json={"shipment_id": "DOES-NOT-EXIST-999"}
    )
    assert response.status_code == 404

def test_predict_requires_shipment_id():
    response = client.post("/predict-delay", json={})
    assert response.status_code == 422
