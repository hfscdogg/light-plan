import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models.database import Fixture, FloorPlan, Project, Room, get_db
from app.models.schemas import PlanUploadResponse, RoomData, RoomResponse, RoomUpdate
from app.services.lighting_engine import LightingEngine
from app.services.plan_parser import KNOWN_ROOM_TYPES, PageOutOfRange, PlanParser
from app.services.placement import (
    compute_plan_positions,
    resolve_name,
    room_bounds,
    spread_fixtures,
)
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

# Cans go on the rules engine's grid — spaced at half the ceiling height and
# inset from the walls — rather than wherever the placement model drops them.
# The model knows where an island or a vanity is; it does not keep spacing.
GRID_FIXTURE_TYPES = {"recessed"}

# Used when neither the plan nor the user gives a ceiling height.
DEFAULT_CEILING_FT = 9.0


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


def _resolve_plan_positions(
    parser: PlanParser,
    file_path: str,
    file_type: str,
    rooms_data,
    fixtures_by_room,
    page: int = 1,
) -> dict[str, list[tuple[float, float]]]:
    """Work out where each fixture sits on the plan image.

    Asks Vision to place fixtures where they belong (island, vanity wall,
    ...) and falls back to algorithmic placement for anything it doesn't
    cover.  The Vision call is best-effort: it is a second model round-trip
    that can time out or hit a quota, and losing it must not throw away the
    rooms we already parsed — so a failure downgrades to the algorithmic
    layout instead of failing the whole upload.

    Whatever the mix, the result goes through the separation pass: two
    fixtures on the same point draw as one marker, and the rep then has to
    discover and drag apart every fixture hiding under another.
    """
    bounds_lookup = room_bounds(rooms_data)
    algo_positions = compute_plan_positions(rooms_data, fixtures_by_room)

    try:
        vision_positions = parser.place_fixtures_on_plan(
            file_path,
            file_type,
            rooms_with_fixtures=dict(fixtures_by_room),
            rooms_data=rooms_data,
            page=page,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Vision placement failed (%s) — falling back to algorithmic placement", e
        )
        vision_positions = {}

    if not vision_positions:
        logger.warning("No Vision placements returned, using algorithmic layout")
        return algo_positions

    # Vision echoes our room names back in whatever shape it read them off the
    # drawing, so reconcile them against the rooms we actually parsed rather
    # than comparing strings exactly.
    vision_by_room: dict[str, list[tuple[float, float, str]]] = {}
    for echoed, placements in vision_positions.items():
        room_name = resolve_name(echoed, fixtures_by_room.keys())
        if room_name is None:
            logger.warning(
                "Vision placed fixtures in %r, which matches no parsed room", echoed
            )
            continue
        vision_by_room.setdefault(room_name, []).extend(placements)

    plan_positions: dict[str, list[tuple[float, float]]] = {}
    from_vision = 0
    total = 0
    for room_name, fixture_list in fixtures_by_room.items():
        wanted_types = {fa.fixture_type for fa in fixture_list}

        # Vision returns [(x, y, type), ...] — build a per-type queue
        vision_by_type: dict[str, list[tuple[float, float]]] = {}
        for vx, vy, vtype in vision_by_room.get(room_name, []):
            matched = resolve_name(vtype, wanted_types)
            if matched is None:
                continue
            vision_by_type.setdefault(matched, []).append((vx, vy))

        algo_room = algo_positions.get(room_name, [])
        positions = []
        for i, fa in enumerate(fixture_list):
            total += 1
            # Use Vision position if available for this fixture type
            if fa.fixture_type in GRID_FIXTURE_TYPES and i < len(algo_room):
                positions.append(algo_room[i])
            elif vision_by_type.get(fa.fixture_type):
                positions.append(vision_by_type[fa.fixture_type].pop(0))
                from_vision += 1
            elif i < len(algo_room):
                positions.append(algo_room[i])
            else:
                positions.append((0.5, 0.5))
        plan_positions[room_name] = positions

    # How much of the overlay the rep will have to move by hand comes down to
    # this ratio: a Vision placement knows about the island and the vanity, an
    # algorithmic one only knows the room's outline.  Worth seeing per upload.
    logger.info(
        "Placement: %d of %d fixtures from Vision, %d from the grid",
        from_vision, total, total - from_vision,
    )

    return spread_fixtures(plan_positions, bounds_lookup)


