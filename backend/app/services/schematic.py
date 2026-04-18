"""Compute a schematic layout for frontend SVG rendering.

Maps room bounding boxes and fixture positions onto a fixed canvas,
producing a JSON structure the frontend renders as a clean diagram
instead of overlaying icons on the floor plan image.
"""

from app.models.schemas import FixtureAssignment, RoomData

# Canvas defaults
CANVAS_WIDTH = 1000
CANVAS_HEIGHT = 750

# Room types to exclude from the schematic
SKIP_ROOM_TYPES = {"closet", "pantry", "walk_in_closet", "other"}

# Fixture types to include in the schematic
SCHEMATIC_FIXTURE_TYPES = {
    "recessed",
    "pendant",
    "sconce",
    "ceiling_fan",
    "coach_light",
    "exhaust_fan",
}

# Color map matching frontend legend
TYPE_COLORS = {
    "recessed": "#444444",
    "pendant": "#d97706",
    "sconce": "#7c3aed",
    "ceiling_fan": "#16a34a",
    "coach_light": "#ca8a04",
    "exhaust_fan": "#64748b",
}

# Fixture types that always go at the exact center of the room rect
_CENTER_TYPES = {"ceiling_fan", "pendant"}

# Inset fraction to keep fixtures away from room edges
_INSET = 0.12


def compute_schematic_layout(
    rooms_data: list[RoomData],
    fixtures_by_room: dict[str, list[FixtureAssignment]],
) -> dict:
    """Build the schematic_layout dict consumed by the frontend.

    Parameters
    ----------
    rooms_data:
        Parsed room list with bounding boxes in 0-1 fractions.
    fixtures_by_room:
        Mapping of room name to fixture assignments from the lighting engine.

    Returns
    -------
    dict matching the SchematicLayout schema.
    """
    canvas_w = CANVAS_WIDTH
    canvas_h = CANVAS_HEIGHT

    rooms_out: list[dict] = []

    for rd in rooms_data:
        # Skip room types the frontend does not render
        if rd.room_type in SKIP_ROOM_TYPES:
            continue

        # Compute the room rectangle on the canvas from bbox fractions
        if (
            rd.bbox_x1 is not None
            and rd.bbox_y1 is not None
            and rd.bbox_x2 is not None
            and rd.bbox_y2 is not None
        ):
            x1 = rd.bbox_x1 * canvas_w
            y1 = rd.bbox_y1 * canvas_h
            x2 = rd.bbox_x2 * canvas_w
            y2 = rd.bbox_y2 * canvas_h

            # Ensure correct ordering
            if x1 > x2:
                x1, x2 = x2, x1
            if y1 > y2:
                y1, y2 = y2, y1

            rect_x = round(x1, 1)
            rect_y = round(y1, 1)
            rect_w = round(x2 - x1, 1)
            rect_h = round(y2 - y1, 1)
        else:
            # No bbox available -- place a default-sized rect
            rect_w = 200.0
            rect_h = 150.0
            rect_x = round((rd.position_x or 0.5) * canvas_w - rect_w / 2, 1)
            rect_y = round((rd.position_y or 0.5) * canvas_h - rect_h / 2, 1)

        # Gather all fixtures for this room
        all_room_fixtures = fixtures_by_room.get(rd.name, [])
        total_fixture_count = len(all_room_fixtures)

        # Filter to only schematic-visible fixture types
        visible_fixtures = [
            fa for fa in all_room_fixtures
            if fa.fixture_type in SCHEMATIC_FIXTURE_TYPES
        ]

        # Compute fixture positions within the room rect
        schematic_fixtures: list[dict] = []
        for fa in visible_fixtures:
            if fa.fixture_type in _CENTER_TYPES:
                # Place at the exact center of the room rect
                fx = rect_x + rect_w / 2
                fy = rect_y + rect_h / 2
            else:
                # Map position_x/position_y through the inset region
                inner_x = rect_x + rect_w * _INSET
                inner_y = rect_y + rect_h * _INSET
                inner_w = rect_w * (1 - 2 * _INSET)
                inner_h = rect_h * (1 - 2 * _INSET)

                fx = inner_x + fa.position_x * inner_w
                fy = inner_y + fa.position_y * inner_h

            # Clamp to room rect bounds
            fx = max(rect_x + 1, min(rect_x + rect_w - 1, fx))
            fy = max(rect_y + 1, min(rect_y + rect_h - 1, fy))

            schematic_fixtures.append({
                "type": fa.fixture_type,
                "x": round(fx, 1),
                "y": round(fy, 1),
                "color": TYPE_COLORS.get(fa.fixture_type, "#444444"),
            })

        rooms_out.append({
            "name": rd.name,
            "room_type": rd.room_type,
            "label": rd.name,
            "rect": {
                "x": rect_x,
                "y": rect_y,
                "w": rect_w,
                "h": rect_h,
            },
            "fixtures": schematic_fixtures,
            "fixture_count": total_fixture_count,
        })

    return {
        "canvas": {"width": canvas_w, "height": canvas_h},
        "rooms": rooms_out,
    }
