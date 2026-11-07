"""Untangle room boxes the plan reader drew on top of one another.

The model often hands back a box per room that swallows its neighbours.
On Morgan's Keel plan (Nov 2026):

* Kitchen, Dining and Living all shared one box's left, right and top
  edges; Dining's ran from the back wall to the front wall.  Every room's
  cans landed on top of the others', the living room stopped 13 ft short
  of the front wall, and its fan hung 5 ft off centre.
* Each secondary bedroom's box took in its closet, so the row of cans
  nearest the closet sat on the closet wall and the fan sat a foot off.
* The primary bedroom's box took in the walk-in closet and the primary
  bath.

Two passes put that right before rooms are measured:

1. ``split_open_plan``: open-plan rooms (kitchen, dining, living ...)
   whose boxes mostly overlap are one open area.  It is cut into one zone
   per room, using where each room's name is printed: the name sits near
   the middle of its zone.
2. ``carve_enclosed``: a closet, bath, laundry or other enclosed space
   lying along one side of a bigger room's box is cut out of it, moving
   that side of the bigger box to the enclosed room's far wall.

Both work on box coordinates only (fractions of the page) and leave a
room alone whenever the cut would push its printed name outside it.
"""

from __future__ import annotations

import logging
import math
import re

logger = logging.getLogger(__name__)

OPEN_PLAN_TYPES = {
    "kitchen", "dining", "living", "family", "great_room", "foyer", "entry",
}

ENCLOSED_TYPES = {
    "closet", "walk_in_closet", "pantry", "bathroom", "master_bathroom",
    "half_bath", "powder_room", "laundry", "mudroom", "hallway",
}

# Two open-plan boxes are one open area when this much of the smaller
# lies inside the larger.  Low on purpose: on one Hatteras run the kitchen
# and dining boxes overlapped by half, were left apart, and both lit the
# same corner (the dining box also ran out through the back wall).
SAME_AREA = 0.1

# An enclosed room counts as inside a bigger one when this much of it is.
INSIDE = 0.6

# ...and is carved out when the enclosed rooms along one side cover at
# least this much of that side.
SIDE_COVERED = 0.5

# How close (fraction of the page) an edge must be to count as touching.
TOUCH = 0.02

# A cut never leaves a room less than this share of its original size
# along the cut axis.
MIN_KEPT = 0.35

# A name this close to a zone edge is not inside it for our purposes.
LABEL_MARGIN = 0.01


def _box(room):
    if None in (room.bbox_x1, room.bbox_y1, room.bbox_x2, room.bbox_y2):
        return None
    return (room.bbox_x1, room.bbox_y1, room.bbox_x2, room.bbox_y2)


def _area(box) -> float:
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def _overlap(a, b) -> float:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def _label(room):
    if room.position_x is None or room.position_y is None:
        return None
    return (room.position_x, room.position_y)


def _with_box(room, box):
    return room.model_copy(
        update={"bbox_x1": box[0], "bbox_y1": box[1], "bbox_x2": box[2], "bbox_y2": box[3]}
    )


# ---------------------------------------------------------------------------
# 1. Open-plan areas
# ---------------------------------------------------------------------------

OUTDOOR_TYPES = {"porch", "patio", "garage", "exterior", "deck", "exterior_door"}

# Exterior doors are points on the outside wall, read so each can get its
# light; they take no part in reshaping rooms.
DOOR_TYPES = {"exterior_door"}


def _house_edges(rooms) -> dict[str, float]:
    """The house's outside walls, where the other rooms say they are.

    An outside wall is an extreme edge that two or more rooms (other than
    open-plan and outdoor ones) share: Hatteras's back wall is the top of
    Bedroom 3, the pantry and the laundry.  One room alone is not enough to
    call a wall.
    """
    boxes = [
        _box(r) for r in rooms
        if _box(r) and r.room_type not in OPEN_PLAN_TYPES | OUTDOOR_TYPES
    ]
    edges = {}
    for side, index, pick in (
        ("left", 0, min), ("top", 1, min), ("right", 2, max), ("bottom", 3, max),
    ):
        if len(boxes) < 2:
            break
        extreme = pick(b[index] for b in boxes)
        if sum(abs(b[index] - extreme) <= TOUCH for b in boxes) >= 2:
            edges[side] = extreme
    return edges


