import math
import re
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


# --- Request models ---


class ProjectCreate(BaseModel):
    name: str
    address: str | None = None
    tier: str = "better"
    builder_id: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    tier: str | None = None
    status: str | None = None
    builder_id: str | None = None


# --- Room data from Claude Vision parser ---

# Feet and inches the way plans print them: 12'-8", 12' 8", 16'-3 1/4", 12 ft.
_FEET_INCHES = re.compile(
    r"""(?P<ft>\d+(?:\.\d+)?)\s*(?:'|ft\.?|feet|foot)
        (?:\s*-?\s*(?P<inch>\d+(?:\.\d+)?)(?:\s+(?P<num>\d+)/(?P<den>\d+))?
        \s*(?:"|in\.?|inch(?:es)?)?)?""",
    re.VERBOSE,
)
_INCHES = re.compile(
    r'(?P<inch>\d+(?:\.\d+)?)(?:\s+(?P<num>\d+)/(?P<den>\d+))?\s*(?:"|in\.?|inch(?:es)?)'
)
_NUMBER = re.compile(r"\d+(?:\.\d+)?")


def as_feet(value) -> float | None:
    """Read a length the model copied off the plan as decimal feet.

    The model is asked for a number but often copies the label as printed —
    "12'-8\"" — and one such room used to fail the whole page.  Anything that
    is not a positive length comes back as None, which means "not printed".
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = (
            value.strip().lower()
            .replace("\u2019", "'").replace("\u2032", "'")
            .replace("\u201d", '"').replace("\u2033", '"').replace("''", '"')
            .replace(",", "")
        )
        if m := _FEET_INCHES.fullmatch(text):
            number = float(m["ft"]) + _inches(m) / 12.0
        elif m := _INCHES.fullmatch(text):
            number = _inches(m) / 12.0
        elif m := _NUMBER.match(text):
            number = float(m[0])
        else:
            return None
    else:
        return None
    if math.isnan(number) or math.isinf(number) or number <= 0:
        return None
    return round(number, 2)


def _inches(m: re.Match) -> float:
    inches = float(m["inch"] or 0)
    if m["num"] and m["den"] and float(m["den"]):
        inches += float(m["num"]) / float(m["den"])
    return inches


class RoomData(BaseModel):
    name: str
    room_type: str
    # False when no name is printed in the space and the model guessed one;
    # the viewer asks the user to name those.
    labeled: bool = True
    sqft: float | None = None
    width_ft: float | None = None
    length_ft: float | None = None
    ceiling_height_ft: float | None = 9.0
    position_x: float | None = None
    position_y: float | None = None
    bbox_x1: float | None = None
    bbox_y1: float | None = None
    bbox_x2: float | None = None
    bbox_y2: float | None = None

    @field_validator("sqft", "width_ft", "length_ft", "ceiling_height_ft", mode="before")
    @classmethod
    def _plan_length(cls, value):
        return as_feet(value)


# --- Fixture assignment from lighting engine ---


class FixtureAssignment(BaseModel):
    fixture_type: str
    zone: str = ""
    position_x: float = 0.5
    position_y: float = 0.5
    notes: str = ""
    is_prewire: bool = False
    product_sku: str = ""
    product_desc: str = ""
    msrp_range: str = ""


# --- Response models ---


class FixtureResponse(BaseModel):
    id: str
    fixture_type: str
    product_sku: str | None = None
    product_desc: str | None = None
    msrp_range: str | None = None
    zone: str | None = None
    position_x: float
    position_y: float
    plan_x: float | None = None
    plan_y: float | None = None
    notes: str | None = None
    is_prewire: bool

    model_config = {"from_attributes": True}


class RoomResponse(BaseModel):
    id: str
    name: str
    room_type: str
    sqft: float | None = None
    width_ft: float | None = None
    length_ft: float | None = None
    ceiling_height_ft: float | None = None
    position_x: float | None = None
    position_y: float | None = None
    bbox_x1: float | None = None
    bbox_y1: float | None = None
    bbox_x2: float | None = None
    bbox_y2: float | None = None
    # Not stored: only the response to the upload that read the room says
    # whether its name was printed on the plan or guessed.
    labeled: bool = True
    fixtures: list[FixtureResponse] = []

    model_config = {"from_attributes": True}


class FloorPlanResponse(BaseModel):
    id: str
    original_filename: str
    file_type: str
    page_count: int
    parsed_at: datetime | None = None
    rooms: list[RoomResponse] = []

    model_config = {"from_attributes": True}


class ProjectResponse(BaseModel):
    id: str
    name: str
    address: str | None = None
    status: str
    tier: str
    created_at: datetime
    updated_at: datetime
    builder_id: str | None = None
    floor_plans: list[FloorPlanResponse] = []

    model_config = {"from_attributes": True}


class ProjectListItem(BaseModel):
    id: str
    name: str
    address: str | None = None
    status: str
    tier: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SchematicFixture(BaseModel):
    type: str
    x: float
    y: float
    color: str


class SchematicRoom(BaseModel):
    name: str
    room_type: str
    label: str
    rect: dict  # {"x": float, "y": float, "w": float, "h": float}
    fixtures: list[SchematicFixture]
    fixture_count: int


class SchematicLayout(BaseModel):
    canvas: dict  # {"width": float, "height": float}
    rooms: list[SchematicRoom]


class PlanUploadResponse(BaseModel):
    floor_plan_id: str
    status: str
    rooms: list[RoomResponse] = []
    schematic_layout: SchematicLayout | None = None
    # Pages in the uploaded file vs. pages actually analyzed. Fixture
    # coordinates are fractions of the analyzed page, so the viewer needs
    # both numbers to tell the user which sheets were left out.
    page_count: int = 1
    pages_analyzed: int = 1
    # Which page (1-based) the rooms and fixture coordinates belong to.
    page: int = 1
    # Conditioned square footage measured off this page, when the plan's
    # scale could be read from the room sizes printed on it; else null.
    measured_sqft: float | None = None
    # The ceiling height rooms on this page were laid out for, unless the
    # plan printed a different one for a room.
    ceiling_height_ft: float | None = None


class RoomUpdate(BaseModel):
    """A user naming a space the model could not read, or correcting one."""

    name: str | None = None
    room_type: str | None = None
    ceiling_height_ft: float | None = Field(None, gt=0, le=40)


# --- Estimate models ---


class EstimateCreate(BaseModel):
    total_sqft: int
    num_stories: int = 1
    pct_good: int = 0
    pct_better: int = 100
    pct_best: int = 0
    ceiling_height_default: float = 9.0


class EstimateRoomInput(BaseModel):
    name: str
    room_type: str
    sqft: float | None = None
    width_ft: float | None = None
    length_ft: float | None = None
    ceiling_height_ft: float = 9.0


class EstimateUpdate(BaseModel):
    total_sqft: int | None = None
    num_stories: int | None = None
    pct_good: int | None = None
    pct_better: int | None = None
    pct_best: int | None = None
    ceiling_height_default: float | None = None
    rooms: list[EstimateRoomInput] | None = None


class EstimateFixtureResponse(BaseModel):
    fixture_type: str
    product_sku: str = ""
    product_desc: str = ""
    msrp_range: str = ""
    zone: str = ""
    notes: str = ""
    is_prewire: bool = False


class EstimateRoomResponse(BaseModel):
    id: str
    name: str
    room_type: str
    sqft: float | None = None
    width_ft: float | None = None
    length_ft: float | None = None
    ceiling_height_ft: float | None = None
    assigned_tier: str
    sort_order: int = 0
    fixtures: list[EstimateFixtureResponse] = []


class EstimateSummary(BaseModel):
    total_fixtures: int = 0
    total_prewires: int = 0
    budget_low: float = 0
    budget_high: float = 0
    fixtures_by_type: dict[str, int] = {}
    rooms_by_tier: dict[str, int] = {}


class EstimateResponse(BaseModel):
    id: str
    project_id: str
    total_sqft: int
    num_stories: int
    pct_good: int
    pct_better: int
    pct_best: int
    ceiling_height_default: float
    rooms: list[EstimateRoomResponse] = []
    summary: EstimateSummary = EstimateSummary()
