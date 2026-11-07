"""Lay out fixtures around the things drawn in a room, not just its outline.

The room read gives each room a box; the rules engine fills the box.  That
left three rooms wrong on Zack's Keel markup, all for the same reason: the
fixtures did not know what was in the room.

- Kitchen (#8, #10): a can landed on the edge of the island, nothing was
  centered on the sink, and the under-cabinet light was one short run that
  crossed into the pantry wall while the range wall had none.
- Porch (#17): lanterns floated mid-porch, nothing lit the bays between the
  columns, and the door light sat on the door opening.
- Primary bedroom (#16): the cans, fan and bedside outlets were laid out
  with no idea where the bed goes.

One extra model pass reads those things off the drawing (``FEATURES_PROMPT``)
and ``apply_features`` moves, adds or removes fixtures around them.  Every
feature is checked against its room before it is used, and anything missing
or unreadable leaves that room as the rules engine laid it out.
"""

from __future__ import annotations

import json
import logging
import math
import re
from statistics import median

logger = logging.getLogger(__name__)

FEATURES_SYSTEM_PROMPT = """You read residential floor plans for a lighting designer.

You will receive a floor plan image and a few rooms with their bounding boxes
(fractions of the image width and height, 0 to 1).  Report what is drawn in
those rooms.  Every coordinate is a fraction of the image, written like 0.412:
x across the image from the left edge, y down the image from the top edge.

Return one JSON object with these keys (use null for anything not drawn):

"kitchen": {
  "room_name": the kitchen's name exactly as given,
  "island": [x1, y1, x2, y2] the island's rectangle, or null if there is no island,
  "sink": [x, y] the center of the kitchen sink bowl,
  "cabinet_runs": [[x1, y1, x2, y2], ...] one line per straight run of wall
      counter with upper cabinets above it, drawn along the front edge of the
      counter.  Split a run where the range, a window with no uppers, the
      refrigerator or a door interrupts it.  Never the island.
}

"porch": {
  "room_name": the front porch's name exactly as given,
  "columns": [[x, y], ...] the center of every porch column or post drawn
      along the porch's outer edge, in order,
  "front_door": {"hinge_end": [x, y], "latch_end": [x, y]} the two ends of
      the front door opening on the wall between the house and the porch.
      The hinge end is where the door swing arc is centered; the latch end is
      where the swing arc meets the wall.
}

"closets": [{"name": the printed name ("Coats", "Linen", "Pantry", "WH"...),
      "box": [x1, y1, x2, y2] its rectangle}, ...] every closet with its own
      door anywhere on the plan: coat, linen, pantry, mechanical or storage
      closets, however small, including ones inside or beside another room.
      Not walk-in closets that are their own room, and not cabinets.

"primary_bedroom": {
  "room_name": the primary bedroom's name exactly as given,
  "headboard_wall": "top", "bottom", "left" or "right": the wall a designer
      would put the bed's headboard against: the longest wall with no door
      and, if possible, no window,
  "bed_center": [x, y] the middle of that wall's usable length, where the
      center of the headboard goes
}

Return the JSON object only."""

# A feature may sit this far (fraction of the page) outside its room's box,
# for a box drawn to the inside of the walls.
_SLACK = 0.02

# Feet a fixture keeps clear of the island's edge.
ISLAND_CLEARANCE_FT = 1.5
# A can this close to the sink is moved onto it rather than adding another.
SINK_REACH_FT = 6.0
# A king bed with room to make it; cans flank it this far past its side.
BED_WIDTH_FT = 6.0
NIGHTSTAND_FT = 1.5
# The door light sits this far past the latch side of the front door.
DOOR_LIGHT_OFFSET_FT = 1.25
# Columns closer than this are one post, not a bay.
MIN_BAY_FT = 4.0

PORCH_LIGHT_NOTE = "Porch ceiling light"


