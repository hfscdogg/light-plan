from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session, joinedload

from app.models.database import Builder, Fixture, FloorPlan, Project, Room, get_db
from app.models.schemas import FixtureAssignment
from app.services.pdf_generator import PDFGenerator

router = APIRouter()


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
        )
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.floor_plans:
        raise HTTPException(status_code=400, detail="No floor plans uploaded for this project")

    # Collect all rooms and fixtures across all floor plans
    rooms_with_fixtures: dict[str, list[FixtureAssignment]] = {}
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

    builder_name = project.builder.name if project.builder else ""

    generator = PDFGenerator()
    pdf_bytes = generator.generate(
        project_name=project.name,
        project_address=project.address or "",
        tier=project.tier,
        rooms_with_fixtures=rooms_with_fixtures,
        builder_name=builder_name,
        include_cover=include_cover,
    )

    filename = f"LightPlan_{project.name.replace(' ', '_')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
