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

def test_predict_delay():
    response = client.post(
        "/predict-delay",
        json={"shipment_id": "SHP-00001"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["shipment_id"] == "SHP-00001"
    assert isinstance(data["predicted_more_than_24h_late"], bool)
    assert 0 <= data["probability_more_than_24h_late"] <= 1

def test_predict_unknown_shipment_returns_404():
    response = client.post(
        "/predict-delay",
        json={"shipment_id": "DOES-NOT-EXIST-999"}
    )
    assert response.status_code == 404

def test_predict_requires_shipment_id():
    response = client.post("/predict-delay", json={})
    assert response.status_code == 422
