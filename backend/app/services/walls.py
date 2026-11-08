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

from PIL import Image, ImageDraw, ImageFilter

logger = logging.getLogger(__name__)

# Work on at most this many pixels along the long side.  A 24x36 sheet at
# 200 dpi is 7200 px tall; fitting walls does not need that, and the server
# has little memory to spare.
_MAX_SIDE = 2400

# A pixel darker than this is ink.
_INK = 160

# ...on a page smaller than _SMALL_SIDE along its long side, darker than
# _SMALL_INK.  Shrunk to 960 px, the thin lines that draw a window's edges in a
# wall come out light grey (about 195-210 on Sullivan): at 160 the window
# broke the wall, and the porch and primary bedroom were stretched to the
# page frame.  At 2560 px the same lines are 107-141.
_SMALL_SIDE = 1600
_SMALL_INK = 215

# A row or column inked across this share of the whole page is the sheet's
# frame (or a title-block rule), not a wall.
_FRAME_COVERAGE = 0.9

# The wall an open edge comes in to may be mostly windows: Catalina's living
# room's back wall at 960 px is ink across only 44% of the room, the rest
# light-grey window lines.  Thick ink across this share of the room will do.
_INNER_WALL = 0.35

# Floors are found on the sheet shrunk to _FLOOR_GRID pixels along its long
# side.  A floor holds at least _FLOOR_SHARE of the sheet's ink, so a title,
# a north arrow or a note is not a floor.
_FLOOR_GRID = 300
_FLOOR_SHARE = 0.15