def features_request(rooms_data) -> str | None:
    """The room list for the features pass, or None if no room needs it."""
    lines = []
    for rd in rooms_data:
        if rd.bbox_x1 is None or rd.room_type not in ("kitchen", "porch", "master_bedroom"):
            continue
        lines.append(
            f"{rd.room_type}: {rd.name}  box x1={rd.bbox_x1:.3f}, y1={rd.bbox_y1:.3f}, "
            f"x2={rd.bbox_x2:.3f}, y2={rd.bbox_y2:.3f}"
        )
    if not any(rd.bbox_x1 is not None for rd in rooms_data):
        return None
    return "Rooms:\n" + ("\n".join(lines) or "(no kitchen, porch or primary bedroom)")


def parse_features(raw: str | None) -> dict:
    if not raw:
        return {}
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Features reply was not JSON: %s", text[:300])
        return {}
    return data if isinstance(data, dict) else {}


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _box(rd):
    return rd.bbox_x1, rd.bbox_y1, rd.bbox_x2, rd.bbox_y2


def _number(v):
    if isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if math.isfinite(n) else None


def _point(value, box, slack=_SLACK):
    """A point inside ``box`` (with slack), or None."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    x, y = (_number(v) for v in value)
    if x is None or y is None:
        return None
    x1, y1, x2, y2 = box
    if not (x1 - slack <= x <= x2 + slack and y1 - slack <= y <= y2 + slack):
        return None
    return x, y


# An island in an open plan often runs past the line the kitchen was split
# from the living room on (Hatteras's runs 2 ft into the living room's box).
_ISLAND_SLACK = 0.08


def _rect(value, box):
    """A rectangle whose middle is inside ``box`` and which stays near it."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    a = _point(value[:2], box, _ISLAND_SLACK)
    b = _point(value[2:], box, _ISLAND_SLACK)
    if a is None or b is None:
        return None
    if _point(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), box, 0.0) is None:
        return None
    return min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])


def page_scale(rooms_data) -> tuple[float, float] | None:
    """Feet per page width and per page height, from the measured rooms."""
    across, down = [], []
    for rd in rooms_data:
        if None in _box(rd) or not rd.width_ft or not rd.length_ft:
            continue
        if rd.room_type in ("porch", "patio", "deck", "exterior_door"):
            continue
        w = rd.bbox_x2 - rd.bbox_x1
        h = rd.bbox_y2 - rd.bbox_y1
        if w > 0.01 and h > 0.01:
            across.append(rd.width_ft / w)
            down.append(rd.length_ft / h)
    if not across:
        return None
    return median(across), median(down)


def _inside(box, x, y, margin_x=0.0, margin_y=0.0):
    x1, y1, x2, y2 = box
    lo_x, hi_x = x1 + margin_x, x2 - margin_x
    lo_y, hi_y = y1 + margin_y, y2 - margin_y
    if lo_x > hi_x:
        lo_x = hi_x = (x1 + x2) / 2
    if lo_y > hi_y:
        lo_y = hi_y = (y1 + y2) / 2
    return max(lo_x, min(hi_x, x)), max(lo_y, min(hi_y, y))


def _general_can(fa) -> bool:
    return (
        fa.fixture_type == "recessed"
        and not fa.is_prewire
        and "wet location" not in (fa.notes or "").lower()
        and PORCH_LIGHT_NOTE.lower() not in (fa.notes or "").lower()
    )


def _named(rooms_data, data, key, room_type):
    """The room a feature block is about: the name it gives, else the only room of the type."""
    block = data.get(key)
    if not isinstance(block, dict):
        return None, None
    rooms = [rd for rd in rooms_data if rd.room_type == room_type and None not in _box(rd)]
    name = str(block.get("room_name") or "").strip().lower()
    for rd in rooms:
        if rd.name.strip().lower() == name:
            return rd, block
    if len(rooms) == 1:
        return rooms[0], block
    return None, None


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------

