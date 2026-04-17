"""Compute validated plan-level fixture positions from room bounding boxes.

Maps room-relative fixture positions (0-1 within room) into plan-image
coordinates using the room's bounding box, with validation and clamping.

Ceiling fans and pendants are placed directly at the room's label center
(position_x/position_y from the parser) so they always appear at the
visual center of the room, independent of bbox accuracy.
"""


def compute_plan_positions(
    rooms_data: list,
    fixtures_by_room: dict,
) -> dict[str, list[tuple[float, float]]]:
    """Compute plan-level (x, y) for each fixture in each room."""
    # Build bbox + center lookup from rooms_data
    bbox_lookup = {}
    center_lookup = {}
    for rd in rooms_data:
        # Store the label-derived center (authoritative room center)
        if rd.position_x is not None and rd.position_y is not None:
            center_lookup[rd.name] = (rd.position_x, rd.position_y)

        if rd.bbox_x1 is not None and rd.bbox_x2 is not None:
            x1 = max(0.03, min(0.97, rd.bbox_x1))
            y1 = max(0.03, min(0.97, rd.bbox_y1))
            x2 = max(0.03, min(0.97, rd.bbox_x2))
            y2 = max(0.03, min(0.97, rd.bbox_y2))

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

    # Fixture types that should be placed at the exact room center
    # (label position) rather than mapped through the bbox grid.
    _CENTER_TYPES = {"ceiling_fan", "pendant"}

    result = {}
    for room_name, fixtures in fixtures_by_room.items():
        bbox = bbox_lookup.get(room_name)
        center = center_lookup.get(room_name)

        if not bbox:
            result[room_name] = [(0.5, 0.5)] * len(fixtures)
            continue

        x1, y1, x2, y2 = bbox
        w = x2 - x1
        h = y2 - y1

        inset = 0.12
        inner_x1 = x1 + w * inset
        inner_y1 = y1 + h * inset
        inner_w = w * (1 - 2 * inset)
        inner_h = h * (1 - 2 * inset)

        positions = []
        for fa in fixtures:
            if fa.fixture_type in _CENTER_TYPES and center:
                # Place directly at the label center — guaranteed to be
                # at the architect-defined room center.
                px, py = center
            else:
                px = inner_x1 + fa.position_x * inner_w
                py = inner_y1 + fa.position_y * inner_h

            px = max(x1 + 0.005, min(x2 - 0.005, px))
            py = max(y1 + 0.005, min(y2 - 0.005, py))

            positions.append((round(px, 4), round(py, 4)))

        result[room_name] = positions

    return result
