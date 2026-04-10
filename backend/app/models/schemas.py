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


class PlanUploadResponse(BaseModel):
    floor_plan_id: str
    status: str
    rooms: list[RoomResponse] = []