def _kitchen(rd, block, fixtures, positions, fx, fy):
    box = _box(rd)
    margin_x, margin_y = 1.0 / fx, 1.0 / fy   # a foot off the walls
    island = _rect(block.get("island"), box)
    if island:
        w_ft = (island[2] - island[0]) * fx
        h_ft = (island[3] - island[1]) * fy
        if not (1.5 <= min(w_ft, h_ft) and max(w_ft, h_ft) <= 14):
            island = None

    # Pendants: evenly along the island's long axis, on its centerline.
    if island:
        pendants = [i for i, fa in enumerate(fixtures) if fa.fixture_type == "pendant"]
        n = len(pendants)
        ix1, iy1, ix2, iy2 = island
        wide = (ix2 - ix1) * fx >= (iy2 - iy1) * fy
        for k, i in enumerate(pendants):
            t = (k + 0.5) / n
            positions[i] = (
                (ix1 + t * (ix2 - ix1), (iy1 + iy2) / 2) if wide
                else ((ix1 + ix2) / 2, iy1 + t * (iy2 - iy1))
            )

        # Cans: none over the island or on its edge.  Push a can that is
        # out past the nearer long side, into the aisle.
        cx, cy = ISLAND_CLEARANCE_FT / fx, ISLAND_CLEARANCE_FT / fy
        for i, fa in enumerate(fixtures):
            if not _general_can(fa):
                continue
            x, y = positions[i]
            if not (ix1 - cx < x < ix2 + cx and iy1 - cy < y < iy2 + cy):
                continue
            if wide:
                up, down = iy1 - cy, iy2 + cy
                y = up if abs(y - up) <= abs(y - down) else down
            else:
                left, right = ix1 - cx, ix2 + cx
                x = left if abs(x - left) <= abs(x - right) else right
            positions[i] = _inside(box, x, y, margin_x, margin_y)

    # A can centered on the sink.
    sink = _point(block.get("sink"), box)
    if sink:
        cans = [i for i, fa in enumerate(fixtures) if _general_can(fa)]
        def feet(i):
            x, y = positions[i]
            return math.hypot((x - sink[0]) * fx, (y - sink[1]) * fy)
        nearest = min(cans, key=feet, default=None)
        if nearest is not None and feet(nearest) <= SINK_REACH_FT:
            positions[nearest] = sink
            fixtures[nearest] = fixtures[nearest].model_copy(
                update={"notes": "Centered on the sink"})
        elif nearest is not None:
            fixtures.append(fixtures[nearest].model_copy(update={"notes": "Centered on the sink"}))
            positions.append(sink)

    # Under-cabinet: one strip per run of upper cabinets.
    strips = [i for i, fa in enumerate(fixtures) if fa.fixture_type == "under_cabinet"]
    runs = []
    for value in block.get("cabinet_runs") or []:
        line = value if isinstance(value, (list, tuple)) and len(value) == 4 else None
        a = _point(line[:2], box) if line else None
        b = _point(line[2:], box) if line else None
        if a is None or b is None:
            continue
        length = math.hypot((b[0] - a[0]) * fx, (b[1] - a[1]) * fy)
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if length < 2:
            continue
        if island and island[0] <= mid[0] <= island[2] and island[1] <= mid[1] <= island[3]:
            continue
        runs.append((mid, length))
    if strips and runs:
        template = fixtures[strips[0]]
        keep = [i for i in range(len(fixtures)) if i not in strips]
        fixtures[:] = [fixtures[i] for i in keep]
        positions[:] = [positions[i] for i in keep]
        for mid, length in runs:
            fixtures.append(template.model_copy(update={
                "notes": f"Under-cabinet LED under the uppers, about {round(length)} ft run"}))
            positions.append(mid)


