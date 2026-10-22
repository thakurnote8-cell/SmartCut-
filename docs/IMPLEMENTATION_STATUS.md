# Elite Cuts — implementation status

## Implemented on this branch
- FastAPI service with SQLite-backed booking records and event history.
- Create and list bookings; deterministic chair assignment from current active database records.
- Simulated 2.5 km / 800 m / 150 m geofence state transitions.
- Guarded service lifecycle: booked → arrived → in_service → completed.
- Queue metrics derived from database rows.
- Responsive Salon Command page that calls this API; no fabricated live GPS status.
- Tests for booking lifecycle, invalid transitions, unknown bookings, and metrics.
- GitHub Actions test workflow.

## Not implemented / not verified
- No customer mobile app, authentication, salon tenant isolation, production database, payments, messaging, real GPS, map matching, ETA prediction, or vendor integration.
- No production hosting or deployment.
- No GPT model call yet. AI recommendations should be added only after operational data contracts and access controls are reviewed.

## Local run
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```
Visit `http://127.0.0.1:8000`. API docs: `http://127.0.0.1:8000/docs`.
Test with `pytest -q`.

## Before pilot
Add authentication and salon-level authorization, migrations and managed PostgreSQL, rate limits, audit log retention, consent and privacy flows, real-device geofence adapter with spoofing checks, notification provider, load tests, monitoring, backups, and a security review. The current SQLite app is a development MVP, not a production deployment.