def _fit_to_house(area, rooms, group) -> tuple:
    """Pull an open area's edges onto the house's outside walls.

    The model's boxes for an open plan are often wrong at the ends: on one
    Hatteras run the kitchen's ran above the back wall and the living room's
    stopped 6 ft short of the front.  An edge past an outside wall comes back
    to it; an edge short of one goes out to it, when no other room is in the
    way.
    """
    edges = _house_edges(rooms)
    others = [
        _box(r) for i, r in enumerate(rooms)
        if i not in group and _box(r) and r.room_type not in OUTDOOR_TYPES
    ]
    x1, y1, x2, y2 = area
    for side, wall in edges.items():
        if side == "top":
            strip = (x1, min(y1, wall), x2, max(y1, wall))
        elif side == "bottom":
            strip = (x1, min(y2, wall), x2, max(y2, wall))
        elif side == "left":
            strip = (min(x1, wall), y1, max(x1, wall), y2)
        else:
            strip = (min(x2, wall), y1, max(x2, wall), y2)
        beyond = {
            "top": y1 < wall, "bottom": y2 > wall,
            "left": x1 < wall, "right": x2 > wall,
        }[side]
        if not beyond and any(_overlap(strip, o) > 0.1 * _area(o) for o in others):
            continue  # a room sits between the area and the wall
        if side == "top":
            y1 = wall
        elif side == "bottom":
            y2 = wall
        elif side == "left":
            x1 = wall
        else:
            x2 = wall
    return (x1, y1, x2, y2)


def _open_plan_groups(rooms) -> list[list[int]]:
    """Indices of open-plan rooms that share one open area, two or more each."""
    idx = [
        i for i, r in enumerate(rooms)
        if r.room_type in OPEN_PLAN_TYPES and _box(r) and _label(r)
    ]
    parent = {i: i for i in idx}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a_pos, a in enumerate(idx):
        for b in idx[a_pos + 1:]:
            ba, bb = _box(rooms[a]), _box(rooms[b])
            smaller = min(_area(ba), _area(bb))
            if smaller > 0 and _overlap(ba, bb) / smaller >= SAME_AREA:
                parent[find(a)] = find(b)

    groups: dict[int, list[int]] = {}
    for i in idx:
        groups.setdefault(find(i), []).append(i)
    return [g for g in groups.values() if len(g) > 1]


def _partition(
    area, labels: dict[int, tuple[float, float]], aspect: float = 1.0
) -> dict[int, tuple] | None:
    """Cut ``area`` into one box per label, each name near its zone's middle.

    Cuts are straight lines, chosen recursively at the widest gap between
    names.  Gaps are compared in real distance (``aspect`` is the page's
    width over its height) against the area's longer side, so a wide area
    with names side by side is cut down the middle rather than across.
    Returns None if two names are too close together to separate.
    """
    if len(labels) == 1:
        (i,) = labels
        return {i: area}

    x1, y1, x2, y2 = area
    scale = (aspect, 1.0)
    longest = max((x2 - x1) * aspect, (y2 - y1))
    if longest <= 0:
        return None
    best = None
    for axis, lo, hi in ((0, x1, x2), (1, y1, y2)):
        if hi <= lo:
            continue
        ordered = sorted(labels.items(), key=lambda kv: kv[1][axis])
        for k in range(1, len(ordered)):
            gap = (ordered[k][1][axis] - ordered[k - 1][1][axis]) * scale[axis]
            if best is None or gap / longest > best[0]:
                best = (gap / longest, axis, ordered[:k], ordered[k:], lo, hi)
    if best is None or best[0] < 0.05:
        return None

    _, axis, before, after, lo, hi = best
    # Each name is taken to be at the middle of its zone; each implies a cut.
    estimates = [2 * p[axis] - lo for _, p in before] + [2 * p[axis] - hi for _, p in after]
    cut = sum(estimates) / len(estimates)
    floor = max(p[axis] for _, p in before) + LABEL_MARGIN
    ceil = min(p[axis] for _, p in after) - LABEL_MARGIN
    cut = min(max(cut, floor), ceil)

    if axis == 0:
        first, second = (x1, y1, cut, y2), (cut, y1, x2, y2)
    else:
        first, second = (x1, y1, x2, cut), (x1, cut, x2, y2)
    a = _partition(first, dict(before), aspect)
    b = _partition(second, dict(after), aspect)
    if a is None or b is None:
        return None
    return {**a, **b}


