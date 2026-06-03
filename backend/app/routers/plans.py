import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.database import Fixture, FloorPlan, Project, Room, get_db
from app.models.schemas import PlanUploadResponse, RoomResponse
from app.services.lighting_engine import LightingEngine
from app.services.plan_parser import PlanParser
from app.services.placement import compute_plan_positions
from app.services.schematic import compute_schematic_layout

logger = logging.getLogger(__name__)

router = APIRouter()

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
}
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def _validate_file(file: UploadFile) -> str:
    """Validate upload file type. Returns the normalized file type string."""
    # Check content type
    file_type = ALLOWED_TYPES.get(file.content_type)

    # Fall back to extension check
    if not file_type and file.filename:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext in ALLOWED_EXTENSIONS:
            file_type = ext.lstrip(".")
            if file_type == "jpeg":
                file_type = "jpg"

    if not file_type:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {file.content_type}. Upload a PDF, PNG or JPG.",
        )

    return file_type


@router.post("/{project_id}/plans/upload", response_model=PlanUploadResponse, status_code=201)
async def upload_plan(
    project_id: str,
    file: UploadFile,
    db: Session = Depends(get_db),
):
    # 1. Validate project exists
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. Validate file type
    file_type = _validate_file(file)

    # 3. Save file to uploads/{project_id}/{filename}
    project_dir = os.path.join(settings.upload_dir, project_id)
    os.makedirs(project_dir, exist_ok=True)

    filename = file.filename or f"plan.{file_type}"
    file_path = os.path.join(project_dir, filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    # 4. Create FloorPlan record
    floor_plan = FloorPlan(
        project_id=project_id,
        original_filename=filename,
        stored_path=file_path,
        file_type=file_type,
    )
    db.add(floor_plan)
    db.flush()  # Get the ID

    # 5. Update project status
    project.status = "parsing"
    project.updated_at = datetime.now(timezone.utc)
    db.flush()

    # 6. Parse floor plan with Claude Vision
    try:
        parser = PlanParser()
        rooms_data, raw_json = parser.parse_plan(file_path, file_type)
    except Exception as e:
        logger.error(f"Failed to parse floor plan: {e}")
        project.status = "draft"
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze floor plan: {str(e)}",
        )

    # 7. Store raw parse JSON
    floor_plan.raw_parse_json = raw_json
    floor_plan.parsed_at = datetime.now(timezone.utc)
    floor_plan.page_count = 1  # TODO: detect actual page count for PDFs

    # 8. Create Room records
    room_records = []
    for rd in rooms_data:
        room = Room(
            floor_plan_id=floor_plan.id,
            name=rd.name,
            room_type=rd.room_type,
            sqft=rd.sqft,
            width_ft=rd.width_ft,
            length_ft=rd.length_ft,
            ceiling_height_ft=rd.ceiling_height_ft or 9.0,
            position_x=rd.position_x,
            position_y=rd.position_y,
            bbox_x1=rd.bbox_x1,
            bbox_y1=rd.bbox_y1,
            bbox_x2=rd.bbox_x2,
            bbox_y2=rd.bbox_y2,
        )
        db.add(room)
        db.flush()
        room_records.append((room, rd))

    # 9. Run lighting engine
    engine = LightingEngine()
    fixtures_by_room = engine.process_rooms(rooms_data, project.tier)

    # 10. Compute validated plan-level positions
    plan_positions = compute_plan_positions(rooms_data, fixtures_by_room)

    # 11. Create Fixture records with plan positions
    for room_record, rd in room_records:
        room_fixtures = fixtures_by_room.get(rd.name, [])
        room_plan_pos = plan_positions.get(rd.name, [])
        for i, fa in enumerate(room_fixtures):
            px, py = room_plan_pos[i] if i < len(room_plan_pos) else (0.5, 0.5)
            fixture = Fixture(
                room_id=room_record.id,
                fixture_type=fa.fixture_type,
                product_sku=fa.product_sku,
                product_desc=fa.product_desc,
                msrp_range=fa.msrp_range,
                tier_product_line=project.tier,
                zone=fa.zone,
                position_x=fa.position_x,
                position_y=fa.position_y,
                plan_x=px,
                plan_y=py,
                notes=fa.notes,
                is_prewire=fa.is_prewire,
            )
            db.add(fixture)

    # 12. Update project status
    project.status = "assigned"
    project.updated_at = datetime.now(timezone.utc)

    db.commit()

    # Compute schematic layout
    schematic = compute_schematic_layout(rooms_data, fixtures_by_room)

    # 12. Reload with relationships for response
    floor_plan = (
        db.query(FloorPlan)
        .options(joinedload(FloorPlan.rooms).joinedload(Room.fixtures))
        .filter(FloorPlan.id == floor_plan.id)
        .first()
    )

    return PlanUploadResponse(
        floor_plan_id=floor_plan.id,
        status=project.status,
        rooms=[RoomResponse.model_validate(r) for r in floor_plan.rooms],
        schematic_layout=schematic,
    )