def _with_ceiling(rooms_data: list[RoomData], ceiling_ft: float) -> list[RoomData]:
    """Give every room the floor's ceiling height unless the plan printed its own.

    A vaulted great room or a 10' tray in the primary suite is called out on
    the drawing; everything else on the floor shares the height the user gave.
    """
    return [
        rd if rd.ceiling_height_ft else rd.model_copy(update={"ceiling_height_ft": ceiling_ft})
        for rd in rooms_data
    ]


def _analyze_page(
    file_path: str, file_type: str, page: int, tier: str, ceiling_ft: float
):
    """Read one page and lay out its fixtures.  Blocking: two model calls.

    Runs off the event loop.  The model calls take a minute, and on the loop
    they held up every other request — a second floor's analysis, even the
    viewer's health check — until the first floor finished.
    """
    parser = PlanParser()
    rooms_data, raw_json, page_count = parser.parse_plan(file_path, file_type, page=page)
    rooms_data = _with_ceiling(rooms_data, ceiling_ft)

    engine = LightingEngine()
    fixtures_by_room = engine.process_rooms(rooms_data, tier)

    # Vision-based fixture placement: let the model see the actual plan
    # and place each fixture where it belongs (island, vanity wall, etc.)
    plan_positions = _resolve_plan_positions(
        parser, file_path, file_type, rooms_data, fixtures_by_room, page=page
    )
    measured_sqft = getattr(parser, "measured_sqft", None)
    return rooms_data, raw_json, page_count, fixtures_by_room, plan_positions, measured_sqft


def _add_fixtures(db: Session, room: Room, fixtures, positions, tier: str) -> None:
    for i, fa in enumerate(fixtures):
        px, py = positions[i] if i < len(positions) else (0.5, 0.5)
        db.add(
            Fixture(
                room_id=room.id,
                fixture_type=fa.fixture_type,
                product_sku=fa.product_sku,
                product_desc=fa.product_desc,
                msrp_range=fa.msrp_range,
                tier_product_line=tier,
                zone=fa.zone,
                position_x=fa.position_x,
                position_y=fa.position_y,
                plan_x=px,
                plan_y=py,
                notes=fa.notes,
                is_prewire=fa.is_prewire,
            )
        )


async def _read_into_plan(
    db: Session,
    project: Project,
    floor_plan: FloorPlan,
    page: int,
    ceiling_ft: float,
) -> PlanUploadResponse:
    """Analyze ``page`` of ``floor_plan`` and store its rooms and fixtures."""
    project.status = "parsing"
    project.updated_at = datetime.now(timezone.utc)
    db.flush()

    try:
        (
            rooms_data, raw_json, page_count, fixtures_by_room, plan_positions,
            measured_sqft,
        ) = await run_in_threadpool(
            _analyze_page,
            floor_plan.stored_path,
            floor_plan.file_type,
            page,
            project.tier,
            ceiling_ft,
        )
    except PageOutOfRange as e:
        project.status = "draft"
        db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to analyze floor plan: {e}")
        project.status = "draft"
        db.commit()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze floor plan: {str(e)}",
        )

    floor_plan.raw_parse_json = raw_json
    floor_plan.parsed_at = datetime.now(timezone.utc)
    floor_plan.page_count = page_count

    labeled: dict[str, bool] = {}
    for rd in rooms_data:
        room = Room(
            floor_plan_id=floor_plan.id,
            name=rd.name,
            room_type=rd.room_type,
            sqft=rd.sqft,
            width_ft=rd.width_ft,
            length_ft=rd.length_ft,
            ceiling_height_ft=rd.ceiling_height_ft or ceiling_ft,
            position_x=rd.position_x,
            position_y=rd.position_y,
            bbox_x1=rd.bbox_x1,
            bbox_y1=rd.bbox_y1,
            bbox_x2=rd.bbox_x2,
            bbox_y2=rd.bbox_y2,
        )
        db.add(room)
        db.flush()
        labeled[room.id] = rd.labeled
        _add_fixtures(
            db, room, fixtures_by_room.get(rd.name, []),
            plan_positions.get(rd.name, []), project.tier,
        )

    project.status = "assigned"
    project.updated_at = datetime.now(timezone.utc)
    db.commit()

    schematic = compute_schematic_layout(rooms_data, fixtures_by_room)

    floor_plan = (
        db.query(FloorPlan)
        .options(joinedload(FloorPlan.rooms).joinedload(Room.fixtures))
        .filter(FloorPlan.id == floor_plan.id)
        .first()
    )

    rooms = []
    for r in floor_plan.rooms:
        response = RoomResponse.model_validate(r)
        response.labeled = labeled.get(r.id, True)
        rooms.append(response)

    return PlanUploadResponse(
        floor_plan_id=floor_plan.id,
        status=project.status,
        rooms=rooms,
        schematic_layout=schematic,
        page_count=floor_plan.page_count,
        pages_analyzed=min(PlanParser.MAX_ANALYSIS_PAGES, floor_plan.page_count),
        page=page,
        measured_sqft=measured_sqft,
        ceiling_height_ft=ceiling_ft,
    )


