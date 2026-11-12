# British Auction RFQ

A local RFQ demo where suppliers submit lower quotes and configurable rules can extend bidding near the scheduled close.

## How it works

Buyers create an RFQ with a start time, scheduled close, forced close, service date, and extension settings. Suppliers enter a name and quote charges; the lowest total ranks first. A supplier can replace their quote only with a lower total. Selected trigger events in the final `X` minutes add `Y` minutes to the close, capped at the forced close. Accepted bids and extensions appear in the activity log.

The browser refreshes auction data by polling the API every five seconds. There is no login or WebSocket connection; supplier names are self-reported, so use this only as a local demo.

## Stack and layout

- API and auction rules: Python 3.10+, FastAPI, Pydantic, SQLite
- UI: React, TypeScript, Vite
- `backend/app/main.py`: API, validation, and auction logic
- `backend/tests/`: backend behavior tests
- `frontend/src/`: auction screens and styles

SQLite creates `backend/auction.db` on startup. The `auctions` table stores schedules and trigger settings, `bids` stores each supplier's current quote, and `activity` stores bid and extension events. The extension update and bid write use one SQLite transaction. The demo stores amounts as floating-point values; production pricing should use fixed-precision amounts and a migration-managed database.

## Run locally

Use Python 3.10+ and Node.js 20.19+ or 22.12+. In one terminal, start the API:

```powershell
cd backend
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

From the repository root, start the UI in another terminal:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Open the Vite URL shown in the terminal (normally `http://localhost:5173`). API documentation is at `http://localhost:8000/docs`.

The backend uses `AUCTION_DB` to override the SQLite file path. The frontend uses `VITE_API_BASE_URL`, set in `frontend/.env.local`; its example points to `http://localhost:8000`. Vite variables are exposed to the browser, so do not store secrets there.

## Checks

Run backend checks from `backend`:

```powershell
python -m unittest discover -s tests -v
python -m ruff check app tests
python -m ruff format --check app tests
```

Run frontend checks from `frontend` after `npm ci`:

```powershell
npm run format:check
npm run typecheck
npm run build
```

## Limitations

There is no authentication, supplier identity verification, or authorization. All auction detail responses include supplier names and quote breakdowns. The API has no migration framework, and SQLite plus floating-point amounts are intended for a small demonstration rather than concurrent production bidding. Reuse and redistribution terms are not specified because this repository has no license.