# A blank strip between two drawings is at least this share of the page
# (Catalina's is about 7%), with no more than _GUTTER_INK ink pixels across.
_GUTTER = 0.025
_GUTTER_INK = 2

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
UNCONDITIONED = {"garage", "porch", "patio", "exterior", "deck", "exterior_door"}


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
        ink = _INK if max(self.width, self.height) >= _SMALL_SIDE else _SMALL_INK
        self.mask = gray.point(lambda p: 255 if p < ink else 0, "L")
        longest = max(self.width, self.height)
        # A drawn wall is either solid and a few pixels thick, or two thin
        # lines a short way apart.  A single hairline (a counter edge, a
        # dimension string) is neither.
        self.min_thickness = max(2, round(longest * 0.0015))
        self.max_gap = max(3, round(longest * 0.01))
        # The frame drawn round the sheet is not a wall.  Nothing in a house
        # runs unbroken across nearly the whole page; a frame line does.  On
        # Sullivan at 960 px the porch's open front edge found no wall and
        # was stretched down to the frame, 18 ft past the columns.
        self.frame_rows = self._full_lines(self._row_coverage(0, self.width, 0, self.height))
        self.frame_cols = self._full_lines(self._col_coverage(0, self.width, 0, self.height))

    @staticmethod
    def _full_lines(profile: list[float]) -> set[int]:
        return {i for i, cover in enumerate(profile) if cover >= _FRAME_COVERAGE}

    # -- floors -----------------------------------------------------------

    def floors(self) -> list[tuple[float, float, float, float]]:
        """The separate drawings on the sheet, as page-fraction boxes.

        A two-story plan set often draws both floors side by side on one
        sheet (Keel's Catalina, Castlewood, Bonaire, Tybee).  Read as one
        house, a second-floor room's edge snapped across the blank gutter to
        the first floor's outside wall, and halls and open plans were worked
        out across both floors.

        Floors split by a blank strip across the whole drawing are found
        that way (Catalina's first floor is drawn with so many openings that
        it falls apart into pieces as ink).  Floors that overlap side to
        side with no clear strip between them (Bonaire's attic sits over its
        porch) are found as separate blobs of ink.  One box when the sheet
        holds one drawing.
        """
        mask = self.mask.copy()
        draw = ImageDraw.Draw(mask)
        # The frame's anti-aliased edge is ink too, and joins everything.
        for y in self.frame_rows:
            draw.rectangle([(0, y - 2), (self.width, y + 2)], fill=0)
        for x in self.frame_cols:
            draw.rectangle([(x - 2, 0), (x + 2, self.height)], fill=0)
        return self._gutter_floors(mask) or self._blob_floors(mask) or [(0.0, 0.0, 1.0, 1.0)]

    def _gutter_floors(self, mask):
        """Drawings split by a blank band of columns (or rows), or None."""
        w, h = self.width, self.height
        cols = [round(v / 255 * h) for v in mask.resize((w, 1), Image.BOX).getdata()]
        rows = [round(v / 255 * w) for v in mask.resize((1, h), Image.BOX).getdata()]
        xs = [i for i, v in enumerate(cols) if v > 0]
        ys = [i for i, v in enumerate(rows) if v > 0]
        if not xs or not ys:
            return None
        x1, x2, y1, y2 = xs[0], xs[-1], ys[0], ys[-1]
        across = self._split(cols, x1, x2, w)
        if across:
            return [(a / w, y1 / h, b / w, (y2 + 1) / h) for a, b in across]
        down = self._split(rows, y1, y2, h)
        if down:
            return [(x1 / w, a / h, (x2 + 1) / w, b / h) for a, b in down]
        return None

    def _split(self, profile, lo: int, hi: int, size: int):
        gutter = max(3, round(_GUTTER * size))
        parts, start, blank = [], lo, 0
        for i in range(lo, hi + 1):
            if profile[i] <= _GUTTER_INK:
                blank += 1
                continue
            if blank >= gutter and i - blank > start:
                parts.append((start, i - blank))
                start = i
            blank = 0
        parts.append((start, hi + 1))
        total = sum(profile[lo:hi + 1]) or 1
        kept = [(a, b) for a, b in parts if sum(profile[a:b]) >= _FLOOR_SHARE * total]
        return kept if len(kept) >= 2 else None

    def _blob_floors(self, mask):
        """Separate blobs of ink, each a real share of the sheet, or None.

        The sheet is shrunk and its ink thickened a little so a door or a
        window does not break a wall; pieces of one floor that sit mostly
        inside one another are merged.
        """
        factor = _FLOOR_GRID / max(self.width, self.height)
        gw, gh = max(1, round(self.width * factor)), max(1, round(self.height * factor))
        small = mask.resize((gw, gh), Image.BOX).point(lambda v: 255 if v > 0 else 0)
        small = small.filter(ImageFilter.MaxFilter(5))
        ink = small.load()

        seen = bytearray(gw * gh)
        blobs = []
        for y0 in range(gh):
            for x0 in range(gw):
                if not ink[x0, y0] or seen[y0 * gw + x0]:
                    continue
                stack, size = [(x0, y0)], 0
                seen[y0 * gw + x0] = 1
                bx1, by1, bx2, by2 = x0, y0, x0, y0
                while stack:
                    x, y = stack.pop()
                    size += 1
                    bx1, by1, bx2, by2 = min(bx1, x), min(by1, y), max(bx2, x), max(by2, y)
                    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                        if 0 <= nx < gw and 0 <= ny < gh and ink[nx, ny] and not seen[ny * gw + nx]:
                            seen[ny * gw + nx] = 1
                            stack.append((nx, ny))
                blobs.append((size, (bx1 / gw, by1 / gh, (bx2 + 1) / gw, (by2 + 1) / gh)))
        # Whatever is left of a frame spans the sheet; it is not a floor.
        blobs = [(size, box) for size, box in blobs
                 if not (box[2] - box[0] > 0.9 and box[3] - box[1] > 0.9)]
        total = sum(size for size, _ in blobs) or 1

        # Long windows and open plans break one floor into pieces (Catalina's
        # first floor came apart in four).  Pieces of one floor sit inside
        # one another's outline; two floors barely touch (Bonaire's overlap
        # by 3%), so pieces overlapping by half are one floor.
        pieces = [[size, box] for size, box in blobs if size >= 0.01 * total]
        merged = True
        while merged:
            merged = False
            for i in range(len(pieces)):
                for j in range(i + 1, len(pieces)):
                    a, b = pieces[i][1], pieces[j][1]
                    w = min(a[2], b[2]) - max(a[0], b[0])
                    h = min(a[3], b[3]) - max(a[1], b[1])
                    smaller = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
                    if w > 0 and h > 0 and w * h >= 0.5 * smaller:
                        pieces[i] = [pieces[i][0] + pieces[j][0],
                                     (min(a[0], b[0]), min(a[1], b[1]),
                                      max(a[2], b[2]), max(a[3], b[3]))]
                        del pieces[j]
                        merged = True
                        break
                if merged:
                    break
        floors = [box for size, box in pieces if size >= _FLOOR_SHARE * total]
        return sorted(floors) if len(floors) >= 2 else None

    # -- line of sight ----------------------------------------------------

    def _ink_extent(self, px: int, py: int) -> int:
        """Longest straight run of ink, across or down, through a pixel."""
        best = 0
        for dx, dy in ((1, 0), (0, 1)):
            length = 1
            for sign in (1, -1):
                x, y, gap = px, py, 0
                while True:
                    x += dx * sign
                    y += dy * sign
                    if not (0 <= x < self.width and 0 <= y < self.height):
                        break
                    if self.mask.getpixel((x, y)):
                        length += 1 + gap
                        gap = 0
                    elif gap < 2:
                        gap += 1  # a pixel or two missing from a scanned line
                    else:
                        break
            best = max(best, length)
        return best

    def wall_between(
        self, start: tuple[float, float], end: tuple[float, float], skip: float = 0.0
    ) -> float | None:
        """How far from ``start`` towards ``end`` (0-1) the first wall lies.

        Points are page fractions.  A wall is ink at least as thick as a
        drawn wall, crossed along the line, that also runs straight for a
        long way across or down the page.  Lettering, door swings, counters
        and fixture symbols are thinner or shorter and do not count.  Ink
        within ``skip`` of ``start`` (a fraction of the page's longer side)
        is not looked at: the line starts on the room's printed name.
        None when the line crosses no wall.
        """
        x0, y0 = start[0] * self.width, start[1] * self.height
        x1, y1 = end[0] * self.width, end[1] * self.height
        length = math.hypot(x1 - x0, y1 - y0)
        steps = max(1, round(length))
        longest = max(self.width, self.height)
        skip_px = skip * longest
        wall_length = longest * 0.025
        thick = self.min_thickness
        run = 0
        for i in range(steps + 1):
            t = i / steps
            px, py = round(x0 + (x1 - x0) * t), round(y0 + (y1 - y0) * t)
            if t * length < skip_px or not (0 <= px < self.width and 0 <= py < self.height):
                run = 0
                continue
            if self.mask.getpixel((px, py)):
                run += 1
                if run >= thick and self._ink_extent(px, py) >= wall_length:
                    return max(0.0, t - run / steps)
            else:
                run = 0
        return None

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

    def _wall_bands(
        self, profile: list[float], offset: int, frame: set[int] = frozenset(),
        coverage: float = None,
    ) -> list[tuple[int, int]]:
        """Runs of wall-like rows/columns, as (first, last) pixel indices.

        A run that touches a line of the sheet's frame is not a wall.
        """
        bands: list[tuple[int, int]] = []
        start = last = None
        for i, cover in enumerate(profile):
            if cover < (_WALL_COVERAGE if coverage is None else coverage):
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
            and not any(i in frame for i in range(a + offset, b + offset + 1))
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

    # -- tightening -------------------------------------------------------

    def tighten(self, bbox, label=None, sides=("left", "top", "right", "bottom")):
        """Bring an edge with no wall along it in to the wall inside the box.

        Splitting an open plan divides the rectangle round all its rooms, so
        a room can take in space outside the house: Catalina's living room
        reached up past the back wall into the empty corner beside the
        dining bump-out, and one of its cans landed on the window line.  An
        edge with almost no wall along it moves in to the first solid wall
        that runs across the box, within 40% of the box, as long as the
        room's label stays inside.  An edge already on a wall never moves.
        Returns the box (page fractions).
        """
        W, H = self.width, self.height
        x1, y1, x2, y2 = bbox[0] * W, bbox[1] * H, bbox[2] * W, bbox[3] * H
        w, h = x2 - x1, y2 - y1
        if w < 8 or h < 8:
            return bbox
        band = max(2, round(0.006 * max(W, H)))
        sx1, sx2 = int(x1 + w * _SPAN_TRIM), int(math.ceil(x2 - w * _SPAN_TRIM))
        sy1, sy2 = int(y1 + h * _SPAN_TRIM), int(math.ceil(y2 - h * _SPAN_TRIM))
        lx = label[0] * W if label and label[0] is not None else None
        ly = label[1] * H if label and label[1] is not None else None

        def walled(profile_fn, at, frame):
            # A real wall along the edge: thick and covering most of it.
            # Hairlines (the back steps beside Catalina's living room, a
            # porch outline) do not count.
            a = int(at) - band
            return bool(self._wall_bands(profile_fn(a, int(at) + band + 1), a, frame))

        def solid(bands, across):
            # Lettering (Camden's "Covered Porch" label) covers a row in many
            # short marks; a wall, even one broken by windows, has a long
            # unbroken stretch.  Keep bands with a run of ink at least a
            # quarter of the room across.
            lo, hi = (sx1, sx2) if across else (sy1, sy2)
            need = 0.25 * (hi - lo)
            kept = []
            for first, last in bands:
                for i in range(first, last + 1):
                    run = best = 0
                    for j in range(lo, hi):
                        px = (j, i) if across else (i, j)
                        if 0 <= px[0] < W and 0 <= px[1] < H and self.mask.getpixel(px):
                            run += 1
                            best = max(best, run)
                        else:
                            run = 0
                    if best >= need:
                        kept.append((first, last))
                        break
            return kept

        rows = lambda a, b: self._row_coverage(sx1, sx2, max(0, a), min(H, b))
        cols = lambda a, b: self._col_coverage(max(0, a), min(W, b), sy1, sy2)
        reach_y, reach_x = int(h * 0.4), int(w * 0.4)

        if "top" in sides and not walled(rows, y1, self.frame_rows):
            a = int(y1) + band + 1
            for first, last in solid(self._wall_bands(rows(a, a + reach_y), a, self.frame_rows, _INNER_WALL), True):
                if ly is None or last + 1 < ly:
                    y1 = last + 1
                break
        if "bottom" in sides and not walled(rows, y2, self.frame_rows):
            b = int(y2) - band
            found = solid(self._wall_bands(rows(b - reach_y, b), b - reach_y, self.frame_rows, _INNER_WALL), True)
            if found and (ly is None or found[-1][0] > ly):
                y2 = found[-1][0]
        if "left" in sides and not walled(cols, x1, self.frame_cols):
            a = int(x1) + band + 1
            for first, last in solid(self._wall_bands(cols(a, a + reach_x), a, self.frame_cols, _INNER_WALL), False):
                if lx is None or last + 1 < lx:
                    x1 = last + 1
                break
        if "right" in sides and not walled(cols, x2, self.frame_cols):
            b = int(x2) - band
            found = solid(self._wall_bands(cols(b - reach_x, b), b - reach_x, self.frame_cols, _INNER_WALL), False)
            if found and (lx is None or found[-1][0] > lx):
                x2 = found[-1][0]
        return (x1 / W, y1 / H, x2 / W, y2 / H)

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
            self._wall_bands(self._row_coverage(sx1, sx2, a, b), a, self.frame_rows),
            y1, "after", -1,
        )
        a, b = window(y2 - h * _SEARCH_IN, y2 + reach, H)
        found["bottom"] = self._closest(
            self._wall_bands(self._row_coverage(sx1, sx2, a, b), a, self.frame_rows),
            y2, "before", 1,
        )
        a, b = window(x1 - reach, x1 + w * _SEARCH_IN, W)
        found["left"] = self._closest(
            self._wall_bands(self._col_coverage(a, b, sy1, sy2), a, self.frame_cols),
            x1, "after", -1,
        )
        a, b = window(x2 - w * _SEARCH_IN, x2 + reach, W)
        found["right"] = self._closest(
            self._wall_bands(self._col_coverage(a, b, sy1, sy2), a, self.frame_cols),
            x2, "before", 1,
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


# Two spans agree on the plan's scale when they are this close (log ratio,
# about 6%).  Printed sizes are rounded to the inch and walls are a few pixels
# thick, so a real match is well inside it.
_SCALE_AGREEMENT = 0.06


def span_scale(fitted, page_width: int, page_height: int) -> float | None:
    """The plan's scale, read from rooms with both walls found across one axis.

    ``fitted`` is ``(RoomData, Fit)`` pairs.  A room seated on its left and
    right walls has a measured width in pixels, and its printed size says how
    many feet that is — but not which printed number runs across, so each
    span offers both.  The scale most spans agree on wins.  Unlike
    ``feet_per_pixel`` this needs only two facing walls, so a room open on
    one side (a cased opening, an open kitchen) still counts.
    """
    pairs = []
    for r, fit in fitted:
        if fit is None or not (r.width_ft and r.length_ft):
            continue
        left, top, right, bottom = fit.snapped
        spans = []
        if left and right:
            spans.append((fit.x2 - fit.x1) * page_width)
        if top and bottom:
            spans.append((fit.y2 - fit.y1) * page_height)
        for px in spans:
            if px >= 5:
                pairs.append((r.width_ft / px, r.length_ft / px))

    def agrees(a: float, b: float) -> bool:
        return abs(math.log(a / b)) < _SCALE_AGREEMENT

    best: list[float] = []
    for candidate in {s for pair in pairs for s in pair}:
        matched = [
            min(pair, key=lambda s: abs(math.log(s / candidate)))
            for pair in pairs
            if any(agrees(s, candidate) for s in pair)
        ]
        if len(matched) > len(best):
            best = matched
    # One span cannot tell which printed number it is; two that agree can.
    if len(best) < 2:
        return None
    scale = statistics.median(best)
    logger.info("Scale: %.4f ft/px from %d wall-to-wall span(s)", scale, len(best))
    return scale


# Two facing walls belong to the room when the gap between them is within
# this share of a printed size; further off, one of them is some other wall.
_SPAN_TOLERANCE = 0.15


def size_box(
    fit: Fit,
    width_ft: float,
    length_ft: float,
    scale: float,
    page_width: int,
    page_height: int,
    label: tuple[float | None, float | None] | None = None,
) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    """Finish a room's box from its walls and its printed size.

    A side with no wall found (an opening, an open plan) used to keep the
    model's box grown by a third, which ran through walls and into the next
    room — and the cans went with it.  With a scale and a printed size, the
    side is instead placed the room's width from the wall opposite it, or,
    with neither wall on an axis, the room's width centred on the model's
    box.

    Returns the room's (x1, x2) and (y1, y2) in page fractions.  An axis is
    None when the printed size cannot settle it — its two walls disagree
    with the size, or the sized room would leave its own label — and the
    caller keeps whatever it had for that axis.
    """
    left, top, right, bottom = fit.snapped
    span_x = (fit.x2 - fit.x1) * page_width * scale if left and right else None
    span_y = (fit.y2 - fit.y1) * page_height * scale if top and bottom else None

    def near(span: float, size: float) -> bool:
        return abs(span - size) <= size * _SPAN_TOLERANCE

    def place(lo, hi, lo_wall, hi_wall, span, size, extent, mark):
        if span is not None:
            return (lo, hi) if near(span, size) else None
        if lo_wall:
            lo, hi = lo, lo + extent
        elif hi_wall:
            lo, hi = hi - extent, hi
        else:
            mid = (lo + hi) / 2
            lo, hi = mid - extent / 2, mid + extent / 2
        if lo < -0.02 or hi > 1.02 or (mark is not None and not lo < mark < hi):
            return None
        return max(0.0, lo), min(1.0, hi)

    lx, ly = label or (None, None)

    def settle(across: float, down: float):
        xs = place(fit.x1, fit.x2, left, right, span_x, across,
                   across / scale / page_width, lx)
        ys = place(fit.y1, fit.y2, top, bottom, span_y, down,
                   down / scale / page_height, ly)
        return xs, ys

    # The prompt asks for the printed width first, so that is tried first;
    # the other way round wins only if it settles more of the room.  A pair
    # of walls that happens to sit one printed size apart is not enough on
    # its own to turn the room.
    printed = settle(width_ft, length_ft)
    turned = settle(length_ft, width_ft)
    count = lambda axes: sum(a is not None for a in axes)  # noqa: E731
    return turned if count(turned) > count(printed) else printed


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


# Rooms named like this are not living space, whatever type they were read as:
# Castlewood's "Unfinished Storage" and Bonaire's "Unfinished Attic" were
# counted as conditioned rooms.
_NOT_LIVING = ("unfinished", "attic")


def floor_area(rooms) -> float:
    """Square feet of the conditioned rooms.

    Each room counts its own size, once.  Two rooms read with the same box
    are one space counted twice: on Tybee the primary bath and a walk-in
    closet came back with identical boxes, and the house measured 9% over
    Keel's listed size; the second of such a pair is left out.  (Overlap in
    general is not taken off: a bedroom's printed size already leaves out
    the closet drawn inside its box.)
    """
    counted, total = [], 0.0
    for r in rooms:
        if r.room_type in UNCONDITIONED:
            continue
        if any(word in (r.name or "").lower() for word in _NOT_LIVING):
            continue
        box = (r.bbox_x1, r.bbox_y1, r.bbox_x2, r.bbox_y2)
        if None not in box and any(_same_box(box, b) for b in counted):
            continue
        if None not in box:
            counted.append(box)
        total += r.sqft or 0
    return round(total)


def _same_box(a, b) -> bool:
    """Two boxes covering the same space (overlap over union of 80% or more)."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return False
    inter = w * h
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter >= 0.8 * union
