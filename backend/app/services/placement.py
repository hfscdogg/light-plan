"""Compute validated plan-level fixture positions from room bounding boxes.

Maps room-relative fixture positions (0-1 within room) into plan-image
coordinates using the room's bounding box.

Two fixtures that resolve to the same point render as a single marker: the
rep sees one icon, drags it, and finds another underneath.  Every position
this module returns therefore goes through a separation pass that nudges
co-located fixtures apart while keeping them inside their room.
"""

import logging
import math
import re

logger = logging.getLogger(__name__)

# How far apart two markers must sit, as a fraction of the plan's width.
# A marker is a 26px circle; on a plan rendered ~900px wide that is ~0.029,
# so 0.02 keeps two markers distinguishable and separately clickable without
# throwing a fixture across the room to get there.
MIN_SEPARATION = 0.02

# Candidate offsets are tried on rings around the wanted point: near first,
# so a displaced fixture stays as close as possible to where it belongs.
_RING_STEPS = 6
_RING_ANGLES = 8

# Keep markers off the exact bbox edge so they read as inside the room.
_EDGE_INSET = 0.005


def match_key(value: str) -> str:
    """Strip a name down to what matters for matching.

    The placement model echoes room and fixture names back in whatever shape
    it read them — "KITCHEN", "Kitchen ", "Ceiling Fan" — and an exact string
    comparison threw those placements away silently, dropping the room back
    to the algorithmic grid.  Case, spaces, underscores and punctuation all
    come out here so "Ceiling Fan" and "ceiling_fan" are one key.
    """
    return re.sub(r"[^a-z0-9]+", "", (value or "").lower())


def resolve_name(value: str, candidates) -> str | None:
    """Find which of ``candidates`` the model meant by ``value``.

    Exact match after normalising wins.  Otherwise a candidate that the
    answer merely extends counts — "recessed" for "recessed light", "Bath"
    for "Bathroom" — but only when exactly one candidate fits, so an
    ambiguous answer is dropped rather than assigned to the wrong room.
    """
    key = match_key(value)
    if not key:
        return None

    by_key = {}
    for candidate in candidates:
        by_key.setdefault(match_key(candidate), candidate)

    if key in by_key:
        return by_key[key]

    extended = [
        candidate
        for candidate_key, candidate in by_key.items()
        if candidate_key and key.startswith(candidate_key)
    ]
    if len(extended) == 1:
        return extended[0]
    return None


def room_bounds(rooms_data: list) -> dict[str, tuple[float, float, float, float]]:
    """Usable (x1, y1, x2, y2) plan bounds for each room, keyed by name.

    A room with a bounding box uses it.  A room with only a label position
    gets a small box around that label.  A room with neither is absent, and
    callers fall back to the middle of the sheet.
    """
    bounds = {}
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

            bounds[rd.name] = (x1, y1, x2, y2)
        elif rd.position_x is not None:
            cx = rd.position_x
            cy = rd.position_y or 0.5
            span = 0.06
            bounds[rd.name] = (cx - span, cy - span, cx + span, cy + span)

    return bounds


def clamp_to_bounds(
    x: float, y: float, bounds: tuple[float, float, float, float] | None
) -> tuple[float, float]:
    """Pull a point inside a room's bounds, or inside the sheet if unknown."""
    if bounds is None:
        return max(0.0, min(1.0, x)), max(0.0, min(1.0, y))
    x1, y1, x2, y2 = bounds
    return (
        max(x1 + _EDGE_INSET, min(x2 - _EDGE_INSET, x)),
        max(y1 + _EDGE_INSET, min(y2 - _EDGE_INSET, y)),
    )


def _nearest(x: float, y: float, placed: list[tuple[float, float]]) -> float:
    """Distance to the closest already-placed fixture (inf if there are none)."""
    if not placed:
        return math.inf
    return min(math.hypot(x - px, y - py) for px, py in placed)