def split_open_plan(rooms, aspect: float = 1.0) -> list:
    rooms = list(rooms)
    for group in _open_plan_groups(rooms):
        boxes = [_box(rooms[i]) for i in group]
        area = (
            min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes),
        )
        area = _fit_to_house(area, rooms, set(group))
        labels = {i: _label(rooms[i]) for i in group}
        zones = _partition(area, labels, aspect)
        if zones is None:
            logger.info(
                "Open plan: could not separate %s by their labels; left as read",
                ", ".join(rooms[i].name for i in group),
            )
            continue
        for i, zone in zones.items():
            rooms[i] = _with_box(rooms[i], zone)
        logger.info(
            "Open plan: split one area into %s",
            ", ".join(
                f"{rooms[i].name} {tuple(round(v, 3) for v in zones[i])}" for i in group
            ),
        )
    return rooms


# ---------------------------------------------------------------------------
# 2. Enclosed spaces inside a bigger room's box
# ---------------------------------------------------------------------------

_SIDES = ("top", "bottom", "left", "right")
_INDEX = {"left": 0, "top": 1, "right": 2, "bottom": 3}


def _covered(intervals, lo, hi) -> float:
    """Share of [lo, hi] covered by the union of ``intervals``."""
    spans = sorted((max(a, lo), min(b, hi)) for a, b in intervals if b > lo and a < hi)
    total, end = 0.0, lo
    for a, b in spans:
        a = max(a, end)
        if b > a:
            total += b - a
            end = b
    return total / max(hi - lo, 1e-9)


def _near_far(side, box):
    """A box's edge nearest ``side`` of its parent, and the edge opposite."""
    x1, y1, x2, y2 = box
    return {
        "top": (y1, y2), "bottom": (-y2, -y1),
        "left": (x1, x2), "right": (-x2, -x1),
    }[side]


def _band_cut(side, pbox, children):
    """Where to cut ``pbox`` to take out the band of enclosed rooms along
    ``side``, and how much of that side the band covers.

    The band starts with the rooms lying against the side and takes in any
    other room that starts inside it: on the Hatteras plan the walk-in sits
    against the primary bedroom's top wall, and the shower and primary bath
    beside it start a little lower but inside the same band.
    """
    edge = _near_far(side, pbox)[0]
    # Against the side, or straddling it: a box drawn a foot past the
    # bedroom's real wall takes in the bottom of the walk-in and bath.
    band = [
        c for c in children
        if _near_far(side, c)[0] <= edge + TOUCH and _near_far(side, c)[1] > edge
    ]
    if not band:
        return None
    while True:
        cut = max(_near_far(side, c)[1] for c in band)
        more = [
            c for c in children
            if c not in band and _near_far(side, c)[0] < cut and _near_far(side, c)[1] > edge
        ]
        if not more:
            break
        band += more
    if side in ("top", "bottom"):
        share = _covered([(c[0], c[2]) for c in band], pbox[0], pbox[2])
    else:
        share = _covered([(c[1], c[3]) for c in band], pbox[1], pbox[3])
    return (cut if side in ("top", "left") else -cut), share, band


