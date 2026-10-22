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


## Required configuration before running

Set `ELITE_CUTS_API_TOKEN` to a cryptographically random secret of at least 32 characters before using the operational API. Generate one with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Never commit the token. The dashboard prompts for it and keeps it in the current tab session.

The API uses a shared bearer token only; it does not provide individual staff identities or salon-level authorization. Keep the app on localhost or behind HTTPS and a trusted reverse proxy. Do not use real customer data or expose it publicly until per-user identity, tenant isolation, managed database migrations, backups, rate limiting, monitoring, privacy/retention controls, and a security review are complete.
