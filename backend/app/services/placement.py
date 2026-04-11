"""Compute validated plan-level fixture positions from room bounding boxes.

Maps room-relative fixture positions (0-1 within room) into plan-image
coordinates using the room's bounding box, with validation and clamping.
"""


def compute_plan_positions(
    rooms_data: list,
    fixtures_by_room: dict,
) -> dict[str, list[tuple[float, float]]]:
    """Compute plan-level (x, y) for each fixture in each room.

    Returns a dict mapping room name to a list of (plan_x, plan_y) tuples,
    one per fixture in the same order as fixtures_by_room.

    Bounding boxes are validated and sanitized:
    - Clamped to [0.03, 0.97] to stay within the plan drawing area
    - Minimum room size enforced (3% of plan in each dimension)
    - 20% inset from room edges for fixture placement
    """
    # Build bbox lookup from rooms_data
    bbox_lookup = {}
    for rd in rooms_data:
        if rd.bbox_x1 is not None and rd.bbox_x2 is not None:
            # Clamp to plan drawing area (exclude titles, legends, borders)
            x1 = max(0.03, min(0.97, rd.bbox_x1))
            y1 = max(0.03, min(0.97, rd.bbox_y1))
            x2 = max(0.03, min(0.97, rd.bbox_x2))
            y2 = max(0.03, min(0.97, rd.bbox_y2))

            # Ensure x1 < x2 and y1 < y2
            if x1 >= x2:
                x1, x2 = min(x1, x2), max(x1, x2)
            if y1 >= y2:
                y1, y2 = min(y1, y2), max(y1, y2)

            # Enforce minimum room size (3% of plan)
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
            # Fallback: create a small bbox around the center point
            cx = rd.position_x
            cy = rd.position_y or 0.5
            span = 0.06
            bbox_lookup[rd.name] = (cx - span, cy - span, cx + span, cy + span)

    result = {}
    for room_name, fixtures in fixtures_by_room.items():
        bbox = bbox_lookup.get(room_name)
        if not bbox:
            # No position data at all, center everything
            result[room_name] = [(0.5, 0.5)] * len(fixtures)
            continue

        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1

        # 20% inset from room edges
        inset = 0.20
        inner_x1 = x1 + w * inset
        inner_y1 = y1 + h * inset
        inner_w = w * (1 - 2 * inset)
        inner_h = h * (1 - 2 * inset)

        positions = []
        for fa in fixtures:
            # Map fixture's room-relative position into the inset bbox
            px = inner_x1 + fa.position_x * inner_w
            py = inner_y1 + fa.position_y * inner_h

            # Final safety clamp: must be inside the original bbox
            px = max(x1 + 0.005, min(x2 - 0.005, px))
            py = max(y1 + 0.005, min(y2 - 0.005, py))

            positions.append((round(px, 4), round(py, 4)))

        result[room_name] = positions

    return result