def carve_enclosed(rooms) -> list:
    rooms = list(rooms)
    for p, parent in enumerate(rooms):
        pbox = _box(parent)
        plabel = _label(parent)
        if not pbox or parent.room_type in ENCLOSED_TYPES:
            continue

        box = pbox
        for _ in range(len(_SIDES)):
            # Enclosed rooms mostly inside this box, or overlapping one of
            # its edges.
            inside = {
                c: _box(child) for c, child in enumerate(rooms)
                if c != p and _box(child) and child.room_type in ENCLOSED_TYPES
                and _area(_box(child)) < _area(box)
                and _overlap(box, _box(child)) > 0.0
            }
            if not inside:
                break
            best = None
            for side in _SIDES:
                found = _band_cut(side, box, list(inside.values()))
                if not found:
                    continue
                cut, share, band = found
                trial = list(box)
                trial[_INDEX[side]] = cut
                full = (box[3] - box[1]) if side in ("top", "bottom") else (box[2] - box[0])
                kept = (trial[3] - trial[1]) if side in ("top", "bottom") else (trial[2] - trial[0])
                if share < SIDE_COVERED or kept < MIN_KEPT * full:
                    continue
                if plabel and not (
                    trial[0] < plabel[0] < trial[2] and trial[1] < plabel[1] < trial[3]
                ):
                    continue
                if best is None or share > best[0]:
                    best = (share, side, tuple(trial), band)
            if best is None:
                break
            _, side, box, band = best
            logger.info(
                "Carved %s out of the %s of %s's box",
                " + ".join(rooms[c].name for c, b in inside.items() if b in band),
                side, parent.name,
            )
        if box != pbox:
            rooms[p] = _with_box(parent, box)
    return rooms


# Labels printed on fixtures inside a bath, which the model sometimes reads
# as rooms of their own.
_FIXTURE_LABEL = re.compile(r"^(shr|shwr|shower|tub|bathtub|bath tub|tub/shower|shower/tub)$")
_BATH_TYPES = {"bathroom", "master_bathroom", "half_bath", "powder_room"}


def _beside(box, other) -> bool:
    """Whether ``box`` lies right against one side of ``other`` and mostly
    along it: within TOUCH of its edge, and overlapping half its own span on
    the other axis."""
    x_span = min(box[2], other[2]) - max(box[0], other[0])
    y_span = min(box[3], other[3]) - max(box[1], other[1])
    x_gap = max(other[0] - box[2], box[0] - other[2])
    y_gap = max(other[1] - box[3], box[1] - other[3])
    return (
        (y_gap <= TOUCH and x_span >= 0.5 * (box[2] - box[0]))
        or (x_gap <= TOUCH and y_span >= 0.5 * (box[3] - box[1]))
    )


def drop_fixture_labels(rooms) -> list:
    """Fold a "room" that is a shower or tub into the bath it belongs to.

    Hatteras prints SHR on the primary bath's shower; one run read it as a
    bathroom of its own, which got its own vanity light and exhaust fan
    inside the shower.  When such a label sits inside a bath's box, or right
    against it, it is dropped and the bath's box grown to take it in: the
    bath already puts its wet-rated can in the shower.
    """
    rooms = list(rooms)

    def is_label(r):
        return bool(_FIXTURE_LABEL.match((r.name or "").strip().lower()))

    drop = set()
    for i, r in enumerate(rooms):
        box = _box(r)
        if not box or not is_label(r):
            continue
        for j, bath in enumerate(rooms):
            bbox = _box(bath)
            if j == i or j in drop or not bbox or bath.room_type not in _BATH_TYPES or is_label(bath):
                continue
            if _overlap(box, bbox) >= 0.5 * _area(box) or _beside(box, bbox):
                rooms[j] = _with_box(bath, (
                    min(bbox[0], box[0]), min(bbox[1], box[1]),
                    max(bbox[2], box[2]), max(bbox[3], box[3]),
                ))
                drop.add(i)
                logger.info("Folded %s into %s: a fixture label, not a room", r.name, bath.name)
                break
    return [r for i, r in enumerate(rooms) if i not in drop]