def _porch(rd, block, fixtures, positions, fx, fy):
    box = _box(rd)
    x1, y1, x2, y2 = box
    wide = (x2 - x1) * fx >= (y2 - y1) * fy

    # Ceiling lights centered on each bay between columns.
    columns = [p for p in (_point(v, box) for v in block.get("columns") or []) if p]
    lights = [i for i, fa in enumerate(fixtures)
              if PORCH_LIGHT_NOTE.lower() in (fa.notes or "").lower()]
    if lights and len(columns) >= 2:
        along = sorted(p[0] if wide else p[1] for p in columns)
        unit = fx if wide else fy
        bays = [(a, b) for a, b in zip(along, along[1:]) if (b - a) * unit >= MIN_BAY_FT]
        if bays:
            template = fixtures[lights[0]]
            keep = [i for i in range(len(fixtures)) if i not in lights]
            fixtures[:] = [fixtures[i] for i in keep]
            positions[:] = [positions[i] for i in keep]
            middle = (y1 + y2) / 2 if wide else (x1 + x2) / 2
            for a, b in bays:
                c = (a + b) / 2
                fixtures.append(template.model_copy(update={
                    "notes": f"{PORCH_LIGHT_NOTE}, centered on the bay between columns"}))
                positions.append((c, middle) if wide else (middle, c))

    # The door light beside the front door, past its latch side.
    door = block.get("front_door")
    if isinstance(door, dict):
        hinge = _point(door.get("hinge_end"), box)
        latch = _point(door.get("latch_end"), box)
        entry = [i for i, fa in enumerate(fixtures) if fa.fixture_type == "coach_light"]
        if hinge and latch and entry:
            dx, dy = (latch[0] - hinge[0]) * fx, (latch[1] - hinge[1]) * fy
            span = math.hypot(dx, dy)
            if span >= 1.5:
                ux, uy = dx / span, dy / span
                x = latch[0] + ux * DOOR_LIGHT_OFFSET_FT / fx
                y = latch[1] + uy * DOOR_LIGHT_OFFSET_FT / fy
                positions[entry[0]] = _inside(box, x, y, 0.3 / fx, 0.3 / fy)
                fixtures[entry[0]] = fixtures[entry[0]].model_copy(update={
                    "notes": "Entry light on the wall beside the front door, latch side"})


def _primary(rd, block, fixtures, positions, fx, fy):
    box = _box(rd)
    x1, y1, x2, y2 = box
    wall = str(block.get("headboard_wall") or "").strip().lower()
    center = _point(block.get("bed_center"), box)
    if wall not in ("top", "bottom", "left", "right") or center is None:
        return

    # "along" runs down the headboard wall, "out" runs from it into the room.
    vertical_wall = wall in ("left", "right")
    c = center[1] if vertical_wall else center[0]
    a_unit, o_unit = (fy, fx) if vertical_wall else (fx, fy)
    wall_at = {"left": x1, "right": x2, "top": y1, "bottom": y2}[wall]
    sign = 1 if wall in ("left", "top") else -1      # direction into the room

    def to_xy(along, out):
        return (out, along) if vertical_wall else (along, out)

    half_bed = BED_WIDTH_FT / 2 / a_unit
    room_mid_out = (x1 + x2) / 2 if vertical_wall else (y1 + y2) / 2

    for i, fa in enumerate(fixtures):
        if fa.fixture_type == "ceiling_fan":
            positions[i] = to_xy(c, room_mid_out)
            fixtures[i] = fa.model_copy(update={"notes": "Centered on the bed"})

    # Cans in two lines flanking the bed, over the nightstands and the walk
    # space beside it, rows spread from the headboard wall to the far wall.
    # Nothing over the bed itself, where a can shines in someone's eyes.
    cans = [i for i, fa in enumerate(fixtures) if _general_can(fa)]
    if len(cans) >= 2:
        lo_a, hi_a = (y1, y2) if vertical_wall else (x1, x2)
        margin_a = 1.5 / a_unit
        flank = half_bed + NIGHTSTAND_FT / a_unit
        sides = [max(lo_a + margin_a, c - flank), min(hi_a - margin_a, c + flank)]
        rows = math.ceil(len(cans) / 2)
        far = wall_at + sign * ((x2 - x1) if vertical_wall else (y2 - y1))
        for k, i in enumerate(cans):
            row, side = divmod(k, 2)
            t = (row + 0.5) / rows
            out = wall_at + (far - wall_at) * t
            positions[i] = to_xy(sides[side], out)

    outlets = [i for i, fa in enumerate(fixtures) if fa.fixture_type == "switched_outlet"]
    beside = half_bed + 1.0 / a_unit
    off_wall = wall_at + sign * 0.5 / o_unit
    for k, i in enumerate(outlets[:2]):
        side = -1 if k == 0 else 1
        positions[i] = _inside(box, *to_xy(c + side * beside, off_wall), 0.2 / fx, 0.2 / fy)
        fixtures[i] = fixtures[i].model_copy(update={
            "notes": "Switched outlet for bedside lamp, beside the headboard"})