@router.post("/{project_id}/plans/{plan_id}/parse", response_model=PlanUploadResponse)
def reparse_plan(
    project_id: str,
    plan_id: str,
    db: Session = Depends(get_db),
):
    """Re-run the parser and lighting engine on an existing floor plan."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    floor_plan = (
        db.query(FloorPlan)
        .filter(FloorPlan.id == plan_id, FloorPlan.project_id == project_id)
        .first()
    )
    if not floor_plan:
        raise HTTPException(status_code=404, detail="Floor plan not found")

    # Delete existing rooms and fixtures (cascade)
    db.query(Room).filter(Room.floor_plan_id == plan_id).delete()
    db.flush()

    # Re-parse
    project.status = "parsing"
    db.flush()

    try:
        parser = PlanParser()
        rooms_data, raw_json = parser.parse_plan(floor_plan.stored_path, floor_plan.file_type)
    except Exception as e:
        logger.error(f"Failed to re-parse floor plan: {e}")
        project.status = "draft"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to analyze floor plan: {str(e)}")

    floor_plan.raw_parse_json = raw_json
    floor_plan.parsed_at = datetime.now(timezone.utc)

    room_records = []
    for rd in rooms_data:
        room = Room(
            floor_plan_id=floor_plan.id,
            name=rd.name,
            room_type=rd.room_type,
            sqft=rd.sqft,
            width_ft=rd.width_ft,
            length_ft=rd.length_ft,
            ceiling_height_ft=rd.ceiling_height_ft or 9.0,
            position_x=rd.position_x,
            position_y=rd.position_y,
            bbox_x1=rd.bbox_x1,
            bbox_y1=rd.bbox_y1,
            bbox_x2=rd.bbox_x2,
            bbox_y2=rd.bbox_y2,
        )
        db.add(room)
        db.flush()
        room_records.append((room, rd))

    engine = LightingEngine()
    fixtures_by_room = engine.process_rooms(rooms_data, project.tier)
    plan_positions = compute_plan_positions(rooms_data, fixtures_by_room)

    for room_record, rd in room_records:
        room_fixtures = fixtures_by_room.get(rd.name, [])
        room_plan_pos = plan_positions.get(rd.name, [])
        for i, fa in enumerate(room_fixtures):
            px, py = room_plan_pos[i] if i < len(room_plan_pos) else (0.5, 0.5)
            fixture = Fixture(
                room_id=room_record.id,
                fixture_type=fa.fixture_type,
                product_sku=fa.product_sku,
                product_desc=fa.product_desc,
                msrp_range=fa.msrp_range,
                tier_product_line=project.tier,
                zone=fa.zone,
                position_x=fa.position_x,
                position_y=fa.position_y,
                plan_x=px,
                plan_y=py,
                notes=fa.notes,
                is_prewire=fa.is_prewire,
            )
            db.add(fixture)

    # Compute schematic layout
    schematic = compute_schematic_layout(rooms_data, fixtures_by_room)

    project.status = "assigned"
    project.updated_at = datetime.now(timezone.utc)
    db.commit()

    floor_plan = (
        db.query(FloorPlan)
        .options(joinedload(FloorPlan.rooms).joinedload(Room.fixtures))
        .filter(FloorPlan.id == floor_plan.id)
        .first()
    )

    return PlanUploadResponse(
        floor_plan_id=floor_plan.id,
        status=project.status,
        rooms=[RoomResponse.model_validate(r) for r in floor_plan.rooms],
        schematic_layout=schematic,
    )


@router.get("/{project_id}/plans/{plan_id}")
def get_plan(
    project_id: str,
    plan_id: str,
    db: Session = Depends(get_db),
):
    floor_plan = (
        db.query(FloorPlan)
        .options(joinedload(FloorPlan.rooms).joinedload(Room.fixtures))
        .filter(FloorPlan.id == plan_id, FloorPlan.project_id == project_id)
        .first()
    )
    if not floor_plan:
        raise HTTPException(status_code=404, detail="Floor plan not found")

    # Recompute schematic from stored room/fixture data (not persisted in DB)
    from app.models.schemas import FixtureAssignment, RoomData

    rooms_data = [
        RoomData(
            name=r.name,
            room_type=r.room_type,
            sqft=r.sqft,
            width_ft=r.width_ft,
            length_ft=r.length_ft,
            ceiling_height_ft=r.ceiling_height_ft,
            position_x=r.position_x,
            position_y=r.position_y,
            bbox_x1=r.bbox_x1,
            bbox_y1=r.bbox_y1,
            bbox_x2=r.bbox_x2,
            bbox_y2=r.bbox_y2,
        )
        for r in floor_plan.rooms
    ]
    fixtures_by_room: dict[str, list[FixtureAssignment]] = {}
    for r in floor_plan.rooms:
        fixtures_by_room[r.name] = [
            FixtureAssignment(
                fixture_type=f.fixture_type,
                zone=f.zone or "",
                position_x=f.position_x,
                position_y=f.position_y,
                notes=f.notes or "",
                is_prewire=f.is_prewire,
                product_sku=f.product_sku or "",
                product_desc=f.product_desc or "",
                msrp_range=f.msrp_range or "",
            )
            for f in r.fixtures
        ]

    schematic = compute_schematic_layout(rooms_data, fixtures_by_room)

    return {
        "id": floor_plan.id,
        "original_filename": floor_plan.original_filename,
        "file_type": floor_plan.file_type,
        "page_count": floor_plan.page_count,
        "parsed_at": floor_plan.parsed_at,
        "rooms": [RoomResponse.model_validate(r) for r in floor_plan.rooms],
        "schematic_layout": schematic,
    }


@router.get("/{project_id}/plans/{plan_id}/debug")
def debug_plan(
    project_id: str,
    plan_id: str,
    db: Session = Depends(get_db),
):
    """Debug endpoint: returns raw room bboxes and fixture positions."""
    floor_plan = (
        db.query(FloorPlan)
        .options(joinedload(FloorPlan.rooms).joinedload(Room.fixtures))
        .filter(FloorPlan.id == plan_id, FloorPlan.project_id == project_id)
        .first()
    )
    if not floor_plan:
        raise HTTPException(status_code=404, detail="Floor plan not found")

    rooms_debug = []
    for r in floor_plan.rooms:
        fixtures_debug = [
            {
                "type": f.fixture_type,
                "room_rel": [round(f.position_x, 3), round(f.position_y, 3)],
                "plan_pos": [round(f.plan_x, 4) if f.plan_x else None,
                             round(f.plan_y, 4) if f.plan_y else None],
            }
            for f in r.fixtures
        ]
        rooms_debug.append({
            "name": r.name,
            "type": r.room_type,
            "label": [round(r.position_x, 3) if r.position_x else None,
                       round(r.position_y, 3) if r.position_y else None],
            "bbox": [round(r.bbox_x1, 3) if r.bbox_x1 else None,
                     round(r.bbox_y1, 3) if r.bbox_y1 else None,
                     round(r.bbox_x2, 3) if r.bbox_x2 else None,
                     round(r.bbox_y2, 3) if r.bbox_y2 else None],
            "bbox_size": [round(r.bbox_x2 - r.bbox_x1, 3) if r.bbox_x1 and r.bbox_x2 else None,
                          round(r.bbox_y2 - r.bbox_y1, 3) if r.bbox_y1 and r.bbox_y2 else None],
            "dims_ft": [r.width_ft, r.length_ft],
            "sqft": r.sqft,
            "fixtures": fixtures_debug,
        })

    return {"plan_id": plan_id, "rooms": rooms_debug}
