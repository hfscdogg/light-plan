"""Put keypads and accent lights on a real wall.

The placement model puts these by eye, and on an open plan it sometimes
picks a line that is not a wall at all:

- Hatteras, 7 Nov 2026: the kitchen's Entertain keypad landed in the open
  floor beside the island, and on another run the living room's two accent
  lights sat on the line the kitchen and living room were split along, at
  the foot of the island.

Every room box is fitted to the drawn walls, so a side of the box either
lies on a wall or is open (a split in an open plan, a cased opening).  This
reads which along the drawing itself, then:

- a keypad not on a wall moves to the nearest point of its room's sides
  that is, half a foot in;
- accent lights not along a wall move to the room's most solid side, evenly
  spaced along it, 2 ft off it.
"""

from __future__ import annotations

import logging
import math

from PIL import Image

from app.services.features import page_scale

logger = logging.getLogger(__name__)

# Half the width (share of the page's longer side) of the strip along a side
# that is looked at for its wall: the box sits on the wall, give or take.
_BAND = 0.006
# A sample along a side is wall when this share of the strip across it is
# ink: a drawn wall fills a good part of it, window lines and openings don't.
_WALL_INK = 0.15
# Ends of each side not looked at: the walls of the rooms beside run across them.
_TRIM = 0.05

KEYPAD_WALL_FT = 1.5     # a keypad this close to a wall is on it
KEYPAD_INSET_FT = 0.5
ACCENT_WALL_FT = 3.0     # accents this close to one solid side are along it
ACCENT_INSET_FT = 2.0
SOLID_SIDE = 0.5         # a side at least this much wall can carry accents

_SIDES = ("left", "top", "right", "bottom")


class SideProfile:
    """Which stretches of each side of a room's box are drawn wall."""

    def __init__(self, wall_map, box):
        self.box = box
        self.samples = {side: self._profile(wall_map, side) for side in _SIDES}

    def _profile(self, wall_map, side) -> list[bool]:
        x1, y1, x2, y2 = self.box
        w, h = wall_map.width, wall_map.height
        band = max(2, round(_BAND * max(w, h)))
        if side in ("left", "right"):
            x = round((x1 if side == "left" else x2) * w)
            top, bottom = round(y1 * h), round(y2 * h)
            if bottom - top < 4:
                return []
            strip = wall_map.mask.crop((max(0, x - band), top, min(w, x + band + 1), bottom))
            values = strip.resize((1, bottom - top), Image.BOX).getdata()
        else:
            y = round((y1 if side == "top" else y2) * h)
            left, right = round(x1 * w), round(x2 * w)
            if right - left < 4:
                return []
            strip = wall_map.mask.crop((left, max(0, y - band), right, min(h, y + band + 1)))
            values = strip.resize((right - left, 1), Image.BOX).getdata()
        return [v / 255 >= _WALL_INK for v in values]

    def coverage(self, side) -> float:
        s = self.samples[side]
        n = len(s)
        core = s[int(n * _TRIM): n - int(n * _TRIM)] if n else []
        return sum(core) / len(core) if core else 0.0

    def wall_at(self, side, t: float, reach: float) -> bool:
        """Is the side wall around ``t`` (0-1 along it), within ``reach`` (0-1)?"""
        s = self.samples[side]
        n = len(s)
        if not n:
            return False
        lo = max(int(n * _TRIM), int((t - reach) * n))
        hi = min(n - int(n * _TRIM), int(math.ceil((t + reach) * n)))
        window = s[lo:hi]
        return bool(window) and sum(window) / len(window) >= 0.5


def _along(box, side, x, y) -> float:
    x1, y1, x2, y2 = box
    if side in ("left", "right"):
        return (y - y1) / max(1e-9, y2 - y1)
    return (x - x1) / max(1e-9, x2 - x1)


def _distance_ft(box, side, x, y, fx, fy) -> float:
    x1, y1, x2, y2 = box
    return {
        "left": abs(x - x1) * fx, "right": abs(x2 - x) * fx,
        "top": abs(y - y1) * fy, "bottom": abs(y2 - y) * fy,
    }[side]