def apply_features(rooms_data, fixtures_by_room, plan_positions, data):
    """Lay out kitchen, porch and primary bedroom fixtures around what is drawn.

    Returns new ``(fixtures_by_room, plan_positions)``; the inputs are not
    changed.  Rooms without readable features are passed through.
    """
    if not data:
        return fixtures_by_room, plan_positions
    scale = page_scale(rooms_data)
    if scale is None:
        return fixtures_by_room, plan_positions
    fx, fy = scale

    fixtures_by_room = {k: list(v) for k, v in fixtures_by_room.items()}
    plan_positions = {k: list(v) for k, v in plan_positions.items()}
    for key, room_type, apply in (
        ("kitchen", "kitchen", _kitchen),
        ("porch", "porch", _porch),
        ("primary_bedroom", "master_bedroom", _primary),
    ):
        rd, block = _named(rooms_data, data, key, room_type)
        if rd is None or rd.name not in fixtures_by_room:
            continue
        fixtures = list(fixtures_by_room[rd.name])
        positions = list(plan_positions.get(rd.name, []))
        if len(positions) < len(fixtures):
            continue
        try:
            apply(rd, block, fixtures, positions, fx, fy)
        except Exception as e:  # noqa: BLE001 — a bad read must not lose the plan
            logger.warning("Could not lay out %s around its features: %s", rd.name, e)
            continue
        fixtures_by_room[rd.name] = fixtures
        plan_positions[rd.name] = positions
        logger.info("Laid out %s around what is drawn in it", rd.name)
    _front_door_keypad(rooms_data, fixtures_by_room, plan_positions, data, fx, fy)
    return fixtures_by_room, plan_positions


# The Welcome keypad sits this far past the latch side of the front door,
# and this far in from the wall, inside the house.
KEYPAD_PAST_LATCH_FT = 0.75
KEYPAD_OFF_WALL_FT = 0.5


def _front_door_keypad(rooms_data, fixtures_by_room, plan_positions, data, fx, fy):
    """The front-door keypad on the latch side, where the hand goes for it.

    Hatteras, 7 Nov 2026: on two of five runs the Welcome keypad was on the
    hinge side of the front door, behind the door once it is open.  The
    porch read already says which end of the opening is the latch.
    """
    porch, block = _named(rooms_data, data, "porch", "porch")
    door = block.get("front_door") if block else None
    if not isinstance(door, dict):
        return
    box = _box(porch)
    hinge = _point(door.get("hinge_end"), box)
    latch = _point(door.get("latch_end"), box)
    if not (hinge and latch):
        return
    ux, uy = (latch[0] - hinge[0]) * fx, (latch[1] - hinge[1]) * fy
    span = math.hypot(ux, uy)
    if span < 1.5:
        return
    ux, uy = ux / span, uy / span
    # Into the house: the side of the wall away from the porch.
    nx, ny = -uy, ux
    pcx, pcy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    if nx * (pcx - latch[0]) * fx + ny * (pcy - latch[1]) * fy > 0:
        nx, ny = -nx, -ny
    x = latch[0] + (ux * KEYPAD_PAST_LATCH_FT + nx * KEYPAD_OFF_WALL_FT) / fx
    y = latch[1] + (uy * KEYPAD_PAST_LATCH_FT + ny * KEYPAD_OFF_WALL_FT) / fy
    for name, fixtures in fixtures_by_room.items():
        for i, fa in enumerate(fixtures):
            if fa.fixture_type == "keypad" and "front door" in (fa.notes or "").lower():
                positions = plan_positions.get(name, [])
                if i < len(positions):
                    positions[i] = (x, y)
                    logger.info("Put the %s front-door keypad on the latch side", name)
                return


# ---------------------------------------------------------------------------
# Closets the room read missed
# ---------------------------------------------------------------------------

