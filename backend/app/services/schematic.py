"""Compute a schematic layout for frontend SVG rendering.

Maps room bounding boxes and fixture positions onto a fixed canvas,
producing a JSON structure the frontend renders as a clean diagram
instead of overlaying icons on the floor plan image.

Room rectangles are positioned using bbox centers from the plan parser
so the schematic preserves the spatial relationships of the real plan.
Sizes are proportional to actual room dimensions with min/max bounds.
"""

from app.models.schemas import FixtureAssignment, RoomData

# Canvas defaults
CANVAS_WIDTH = 1000
CANVAS_HEIGHT = 750

# Padding around the edges of the canvas
_CANVAS_PAD = 24

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

# Reserved header band (px) for the room label so icons never overlap it
_LABEL_BAND = 28

# Room rect size constraints (canvas px)
_MIN_RECT_W = 100
_MIN_RECT_H = 80
_MAX_RECT_W = 450
_MAX_RECT_H = 350


def compute_schematic_layout(
    rooms_data: list[RoomData],
    fixtures_by_room: dict[str, list[FixtureAssignment]],
) -> dict:
    """Build the schematic_layout dict consumed by the frontend."""
    canvas_w = CANVAS_WIDTH
    canvas_h = CANVAS_HEIGHT

    # --- Phase 1: collect rooms with their bbox data ---
    entries: list[tuple[RoomData, float, float, float, float]] = []
    for rd in rooms_data:
        if rd.room_type in SKIP_ROOM_TYPES:
            continue

        if (
            rd.bbox_x1 is not None
            and rd.bbox_y1 is not None
            and rd.bbox_x2 is not None
            and rd.bbox_y2 is not None
        ):
            bx1, by1 = rd.bbox_x1, rd.bbox_y1
            bx2, by2 = rd.bbox_x2, rd.bbox_y2
            if bx1 > bx2:
                bx1, bx2 = bx2, bx1
            if by1 > by2:
                by1, by2 = by2, by1
            entries.append((rd, bx1, by1, bx2, by2))
        elif rd.position_x is not None:
            cx = rd.position_x
            cy = rd.position_y or 0.5
            entries.append((rd, cx - 0.05, cy - 0.05, cx + 0.05, cy + 0.05))

    if not entries:
        return {"canvas": {"width": canvas_w, "height": canvas_h}, "rooms": []}

    # --- Phase 2: compute proportional rect sizes with min/max ---
    raw_sizes: list[tuple[float, float]] = []
    for _, bx1, by1, bx2, by2 in entries:
        raw_sizes.append((bx2 - bx1, by2 - by1))

    # Scale bbox fractions to canvas pixels
    sized: list[tuple[float, float]] = []
    for rw, rh in raw_sizes:
        w = rw * canvas_w
        h = rh * canvas_h
        w = max(_MIN_RECT_W, min(_MAX_RECT_W, w))
        h = max(_MIN_RECT_H, min(_MAX_RECT_H, h))
        sized.append((round(w, 1), round(h, 1)))

    # --- Phase 3: position rects using bbox centers ---
    centers: list[tuple[float, float]] = []
    for _, bx1, by1, bx2, by2 in entries:
        centers.append(((bx1 + bx2) / 2, (by1 + by2) / 2))

    # Map the center range to canvas coordinates with padding
    cx_vals = [c[0] for c in centers]
    cy_vals = [c[1] for c in centers]
    min_cx, max_cx = min(cx_vals), max(cx_vals)
    min_cy, max_cy = min(cy_vals), max(cy_vals)

    span_cx = max_cx - min_cx if max_cx > min_cx else 1.0
    span_cy = max_cy - min_cy if max_cy > min_cy else 1.0

    # Usable area after padding and accounting for rect sizes
    max_half_w = max(s[0] for s in sized) / 2
    max_half_h = max(s[1] for s in sized) / 2
    usable_x0 = _CANVAS_PAD + max_half_w
    usable_x1 = canvas_w - _CANVAS_PAD - max_half_w
    usable_y0 = _CANVAS_PAD + max_half_h
    usable_y1 = canvas_h - _CANVAS_PAD - max_half_h

    if usable_x1 <= usable_x0:
        usable_x0, usable_x1 = _CANVAS_PAD, canvas_w - _CANVAS_PAD
    if usable_y1 <= usable_y0:
        usable_y0, usable_y1 = _CANVAS_PAD, canvas_h - _CANVAS_PAD

    rects: list[list[float]] = []  # [x, y, w, h] per room
    for i, (cx, cy) in enumerate(centers):
        w, h = sized[i]
        # Normalize center to 0-1 within the center range, then map to usable area
        nx = (cx - min_cx) / span_cx if span_cx > 0 else 0.5
        ny = (cy - min_cy) / span_cy if span_cy > 0 else 0.5
        sx = usable_x0 + nx * (usable_x1 - usable_x0)
        sy = usable_y0 + ny * (usable_y1 - usable_y0)
        rects.append([round(sx - w / 2, 1), round(sy - h / 2, 1), w, h])

    # --- Phase 4: resolve overlaps then compact ---
    _resolve_overlaps(rects, canvas_w, canvas_h)
    _compact_layout(rects, canvas_w, canvas_h)

    # --- Phase 5: build fixture positions within each rect ---
    rooms_out: list[dict] = []
    for i, (rd, *_) in enumerate(entries):
        rect_x, rect_y, rect_w, rect_h = rects[i]

        all_room_fixtures = fixtures_by_room.get(rd.name, [])
        total_fixture_count = len(all_room_fixtures)

        visible_fixtures = [
            fa for fa in all_room_fixtures
            if fa.fixture_type in SCHEMATIC_FIXTURE_TYPES
        ]

        schematic_fixtures = _place_fixtures(
            visible_fixtures, rect_x, rect_y, rect_w, rect_h
        )

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


