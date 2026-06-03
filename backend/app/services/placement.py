"""Compute validated plan-level fixture positions from room bounding boxes.

Maps room-relative fixture positions (0-1 within room) into plan-image
coordinates using the room's bounding box.

Ceiling fans and pendants are placed at the bbox geometric center (the
true room center), independent of where the label text is printed.
"""

import logging

logger = logging.getLogger(__name__)


def compute_plan_positions(
    rooms_data: list,
    fixtures_by_room: dict,
) -> dict[str, list[tuple[float, float]]]:
    """Compute plan-level (x, y) for each fixture in each room."""
    bbox_lookup = {}
    for rd in rooms_data:
        if rd.bbox_x1 is not None and rd.bbox_x2 is not None:
            x1 = max(0.01, min(0.99, rd.bbox_x1))
            y1 = max(0.01, min(0.99, rd.bbox_y1))
            x2 = max(0.01, min(0.99, rd.bbox_x2))
            y2 = max(0.01, min(0.99, rd.bbox_y2))

            if x1 >= x2:
                x1, x2 = min(x1, x2), max(x1, x2)
            if y1 >= y2:
                y1, y2 = min(y1, y2), max(y1, y2)

            if x2 - x1 < 0.03:
                mid = (x1 + x2) / 2
                x1 = mid - 0.015
                x2 = mid + 0.015
            if y2 - y1 < 0.03:
                mid = (y1 + y2) / 2
                y1 = mid - 0.015
                y2 = mid + 0.015

            bbox_lookup[rd.name] = (x1, y1, x2, y2)
        elif rd.position_x is not None:
            cx = rd.position_x
            cy = rd.position_y or 0.5
            span = 0.06
            bbox_lookup[rd.name] = (cx - span, cy - span, cx + span, cy + span)

    _CENTER_TYPES = {"ceiling_fan", "pendant"}

    result = {}
    for room_name, fixtures in fixtures_by_room.items():
        bbox = bbox_lookup.get(room_name)

        if not bbox:
            result[room_name] = [(0.5, 0.5)] * len(fixtures)
            continue

        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1
        bbox_cx = (x1 + x2) / 2
        bbox_cy = (y1 + y2) / 2

        positions = []
        for fa in fixtures:
            if fa.fixture_type in _CENTER_TYPES:
                px, py = bbox_cx, bbox_cy
            else:
                # Map room-relative position (0-1) directly into bbox.
                # The lighting engine already applies wall insets in its
                # grid algorithm, so we map the full 0-1 range to the
                # full bbox — no additional inset here.
                px = x1 + fa.position_x * w
                py = y1 + fa.position_y * h

            px = max(x1 + 0.005, min(x2 - 0.005, px))
            py = max(y1 + 0.005, min(y2 - 0.005, py))

            positions.append((round(px, 4), round(py, 4)))
            logger.info(
                "PLACE %-20s %-12s rel=(%.3f,%.3f) -> plan=(%.4f,%.4f) bbox=(%.3f,%.3f)-(%.3f,%.3f)",
                room_name, fa.fixture_type,
                fa.position_x, fa.position_y,
                px, py, x1, y1, x2, y2,
            )

        result[room_name] = positions

    return result