def _point_on(box, side, t, inset_ft, fx, fy):
    x1, y1, x2, y2 = box
    t = max(_TRIM, min(1 - _TRIM, t))
    if side == "left":
        return x1 + inset_ft / fx, y1 + t * (y2 - y1)
    if side == "right":
        return x2 - inset_ft / fx, y1 + t * (y2 - y1)
    if side == "top":
        return x1 + t * (x2 - x1), y1 + inset_ft / fy
    return x1 + t * (x2 - x1), y2 - inset_ft / fy


def _side_length(box, side, fx, fy) -> float:
    x1, y1, x2, y2 = box
    return (y2 - y1) * fy if side in ("left", "right") else (x2 - x1) * fx


def _on_wall(profile, x, y, limit_ft, fx, fy) -> str | None:
    box = profile.box
    for side in _SIDES:
        if _distance_ft(box, side, x, y, fx, fy) > limit_ft:
            continue
        reach = 1.0 / max(1.0, _side_length(box, side, fx, fy))   # about a foot
        if profile.wall_at(side, _along(box, side, x, y), reach):
            return side
    return None


def _near_wall(wall_map, x, y, limit_ft, fx, fy) -> bool:
    """Is there a drawn wall within ``limit_ft`` of the point, in any direction?

    Looks at the drawing, not the room's box: a box that sits a little off
    its wall must not make a keypad that is on the real wall look loose.
    """
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        end = (x + dx * limit_ft / fx, y + dy * limit_ft / fy)
        if wall_map.wall_between((x, y), end) is not None:
            return True
    return False


def _snap_keypad(profile, x, y, fx, fy):
    """The nearest point half a foot in from a wall of the room, or None."""
    box = profile.box
    best = None
    for side in _SIDES:
        t = max(_TRIM, min(1 - _TRIM, _along(box, side, x, y)))
        length = _side_length(box, side, fx, fy)
        reach = 1.0 / max(1.0, length)
        # Slide along the side to the nearest stretch of wall (a door or an
        # opening may sit right at the projection).
        for step in range(0, 40):
            found = None
            for tt in (t - step * reach, t + step * reach):
                if _TRIM <= tt <= 1 - _TRIM and profile.wall_at(side, tt, reach):
                    found = tt
                    break
            if found is not None:
                px, py = _point_on(box, side, found, KEYPAD_INSET_FT, fx, fy)
                d = math.hypot((px - x) * fx, (py - y) * fy)
                if best is None or d < best[0]:
                    best = (d, (px, py))
                break
    return best[1] if best else None


def _place_accents(profile, count, fx, fy, avoid_side=None):
    box = profile.box
    sides = [s for s in _SIDES if s != avoid_side and profile.coverage(s) >= SOLID_SIDE]
    if not sides:
        return None
    side = max(sides, key=lambda s: (round(profile.coverage(s), 1), _side_length(box, s, fx, fy)))
    length = _side_length(box, side, fx, fy)
    reach = 1.0 / max(1.0, length)
    points = []
    for k in range(count):
        t = (k + 1) / (count + 1)
        # Off an opening in that wall, onto the nearest solid stretch.
        for step in range(0, 20):
            hit = next((tt for tt in (t - step * reach, t + step * reach)
                        if profile.wall_at(side, tt, reach)), None)
            if hit is not None:
                t = hit
                break
        points.append(_point_on(box, side, t, ACCENT_INSET_FT, fx, fy))
    return points


