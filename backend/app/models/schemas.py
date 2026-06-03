from datetime import datetime

from pydantic import BaseModel, Field


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


class RoomData(BaseModel):
    name: str
    room_type: str
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
