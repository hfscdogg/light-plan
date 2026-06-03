from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.models.database import (
    Builder, Estimate, EstimateRoom, Fixture, FloorPlan, Project, Room, get_db,
)
from app.models.schemas import FixtureAssignment, RoomData
from app.services.estimate_calculator import calculate_estimate
from app.services.pdf_generator import PDFGenerator
from app.services.schematic import compute_schematic_layout

router = APIRouter()


def _build_estimate_data(estimate: Estimate) -> tuple[dict, dict]:
    """Build rooms_with_fixtures and estimate_summary from an Estimate."""
    rooms = [
        {
            "name": r.name,
            "room_type": r.room_type,
            "sqft": r.sqft,
            "width_ft": r.width_ft,
            "length_ft": r.length_ft,
            "ceiling_height_ft": r.ceiling_height_ft,
            "sort_order": r.sort_order,
        }
        for r in estimate.rooms
    ]

    result = calculate_estimate(
        rooms, estimate.pct_good, estimate.pct_better, estimate.pct_best
    )

    rooms_with_fixtures = {}
    for room_data in result["rooms"]:
        fixtures = [
            FixtureAssignment(
                fixture_type=f["fixture_type"],
                zone=f.get("zone", ""),
                notes=f.get("notes", ""),
                is_prewire=f.get("is_prewire", False),
                product_sku=f.get("product_sku", ""),
                product_desc=f.get("product_desc", ""),
                msrp_range=f.get("msrp_range", ""),
            )
            for f in room_data.get("fixtures", [])
        ]
        rooms_with_fixtures[room_data["name"]] = fixtures

    estimate_summary = {
        "total_sqft": estimate.total_sqft,
        "pct_good": estimate.pct_good,
        "pct_better": estimate.pct_better,
        "pct_best": estimate.pct_best,
        **result["summary"],
    }

    return rooms_with_fixtures, estimate_summary


@router.get("/projects/{project_id}/pdf")
def export_pdf(
    project_id: str,
    include_cover: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """Generate and download a branded PDF fixture schedule."""
    project = (
        db.query(Project)
        .options(
            joinedload(Project.floor_plans)
            .joinedload(FloorPlan.rooms)
            .joinedload(Room.fixtures),
            joinedload(Project.builder),
            joinedload(Project.estimate)
            .joinedload(Estimate.rooms),
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    builder_name = project.builder.name if project.builder else ""
    floor_plan_image_path = None
    estimate_summary = None

    # Check for estimate-mode project
    if project.estimate and project.estimate.rooms:
        rooms_with_fixtures, estimate_summary = _build_estimate_data(project.estimate)
        tier = "better"

        # Optional: if a floor plan was attached for reference
        for plan in (project.floor_plans or []):
            if plan.stored_path:
                floor_plan_image_path = plan.stored_path
                break

        generator = PDFGenerator()
        pdf_bytes = generator.generate(
            project_name=project.name,
            project_address=project.address or "",
            tier=tier,
            rooms_with_fixtures=rooms_with_fixtures,
            builder_name=builder_name,
            include_cover=include_cover,
            schematic_layout=None,
            floor_plan_image_path=floor_plan_image_path,
            estimate_summary=estimate_summary,
        )
    elif project.floor_plans:
        # Legacy floor plan mode
        rooms_with_fixtures = {}
        for plan in project.floor_plans:
            for room in plan.rooms:
                fixtures = [
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
                    for f in room.fixtures
                ]
                rooms_with_fixtures[room.name] = fixtures

        rooms_data = []
        for plan in project.floor_plans:
            if plan.stored_path:
                floor_plan_image_path = plan.stored_path
            for room in plan.rooms:
                rooms_data.append(RoomData(
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
                ))

        schematic = compute_schematic_layout(rooms_data, rooms_with_fixtures) if rooms_data else None

        generator = PDFGenerator()
        pdf_bytes = generator.generate(
            project_name=project.name,
            project_address=project.address or "",
            tier=project.tier,
            rooms_with_fixtures=rooms_with_fixtures,
            builder_name=builder_name,
            include_cover=include_cover,
            schematic_layout=schematic,
            floor_plan_image_path=floor_plan_image_path,
        )
    else:
        raise HTTPException(status_code=400, detail="No estimate or floor plans for this project")

    filename = f"LightPlan_{project.name.replace(' ', '_')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