def snap_to_walls(wall_map, rooms_data, fixtures_by_room, plan_positions):
    """Keypads and accent lights onto real walls.  Returns new positions."""
    scale = page_scale(rooms_data)
    if scale is None:
        return plan_positions
    fx, fy = scale
    result = {k: list(v) for k, v in plan_positions.items()}
    moved = 0
    for rd in rooms_data:
        box = (rd.bbox_x1, rd.bbox_y1, rd.bbox_x2, rd.bbox_y2)
        fixtures = fixtures_by_room.get(rd.name)
        positions = result.get(rd.name)
        if None in box or not fixtures or not positions or len(positions) < len(fixtures):
            continue
        kinds = {fa.fixture_type for fa in fixtures}
        if not kinds & {"keypad", "accent"}:
            continue
        profile = SideProfile(wall_map, box)

        entry_side = None
        for i, fa in enumerate(fixtures):
            if fa.fixture_type != "keypad":
                continue
            x, y = positions[i]
            side = _on_wall(profile, x, y, KEYPAD_WALL_FT, fx, fy)
            if side is None and not _near_wall(wall_map, x, y, KEYPAD_WALL_FT, fx, fy):
                snapped = _snap_keypad(profile, x, y, fx, fy)
                if snapped is not None:
                    positions[i] = snapped
                    side = _on_wall(profile, *snapped, KEYPAD_WALL_FT, fx, fy)
                    moved += 1
                    logger.info("Walls: moved the %s keypad onto a wall", rd.name)
            if "front door" in (fa.notes or "").lower():
                entry_side = side

        accents = [i for i, fa in enumerate(fixtures) if fa.fixture_type == "accent"]
        if accents:
            sides = {_on_wall(profile, *positions[i], ACCENT_WALL_FT, fx, fy) for i in accents}
            loose = any(
                not _near_wall(wall_map, *positions[i], ACCENT_WALL_FT, fx, fy) for i in accents
            )
            if loose or len(sides) > 1 or (entry_side is not None and entry_side in sides):
                points = _place_accents(profile, len(accents), fx, fy, avoid_side=entry_side)
                if points:
                    for i, p in zip(accents, points):
                        positions[i] = p
                    moved += len(accents)
                    logger.info("Walls: moved the %s accent lights onto its feature wall", rd.name)
        result[rd.name] = positions
    if moved:
        logger.info("Walls: moved %d keypad/accent fixture(s) onto a wall", moved)
    return result


# ---------------------------------------------------------------------------
# Ceiling fixtures sitting on a wall line
# ---------------------------------------------------------------------------

# Pendants and chandeliers are placed over the island or the table on purpose.
CEILING_TYPES = {"recessed", "ceiling_fan", "exhaust_fan"}
WALL_CLEAR_FT = 0.6      # a ceiling fixture this close to a drawn wall is on it
PULL_STEP_FT = 0.25
PULL_MAX_FT = 2.0


def pull_off_walls(wall_map, rooms_data, fixtures_by_room, plan_positions):
    """Move a ceiling fixture that sits on a drawn wall back into its room.

    Catalina, 7 Nov 2026: two of the living room's cans sat right on the
    wall line between the living room and the dining bump-out.  A ceiling
    fixture within about half a foot of a drawn wall steps toward the
    middle of its room until it is clear, at most 2 ft.  Returns new
    positions.
    """
    scale = page_scale(rooms_data)
    if scale is None:
        return plan_positions
    fx, fy = scale
    boxes = {rd.name: (rd.bbox_x1, rd.bbox_y1, rd.bbox_x2, rd.bbox_y2) for rd in rooms_data
             if rd.room_type not in ("porch", "patio", "deck", "exterior", "exterior_door", "garage")}
    result = {k: list(v) for k, v in plan_positions.items()}
    moved = 0
    for name, fixtures in fixtures_by_room.items():
        box = boxes.get(name)
        positions = result.get(name)
        if not box or None in box or not positions:
            continue
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        for i, fa in enumerate(fixtures):
            if fa.fixture_type not in CEILING_TYPES or i >= len(positions):
                continue
            x, y = positions[i]
            # A drawn wall is thick and runs a long way; an island or a
            # counter edge is a hairline and does not count.
            if not _near_wall(wall_map, x, y, WALL_CLEAR_FT, fx, fy):
                continue
            dx_ft, dy_ft = (cx - x) * fx, (cy - y) * fy
            dist = math.hypot(dx_ft, dy_ft)
            if dist < 0.5:
                continue
            ux, uy = dx_ft / dist, dy_ft / dist
            step = PULL_STEP_FT
            while step <= min(PULL_MAX_FT, dist):
                nx, ny = x + ux * step / fx, y + uy * step / fy
                if not _near_wall(wall_map, nx, ny, WALL_CLEAR_FT, fx, fy):
                    positions[i] = (nx, ny)
                    moved += 1
                    break
                step += PULL_STEP_FT
        result[name] = positions
    if moved:
        logger.info("Walls: pulled %d ceiling fixture(s) off a wall line", moved)
    return result