def clip_to_outdoor(rooms) -> list:
    """Stop an indoor room's box at the porch it runs onto.

    The front porch's inside edge is the house's front wall.  On one
    Hatteras run the primary bedroom's box ran a foot onto the porch: two of
    its cans landed outdoors, and the front wall could not be found for the
    living room, which stopped halfway.
    """
    outdoor = [
        _box(r) for r in rooms if _box(r) and r.room_type in OUTDOOR_TYPES
    ]
    out = []
    for r in rooms:
        box = _box(r)
        label = _label(r)
        if not box or r.room_type in OUTDOOR_TYPES or not label:
            out.append(r)
            continue
        x1, y1, x2, y2 = box
        for ox1, oy1, ox2, oy2 in outdoor:
            if min(x2, ox2) <= max(x1, ox1) or min(y2, oy2) <= max(y1, oy1):
                continue  # no overlap
            if y1 < oy1 < y2 and label[1] < oy1:      # porch below the room
                y2 = oy1
            elif y1 < oy2 < y2 and label[1] > oy2:    # porch above
                y1 = oy2
            elif x1 < ox1 < x2 and label[0] < ox1:    # porch to the right
                x2 = ox1
            elif x1 < ox2 < x2 and label[0] > ox2:    # porch to the left
                x1 = ox2
        if (x1, y1, x2, y2) != box:
            logger.info("Stopped %s at the porch", r.name)
            r = _with_box(r, (x1, y1, x2, y2))
        out.append(r)
    return out


def fit_outdoor(rooms, aspect: float = 1.0) -> list:
    """Keep a porch or patio no wider than the house wall it runs along,
    and no deeper than its printed size says.

    Hatteras's front porch came back spanning the whole sheet and twice as
    deep as its printed 7 ft, and its landscape pre-wires, placed at the
    porch's ends, landed off the page and then out past the porch steps.
    """
    edges = _house_edges(rooms)
    indoor = [
        _box(r) for r in rooms
        if _box(r) and r.room_type not in OUTDOOR_TYPES
    ]
    if not indoor:
        return list(rooms)
    top = min(b[1] for b in indoor)
    bottom = max(b[3] for b in indoor)
    left = min(b[0] for b in indoor)
    right = max(b[2] for b in indoor)
    out = []
    for r in rooms:
        box = _box(r)
        if not box or r.room_type not in OUTDOOR_TYPES:
            out.append(r)
            continue
        x1, y1, x2, y2 = box
        # The porch's printed depth over its printed length, if both read.
        sizes = sorted(v for v in (r.width_ft, r.length_ft) if v)
        ratio = sizes[0] / sizes[1] if len(sizes) == 2 and sizes[1] > 0 else None
        if y1 >= bottom - TOUCH or y2 <= top + TOUCH:      # front or back
            x1 = max(x1, edges.get("left", left))
            x2 = min(x2, edges.get("right", right))
            if ratio:
                depth = ratio * (x2 - x1) * aspect   # in fractions of height
                if y1 >= bottom - TOUCH:                  # front: deep downwards
                    y2 = min(y2, y1 + depth)
                else:                                     # back: deep upwards
                    y1 = max(y1, y2 - depth)
        elif x1 >= right - TOUCH or x2 <= left + TOUCH:    # a side
            y1 = max(y1, edges.get("top", top))
            y2 = min(y2, edges.get("bottom", bottom))
            if ratio:
                depth = ratio * (y2 - y1) / aspect   # in fractions of width
                if x1 >= right - TOUCH:
                    x2 = min(x2, x1 + depth)
                else:
                    x1 = max(x1, x2 - depth)
        if (x1, y1, x2, y2) != box and x2 > x1 and y2 > y1:
            logger.info("Kept %s within the house's width and printed depth", r.name)
            r = _with_box(r, (x1, y1, x2, y2))
        out.append(r)
    return out


def drop_porch_doors(doors, rooms) -> list:
    """Keep only the exterior doors a porch or patio does not already light.

    The porch rule puts a coach light at the front door; a door opening
    onto a porch or patio needs no second one.
    """
    outdoor = [
        _box(r) for r in rooms
        if _box(r) and r.room_type in OUTDOOR_TYPES - DOOR_TYPES
    ]
    kept = []
    for d in doors:
        point = _label(d)
        if point and any(
            b[0] - TOUCH <= point[0] <= b[2] + TOUCH and b[1] - TOUCH <= point[1] <= b[3] + TOUCH
            for b in outdoor
        ):
            logger.info("%s opens onto a porch, which already has its light", d.name)
            continue
        kept.append(d)
    return kept


