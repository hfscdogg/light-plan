"""Estimate builder API: form-driven fixture estimation without floor plans."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.database import Estimate, EstimateRoom, Project, get_db
from app.models.schemas import (
    EstimateCreate,
    EstimateFixtureResponse,
    EstimateResponse,
    EstimateRoomInput,
    EstimateRoomResponse,
    EstimateSummary,
    EstimateUpdate,
)
from app.services.estimate_calculator import calculate_estimate
from app.services.room_templates import generate_rooms

logger = logging.getLogger(__name__)

router = APIRouter()


def _run_calculator(estimate: Estimate) -> dict:
    """Build room dicts from DB and run the calculator."""
    rooms = [
        {
            "id": r.id,
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
    return calculate_estimate(
        rooms, estimate.pct_good, estimate.pct_better, estimate.pct_best
    )


def _build_response(estimate: Estimate, calc_result: dict) -> EstimateResponse:
    """Build the full API response from an estimate and its calculation."""
    room_responses = []
    for room_data in calc_result["rooms"]:
        fixtures = [
            EstimateFixtureResponse(**f) for f in room_data.get("fixtures", [])
        ]
        room_responses.append(
            EstimateRoomResponse(
                id=room_data.get("id", ""),
                name=room_data["name"],
                room_type=room_data["room_type"],
                sqft=room_data.get("sqft"),
                width_ft=room_data.get("width_ft"),
                length_ft=room_data.get("length_ft"),
                ceiling_height_ft=room_data.get("ceiling_height_ft"),
                assigned_tier=room_data.get("assigned_tier", "better"),
                sort_order=room_data.get("sort_order", 0),
                fixtures=fixtures,
            )
        )

    return EstimateResponse(
        id=estimate.id,
        project_id=estimate.project_id,
        total_sqft=estimate.total_sqft,
        num_stories=estimate.num_stories,
        pct_good=estimate.pct_good,
        pct_better=estimate.pct_better,
        pct_best=estimate.pct_best,
        ceiling_height_default=estimate.ceiling_height_default,
        rooms=room_responses,
        summary=EstimateSummary(**calc_result["summary"]),
    )


@router.post("/{project_id}/estimate", response_model=EstimateResponse)
def create_estimate(
    project_id: str,
    body: EstimateCreate,
    db: Session = Depends(get_db),
):
    """Create an estimate for a project, auto-generating rooms from sqft."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if db.query(Estimate).filter(Estimate.project_id == project_id).first():
        raise HTTPException(status_code=409, detail="Estimate already exists for this project")

    if body.pct_good + body.pct_better + body.pct_best != 100:
        raise HTTPException(status_code=422, detail="Tier percentages must sum to 100")

    estimate = Estimate(
        project_id=project_id,
        total_sqft=body.total_sqft,
        num_stories=body.num_stories,
        pct_good=body.pct_good,
        pct_better=body.pct_better,
        pct_best=body.pct_best,
        ceiling_height_default=body.ceiling_height_default,
    )
    db.add(estimate)
    db.flush()

    room_dicts = generate_rooms(body.total_sqft, ceiling_height=body.ceiling_height_default)
    for rd in room_dicts:
        room = EstimateRoom(
            estimate_id=estimate.id,
            name=rd["name"],
            room_type=rd["room_type"],
            sqft=rd["sqft"],
            width_ft=rd["width_ft"],
            length_ft=rd["length_ft"],
            ceiling_height_ft=rd["ceiling_height_ft"],
            sort_order=rd["sort_order"],
        )
        db.add(room)

    project.status = "assigned"
    db.commit()
    db.refresh(estimate)

    result = _run_calculator(estimate)
    return _build_response(estimate, result)


@router.get("/{project_id}/estimate", response_model=EstimateResponse)
def get_estimate(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Retrieve the current estimate with fixtures and summary."""
    estimate = (
        db.query(Estimate).filter(Estimate.project_id == project_id).first()
    )
    if not estimate:
        raise HTTPException(status_code=404, detail="No estimate found for this project")

    result = _run_calculator(estimate)
    return _build_response(estimate, result)


@router.patch("/{project_id}/estimate", response_model=EstimateResponse)
def update_estimate(
    project_id: str,
    body: EstimateUpdate,
    db: Session = Depends(get_db),
):
    """Update estimate parameters and recalculate."""
    estimate = (
        db.query(Estimate).filter(Estimate.project_id == project_id).first()
    )
    if not estimate:
        raise HTTPException(status_code=404, detail="No estimate found for this project")

    if body.total_sqft is not None:
        estimate.total_sqft = body.total_sqft
    if body.num_stories is not None:
        estimate.num_stories = body.num_stories
    if body.pct_good is not None:
        estimate.pct_good = body.pct_good
    if body.pct_better is not None:
        estimate.pct_better = body.pct_better
    if body.pct_best is not None:
        estimate.pct_best = body.pct_best
    if body.ceiling_height_default is not None:
        estimate.ceiling_height_default = body.ceiling_height_default

    if estimate.pct_good + estimate.pct_better + estimate.pct_best != 100:
        raise HTTPException(status_code=422, detail="Tier percentages must sum to 100")

    if body.rooms is not None:
        db.query(EstimateRoom).filter(
            EstimateRoom.estimate_id == estimate.id
        ).delete()
        for i, rd in enumerate(body.rooms):
            room = EstimateRoom(
                estimate_id=estimate.id,
                name=rd.name,
                room_type=rd.room_type,
                sqft=rd.sqft,
                width_ft=rd.width_ft,
                length_ft=rd.length_ft,
                ceiling_height_ft=rd.ceiling_height_ft,
                sort_order=i,
            )
            db.add(room)

    db.commit()
    db.refresh(estimate)

    result = _run_calculator(estimate)
    return _build_response(estimate, result)


@router.post("/{project_id}/estimate/rooms", response_model=EstimateResponse)
def add_estimate_room(
    project_id: str,
    body: EstimateRoomInput,
    db: Session = Depends(get_db),
):
    """Add a single room to the estimate."""
    estimate = (
        db.query(Estimate).filter(Estimate.project_id == project_id).first()
    )
    if not estimate:
        raise HTTPException(status_code=404, detail="No estimate found")

    max_order = max((r.sort_order for r in estimate.rooms), default=-1)
    room = EstimateRoom(
        estimate_id=estimate.id,
        name=body.name,
        room_type=body.room_type,
        sqft=body.sqft,
        width_ft=body.width_ft,
        length_ft=body.length_ft,
        ceiling_height_ft=body.ceiling_height_ft,
        sort_order=max_order + 1,
    )
    db.add(room)
    db.commit()
    db.refresh(estimate)

    result = _run_calculator(estimate)
    return _build_response(estimate, result)


@router.delete("/{project_id}/estimate/rooms/{room_id}", response_model=EstimateResponse)
def delete_estimate_room(
    project_id: str,
    room_id: str,
    db: Session = Depends(get_db),
):
    """Remove a room from the estimate."""
    estimate = (
        db.query(Estimate).filter(Estimate.project_id == project_id).first()
    )
    if not estimate:
        raise HTTPException(status_code=404, detail="No estimate found")

    room = db.query(EstimateRoom).filter(
        EstimateRoom.id == room_id,
        EstimateRoom.estimate_id == estimate.id,
    ).first()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    db.delete(room)
    db.commit()
    db.refresh(estimate)

    result = _run_calculator(estimate)
    return _build_response(estimate, result)
