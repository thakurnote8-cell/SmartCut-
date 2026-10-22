import pytest
from fastapi.testclient import TestClient
import app.main as cuts


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(cuts, "DB_PATH", str(tmp_path / "test.db"))
    cuts.init_db()
    monkeypatch.setenv("ELITE_CUTS_API_TOKEN", "test-token-that-is-at-least-thirty-two-characters")
    return TestClient(cuts.app, headers={"Authorization": "Bearer test-token-that-is-at-least-thirty-two-characters"})


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

def test_ai_insight_requires_explicit_provider_configuration(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    response = client.post("/v1/ai/operations-insight", json={"salon_id": "test-salon"})
    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_ai_insight_returns_validated_recommendations(client, monkeypatch):
    expected = cuts.OperationsInsight(
        summary="Review the current queue before the next booking.",
        observations=["One booking is active."],
        recommendations=["Confirm chair readiness with the salon team."],
        limitations=["No real GPS or measured service duration was provided."],
    )
    monkeypatch.setattr(cuts, "generate_operations_insight", lambda salon_id: expected)
    response = client.post("/v1/ai/operations-insight", json={"salon_id": "test-salon"})
    assert response.status_code == 200
    assert response.json()["recommendations"] == expected.recommendations

def test_dashboard_is_served_by_api(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Salon Command" in response.text

def test_ai_insight_sends_aggregate_counts_not_customer_pii(client, monkeypatch):
    import json
    import openai

    client.post("/v1/bookings", json={
        "customer_name": "Private Test Name",
        "service": "Haircut",
        "salon_id": "privacy-test-salon",
    })
    expected = cuts.OperationsInsight(
        summary="One active booking is recorded.",
        observations=["The database contains one active booking."],
        recommendations=["Confirm chair readiness."],
        limitations=["No live GPS or service duration data is available."],
    )
    captured = {}

    class FakeResponses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return type("Response", (), {"output_text": json.dumps(expected.model_dump())})()

    class FakeClient:
        def __init__(self, **kwargs):
            self.responses = FakeResponses()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setattr(openai, "OpenAI", FakeClient)

    result = cuts.generate_operations_insight("privacy-test-salon")
    assert result.summary == expected.summary
    assert "Private Test Name" not in captured["input"]
    assert "counts_by_status" in captured["input"]


def test_geofence_events_cannot_regress_arrived_booking(client):
    booking = client.post("/v1/bookings", json={
        "customer_name": "Arrival Customer", "service": "Haircut"
    }).json()
    arrived = client.post("/v1/geofence-events", json={
        "booking_id": booking["id"], "distance_meters": 100
    })
    assert arrived.status_code == 200
    assert arrived.json()["booking"]["status"] == "arrived"

    delayed_outer_ring = client.post("/v1/geofence-events", json={
        "booking_id": booking["id"], "distance_meters": 2500
    })
    assert delayed_outer_ring.status_code == 200
    assert delayed_outer_ring.json()["booking"]["status"] == "arrived"
    assert delayed_outer_ring.json()["event"] == "simulated_arrival_already_confirmed"


def test_waitlisted_booking_rejects_geofence_events(client):
    for i in range(5):
        response = client.post("/v1/bookings", json={
            "customer_name": f"Customer {i}", "service": "Haircut", "salon_id": "full-salon"
        })
        assert response.status_code == 201
    waitlisted = client.post("/v1/bookings", json={
        "customer_name": "Waitlisted Person", "service": "Haircut", "salon_id": "full-salon"
    }).json()
    assert waitlisted["status"] == "waitlisted"
    response = client.post("/v1/geofence-events", json={
        "booking_id": waitlisted["id"], "distance_meters": 100
    })
    assert response.status_code == 409


def test_delayed_outer_ring_event_cannot_regress_approaching_booking(client):
    booking = client.post("/v1/bookings", json={
        "customer_name": "Approaching Customer", "service": "Haircut"
    }).json()
    approaching = client.post("/v1/geofence-events", json={
        "booking_id": booking["id"], "distance_meters": 700
    })
    assert approaching.status_code == 200
    assert approaching.json()["booking"]["status"] == "approaching"

    delayed_outer_ring = client.post("/v1/geofence-events", json={
        "booking_id": booking["id"], "distance_meters": 2500
    })
    assert delayed_outer_ring.status_code == 200
    assert delayed_outer_ring.json()["booking"]["status"] == "approaching"
    assert delayed_outer_ring.json()["event"] == "simulated_stale_outer_ring_ignored"


def test_operational_api_rejects_missing_bearer_token(client):
    response = TestClient(cuts.app).get("/v1/metrics")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_operational_api_fails_closed_without_configured_token(client, monkeypatch):
    monkeypatch.delenv("ELITE_CUTS_API_TOKEN", raising=False)
    response = TestClient(cuts.app).get("/v1/metrics")
    assert response.status_code == 503
    assert "ELITE_CUTS_API_TOKEN" in response.json()["detail"]


def test_booking_rejects_unexpected_fields(client):
    response = client.post("/v1/bookings", json={"customer_name": "Customer", "service": "Haircut", "is_admin": True})
    assert response.status_code == 422