def untangle(rooms, aspect: float = 1.0) -> list:
    """All the passes, open-plan split first: a pantry inside the kitchen's
    zone is judged against the kitchen, not the whole open area.

    ``aspect`` is the page's width over its height, so distances across and
    down the page compare fairly.
    """
    doors = [r for r in rooms if r.room_type in DOOR_TYPES]
    rooms = [r for r in rooms if r.room_type not in DOOR_TYPES]
    rooms = clip_to_outdoor(drop_fixture_labels(rooms))
    rooms = fit_outdoor(carve_enclosed(split_open_plan(rooms, aspect)), aspect)
    return rooms + drop_porch_doors(doors, rooms)


# ---------------------------------------------------------------------------
# 3. Halls nobody named
# ---------------------------------------------------------------------------

# A hall is at least this wide and this long, in feet, and no wider than a
# room would be.  NEC 210.70 wants a switched light in one.
HALL_MIN_WIDTH_FT = 2.5
# Up to 10 ft wide takes in a stair hall or landing: Tybee's upstairs
# landing round the stair is 9.7 x 12.6 ft and got no light at 6.  Stairs
# need a switched light anyway (IRC R303.7).  HALL_MAX_SQFT keeps a room the
# model missed altogether from being read as a hall.
HALL_MAX_WIDTH_FT = 10.0
HALL_MAX_SQFT = 160.0
HALL_MIN_LENGTH_FT = 6.0

# The open space must fill at least this share of its bounding box: an
# L-shaped gap of slivers between rooms is not a hall.
HALL_FILL = 0.5

_GRID = 240


def _open_spaces(rooms, scale: float, page_width: int, page_height: int):
    """Enclosed open space inside the house that no room's box covers.

    Yields ``(box, w_ft, h_ft, fill, area_ft2)`` for each piece: the box in
    page fractions, its size in feet, the share of the box that is open and
    the open area.  Pieces touching the house's outline are outside it.
    """
    indoor = [
        _box(r) for r in rooms
        if _box(r) and r.room_type not in OUTDOOR_TYPES
    ]
    if len(indoor) < 3 or not scale:
        return
    hx1 = min(b[0] for b in indoor)
    hy1 = min(b[1] for b in indoor)
    hx2 = max(b[2] for b in indoor)
    hy2 = max(b[3] for b in indoor)
    if hx2 <= hx1 or hy2 <= hy1:
        return

    cols = _GRID
    rows = max(1, round(_GRID * (hy2 - hy1) * page_height / ((hx2 - hx1) * page_width)))
    cw, ch = (hx2 - hx1) / cols, (hy2 - hy1) / rows

    open_cells = [[True] * cols for _ in range(rows)]
    for b in indoor:
        c1 = max(0, int((b[0] - hx1) / cw))
        c2 = min(cols, int(math.ceil((b[2] - hx1) / cw)))
        r1 = max(0, int((b[1] - hy1) / ch))
        r2 = min(rows, int(math.ceil((b[3] - hy1) / ch)))
        for r in range(r1, r2):
            row = open_cells[r]
            for c in range(c1, c2):
                row[c] = False

    ft_x = page_width * scale   # feet per unit of x fraction
    ft_y = page_height * scale

    # Boxes the model drew a few inches apart leave hairline gaps that would
    # join a hall to the outside of the house.  Open space narrower than
    # about a foot is ignored: shrink the open space by half a foot on every
    # side, trace what is left, and grow each piece back by the same.
    kx = max(1, round(0.5 / (cw * ft_x)))
    ky = max(1, round(0.5 / (ch * ft_y)))
    unshrunk = open_cells
    open_cells = _erode(open_cells, kx, ky)

    seen = [[False] * cols for _ in range(rows)]
    for r0 in range(rows):
        for c0 in range(cols):
            if not open_cells[r0][c0] or seen[r0][c0]:
                continue
            stack, cells = [(r0, c0)], []
            seen[r0][c0] = True
            while stack:
                r, c = stack.pop()
                cells.append((r, c))
                for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                    if 0 <= nr < rows and 0 <= nc < cols and open_cells[nr][nc] and not seen[nr][nc]:
                        seen[nr][nc] = True
                        stack.append((nr, nc))
            # Open space touching the house's outline is outside the house
            # (a notch in an L-shaped plan), not a hall.
            if any(r in (0, rows - 1) or c in (0, cols - 1) for r, c in cells):
                continue
            r1 = max(0, min(r for r, _ in cells) - ky)
            r2 = min(rows, max(r for r, _ in cells) + 1 + ky)
            c1 = max(0, min(c for _, c in cells) - kx)
            c2 = min(cols, max(c for _, c in cells) + 1 + kx)
            box = (hx1 + c1 * cw, hy1 + r1 * ch, hx1 + c2 * cw, hy1 + r2 * ch)
            w_ft, h_ft = (box[2] - box[0]) * ft_x, (box[3] - box[1]) * ft_y
            short, long_ = sorted((w_ft, h_ft))
            # Measured on the open space before it was shrunk.  Shrinking
            # eats the narrow part of a hall that jogs round a room: Hatteras's
            # hall, where Bath 2 sticks into it, measured 0.47 shrunk on one
            # run and 0.53 on the next, and the first got no hall light.
            # Slivers are already gone; what is left of an L is a real hall.
            fill = sum(
                unshrunk[r][c] for r in range(r1, r2) for c in range(c1, c2)
            ) / max(1, (r2 - r1) * (c2 - c1))
            area = sum(
                unshrunk[r][c] for r in range(r1, r2) for c in range(c1, c2)
            ) * cw * ft_x * ch * ft_y
            yield box, w_ft, h_ft, fill, area


