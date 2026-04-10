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
- **Database:** SQLite (local dev), Postgres-ready for prod
- **AI/Vision:** Anthropic Claude API (claude-sonnet-4-20250514)
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
      plan_parser.py     Claude Vision API integration
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
| ANTHROPIC_API_KEY | Anthropic API key for Claude Vision | Yes |
| DATABASE_URL | SQLAlchemy database URL | No (defaults to SQLite) |
| UPLOAD_DIR | File upload directory | No (defaults to ./uploads) |
| BASIC_AUTH_USER | HTTP basic auth username | No |
| BASIC_AUTH_PASS | HTTP basic auth password | No |

## API Endpoints

See [docs/API.md](docs/API.md) for full endpoint documentation.

## Lighting Rules

See [docs/RULES_ENGINE.md](docs/RULES_ENGINE.md) for the full lighting standards ruleset.
