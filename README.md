# Elite Cuts — Zero-Wait Grooming Operations

A development MVP for booking records, queue state transitions, and the salon command dashboard.

## Run locally

Python 3.11+ recommended.

```bash
python -m venv .venv
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000` for the dashboard and `http://127.0.0.1:8000/docs` for API docs. Run automated tests with `pytest -q`.

## Included

- SQLite-backed booking records.
- Queue metrics derived from saved records.
- Optional GPT-based operational insight endpoint using aggregate counts only; recommendations are advisory and never execute actions.
- Simulated geofence event transitions at 800 m and 150 m.
- Guarded service lifecycle and responsive salon dashboard.
- Automated test workflow.

## Important limitations

This is not a deployed salon system. Geofence events are simulator-only; no live phone GPS is read. Authentication, tenant isolation, customer notifications, payments, mobile clients, production hosting, and real wearable/device integrations are not implemented. Read `docs/IMPLEMENTATION_STATUS.md` before using beyond local development.


## Containerized single-instance pilot

1. Copy `.env.example` to `.env` and generate a strong `ELITE_CUTS_API_TOKEN` (at least 32 characters).
2. Optionally set `OPENAI_API_KEY` and `OPENAI_MODEL` for the advisory AI endpoint.
3. Run `docker compose up --build -d`; the dashboard is bound to `127.0.0.1:8000` by default.
4. Put a TLS reverse proxy in front before remote access. Keep the shared token secret.

The container runs as a non-root user, uses a read-only root filesystem, drops Linux capabilities, and persists SQLite in a named volume. This is a single-instance pilot setup, not a multi-tenant SaaS deployment. Before real customer data, add per-user identity and salon-level authorization, managed PostgreSQL and migrations, backups/restore drills, rate limiting, monitoring/alerts, privacy/retention policies, and a security review.
