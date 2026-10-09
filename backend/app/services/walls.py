"""Fit each room to the walls drawn around it, and read the plan's scale.

The model's room boxes are rough: sometimes a tight box round the label,
sometimes a box that spills into the next room.  The old fix was to grow every
box by 35%, which pushed rooms through their walls, and fixtures followed.

Walls are the one thing every floor plan draws the same way: long, heavy lines
(a solid poche or a pair of parallel lines) running the length of a room.  So
each edge of a room's box is moved to the inside face of the nearest such line
along that side.  An edge with no wall near it keeps the model's answer.

Once rooms sit on their walls, a room whose size is printed on the plan
("12'-4\" x 14'-0\"") says how many feet a pixel is.  That scale measures every
other room, so nobody has to type in a square footage.
"""

import logging
import math
import statistics
from dataclasses import dataclass

from PIL import Image

logger = logging.getLogger(__name__)

# Work on at most this many pixels along the long side.  A 24x36 sheet at
# 200 dpi is 7200 px tall; fitting walls does not need that, and the server
# has little memory to spare.
_MAX_SIDE = 2400

# A pixel darker than this is ink.
_INK = 160

# A row (or column) belongs to a wall when this share of the room's side is
# inked.  Doors and openings break a wall up, so it cannot be close to 1.
_WALL_COVERAGE = 0.55

# Only the middle of each side is measured, so the walls of the rooms on
# either side (which run across this side's ends) do not count.
_SPAN_TRIM = 0.2

# How far past an edge (as a share of the box's longer side), and how far
# inside it (as a share of the box along that axis), to look for its wall.  Outward reaches far because the
# model's box is often drawn round the room's label, well inside its walls;
# the nearest wall wins, so a long reach does not skip past the right one.
_SEARCH_OUT = 0.75
_SEARCH_IN = 0.3

# Spaces outside the conditioned envelope don't count towards a floor's
# square footage.
UNCONDITIONED = {"garage", "porch", "patio", "exterior", "deck"}


@dataclass
class Fit:
    """A room box in fractions of the page, and which edges found a wall."""

    x1: float
    y1: float
    x2: float
    y2: float
    # Which edges were moved onto a wall: left, top, right, bottom.
    snapped: tuple[bool, bool, bool, bool] = (False, False, False, False)

    @property
    def walls(self) -> int:
        return sum(self.snapped)


class WallMap:
    """Ink coverage of one plan page, for finding the walls around a room."""

    def __init__(self, image: Image.Image):
        gray = image.convert("L")
        w, h = gray.size
        factor = min(1.0, _MAX_SIDE / max(w, h))
        if factor < 1.0:
            gray = gray.resize(
                (max(1, round(w * factor)), max(1, round(h * factor))), Image.BOX
            )
        self.width, self.height = gray.size
        self.mask = gray.point(lambda p: 255 if p < _INK else 0, "L")
        longest = max(self.width, self.height)
        # A drawn wall is either solid and a few pixels thick, or two thin
        # lines a short way apart.  A single hairline (a counter edge, a
        # dimension string) is neither.
        self.min_thickness = max(2, round(longest * 0.0015))
        self.max_gap = max(3, round(longest * 0.01))

    # -- profiles ---------------------------------------------------------

    def _row_coverage(self, x1: int, x2: int, y1: int, y2: int) -> list[float]:
        """Share of inked pixels in each row y1..y2-1, across columns x1..x2."""
        if x2 - x1 < 1 or y2 - y1 < 1:
            return []
        band = self.mask.crop((x1, y1, x2, y2)).resize((1, y2 - y1), Image.BOX)
        return [v / 255 for v in band.getdata()]

    def _col_coverage(self, x1: int, x2: int, y1: int, y2: int) -> list[float]:
        """Share of inked pixels in each column x1..x2-1, across rows y1..y2."""
        if x2 - x1 < 1 or y2 - y1 < 1:
            return []
        band = self.mask.crop((x1, y1, x2, y2)).resize((x2 - x1, 1), Image.BOX)
        return [v / 255 for v in band.getdata()]

    def _wall_bands(self, profile: list[float], offset: int) -> list[tuple[int, int]]:
        """Runs of wall-like rows/columns, as (first, last) pixel indices."""
        bands: list[tuple[int, int]] = []
        start = last = None
        for i, cover in enumerate(profile):
            if cover < _WALL_COVERAGE:
                continue
            if start is None:
                start = last = i
            elif i - last <= self.max_gap:
                last = i
            else:
                bands.append((start, last))
                start = last = i
        if start is not None:
            bands.append((start, last))
        return [
            (a + offset, b + offset)
            for a, b in bands
            if b - a + 1 >= self.min_thickness
        ]

    @staticmethod
    def _closest(
        bands: list[tuple[int, int]], edge: float, face: str, outward: int
    ) -> int | None:
        """The inside face of the band nearest ``edge``.

        ``face`` picks which side of the band faces the room.  A band inside
        the model's box is only trusted half as much as one outside it: a box
        drawn round the label sits inside the room, so its real wall is out.
        """
        best = None
        best_cost = math.inf
        for first, last in bands:
            pos = last + 1 if face == "after" else first - 1
            dist = (pos - edge) * outward  # > 0: further out than the edge
            cost = abs(dist) * (1.0 if dist >= 0 else 1.5)
            if cost < best_cost:
                best, best_cost = pos, cost
        return best

    # -- fitting ----------------------------------------------------------

    def fit(
        self,
        bbox: tuple[float, float, float, float],
        label: tuple[float, float] | None = None,
    ) -> Fit:
        """Move each edge of ``bbox`` (page fractions) onto its wall.

        An edge only moves if the wall it lands on keeps the room's label
        inside the room and leaves a room of plausible size.
        """
        W, H = self.width, self.height
        x1, y1, x2, y2 = bbox[0] * W, bbox[1] * H, bbox[2] * W, bbox[3] * H
        w, h = x2 - x1, y2 - y1
        if w < 4 or h < 4:
            return Fit(*bbox)

        sx1 = int(x1 + w * _SPAN_TRIM)
        sx2 = int(math.ceil(x2 - w * _SPAN_TRIM))
        sy1 = int(y1 + h * _SPAN_TRIM)
        sy2 = int(math.ceil(y2 - h * _SPAN_TRIM))

        def window(lo: float, hi: float, limit: int) -> tuple[int, int]:
            return max(0, int(lo)), min(limit, int(math.ceil(hi)))

        # A label box is wide and short, so its height says little about how
        # far away the walls above and below are; reach by the longer side.
        reach = max(w, h) * _SEARCH_OUT
        found: dict[str, int | None] = {}

        # Top: the wall is above, the room starts after it.
        a, b = window(y1 - reach, y1 + h * _SEARCH_IN, H)
        found["top"] = self._closest(
            self._wall_bands(self._row_coverage(sx1, sx2, a, b), a), y1, "after", -1
        )
        a, b = window(y2 - h * _SEARCH_IN, y2 + reach, H)
        found["bottom"] = self._closest(
            self._wall_bands(self._row_coverage(sx1, sx2, a, b), a), y2, "before", 1
        )
        a, b = window(x1 - reach, x1 + w * _SEARCH_IN, W)
        found["left"] = self._closest(
            self._wall_bands(self._col_coverage(a, b, sy1, sy2), a), x1, "after", -1
        )
        a, b = window(x2 - w * _SEARCH_IN, x2 + reach, W)
        found["right"] = self._closest(
            self._wall_bands(self._col_coverage(a, b, sy1, sy2), a), x2, "before", 1
        )

        nx1 = found["left"] if found["left"] is not None else x1
        nx2 = found["right"] + 1 if found["right"] is not None else x2
        ny1 = found["top"] if found["top"] is not None else y1
        ny2 = found["bottom"] + 1 if found["bottom"] is not None else y2

        lx = label[0] * W if label and label[0] is not None else None
        ly = label[1] * H if label and label[1] is not None else None

        # Undo any edge that crossed the label or made a sliver of the room.
        if nx2 - nx1 < w * 0.4 or (lx is not None and not nx1 < lx < nx2):
            nx1, nx2 = x1, x2
            found["left"] = found["right"] = None
        if ny2 - ny1 < h * 0.4 or (ly is not None and not ny1 < ly < ny2):
            ny1, ny2 = y1, y2
            found["top"] = found["bottom"] = None

        snapped = tuple(
            found[side] is not None for side in ("left", "top", "right", "bottom")
        )
        return Fit(nx1 / W, ny1 / H, nx2 / W, ny2 / H, snapped=snapped)