# A closet is this big, in feet: a 2 x 2 linen closet up to a deep pantry.
CLOSET_MIN_SIDE_FT = 1.5
CLOSET_MAX_SIDE_FT = 12.0
CLOSET_MIN_AREA = 3.0
CLOSET_MAX_AREA = 60.0
# A room no bigger than this that covers most of a reported closet is it.
_SMALL_ROOM_SQFT = 80.0


def _overlap(a, b) -> float:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


def add_missed_closets(rooms_data, fixtures_by_room, plan_positions, data, tier,
                       ceiling_ft=None):
    """Add closets the features pass saw and the room read did not.

    Camden at 960 px, 7 Nov 2026: two runs in a row came back without its
    two coat closets and two linen closets, so none got a light.  They sit
    inside the foyer's, mudroom's and primary bath's boxes, so no open space
    shows them; the features pass is asked to list every closet instead.
    Returns new ``(rooms_data, fixtures_by_room, plan_positions)``.
    """
    from app.services.lighting_engine import LightingEngine
    from app.services.placement import compute_plan_positions

    reported = data.get("closets") if isinstance(data, dict) else None
    scale = page_scale(rooms_data)
    if not isinstance(reported, list) or scale is None:
        return rooms_data, fixtures_by_room, plan_positions
    fx, fy = scale
    indoor = [_box(rd) for rd in rooms_data
              if None not in _box(rd) and rd.room_type not in
              ("porch", "patio", "deck", "garage", "exterior", "exterior_door")]
    if not indoor:
        return rooms_data, fixtures_by_room, plan_positions
    house = (min(b[0] for b in indoor), min(b[1] for b in indoor),
             max(b[2] for b in indoor), max(b[3] for b in indoor))
    def sqft(rd):
        if rd.sqft:
            return rd.sqft
        return rd.width_ft * rd.length_ft if rd.width_ft and rd.length_ft else math.inf

    small = [_box(rd) for rd in rooms_data
             if None not in _box(rd) and sqft(rd) <= _SMALL_ROOM_SQFT]

    names = {rd.name for rd in rooms_data}
    added = []
    for item in reported:
        if not isinstance(item, dict):
            continue
        box = _rect(item.get("box"), house)
        if box is None:
            continue
        w_ft, h_ft = (box[2] - box[0]) * fx, (box[3] - box[1]) * fy
        area = w_ft * h_ft
        if not (CLOSET_MIN_SIDE_FT <= min(w_ft, h_ft) and max(w_ft, h_ft) <= CLOSET_MAX_SIDE_FT
                and CLOSET_MIN_AREA <= area <= CLOSET_MAX_AREA):
            continue
        mine = (box[2] - box[0]) * (box[3] - box[1])
        if any(_overlap(box, b) >= 0.5 * min(mine, (b[2] - b[0]) * (b[3] - b[1]))
               for b in small + [_box(r) for r in added]):
            continue
        raw_name = str(item.get("name") or "Closet").strip() or "Closet"
        name, n = raw_name, 2
        while name in names:
            name, n = f"{raw_name} {n}", n + 1
        names.add(name)
        added.append(rooms_data[0].model_copy(update={
            "name": name,
            "room_type": "pantry" if "pantry" in raw_name.lower() else "closet",
            "labeled": True,
            "position_x": (box[0] + box[2]) / 2, "position_y": (box[1] + box[3]) / 2,
            "bbox_x1": box[0], "bbox_y1": box[1], "bbox_x2": box[2], "bbox_y2": box[3],
            "width_ft": round(w_ft, 1), "length_ft": round(h_ft, 1), "sqft": round(area),
            "ceiling_height_ft": ceiling_ft or rooms_data[0].ceiling_height_ft,
        }))
    if not added:
        return rooms_data, fixtures_by_room, plan_positions

    new_fixtures = LightingEngine().process_rooms(added, tier)
    new_positions = compute_plan_positions(added, new_fixtures)
    logger.info("Added closets the room read missed: %s", [r.name for r in added])
    return (
        list(rooms_data) + added,
        {**fixtures_by_room, **new_fixtures},
        {**plan_positions, **new_positions},
    )
