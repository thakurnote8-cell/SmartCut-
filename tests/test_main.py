import pytest
from fastapi.testclient import TestClient
import app.main as cuts


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cuts, "DB_PATH", str(tmp_path / "test.db"))
    cuts.init_db()
    return TestClient(cuts.app)


def test_health_discloses_demo_limits(client):
    data = client.get("/health").json()
    assert data["status"] == "ok"
    assert data["live_gps_enabled"] is False


def test_booking_and_geofence_simulation_state_machine(client):
    created = client.post("/v1/bookings", json={
        "customer_name": "Test Customer",
        "service": "Haircut",
        "salon_id": "test-salon",
        "estimated_minutes": 30
    })
    assert created.status_code == 201
    booking = created.json()
    assert booking["status"] == "booked"
    assert booking["chair_number"] == 1

    event = client.post("/v1/geofence-events", json={
        "booking_id": booking["id"], "distance_meters": 120, "source": "simulator"
    })
    assert event.status_code == 200
    assert event.json()["booking"]["status"] == "arrived"
    assert event.json()["gps_verified"] is False

    started = client.post(f"/v1/bookings/{booking['id']}/start")
    assert started.status_code == 200
    assert started.json()["status"] == "in_service"

    completed = client.post(f"/v1/bookings/{booking['id']}/complete")
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"


def test_cannot_start_service_before_arrival(client):
    booking = client.post("/v1/bookings", json={
        "customer_name": "Another Customer", "service": "Beard"
    }).json()
    response = client.post(f"/v1/bookings/{booking['id']}/start")
    assert response.status_code == 409


def test_unknown_booking_returns_404(client):
    response = client.post("/v1/geofence-events", json={
        "booking_id": "missing", "distance_meters": 100, "source": "simulator"
    })
    assert response.status_code == 404


def test_metrics_count_real_database_rows(client):
    client.post("/v1/bookings", json={"customer_name": "Customer One", "service": "Haircut"})
    data = client.get("/v1/metrics").json()
    assert data["active_bookings"] == 1
