# LightPlan

A proactive lighting layout tool for residential builders. Upload a floor plan, get back a professional lighting fixture layout with a fixture schedule and rough BOM.

Built by [Livewire](https://livewire.com) as a sales tool to help builders make better lighting decisions before drywall.

## How It Works

1. Create a project (builder name, address, tier)
2. Upload a floor plan (PDF, PNG or JPG)
3. AI analyzes the plan and identifies rooms, dimensions and types
4. Rules engine assigns fixtures per room based on lighting standards
5. Review the fixture schedule in the web UI
6. Export a branded PDF to send to the builder

## Stack

- **Frontend:** React (Vite) + Tailwind CSS
- **Backend:** Python (FastAPI)
- **Database:** SQLite by default, Postgres via `DATABASE_URL`
- **AI/Vision:** Google Gemini (gemini-2.5-pro) for plan reading and fixture placement
- **PDF Generation:** reportlab

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- poppler-utils (for PDF-to-image conversion)

```bash
# macOS
brew install poppler

# Ubuntu/Debian
sudo apt-get install poppler-utils
```

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Copy and edit environment variables
cp .env.example .env
# Add your ANTHROPIC_API_KEY to .env

# Start the server
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs on http://localhost:5173 and proxies API requests to the backend on port 8000.

## Tier System

LightPlan generates fixture layouts in three tiers:

| Tier | Product Line | Character |
|------|-------------|-----------|
| Good | Builder grade (Halo, Commercial Electric) | Basic recessed cans, standard sconces |
| Better | DMF, WAC Lighting | Architectural recessed, quality decorative fixtures |
| Best | Ketra (full-spectrum tunable) | Ketra S30/S38 downlights, linear accent, premium decorative |

The BOM shows fixtures only. Control and dimming are positioned as a follow-up conversation, not a line item.

## Project Structure

```
backend/
  app/
    main.py              FastAPI application
    config.py            Environment configuration
    models/
      database.py        SQLAlchemy models
      schemas.py         Pydantic request/response models
    routers/
      projects.py        Project CRUD endpoints
      plans.py           Upload and parse endpoints
      exports.py         PDF generation endpoint
    services/
      plan_parser.py     Gemini Vision integration (room reading + placement)
      lighting_engine.py Fixture rules engine
      pdf_generator.py   Branded PDF output
      dxf_parser.py      DXF handling (Phase 2 stub)
frontend/
  src/
    components/          React UI components
    hooks/               Custom React hooks
    utils/               Client-side utilities
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| GOOGLE_API_KEY | Gemini API key used by the plan parser | Yes |
| ANTHROPIC_API_KEY | Anthropic API key | No |
| DATA_DIR | Directory holding the database and uploads | No (defaults to ./data) |
| DATABASE_URL | SQLAlchemy database URL | No (derived from DATA_DIR) |
| UPLOAD_DIR | File upload directory | No (derived from DATA_DIR) |
| BASIC_AUTH_USER | HTTP basic auth username | No |
| BASIC_AUTH_PASS | HTTP basic auth password | No |

## Persistence

Two things have to outlive a deploy: the SQLite database and the uploaded plan
files. Both live under `DATA_DIR` (`./data` by default). `DATABASE_URL` and
`UPLOAD_DIR` are derived from it unless you set them explicitly.

Uploads are not just a record of what was sent. Re-parsing a plan — which is
what the Good/Better/Best toggle does — re-reads the original file from disk,
so losing uploads breaks the tier toggle on every existing project.

**Container hosts wipe the filesystem on every deploy.** Unless `DATA_DIR`
points at a mounted volume, each deploy starts from an empty database and every
previously uploaded plan is gone. On Railway the app logs a warning at startup
when it detects this. Pick one:

- **Volume (simplest).** Mount a volume and set `DATA_DIR` to its mount path.
  On Railway: service → Settings → Volumes, mount at e.g. `/var/lightplan`, then
  set `DATA_DIR=/var/lightplan`. On Render this is already wired up in
  `render.yaml`.
- **Postgres (for uploads plus a real database).** Attach a Postgres instance;
  it injects `DATABASE_URL`, which takes precedence over `DATA_DIR`. A
  `postgres://` URL is rewritten to `postgresql://` automatically, since
  SQLAlchemy 2.x only registers the latter. You still want a volume for
  `UPLOAD_DIR`, because the plan files stay on disk.

Moving an existing local database into place is a file copy:

```bash
mkdir -p data && mv lightplan.db data/lightplan.db && mv uploads data/uploads
```

## Tests

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

The suite covers the failure modes that have actually bitten this app in
production — a failed fixture-placement call taking down a whole upload,
multi-page PDFs being analyzed against sheets the viewer never renders, and
storage silently landing somewhere a deploy will erase. It stubs both model
calls, so it needs no API key and makes no network requests.

There is also a browser regression test for the plan viewer:

```bash
cd scripts && npm install
node preview-regression.mjs
```

It serves `frontend/public/preview.html` against a stub API in headless
Chromium and asserts that AI fixtures render, that hand-placed fixtures survive
the analysis landing, and that skipped PDF pages are reported.

## API Endpoints

See [docs/API.md](docs/API.md) for full endpoint documentation.

## Lighting Rules

See [docs/RULES_ENGINE.md](docs/RULES_ENGINE.md) for the full lighting standards ruleset.