def feet_per_pixel(rooms, page_width: int, page_height: int) -> float | None:
    """The plan's scale, read from rooms whose sizes are printed on it.

    ``rooms`` are ``RoomData`` with boxes in page fractions; only rooms
    with a printed width and length count, and only when their box has the
    printed proportions — a box that is clearly not the room it claims to
    be would otherwise skew the scale.  The median of what is left wins, so
    one bad room cannot set the scale on its own.
    """
    estimates = []
    for r in rooms:
        if not (r.width_ft and r.length_ft) or r.bbox_x1 is None or r.bbox_x2 is None:
            continue
        wpx = (r.bbox_x2 - r.bbox_x1) * page_width
        hpx = (r.bbox_y2 - r.bbox_y1) * page_height
        if wpx < 5 or hpx < 5:
            continue
        long_ft, short_ft = max(r.width_ft, r.length_ft), min(r.width_ft, r.length_ft)
        long_px, short_px = max(wpx, hpx), min(wpx, hpx)
        along_long = long_ft / long_px
        along_short = short_ft / short_px
        if abs(math.log(along_long / along_short)) > 0.2:
            continue
        estimates.append(math.sqrt(along_long * along_short))

    if not estimates:
        return None
    scale = statistics.median(estimates)
    logger.info(
        "Scale: %.4f ft/px from %d room(s) with printed sizes", scale, len(estimates)
    )
    return scale


def measure_rooms(rooms, scale: float, page_width: int, page_height: int):
    """Give every room its real width, length and area at ``scale``.

    A printed size wins over a measured one — it is what the architect
    wrote — but it is turned to match the box, so ``width_ft`` always runs
    across the page and ``length_ft`` down it, the way fixtures are laid out.
    """
    measured = []
    for r in rooms:
        if r.bbox_x1 is None or r.bbox_x2 is None:
            measured.append(r)
            continue
        across = (r.bbox_x2 - r.bbox_x1) * page_width * scale
        down = (r.bbox_y2 - r.bbox_y1) * page_height * scale
        if r.width_ft and r.length_ft:
            width, length = r.width_ft, r.length_ft
            if (width >= length) != (across >= down):
                width, length = length, width
        else:
            width, length = round(across, 1), round(down, 1)
        measured.append(
            r.model_copy(
                update={
                    "width_ft": width,
                    "length_ft": length,
                    "sqft": r.sqft or round(width * length),
                }
            )
        )
    return measured


def floor_area(rooms) -> float:
    """Square feet of the conditioned rooms on one floor."""
    return round(
        sum(r.sqft or 0 for r in rooms if r.room_type not in UNCONDITIONED)
    )
