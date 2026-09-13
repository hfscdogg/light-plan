"""Shared fixtures.

Both model round-trips are stubbed here, so the suite needs no API key and
makes no network calls. Storage is redirected to a temp directory *before*
``app`` is imported, because the SQLAlchemy engine is built at import time.
"""

import os
import sys
import tempfile

import pytest

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

# Must happen before any `app.*` import: app.models.database builds the engine
# from settings.database_url on import, and app.config reads the environment
# when it is first instantiated.
_TMP_DATA_DIR = tempfile.mkdtemp(prefix="lightplan-tests-")
os.environ["DATA_DIR"] = _TMP_DATA_DIR
os.environ.pop("DATABASE_URL", None)
os.environ.pop("UPLOAD_DIR", None)
os.environ.setdefault("GOOGLE_API_KEY", "test-key-not-used")

from app.models.schemas import RoomData  # noqa: E402
from app.services import plan_parser as plan_parser_module  # noqa: E402

# A two-room read, as the parser would return after a successful plan analysis.
SAMPLE_ROOMS = [
    RoomData(
        name="Kitchen", room_type="kitchen", sqft=240, width_ft=16, length_ft=15,
        ceiling_height_ft=9, position_x=0.3, position_y=0.4,
        bbox_x1=0.2, bbox_y1=0.3, bbox_x2=0.4, bbox_y2=0.5,
    ),
    RoomData(
        name="Primary Bedroom", room_type="master_bedroom", sqft=300, width_ft=15,
        length_ft=20, ceiling_height_ft=9, position_x=0.7, position_y=0.6,
        bbox_x1=0.6, bbox_y1=0.5, bbox_x2=0.85, bbox_y2=0.75,
    ),
]

# Smallest valid PNG; the parser never sees it because parse_plan is stubbed.
TINY_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c6360000002000154a24f8f0000000049454e44ae426082"
)


@pytest.fixture
def stub_parser(monkeypatch):
    """Stub both Gemini passes.

    Returns a control object so a test can choose how the fixture-placement
    pass behaves: succeed, come back empty, or raise the way a timeout or
    quota error does in production.
    """

    class Control:
        page_count = 1
        placement = "ok"
        rooms = SAMPLE_ROOMS

    ctl = Control()

    def fake_init(self):
        self.client = None
        self.model = "stub"

    def fake_parse_plan(self, file_path, file_type):
        return ctl.rooms, "[]", ctl.page_count

    def fake_place(self, file_path, file_type, rooms_with_fixtures, rooms_data=None):
        if ctl.placement == "raise":
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        if ctl.placement == "empty":
            return {}
        return {"Kitchen": [(0.30, 0.40, "recessed"), (0.33, 0.42, "pendant")]}

    monkeypatch.setattr(plan_parser_module.PlanParser, "__init__", fake_init)
    monkeypatch.setattr(plan_parser_module.PlanParser, "parse_plan", fake_parse_plan)
    monkeypatch.setattr(plan_parser_module.PlanParser, "place_fixtures_on_plan", fake_place)
    return ctl


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.models.database import create_tables

    create_tables()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def project(client):
    r = client.post("/api/projects", json={"name": "Test Residence"})
    assert r.status_code in (200, 201), r.text
    return r.json()


def upload_plan(client, project_id, filename="plan.png", content=None):
    return client.post(
        f"/api/projects/{project_id}/plans/upload",
        files={"file": (filename, content or TINY_PNG, "image/png")},
    )
