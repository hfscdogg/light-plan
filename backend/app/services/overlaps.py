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

logger = logging.getLogger(__name__)

OPEN_PLAN_TYPES = {
    "kitchen", "dining", "living", "family", "great_room", "foyer", "entry",
}

ENCLOSED_TYPES = {
    "closet", "walk_in_closet", "pantry", "bathroom", "master_bathroom",
    "half_bath", "powder_room", "laundry", "mudroom", "hallway",
}

# Two open-plan boxes are one open area when this much of the smaller
# lies inside the larger.
SAME_AREA = 0.6

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


def _touching_sides(parent, child) -> list[str]:
    """Sides of ``parent`` that ``child`` lies against; two in a corner."""
    px1, py1, px2, py2 = parent
    cx1, cy1, cx2, cy2 = child
    touching = {
        "top": abs(cy1 - py1) <= TOUCH,
        "bottom": abs(cy2 - py2) <= TOUCH,
        "left": abs(cx1 - px1) <= TOUCH,
        "right": abs(cx2 - px2) <= TOUCH,
    }
    return [s for s in _SIDES if touching[s]]


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


def carve_enclosed(rooms) -> list:
    rooms = list(rooms)
    for p, parent in enumerate(rooms):
        pbox = _box(parent)
        plabel = _label(parent)
        if not pbox or parent.room_type in ENCLOSED_TYPES:
            continue

        by_side: dict[str, list[tuple]] = {}
        names: dict[str, list[str]] = {}
        for c, child in enumerate(rooms):
            cbox = _box(child)
            if c == p or not cbox or child.room_type not in ENCLOSED_TYPES:
                continue
            if _area(cbox) >= _area(pbox) or _overlap(pbox, cbox) / max(_area(cbox), 1e-9) < INSIDE:
                continue
            for side in _touching_sides(pbox, cbox):
                by_side.setdefault(side, []).append(cbox)
                names.setdefault(side, []).append(child.name)

        box = list(pbox)
        for side, children in by_side.items():
            px1, py1, px2, py2 = box
            if side in ("top", "bottom"):
                share = _covered([(c[0], c[2]) for c in children], px1, px2)
                new = max(c[3] for c in children) if side == "top" else min(c[1] for c in children)
                kept = (py2 - new) if side == "top" else (new - py1)
                full = py2 - py1
            else:
                share = _covered([(c[1], c[3]) for c in children], py1, py2)
                new = max(c[2] for c in children) if side == "left" else min(c[0] for c in children)
                kept = (px2 - new) if side == "left" else (new - px1)
                full = px2 - px1
            if share < SIDE_COVERED or kept < MIN_KEPT * full:
                continue
            trial = list(box)
            trial[{"left": 0, "top": 1, "right": 2, "bottom": 3}[side]] = new
            if plabel and not (
                trial[0] < plabel[0] < trial[2] and trial[1] < plabel[1] < trial[3]
            ):
                continue
            box = trial
            logger.info(
                "Carved %s out of the %s of %s's box",
                " + ".join(names[side]), side, parent.name,
            )
        if tuple(box) != pbox:
            rooms[p] = _with_box(parent, tuple(box))
    return rooms


def untangle(rooms, aspect: float = 1.0) -> list:
    """Both passes, open-plan split first: a pantry inside the kitchen's
    zone is judged against the kitchen, not the whole open area.

    ``aspect`` is the page's width over its height, so distances across and
    down the page compare fairly.
    """
    return carve_enclosed(split_open_plan(rooms, aspect))
