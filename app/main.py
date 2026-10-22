"""Elite Cuts MVP API. Queue and booking state is local SQLite, not a production service."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

DB_PATH = os.getenv("ELITE_CUTS_DB_PATH", "./data/elite_cuts.db")
app = FastAPI(
    title="Elite Cuts API",
    version="0.1.0",
    description="Booking and queue MVP. GPS events are explicitly simulated until a verified mobile integration exists.",
)


class BookingRequest(BaseModel):
    customer_name: str = Field(min_length=2, max_length=80)
    service: Literal["Haircut", "Beard", "Haircut + Beard", "Premium Grooming"]
    salon_id: str = Field(default="connaught-place-demo", min_length=2, max_length=80)
    estimated_minutes: int = Field(default=30, ge=10, le=180)


class GeofenceEvent(BaseModel):
    booking_id: str
    distance_meters: int = Field(ge=0, le=100000)
    source: Literal["simulator"] = "simulator"


class OperationsInsightRequest(BaseModel):
    salon_id: str = Field(default="connaught-place-demo", min_length=2, max_length=80)


class OperationsInsight(BaseModel):
    summary: str
    observations: list[str]
    recommendations: list[str]
    limitations: list[str]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def db():
    path = Path(DB_PATH)
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db():
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id TEXT PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                customer_name TEXT NOT NULL,
                service TEXT NOT NULL,
                salon_id TEXT NOT NULL,
                estimated_minutes INTEGER NOT NULL,
                status TEXT NOT NULL,
                chair_number INTEGER,
                distance_meters INTEGER,
                event_source TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booking_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(booking_id) REFERENCES bookings(id)
            )
        """)


@app.on_event("startup")
def startup():
    init_db()


def row_dict(row):
    return dict(row) if row is not None else None


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(Path(__file__).resolve().parent.parent / "index.html")


@app.get("/health")
def health():
    init_db()
    with db() as conn:
        conn.execute("SELECT 1")
    return {
        "status": "ok",
        "service": "elite-cuts-api",
        "storage": "sqlite",
        "live_gps_enabled": False,
        "payments_enabled": False,
    }