def _place_fixtures(
    fixtures: list[FixtureAssignment],
    rect_x: float,
    rect_y: float,
    rect_w: float,
    rect_h: float,
) -> list[dict]:
    """Compute fixture positions within a room rectangle.

    Reserves a header band for the room label so icons never overlap it.
    """
    result: list[dict] = []

    # Fixture placement area starts below the label band
    top_inset = max(rect_h * _INSET, _LABEL_BAND)
    inner_x = rect_x + rect_w * _INSET
    inner_y = rect_y + top_inset
    inner_w = rect_w * (1 - 2 * _INSET)
    inner_h = rect_h - top_inset - rect_h * _INSET

    if inner_w < 1 or inner_h < 1:
        inner_x, inner_y = rect_x + 4, rect_y + _LABEL_BAND
        inner_w, inner_h = rect_w - 8, rect_h - _LABEL_BAND - 4

    # Center of the fixture area (for fans/pendants)
    center_x = inner_x + inner_w / 2
    center_y = inner_y + inner_h / 2

    for fa in fixtures:
        if fa.fixture_type in _CENTER_TYPES:
            fx, fy = center_x, center_y
        else:
            fx = inner_x + fa.position_x * inner_w
            fy = inner_y + fa.position_y * inner_h

        fx = max(rect_x + 1, min(rect_x + rect_w - 1, fx))
        fy = max(rect_y + _LABEL_BAND, min(rect_y + rect_h - 1, fy))

        result.append({
            "type": fa.fixture_type,
            "x": round(fx, 1),
            "y": round(fy, 1),
            "color": TYPE_COLORS.get(fa.fixture_type, "#444444"),
        })

    return result


def _resolve_overlaps(
    rects: list[list[float]],
    canvas_w: float,
    canvas_h: float,
    max_iterations: int = 20,
) -> None:
    """Push overlapping rectangles apart in-place.

    For each overlapping pair, nudge both rects along the axis with
    the smallest overlap. Clamps to canvas bounds after each pass.
    """
    for _ in range(max_iterations):
        moved = False
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                ax, ay, aw, ah = rects[i]
                bx, by, bw, bh = rects[j]

                # Check overlap
                ox = min(ax + aw, bx + bw) - max(ax, bx)
                oy = min(ay + ah, by + bh) - max(ay, by)

                if ox > 0 and oy > 0:
                    moved = True
                    # Push apart along the axis with least overlap
                    gap = 6  # target gap between rooms (px)
                    if ox < oy:
                        shift = (ox / 2) + gap / 2
                        if ax < bx:
                            rects[i][0] -= shift
                            rects[j][0] += shift
                        else:
                            rects[i][0] += shift
                            rects[j][0] -= shift
                    else:
                        shift = (oy / 2) + gap / 2
                        if ay < by:
                            rects[i][1] -= shift
                            rects[j][1] += shift
                        else:
                            rects[i][1] += shift
                            rects[j][1] -= shift

        # Clamp to canvas
        for r in rects:
            r[0] = max(2, min(canvas_w - r[2] - 2, r[0]))
            r[1] = max(2, min(canvas_h - r[3] - 2, r[1]))
            r[0] = round(r[0], 1)
            r[1] = round(r[1], 1)

        if not moved:
            break


def _compact_layout(
    rects: list[list[float]],
    canvas_w: float,
    canvas_h: float,
) -> None:
    """Scale and re-center rects to fill the canvas tightly.

    After overlap resolution, rects may be spread too far apart.
    This step computes the bounding box of all rects, then scales
    and translates so they fill the canvas with consistent margins.
    """
    if not rects:
        return

    pad = _CANVAS_PAD

    # Compute bounding box of all rects
    all_left = min(r[0] for r in rects)
    all_top = min(r[1] for r in rects)
    all_right = max(r[0] + r[2] for r in rects)
    all_bottom = max(r[1] + r[3] for r in rects)

    layout_w = all_right - all_left
    layout_h = all_bottom - all_top

    if layout_w < 1 or layout_h < 1:
        return

    # Available space
    avail_w = canvas_w - 2 * pad
    avail_h = canvas_h - 2 * pad

    # Scale to fit, preserving aspect ratio
    scale = min(avail_w / layout_w, avail_h / layout_h, 1.2)

    # Center the layout in the canvas
    scaled_w = layout_w * scale
    scaled_h = layout_h * scale
    offset_x = pad + (avail_w - scaled_w) / 2
    offset_y = pad + (avail_h - scaled_h) / 2

    for r in rects:
        # Translate to origin, scale, translate to centered position
        r[0] = round(offset_x + (r[0] - all_left) * scale, 1)
        r[1] = round(offset_y + (r[1] - all_top) * scale, 1)
        r[2] = round(r[2] * scale, 1)
        r[3] = round(r[3] * scale, 1)