def separate_overlapping(
    positions: list[tuple[float, float]],
    bounds: tuple[float, float, float, float] | None = None,
) -> list[tuple[float, float]]:
    """Nudge co-located fixtures apart, keeping them inside ``bounds``.

    Fixtures are processed in order, so the first one at a given spot keeps
    it and later arrivals move.  Each displaced fixture takes the closest
    candidate that clears ``MIN_SEPARATION``; if the room is too small for
    that, it takes the roomiest candidate available rather than landing on
    top of its neighbour.
    """
    placed: list[tuple[float, float]] = []

    def settle(x: float, y: float) -> tuple[float, float]:
        """Clamp, then round to the precision we actually store.

        Measuring an unrounded candidate and storing a rounded one let a
        fixture that cleared the gap by a hair round back under it.
        """
        cx, cy = clamp_to_bounds(x, y, bounds)
        return round(cx, 4), round(cy, 4)

    for x, y in positions:
        wanted = settle(x, y)

        if _nearest(*wanted, placed) >= MIN_SEPARATION:
            placed.append(wanted)
            continue

        best_gap = -1.0
        best = wanted
        found = None

        for step in range(1, _RING_STEPS + 1):
            # Overshoot slightly so a candidate does not land exactly on the
            # threshold, where rounding decides whether it clears.
            radius = MIN_SEPARATION * (step + 0.1)
            for i in range(_RING_ANGLES):
                angle = 2 * math.pi * i / _RING_ANGLES
                candidate = settle(
                    wanted[0] + radius * math.cos(angle),
                    wanted[1] + radius * math.sin(angle),
                )
                gap = _nearest(*candidate, placed)
                if gap >= MIN_SEPARATION:
                    found = candidate
                    break
                if gap > best_gap:
                    best_gap = gap
                    best = candidate
            if found:
                break

        placed.append(found or best)

    return placed


def spread_fixtures(
    plan_positions: dict[str, list[tuple[float, float]]],
    bounds_lookup: dict[str, tuple[float, float, float, float]],
) -> dict[str, list[tuple[float, float]]]:
    """Run the separation pass over every room's positions."""
    spread = {}
    for room_name, positions in plan_positions.items():
        spread[room_name] = separate_overlapping(
            positions, bounds_lookup.get(room_name)
        )
        moved = sum(1 for a, b in zip(positions, spread[room_name]) if a != b)
        if moved:
            logger.info(
                "Separated %d of %d overlapping fixture(s) in %s",
                moved, len(positions), room_name,
            )
    return spread


def compute_plan_positions(
    rooms_data: list,
    fixtures_by_room: dict,
) -> dict[str, list[tuple[float, float]]]:
    """Compute plan-level (x, y) for each fixture in each room."""
    bounds_lookup = room_bounds(rooms_data)

    result = {}
    for room_name, fixtures in fixtures_by_room.items():
        bounds = bounds_lookup.get(room_name)

        if not bounds:
            # Nothing located this room on the sheet.  The fixtures still
            # belong to the plan, so they go to the middle where the rep can
            # see and drag them, spread out rather than in one pile.
            result[room_name] = [(0.5, 0.5)] * len(fixtures)
            continue

        x1, y1, x2, y2 = bounds
        w = x2 - x1
        h = y2 - y1

        positions = []
        for fa in fixtures:
            # Map room-relative position (0-1) directly into the bbox.  The
            # lighting engine already applies wall insets in its grid
            # algorithm, and it spaces island pendants deliberately, so no
            # fixture type gets overridden to the room centre here — doing
            # that stacked every pendant and fan on one point.
            px = x1 + fa.position_x * w
            py = y1 + fa.position_y * h

            positions.append(clamp_to_bounds(px, py, bounds))
            logger.debug(
                "PLACE %-20s %-12s rel=(%.3f,%.3f) -> plan=(%.4f,%.4f) "
                "bbox=(%.3f,%.3f)-(%.3f,%.3f)",
                room_name, fa.fixture_type,
                fa.position_x, fa.position_y,
                positions[-1][0], positions[-1][1], x1, y1, x2, y2,
            )

        result[room_name] = positions

    return spread_fixtures(result, bounds_lookup)