@app.post("/v1/bookings", status_code=201)
def create_booking(request: BookingRequest):
    init_db()
    booking_id = str(uuid.uuid4())
    with db() as conn:
        # Chair assignment is based on actual active rows, never a fabricated live status.
        active = conn.execute(
            "SELECT chair_number FROM bookings WHERE salon_id=? AND status IN ('booked','approaching','arrived','in_service')",
            (request.salon_id,),
        ).fetchall()
        occupied = {row["chair_number"] for row in active if row["chair_number"] is not None}
        chair = next((n for n in (1, 2, 3, 4, 5) if n not in occupied), None)
        status = "booked" if chair is not None else "waitlisted"
        token = "EC-" + uuid.uuid4().hex[:6].upper()
        timestamp = now_iso()
        conn.execute(
            """INSERT INTO bookings
            (id,token,customer_name,service,salon_id,estimated_minutes,status,chair_number,
             distance_meters,event_source,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (booking_id, token, request.customer_name.strip(), request.service, request.salon_id,
             request.estimated_minutes, status, chair, None, None, timestamp, timestamp),
        )
        conn.execute(
            "INSERT INTO events(booking_id,event_type,payload,created_at) VALUES(?,?,?,?)",
            (booking_id, "booking_created", '{"source":"api"}', timestamp),
        )
        row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    return row_dict(row)


@app.get("/v1/bookings")
def list_bookings(salon_id: str = "connaught-place-demo"):
    init_db()
    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM bookings WHERE salon_id=? ORDER BY created_at ASC", (salon_id,)
        ).fetchall()
    return {"items": [row_dict(row) for row in rows], "count": len(rows)}


@app.post("/v1/geofence-events")
def process_geofence_event(event: GeofenceEvent):
    """Accept simulator-only events; this endpoint does not read GPS from a device."""
    init_db()
    with db() as conn:
        row = conn.execute("SELECT * FROM bookings WHERE id=?", (event.booking_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Booking not found")
        if row["status"] in ("cancelled", "completed", "in_service"):
            raise HTTPException(status_code=409, detail=f"Cannot update booking in status {row['status']}")
        if event.distance_meters <= 150:
            status = "arrived"
            event_type = "simulated_arrival_triggered"
        elif event.distance_meters <= 800:
            status = "approaching"
            event_type = "simulated_inner_approach"
        else:
            status = "booked"
            event_type = "simulated_outer_ring"
        timestamp = now_iso()
        conn.execute(
            "UPDATE bookings SET status=?,distance_meters=?,event_source='simulator',updated_at=? WHERE id=?",
            (status, event.distance_meters, timestamp, event.booking_id),
        )
        conn.execute(
            "INSERT INTO events(booking_id,event_type,payload,created_at) VALUES(?,?,?,?)",
            (event.booking_id, event_type, '{"source":"simulator","gps_verified":false}', timestamp),
        )
        updated = conn.execute("SELECT * FROM bookings WHERE id=?", (event.booking_id,)).fetchone()
    return {"booking": row_dict(updated), "event": event_type, "source": "simulator", "gps_verified": False}


@app.post("/v1/bookings/{booking_id}/start")
def start_service(booking_id: str):
    init_db()
    with db() as conn:
        row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Booking not found")
        if row["status"] not in ("arrived",):
            raise HTTPException(status_code=409, detail="Customer must be marked arrived before service starts")
        timestamp = now_iso()
        conn.execute("UPDATE bookings SET status='in_service',updated_at=? WHERE id=?", (timestamp, booking_id))
        conn.execute(
            "INSERT INTO events(booking_id,event_type,payload,created_at) VALUES(?,?,?,?)",
            (booking_id, "service_started", '{"source":"salon_command"}', timestamp),
        )
        updated = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    return row_dict(updated)


@app.post("/v1/bookings/{booking_id}/complete")
def complete_service(booking_id: str):
    init_db()
    with db() as conn:
        row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Booking not found")
        if row["status"] != "in_service":
            raise HTTPException(status_code=409, detail="Only an in-service booking can be completed")
        timestamp = now_iso()
        conn.execute("UPDATE bookings SET status='completed',updated_at=? WHERE id=?", (timestamp, booking_id))
        conn.execute(
            "INSERT INTO events(booking_id,event_type,payload,created_at) VALUES(?,?,?,?)",
            (booking_id, "service_completed", '{"source":"salon_command"}', timestamp),
        )
        updated = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    return row_dict(updated)


def generate_operations_insight(salon_id: str) -> OperationsInsight:
    """Send aggregate operational counts only; no customer names or location history."""
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_MODEL", "").strip()
    if not api_key or not model:
        raise HTTPException(status_code=503, detail="AI insights require OPENAI_API_KEY and OPENAI_MODEL.")
    from openai import OpenAI

    init_db()
    with db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM bookings WHERE salon_id=? GROUP BY status",
            (salon_id,),
        ).fetchall()
    counts = {row["status"]: row["n"] for row in rows}
    snapshot = {
        "salon_id": salon_id,
        "counts_by_status": counts,
        "active_bookings": sum(counts.get(s, 0) for s in ("booked", "approaching", "arrived", "in_service", "waitlisted")),
        "source": "database counts; not live device telemetry",
    }
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "observations": {"type": "array", "items": {"type": "string"}},
            "recommendations": {"type": "array", "items": {"type": "string"}},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "observations", "recommendations", "limitations"],
        "additionalProperties": False,
    }
    response = OpenAI(api_key=api_key).responses.create(
        model=model,
        instructions=(
            "You are Elite Cuts operations analyst. Review only the supplied aggregate counts. "
            "Do not invent wait times, demand forecasts, or causal claims. Recommend low-risk "
            "operational checks, not automatic actions. Explicitly note that these counts do not "
            "include real GPS or measured service durations. Return concise structured output."
        ),
        input=json.dumps(snapshot),
        text={"format": {"type": "json_schema", "name": "elite_cuts_insight", "strict": True, "schema": schema}},
    )
    if not response.output_text:
        raise ValueError("Model returned no structured insight")
    return OperationsInsight.model_validate_json(response.output_text)


@app.post("/v1/ai/operations-insight", response_model=OperationsInsight)
def operations_insight(request: OperationsInsightRequest):
    try:
        return generate_operations_insight(request.salon_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="AI insight provider failed or returned invalid output.")


@app.get("/v1/metrics")
def metrics(salon_id: str = "connaught-place-demo"):
    init_db()
    with db() as conn:
        rows = conn.execute(
            "SELECT status, COUNT(*) AS n FROM bookings WHERE salon_id=? GROUP BY status", (salon_id,)
        ).fetchall()
    counts = {row["status"]: row["n"] for row in rows}
    return {
        "salon_id": salon_id,
        "active_bookings": sum(counts.get(s, 0) for s in ("booked", "approaching", "arrived", "in_service", "waitlisted")),
        "arrived": counts.get("arrived", 0),
        "in_service": counts.get("in_service", 0),
        "completed": counts.get("completed", 0),
        "waitlisted": counts.get("waitlisted", 0),
        "source": "database counts; not live device telemetry",
    }