@router.post("/{project_id}/plans/upload", response_model=PlanUploadResponse, status_code=201)
async def upload_plan(
    project_id: str,
    file: UploadFile,
    # Which sheet of a multi-page plan set to read (1-based). The viewer
    # sends each page of a plan set as its own request, so fixture
    # coordinates land on the drawing of that page.
    page: int = Query(1, ge=1),
    # The ceiling height on this floor, from the user. Sets can spacing.
    ceiling_height: float = Query(DEFAULT_CEILING_FT, gt=0, le=40),
    db: Session = Depends(get_db),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    file_type = _validate_file(file)

    project_dir = os.path.join(settings.upload_dir, project_id)
    os.makedirs(project_dir, exist_ok=True)

    filename = file.filename or f"plan.{file_type}"
    file_path = os.path.join(project_dir, filename)

    content = await file.read()
    with open(file_path, "wb") as f:
        f.write(content)

    floor_plan = FloorPlan(
        project_id=project_id,
        original_filename=filename,
        stored_path=file_path,
        file_type=file_type,
    )
    db.add(floor_plan)
    db.flush()

    return await _read_into_plan(db, project, floor_plan, page, ceiling_height)


@router.post("/{project_id}/plans/{plan_id}/parse", response_model=PlanUploadResponse)
async def reparse_plan(
    project_id: str,
    plan_id: str,
    page: int = Query(1, ge=1),
    ceiling_height: float = Query(DEFAULT_CEILING_FT, gt=0, le=40),
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

    return await _read_into_plan(db, project, floor_plan, page, ceiling_height)


@router.patch(
    "/{project_id}/plans/{plan_id}/rooms/{room_id}", response_model=RoomResponse
)
def update_room(
    project_id: str,
    plan_id: str,
    room_id: str,
    body: RoomUpdate,
    db: Session = Depends(get_db),
):
    """Rename a room, change what kind of room it is, or its ceiling height.

    This is how a user names a space the plan left unlabeled.  When the type
    or ceiling changes, the room's fixtures are laid out again for what it
    really is — a "closet" that turns out to be a bath needs a vanity light —
    on the grid inside its walls.
    """
    room = (
        db.query(Room)
        .join(FloorPlan)
        .filter(
            Room.id == room_id,
            Room.floor_plan_id == plan_id,
            FloorPlan.project_id == project_id,
        )
        .first()
    )
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    name = (body.name or "").strip()
    if body.name is not None and not name:
        raise HTTPException(status_code=400, detail="A room needs a name.")
    if body.room_type is not None and body.room_type not in KNOWN_ROOM_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Unknown room type: {body.room_type}"
        )

    if name and name != room.name:
        clash = (
            db.query(Room)
            .filter(Room.floor_plan_id == plan_id, Room.name == name, Room.id != room.id)
            .first()
        )
        if clash:
            raise HTTPException(
                status_code=409, detail=f"Another room on this page is already called {name}."
            )
        room.name = name

    relayout = (
        body.room_type is not None and body.room_type != room.room_type
    ) or (
        body.ceiling_height_ft is not None
        and body.ceiling_height_ft != room.ceiling_height_ft
    )
    if body.room_type is not None:
        room.room_type = body.room_type
    if body.ceiling_height_ft is not None:
        room.ceiling_height_ft = body.ceiling_height_ft

    if relayout:
        project = db.query(Project).filter(Project.id == project_id).first()
        rd = RoomData(
            name=room.name,
            room_type=room.room_type,
            sqft=room.sqft,
            width_ft=room.width_ft,
            length_ft=room.length_ft,
            ceiling_height_ft=room.ceiling_height_ft,
            position_x=room.position_x,
            position_y=room.position_y,
            bbox_x1=room.bbox_x1,
            bbox_y1=room.bbox_y1,
            bbox_x2=room.bbox_x2,
            bbox_y2=room.bbox_y2,
        )
        fixtures = LightingEngine().process_single_room(rd, project.tier)
        positions = compute_plan_positions([rd], {rd.name: fixtures}).get(rd.name, [])
        for f in list(room.fixtures):
            db.delete(f)
        db.flush()
        _add_fixtures(db, room, fixtures, positions, project.tier)

    db.commit()
    db.refresh(room)
    return RoomResponse.model_validate(room)


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
