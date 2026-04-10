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
        "switched_outlet": {
            "sku": "LUT-HW-SO",
            "desc": "Lutron HomeWorks switched outlet",
            "msrp_range": "$25-40",
        },
    },
}


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


def recessed_grid(
    width_ft: float,
    length_ft: float,
    ceiling_height_ft: float = 9.0,
    wall_inset_min_ft: float = 2.0,
) -> list[tuple[float, float]]:
    """Calculate recessed can positions in a rectangular room.

    Returns a list of (x, y) tuples in 0-1 relative coordinates.

    spacing = ceiling_height / 2
    inset = max(spacing / 2, wall_inset_min)
    """
    if width_ft <= 0 or length_ft <= 0:
        return [(0.5, 0.5)]

    spacing = ceiling_height_ft / 2.0
    inset = max(spacing / 2.0, wall_inset_min_ft)

    effective_w = width_ft - 2 * inset
    effective_l = length_ft - 2 * inset

    if effective_w <= 0 or effective_l <= 0:
        return [(0.5, 0.5)]

    cols = max(1, math.floor(effective_w / spacing) + 1)
    rows = max(1, math.floor(effective_l / spacing) + 1)

    positions = []
    for r in range(rows):
        for c in range(cols):
            x = inset + (effective_w * c / max(cols - 1, 1)) if cols > 1 else width_ft / 2.0
            y = inset + (effective_l * r / max(rows - 1, 1)) if rows > 1 else length_ft / 2.0
            # Convert to 0-1 relative
            rel_x = x / width_ft
            rel_y = y / length_ft
            positions.append((rel_x, rel_y))

    return positions


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
    """Kitchen: perimeter recessed on 36" centers, island pendant, under-cabinet."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        width, length, ceiling = _room_dims(room)
        fixtures: list[FixtureAssignment] = []
        zone_general = "kitchen-general"
        zone_island = "kitchen-island"
        zone_accent = "kitchen-accent"

        # Perimeter recessed: one row of cans inset 18" from walls,
        # spaced 36" (3ft) apart along each wall independently.
        inset = 1.5  # 18 inches from wall
        inset_rel_x = inset / width
        inset_rel_y = inset / length

        # Place along each wall
        for wall_length, positions_fn in [
            (width, lambda frac: (frac, inset_rel_y)),           # top wall
            (width, lambda frac: (frac, 1.0 - inset_rel_y)),     # bottom wall
            (length, lambda frac: (inset_rel_x, frac)),           # left wall
            (length, lambda frac: (1.0 - inset_rel_x, frac)),     # right wall
        ]:
            num_on_wall = max(1, round((wall_length - 2 * inset) / 3.0))
            for i in range(num_on_wall):
                frac = inset / wall_length + (1.0 - 2 * inset / wall_length) * (
                    (i + 0.5) / num_on_wall
                )
                x, y = positions_fn(frac)
                fixtures.append(_fixture("recessed", tier, zone_general, x, y))

        # Island pendant pre-wire (centered, slightly toward the front of the room)
        fixtures.append(
            _fixture("pendant", tier, zone_island, 0.5, 0.4, is_prewire=True)
        )
        if tier == "best":
            # Second pendant for larger islands
            fixtures.append(
                _fixture("pendant", tier, zone_island, 0.35, 0.4, is_prewire=True)
            )

        # Under-cabinet pre-wire (better and best tiers)
        if tier in ("better", "best"):
            fixtures.append(
                _fixture("under_cabinet", tier, zone_accent, 0.5, 0.05, is_prewire=True)
            )

        return fixtures

class MasterBedroomRule(RoomRule):
    """Master bedroom: 4-6 recessed, ceiling fan pre-wire, switched outlets at bed wall."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        width, length, ceiling = _room_dims(room)
        fixtures: list[FixtureAssignment] = []
        zone_general = "master-general"
        zone_bed = "master-bed"

        # Recessed cans: 4 (good), 5 (better), 6 (best)
        grid = recessed_grid(width, length, ceiling)
        target = {"good": 4, "better": 5, "best": 6}.get(tier, 5)
        # Use grid positions but limit to target count
        for x, y in grid[:target]:
            fixtures.append(_fixture("recessed", tier, zone_general, x, y))

        # Ceiling fan pre-wire at center
        fixtures.append(
            _fixture("ceiling_fan", tier, zone_general, 0.5, 0.5, is_prewire=True)
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

        # Recessed grid
        grid = recessed_grid(width, length, ceiling)
        target = {"good": 4, "better": 4, "best": 5}.get(tier, 4)
        for x, y in grid[:target]:
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
    """Full bathroom: vanity sconce pair, shower recessed (IC/AT rated), exhaust fan."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        fixtures: list[FixtureAssignment] = []
        zone_vanity = "bath-vanity"
        zone_general = "bath-general"

        # Vanity sconce pair flanking mirror
        fixtures.append(
            _fixture("sconce", tier, zone_vanity, 0.3, 0.1, notes="Vanity sconce, left of mirror")
        )
        fixtures.append(
            _fixture("sconce", tier, zone_vanity, 0.7, 0.1, notes="Vanity sconce, right of mirror")
        )

        # Shower recessed (IC/AT rated wet location)
        fixtures.append(
            _fixture("recessed", tier, zone_general, 0.7, 0.7, notes="IC/AT rated, wet location")
        )

        # Exhaust fan combo
        fixtures.append(
            _fixture("exhaust_fan", tier, zone_general, 0.5, 0.5)
        )

        # Additional recessed for better/best
        if tier in ("better", "best"):
            fixtures.append(
                _fixture("recessed", tier, zone_general, 0.3, 0.5)
            )

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

        # Recessed grid
        grid = recessed_grid(width, length, ceiling)
        # Scale count by tier
        multiplier = {"good": 1.0, "better": 1.15, "best": 1.3}.get(tier, 1.15)
        target = max(4, round(len(grid) * multiplier))
        for x, y in grid[:target]:
            fixtures.append(_fixture("recessed", tier, zone_general, x, y))

        # Ceiling fan pre-wire at center (better and best)
        if tier in ("better", "best"):
            fixtures.append(
                _fixture("ceiling_fan", tier, zone_general, 0.5, 0.5, is_prewire=True)
            )

        # Accent lighting pre-wire along one wall (best only)
        if tier == "best":
            for i in range(3):
                x = 0.2 + 0.3 * i
                fixtures.append(
                    _fixture("recessed", tier, zone_accent, x, 0.95, notes="Accent wall wash", is_prewire=True)
                )

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

        grid = recessed_grid(width, length, ceiling)
        target = max(2, min(4, len(grid)))
        for x, y in grid[:target]:
            fixtures.append(_fixture("recessed", tier, zone, x, y))

        return fixtures


class ClosetRule(RoomRule):
    """Closet / walk-in closet: 1-2 recessed cans."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        fixtures: list[FixtureAssignment] = []
        zone = f"closet-{room.name.lower().replace(' ', '-')}"

        fixtures.append(_fixture("recessed", tier, zone, 0.5, 0.5))

        if room.room_type == "walk_in_closet" or (room.sqft and room.sqft > 40):
            fixtures.append(_fixture("recessed", tier, zone, 0.5, 0.2))

        return fixtures


class DefaultRule(RoomRule):
    """Fallback rule for any room type not specifically handled."""

    def assign(self, room: RoomData, tier: str) -> list[FixtureAssignment]:
        width, length, ceiling = _room_dims(room)
        fixtures: list[FixtureAssignment] = []
        zone = room.name.lower().replace(" ", "-")

        grid = recessed_grid(width, length, ceiling)
        multiplier = {"good": 1.0, "better": 1.1, "best": 1.25}.get(tier, 1.1)
        target = max(2, round(len(grid) * multiplier))
        for x, y in grid[:target]:
            fixtures.append(_fixture("recessed", tier, zone, x, y))

        return fixtures


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

RULE_REGISTRY: dict[str, type[RoomRule]] = {
    "kitchen": KitchenRule,
    "dining": LivingRoomRule,
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
            rule_cls = RULE_REGISTRY.get(room.room_type, DefaultRule)
            rule = rule_cls()
            result[room.name] = rule.assign(room, tier)
        return result