# A hallway the model drew with this share of its box under other rooms is
# cut back to the part no room covers.  Catalina's and Bonaire's upstairs
# "Hallway" came back covering 64-70% of the bedrooms around it, which added
# about 400 sq ft and dropped the bedrooms' cans as stacked.
HALL_COVERED = 0.4
# What is left of such a hallway must be at least this big to stay.
HALL_LEFT_SQFT = 12.0


def trim_named_halls(rooms, scale: float, page_width: int, page_height: int) -> list:
    """Cut a model-drawn hallway back to the open space it really is.

    The part of its box under no other indoor room is traced on a grid
    (the same half-foot shrink as ``find_halls`` drops the slivers between
    boxes) and the hallway becomes the largest piece left.  A hallway with
    nearly nothing left is dropped; ``find_halls`` will find any real hall
    in the open space.
    """
    if not scale:
        return rooms
    ft_x, ft_y = page_width * scale, page_height * scale
    out = []
    for room in rooms:
        box = _box(room)
        if room.room_type != "hallway" or not box:
            out.append(room)
            continue
        others = [
            _box(r) for r in rooms
            if r is not room and _box(r) and r.room_type not in OUTDOOR_TYPES
        ]
        cols = max(4, round((box[2] - box[0]) * ft_x * 4))     # quarter-foot cells
        rows = max(4, round((box[3] - box[1]) * ft_y * 4))
        cw, ch = (box[2] - box[0]) / cols, (box[3] - box[1]) / rows
        open_cells = [
            [not any(o[0] <= box[0] + (c + 0.5) * cw <= o[2] and o[1] <= box[1] + (r + 0.5) * ch <= o[3]
                     for o in others)
             for c in range(cols)]
            for r in range(rows)
        ]
        covered = 1 - sum(map(sum, open_cells)) / (rows * cols)
        if covered < HALL_COVERED:
            out.append(room)
            continue
        k = 2                                                   # half a foot
        shrunk = _erode(open_cells, k, k)
        best, seen = [], set()
        for r0 in range(rows):
            for c0 in range(cols):
                if not shrunk[r0][c0] or (r0, c0) in seen:
                    continue
                stack, cells = [(r0, c0)], []
                seen.add((r0, c0))
                while stack:
                    r, c = stack.pop()
                    cells.append((r, c))
                    for nr, nc in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
                        if 0 <= nr < rows and 0 <= nc < cols and shrunk[nr][nc] and (nr, nc) not in seen:
                            seen.add((nr, nc))
                            stack.append((nr, nc))
                if len(cells) > len(best):
                    best = cells
        if not best:
            logger.info("Dropped %s: its box lies under other rooms", room.name)
            continue
        r1 = max(0, min(r for r, _ in best) - k)
        r2 = min(rows, max(r for r, _ in best) + 1 + k)
        c1 = max(0, min(c for _, c in best) - k)
        c2 = min(cols, max(c for _, c in best) + 1 + k)
        left_sqft = sum(open_cells[r][c] for r in range(r1, r2) for c in range(c1, c2)) * (cw * ft_x) * (ch * ft_y)
        if left_sqft < HALL_LEFT_SQFT:
            logger.info("Dropped %s: only %.0f sq ft of it is not another room", room.name, left_sqft)
            continue
        nb = (box[0] + c1 * cw, box[1] + r1 * ch, box[0] + c2 * cw, box[1] + r2 * ch)
        w_ft, h_ft = (nb[2] - nb[0]) * ft_x, (nb[3] - nb[1]) * ft_y
        logger.info("Cut %s back to the %.0f sq ft no other room covers", room.name, left_sqft)
        out.append(room.model_copy(update={
            "bbox_x1": nb[0], "bbox_y1": nb[1], "bbox_x2": nb[2], "bbox_y2": nb[3],
            "position_x": (nb[0] + nb[2]) / 2, "position_y": (nb[1] + nb[3]) / 2,
            "width_ft": round(w_ft, 1), "length_ft": round(h_ft, 1), "sqft": round(left_sqft),
        }))
    return out


