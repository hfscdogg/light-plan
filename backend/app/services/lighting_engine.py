"""Lighting fixture rules engine.

Assigns fixtures to rooms based on room type, dimensions and selected tier.
Each room type has a dedicated rule class. The engine is modular: add or edit
room type defaults by modifying a single class without touching other rules.
"""

import math
from abc import ABC, abstractmethod

from app.models.schemas import FixtureAssignment, RoomData

# ---------------------------------------------------------------------------
# Tier product catalog
# ---------------------------------------------------------------------------

TIER_PRODUCTS = {
    "good": {
        "recessed": {
            "sku": "BG-REC-4",
            "desc": '4" builder grade recessed can',
            "msrp_range": "$15-25",
        },
        "pendant": {
            "sku": "BG-PEN-1",
            "desc": "Builder grade pendant",
            "msrp_range": "$50-100",
        },
        "sconce": {
            "sku": "BG-SCN-1",
            "desc": "Builder grade wall sconce",
            "msrp_range": "$30-60",
        },
        "ceiling_fan": {
            "sku": "BG-FAN-1",
            "desc": "Builder grade ceiling fan",
            "msrp_range": "$80-150",
        },
        "exhaust_fan": {
            "sku": "BG-EXH-1",
            "desc": "Bath exhaust fan",
            "msrp_range": "$30-60",
        },
        "coach_light": {
            "sku": "BG-CL-1",
            "desc": "Builder grade exterior coach light",
            "msrp_range": "$25-50",
        },
        "under_cabinet": {
            "sku": "BG-UC-1",
            "desc": "Builder grade under-cabinet strip",
            "msrp_range": "$20-40",
        },
        "landscape": {
            "sku": "BG-LS-1",
            "desc": "Builder grade landscape uplight",
            "msrp_range": "$15-30",
        },
        "chandelier": {
            "sku": "BG-CH-1",
            "desc": "Builder grade chandelier",
            "msrp_range": "$100-250",
        },
        "accent": {
            "sku": "BG-ACC-1",
            "desc": "Adjustable accent / wall-wash trim",
            "msrp_range": "$40-80",
        },
        "keypad": {
            "sku": "BG-KP-1",
            "desc": "Scene keypad",
            "msrp_range": "$60-120",
        },
        "switched_outlet": {
            "sku": "BG-SO-1",
            "desc": "Switched duplex outlet",
            "msrp_range": "$5-10",
        },
    },
    "better": {
        "recessed": {
            "sku": "DMF-DID210",
            "desc": 'DMF DID Series 2" recessed',
            "msrp_range": "$80-120",
        },
        "pendant": {
            "sku": "WAC-PD-XX",
            "desc": "WAC Lighting pendant",
            "msrp_range": "$200-400",
        },
        "sconce": {
            "sku": "WAC-WS-XX",
            "desc": "WAC Lighting wall sconce",
            "msrp_range": "$150-250",
        },
        "ceiling_fan": {
            "sku": "MC-FAN-1",
            "desc": "Modern Forms smart ceiling fan",
            "msrp_range": "$400-700",
        },
        "exhaust_fan": {
            "sku": "PAN-WVENT",
            "desc": "Panasonic WhisperValue exhaust fan",
            "msrp_range": "$80-130",
        },
        "coach_light": {
            "sku": "WAC-EXT-1",
            "desc": "WAC Lighting exterior sconce",
            "msrp_range": "$150-250",
        },
        "under_cabinet": {
            "sku": "WAC-UC-LED",
            "desc": "WAC Lighting LED under-cabinet",
            "msrp_range": "$60-100",
        },
        "landscape": {
            "sku": "WAC-LS-LED",
            "desc": "WAC Landscape LED uplight",
            "msrp_range": "$80-140",
        },
        "chandelier": {
            "sku": "DEC-CH-ALW",
            "desc": "Decorative chandelier (fixture allowance)",
            "msrp_range": "$400-900",
        },
        "accent": {
            "sku": "DMF-ADJ-2",
            "desc": "DMF adjustable accent / wall-wash trim",
            "msrp_range": "$140-210",
        },
        "keypad": {
            "sku": "LUT-HW-RANIA",
            "desc": "Lutron HomeWorks Rania scene keypad",
            "msrp_range": "$350-500",
        },
        "switched_outlet": {
            "sku": "LUT-CO-SW",
            "desc": "Lutron Claro switched outlet",
            "msrp_range": "$15-25",
        },
    },
    "best": {
        "recessed": {
            "sku": "KET-S38",
            "desc": "Ketra S38 full-spectrum downlight",
            "msrp_range": "$350-500",
        },
        "pendant": {
            "sku": "KET-LIN",
            "desc": "Ketra linear pendant",
            "msrp_range": "$800-1200",
        },
        "sconce": {
            "sku": "KET-S30W",
            "desc": "Ketra S30 wall wash",
            "msrp_range": "$300-450",
        },
        "ceiling_fan": {
            "sku": "MF-FAN-PRO",
            "desc": "Modern Forms premium smart fan",
            "msrp_range": "$700-1100",
        },
        "exhaust_fan": {
            "sku": "PAN-WFIT",
            "desc": "Panasonic WhisperFit exhaust fan",
            "msrp_range": "$120-180",
        },
        "coach_light": {
            "sku": "KET-EXT",
            "desc": "Ketra exterior fixture",
            "msrp_range": "$400-600",
        },
        "under_cabinet": {
            "sku": "KET-UC-LIN",
            "desc": "Ketra linear under-cabinet",
            "msrp_range": "$200-350",
        },
        "landscape": {
            "sku": "KET-LS-UP",
            "desc": "Ketra landscape uplight",
            "msrp_range": "$300-500",
        },
        "chandelier": {
            "sku": "DEC-CH-PREM",
            "desc": "Statement chandelier (fixture allowance)",
            "msrp_range": "$900-1500",
        },
        "accent": {
            "sku": "KET-D3-ADJ",
            "desc": "Ketra D3 adjustable accent",
            "msrp_range": "$400-600",
        },
        "keypad": {
            "sku": "LUT-HW-PALL",
            "desc": "Lutron HomeWorks Palladiom scene keypad",
            "msrp_range": "$500-750",
        },
        "switched_outlet": {
            "sku": "LUT-HW-SO",
            "desc": "Lutron HomeWorks switched outlet",
            "msrp_range": "$25-40",
        },
    },
}


# Control devices drawn on the plan (the Controls layer) but not fixtures:
# the builder BOM lists light fixtures only, so these stay out of it.
CONTROL_TYPES = {"keypad"}


def _product(tier: str, fixture_type: str) -> dict:
    """Look up product info for a tier and fixture type."""
    tier_catalog = TIER_PRODUCTS.get(tier, TIER_PRODUCTS["better"])
    return tier_catalog.get(fixture_type, {"sku": "", "desc": "", "msrp_range": ""})


def _fixture(
    fixture_type: str,
    tier: str,
    zone: str,
    x: float,
    y: float,
    notes: str = "",
    is_prewire: bool = False,
) -> FixtureAssignment:
    """Create a FixtureAssignment with product info filled in from the tier catalog."""
    product = _product(tier, fixture_type)
    return FixtureAssignment(
        fixture_type=fixture_type,
        zone=zone,
        position_x=round(max(0.0, min(1.0, x)), 3),
        position_y=round(max(0.0, min(1.0, y)), 3),
        notes=notes,
        is_prewire=is_prewire,
        product_sku=product["sku"],
        product_desc=product["desc"],
        msrp_range=product["msrp_range"],
    )


# ---------------------------------------------------------------------------
# Recessed grid algorithm (shared utility)
# ---------------------------------------------------------------------------


# How far apart ambient cans sit, as a multiple of the ceiling height.
# Half the ceiling height (the old rule) is a wall-wash figure: used as a
# grid it put ten-plus cans in a 13' kitchen and sixteen in a living room,
# and the plan read as a field of dots (Morgan, Nov 2026, the Keel plan).
# Roughly one can per ceiling-height of floor is what the sales team draws
# by hand; a better or best package tightens it a little.
AMBIENT_SPACING = {"good": 1.0, "better": 0.85, "best": 0.75}
MIN_AMBIENT_SPACING_FT = 6.0