def find_halls(rooms, scale: float, page_width: int, page_height: int) -> list:
    """Halls the plan reader did not return, as new hallway rooms.

    The model reads rooms by their printed names, and a hall usually has
    none: on Hatteras the strip between the secondary bedrooms, Bath 2 and
    the living room came back as nothing, and got no light.  Inside the
    house (the extent of its indoor rooms) any open strip no room covers,
    hall-shaped once measured, becomes a hallway.
    """
    halls = []
    for box, w_ft, h_ft, fill, area in _open_spaces(rooms, scale, page_width, page_height):
        short, long_ = sorted((w_ft, h_ft))
        if (
            HALL_MIN_WIDTH_FT <= short <= HALL_MAX_WIDTH_FT
            and long_ >= HALL_MIN_LENGTH_FT
            and fill >= HALL_FILL
            and area <= HALL_MAX_SQFT
        ):
            halls.append((box, round(w_ft, 1), round(h_ft, 1)))

    found = []
    for n, (box, w_ft, h_ft) in enumerate(halls, start=1):
        name = "Hall" if len(halls) == 1 else f"Hall {n}"
        logger.info(
            "Found a hall no room covered: %s %s, %.1f x %.1f ft",
            name, tuple(round(v, 3) for v in box), w_ft, h_ft,
        )
        found.append(
            rooms[0].model_copy(
                update={
                    "name": name,
                    "room_type": "hallway",
                    "labeled": True,
                    "position_x": (box[0] + box[2]) / 2,
                    "position_y": (box[1] + box[3]) / 2,
                    "bbox_x1": box[0], "bbox_y1": box[1],
                    "bbox_x2": box[2], "bbox_y2": box[3],
                    "width_ft": w_ft, "length_ft": h_ft,
                    "sqft": round(w_ft * h_ft),
                    "ceiling_height_ft": None,
                }
            )
        )
    return found


def _erode(cells, kx: int, ky: int):
    """Keep a cell open only if every cell within kx across and ky down is."""
    rows, cols = len(cells), len(cells[0])
    across = [
        [all(row[max(0, c - kx):c + kx + 1]) for c in range(cols)]
        for row in cells
    ]
    return [
        [all(across[rr][c] for rr in range(max(0, r - ky), min(rows, r + ky + 1)))
         for c in range(cols)]
        for r in range(rows)
    ]