def ambient_spacing(ceiling_height_ft: float = 9.0, tier: str = "better") -> float:
    """Centre-to-centre distance between ambient cans, in feet."""
    factor = AMBIENT_SPACING.get(tier, AMBIENT_SPACING["better"])
    return max(MIN_AMBIENT_SPACING_FT, (ceiling_height_ft or 9.0) * factor)


def ambient_grid(
    width_ft: float,
    length_ft: float,
    ceiling_height_ft: float = 9.0,
    tier: str = "better",
    spacing_scale: float = 1.0,
    minimum: int = 1,
    maximum: int | None = None,
    avoid_centre: bool = False,
) -> list[tuple[float, float]]:
    """Lay ambient cans out on an even rows x columns grid.

    Returns (x, y) tuples in 0-1 relative coordinates.  Each can lights a
    square cell of ``spacing`` feet, so the outer cans sit half a spacing
    off the walls and the grid is symmetric about the room's centre.

    ``minimum`` and ``maximum`` bound the count by adding or removing a row
    or column, always along the axis whose cells are longest (or shortest),
    so the grid stays full.  With ``avoid_centre`` (a ceiling fan hangs
    there) an odd-by-odd grid drops its centre can.
    """
    if width_ft <= 0 or length_ft <= 0:
        return [(0.5, 0.5)]

    spacing = ambient_spacing(ceiling_height_ft, tier) * spacing_scale
    cols = max(1, round(width_ft / spacing))
    rows = max(1, round(length_ft / spacing))

    while rows * cols < minimum:
        if width_ft / cols >= length_ft / rows:
            cols += 1
        else:
            rows += 1
    while maximum is not None and rows * cols > maximum and rows * cols > 1:
        if (width_ft / cols <= length_ft / rows and cols > 1) or rows == 1:
            cols -= 1
        else:
            rows -= 1

    if avoid_centre and rows * cols == 1:
        # One can would hang where the fan does: put two either side of it.
        if width_ft >= length_ft:
            cols = 2
        else:
            rows = 2

    grid = [
        ((c + 0.5) / cols, (r + 0.5) / rows)
        for r in range(rows)
        for c in range(cols)
    ]
    return _without_centre(grid) if avoid_centre else grid


def even_grid(
    width_ft: float,
    length_ft: float,
    count: int,
    ceiling_height_ft: float = 9.0,
    wall_inset_min_ft: float = 2.0,
) -> list[tuple[float, float]]:
    """Lay out exactly ``count`` cans as a full, evenly spaced grid.

    Taking the first few points of a bigger grid gave a bedroom its corners
    plus whatever came next, so four or six cans never formed rows and
    columns.  Here the rows and columns are chosen to multiply out to
    ``count`` with cells as close to square as the room allows, inset at
    least 2 ft from the walls.

    An even count never puts a can at the centre of the room, which is where
    the ceiling fan goes.
    """
    count = max(1, count)
    if width_ft <= 0 or length_ft <= 0:
        return [(0.5, 0.5)] * count

    spacing = ceiling_height_ft / 2.0
    inset = max(spacing / 2.0, wall_inset_min_ft)

    pairs = [(r, count // r) for r in range(1, count + 1) if count % r == 0]
    rows, cols = min(
        pairs, key=lambda rc: abs(math.log((width_ft / rc[1]) / (length_ft / rc[0])))
    )

    def line(size: float, n: int) -> list[float]:
        usable = size - 2 * inset
        if n == 1 or usable <= 0:
            # Too small to inset from both walls: spread evenly across it.
            return [(i + 0.5) / n for i in range(n)]
        return [(inset + usable * i / (n - 1)) / size for i in range(n)]

    return [(x, y) for y in line(length_ft, rows) for x in line(width_ft, cols)]


def _without_centre(grid: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop the can at the room's centre: the ceiling fan hangs there."""
    return [
        (x, y) for x, y in grid
        if not (math.isclose(x, 0.5, abs_tol=1e-6) and math.isclose(y, 0.5, abs_tol=1e-6))
    ]


def _room_dims(room: RoomData) -> tuple[float, float, float]:
    """Extract room dimensions with sensible defaults."""
    width = room.width_ft or 12.0
    length = room.length_ft or 12.0
    ceiling = room.ceiling_height_ft or 9.0
    return width, length, ceiling


# ---------------------------------------------------------------------------
# Room rule classes
# ---------------------------------------------------------------------------


class RoomRule(ABC):
    @abstractmethod
    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        ...


class KitchenRule(RoomRule):
    """Kitchen: recessed grid a little tighter than other rooms, island pendant, under-cabinet."""

    # Cans on 36" centres around every wall put twelve cans in a 13' x 10'
    # kitchen.  The counters get their task light from the under-cabinet
    # strip; the cans only need to fill the room, a touch denser than a
    # living room because people work here.
    SPACING_SCALE = 0.8

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        width, length, ceiling = _room_dims(room)
        fixtures: list[FixtureAssignment] = []
        zone_general = "kitchen-general"
        zone_island = "kitchen-island"
        zone_accent = "kitchen-accent"

        minimum = 4 if width * length >= 100 else 2
        for x, y in ambient_grid(
            width, length, ceiling, tier,
            spacing_scale=self.SPACING_SCALE, minimum=minimum,
        ):
            fixtures.append(_fixture("recessed", tier, zone_general, x, y))

        # Island pendants: the sheet sells "pendants", so never one alone.
        # Two over a typical island, three where the kitchen is long enough
        # for an 8 ft+ island or the package is Best.
        long_side = max(width, length)
        count = 3 if (tier == "best" or long_side >= 16) else 2
        for i in range(count):
            along = 0.35 + 0.3 * i / (count - 1)
            x, y = (along, 0.5) if width >= length else (0.5, along)
            fixtures.append(
                _fixture("pendant", tier, zone_island, x, y,
                         notes=f"Island pendant {i + 1} of {count}", is_prewire=True)
            )

        # Scene keypad ("Entertain") at the kitchen's main entry.
        fixtures.append(
            _fixture("keypad", tier, zone_general, 0.05, 0.5,
                     notes="Entertain scene keypad, at the kitchen entry")
        )

        # Under-cabinet pre-wire (better and best tiers)
        if tier in ("better", "best"):
            fixtures.append(
                _fixture("under_cabinet", tier, zone_accent, 0.5, 0.05, is_prewire=True)
            )

        return fixtures

class MasterBedroomRule(RoomRule):
    """Master bedroom: 4 or 6 recessed, ceiling fan pre-wire, switched outlets at bed wall."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        width, length, ceiling = _room_dims(room)
        fixtures: list[FixtureAssignment] = []
        zone_general = "master-general"
        zone_bed = "master-bed"

        # Recessed cans: 4 (good), 6 (better and best).  Always an even
        # number on a full grid: an odd count needs a can at the centre,
        # where the fan goes.
        target = {"good": 4, "better": 6, "best": 6}.get(tier, 6)
        for x, y in even_grid(width, length, target, ceiling):
            fixtures.append(_fixture("recessed", tier, zone_general, x, y))

        # Ceiling fan pre-wire at center
        fixtures.append(
            _fixture("ceiling_fan", tier, zone_general, 0.5, 0.5, is_prewire=True)
        )

        # Scene keypad ("Goodnight") on the latch side of the bedroom door.
        fixtures.append(
            _fixture("keypad", tier, zone_general, 0.05, 0.1,
                     notes="Goodnight scene keypad, inside the bedroom door")
        )

        # Switched outlets on each side of bed wall (assumed at y~0.9)
        fixtures.append(
            _fixture(
                "switched_outlet", tier, zone_bed, 0.2, 0.9,
                notes="Switched outlet for bedside lamp",
            )
        )
        fixtures.append(
            _fixture(
                "switched_outlet", tier, zone_bed, 0.8, 0.9,
                notes="Switched outlet for bedside lamp",
            )
        )

        return fixtures


class BedroomRule(RoomRule):
    """Standard bedroom: 4 recessed, ceiling fan pre-wire (better+), switched outlet."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        width, length, ceiling = _room_dims(room)
        fixtures: list[FixtureAssignment] = []
        zone = f"bedroom-{room.name.lower().replace(' ', '-')}"

        # Recessed cans on a full grid: 4, or 6 at best.  Even, so none sits
        # at the centre where the fan goes.
        target = {"good": 4, "better": 4, "best": 6}.get(tier, 4)
        for x, y in even_grid(width, length, target, ceiling):
            fixtures.append(_fixture("recessed", tier, zone, x, y))

        # Ceiling fan pre-wire (better and best)
        if tier in ("better", "best"):
            fixtures.append(
                _fixture("ceiling_fan", tier, zone, 0.5, 0.5, is_prewire=True)
            )

        # Switched outlet near bed area
        fixtures.append(
            _fixture(
                "switched_outlet", tier, zone, 0.2, 0.9,
                notes="Switched outlet for bedside lamp",
            )
        )

        return fixtures


class BathroomRule(RoomRule):
    """Full bathroom: vanity light, wet-rated can over the tub/shower, exhaust fan.

    Zack's Keel markup: two vanity lights over one 40" sink (one landing in
    the hall wall), a can on top of the sink and no light in the tub.  One
    vanity light centred on the mirror, a wet-rated can over the tub or
    shower, and a second general can only where the room has space for it.
    A primary bath with a double vanity gets a light over each sink.
    """

    WET_NOTE = "Over the tub / shower. IC/AT rated, wet location"

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        fixtures: list[FixtureAssignment] = []
        zone_vanity = "bath-vanity"
        zone_general = "bath-general"
        sqft = room.sqft or 60

        double_vanity = room.room_type == "master_bathroom" and sqft >= 80
        if double_vanity:
            for x, side in ((0.3, "left"), (0.7, "right")):
                fixtures.append(
                    _fixture("sconce", tier, zone_vanity, x, 0.1,
                             notes=f"Vanity light over the {side} sink, on the mirror wall")
                )
        else:
            fixtures.append(
                _fixture("sconce", tier, zone_vanity, 0.5, 0.1,
                         notes="Vanity light centred over the mirror, on the vanity wall")
            )

        # Wet-rated can over the tub / shower.  Listed first so the placement
        # model's first recessed position is the one it put in the wet area.
        fixtures.append(
            _fixture("recessed", tier, zone_general, 0.75, 0.75, notes=self.WET_NOTE)
        )

        # A general can in the open floor, never over the sink.
        if tier in ("better", "best") and sqft >= 60:
            fixtures.append(
                _fixture("recessed", tier, zone_general, 0.4, 0.55,
                         notes="General light, open floor away from the vanity")
            )

        fixtures.append(_fixture("exhaust_fan", tier, zone_general, 0.5, 0.5))

        return fixtures


class HalfBathRule(RoomRule):
    """Half bath / powder room: 1-2 recessed, vanity fixture, exhaust fan."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        fixtures: list[FixtureAssignment] = []
        zone = f"powder-{room.name.lower().replace(' ', '-')}"

        # 1 recessed (good), 2 recessed (better/best)
        fixtures.append(_fixture("recessed", tier, zone, 0.5, 0.5))
        if tier in ("better", "best"):
            fixtures.append(
                _fixture("sconce", tier, zone, 0.5, 0.1, notes="Above vanity mirror")
            )

        # Exhaust fan
        fixtures.append(_fixture("exhaust_fan", tier, zone, 0.5, 0.6))

        return fixtures


class HallwayRule(RoomRule):
    """Hallway: recessed on 6-8ft centers along the long axis."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        width, length, ceiling = _room_dims(room)
        fixtures: list[FixtureAssignment] = []
        zone = f"hallway-{room.name.lower().replace(' ', '-')}"

        # Spacing: 6ft (good), 7ft (better), 8ft (best)
        spacing_ft = {"good": 6.0, "better": 7.0, "best": 8.0}.get(tier, 7.0)

        # Place along the long axis
        long_dim = max(width, length)
        is_width_long = width >= length
        num_cans = max(1, round(long_dim / spacing_ft))

        for i in range(num_cans):
            pos = (i + 0.5) / num_cans
            if is_width_long:
                fixtures.append(_fixture("recessed", tier, zone, pos, 0.5))
            else:
                fixtures.append(_fixture("recessed", tier, zone, 0.5, pos))

        return fixtures


class LivingRoomRule(RoomRule):
    """Living/family/great room: recessed grid, ceiling fan, accent pre-wire."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        width, length, ceiling = _room_dims(room)
        fixtures: list[FixtureAssignment] = []
        zone_general = "living-general"
        zone_accent = "living-accent"

        # Recessed grid.  An odd-by-odd grid has a can at the centre, under
        # the fan, so it comes out when there is a fan.
        has_fan = tier in ("better", "best")
        minimum = 4 if width * length >= 150 else 2
        grid = ambient_grid(
            width, length, ceiling, tier, minimum=minimum, avoid_centre=has_fan,
        )
        for x, y in grid:
            fixtures.append(_fixture("recessed", tier, zone_general, x, y))

        # Ceiling fan pre-wire at center (better and best)
        if tier in ("better", "best"):
            fixtures.append(
                _fixture("ceiling_fan", tier, zone_general, 0.5, 0.5, is_prewire=True)
            )

        # Accent: adjustable trims washing the feature wall (fireplace, TV
        # or art wall).  The Accent layer was empty on Better plans while the
        # L3 card and legend promised it.
        if tier in ("better", "best"):
            count = 3 if tier == "best" else 2
            for i in range(count):
                x = 0.3 + 0.4 * i / (count - 1)
                fixtures.append(
                    _fixture("accent", tier, zone_accent, x, 0.92,
                             notes="Accent wash on the feature wall", is_prewire=True)
                )

        # Scene keypad ("Welcome") beside the front door.
        fixtures.append(
            _fixture("keypad", tier, zone_general, 0.5, 0.95,
                     notes="Welcome scene keypad, beside the front door")
        )

        return fixtures


class DiningRule(RoomRule):
    """Dining: chandelier over the table, a pair of cans either side of it.

    Dining used the living-room rule, so it got a fan and as many cans as a
    room twice its size.  The L3 card promises a chandelier.
    """

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        width, length, ceiling = _room_dims(room)
        fixtures: list[FixtureAssignment] = []
        zone = "dining"

        fixtures.append(
            _fixture("chandelier", tier, zone, 0.5, 0.5,
                     notes="Centred over the table", is_prewire=True)
        )

        # Two cans flanking the chandelier along the room's long axis;
        # four at Best in a big dining room.
        count = 4 if (tier == "best" and width * length >= 150) else 2
        for x, y in ambient_grid(
            width, length, ceiling, tier, minimum=count, maximum=count, avoid_centre=True,
        ):
            fixtures.append(_fixture("recessed", tier, zone, x, y))

        return fixtures


class ExteriorRule(RoomRule):
    """Exterior: coach lights at garage/porch/rear entry, landscape pre-wire."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        fixtures: list[FixtureAssignment] = []
        zone_entry = "exterior-entry"
        zone_landscape = "exterior-landscape"

        room_lower = room.name.lower()

        if "garage" in room_lower:
            # Coach lights at garage bays
            fixtures.append(
                _fixture("coach_light", tier, zone_entry, 0.3, 0.5, notes="Garage bay light")
            )
            fixtures.append(
                _fixture("coach_light", tier, zone_entry, 0.7, 0.5, notes="Garage bay light")
            )
        elif "porch" in room_lower or "entry" in room_lower or "foyer" in room_lower:
            # Porch / entry coach light
            fixtures.append(
                _fixture("coach_light", tier, zone_entry, 0.5, 0.3, notes="Entry coach light")
            )
        else:
            # Generic exterior: coach light at primary position
            fixtures.append(
                _fixture("coach_light", tier, zone_entry, 0.5, 0.5, notes="Exterior coach light")
            )

        # Soffit pre-wire for landscape uplighting (better and best)
        if tier in ("better", "best"):
            fixtures.append(
                _fixture("landscape", tier, zone_landscape, 0.1, 0.5, notes="Soffit pre-wire for landscape uplight", is_prewire=True)
            )
            fixtures.append(
                _fixture("landscape", tier, zone_landscape, 0.9, 0.5, notes="Soffit pre-wire for landscape uplight", is_prewire=True)
            )

        # Additional landscape positions for best tier
        if tier == "best":
            fixtures.append(
                _fixture("landscape", tier, zone_landscape, 0.5, 0.1, notes="Soffit pre-wire for landscape uplight", is_prewire=True)
            )
            fixtures.append(
                _fixture("landscape", tier, zone_landscape, 0.5, 0.9, notes="Soffit pre-wire for landscape uplight", is_prewire=True)
            )

        return fixtures


class LaundryRule(RoomRule):
    """Laundry: recessed cans plus task lighting."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        width, length, ceiling = _room_dims(room)
        fixtures: list[FixtureAssignment] = []
        zone = "laundry"

        # One can, two in a long laundry or mudroom.
        for x, y in ambient_grid(width, length, ceiling, tier, maximum=2):
            fixtures.append(_fixture("recessed", tier, zone, x, y))

        return fixtures


class ClosetRule(RoomRule):
    """Closet / walk-in closet / pantry: one can, two in a large walk-in."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        fixtures: list[FixtureAssignment] = []
        zone = f"closet-{room.name.lower().replace(' ', '-')}"

        # A second can only where there is room to walk between them.  Both
        # sit on the aisle, the centre line along the closet's long axis.
        count = 2 if (room.sqft and room.sqft > 60) else 1
        width, length, _ = _room_dims(room)
        for i in range(count):
            along = (i + 0.5) / count
            x, y = (along, 0.5) if width >= length else (0.5, along)
            fixtures.append(
                _fixture("recessed", tier, zone, x, y, notes="Centred on the closet aisle")
            )

        return fixtures


class DefaultRule(RoomRule):
    """Fallback rule for any room type not specifically handled."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        width, length, ceiling = _room_dims(room)
        fixtures: list[FixtureAssignment] = []
        zone = room.name.lower().replace(" ", "-")

        minimum = 2 if width * length >= 80 else 1
        for x, y in ambient_grid(width, length, ceiling, tier, minimum=minimum):
            fixtures.append(_fixture("recessed", tier, zone, x, y))

        return fixtures


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

RULE_REGISTRY: dict[str, type[RoomRule]] = {
    "kitchen": KitchenRule,
    "dining": DiningRule,
    "living": LivingRoomRule,
    "family": LivingRoomRule,
    "great_room": LivingRoomRule,
    "master_bedroom": MasterBedroomRule,
    "bedroom": BedroomRule,
    "master_bathroom": BathroomRule,
    "bathroom": BathroomRule,
    "half_bath": HalfBathRule,
    "powder_room": HalfBathRule,
    "hallway": HallwayRule,
    "entry": HallwayRule,
    "foyer": HallwayRule,
    "laundry": LaundryRule,
    "mudroom": LaundryRule,
    "pantry": ClosetRule,
    "closet": ClosetRule,
    "walk_in_closet": ClosetRule,
    "garage": ExteriorRule,
    "porch": ExteriorRule,
    "patio": ExteriorRule,
    "exterior": ExteriorRule,
    "office": DefaultRule,
    "den": DefaultRule,
    "bonus_room": DefaultRule,
}


# ---------------------------------------------------------------------------
# Engine orchestrator
# ---------------------------------------------------------------------------


class LightingEngine:
    """Assign fixtures to a list of parsed rooms based on room type and tier."""

    def process_rooms(
        self, rooms: list[RoomData], tier: str = "better"
    ) -> dict[str, list[FixtureAssignment]]:
        """Process all rooms and return a dict mapping room name to fixture list."""
        result: dict[str, list[FixtureAssignment]] = {}
        for room in rooms:
            result[room.name] = self.process_single_room(room, tier)
        return result

    def process_single_room(
        self, room: RoomData, tier: str = "better"
    ) -> list[FixtureAssignment]:
        """Process a single room and return its fixture list."""
        rule_cls = RULE_REGISTRY.get(room.room_type, DefaultRule)
        return rule_cls().assign(room, tier)
