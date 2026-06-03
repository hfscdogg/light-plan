"""Orchestrate estimate calculation: rooms → tier allocation → fixtures → summary.

Ties together room_templates, tier_allocator, and the existing LightingEngine
to produce a complete fixture schedule with budget totals from form inputs.
"""

import re

from app.models.schemas import FixtureAssignment, RoomData
from app.services.lighting_engine import LightingEngine
from app.services.tier_allocator import allocate_tiers


def _parse_msrp(msrp_range: str) -> tuple[float, float]:
    """Parse '$80-120' or '$350-500' into (lo, hi) floats."""
    if not msrp_range:
        return (0.0, 0.0)
    nums = re.findall(r"[\d,]+\.?\d*", msrp_range.replace(",", ""))
    if len(nums) >= 2:
        return (float(nums[0]), float(nums[1]))
    if len(nums) == 1:
        v = float(nums[0])
        return (v, v)
    return (0.0, 0.0)


def calculate_estimate(
    rooms: list[dict],
    pct_good: int,
    pct_better: int,
    pct_best: int,
) -> dict:
    """Run the full estimate calculation.

    Args:
        rooms: list of room dicts with name, room_type, sqft, width_ft,
               length_ft, ceiling_height_ft
        pct_good/better/best: tier allocation percentages (must sum to 100)

    Returns dict with:
        rooms: list of room dicts with assigned_tier and fixtures added
        summary: {total_fixtures, total_prewires, budget_low, budget_high,
                  fixtures_by_type, rooms_by_tier}
    """
    rooms = allocate_tiers(rooms, pct_good, pct_better, pct_best)

    engine = LightingEngine()
    total_fixtures = 0
    total_prewires = 0
    budget_low = 0.0
    budget_high = 0.0
    fixtures_by_type: dict[str, int] = {}
    rooms_by_tier: dict[str, int] = {"good": 0, "better": 0, "best": 0}

    for room in rooms:
        room_data = RoomData(
            name=room["name"],
            room_type=room["room_type"],
            sqft=room.get("sqft"),
            width_ft=room.get("width_ft"),
            length_ft=room.get("length_ft"),
            ceiling_height_ft=room.get("ceiling_height_ft", 9.0),
        )
        tier = room["assigned_tier"]
        fixtures = engine.process_single_room(room_data, tier)

        room["fixtures"] = [
            {
                "fixture_type": f.fixture_type,
                "product_sku": f.product_sku,
                "product_desc": f.product_desc,
                "msrp_range": f.msrp_range,
                "zone": f.zone,
                "notes": f.notes,
                "is_prewire": f.is_prewire,
            }
            for f in fixtures
        ]

        rooms_by_tier[tier] = rooms_by_tier.get(tier, 0) + 1
        for f in fixtures:
            total_fixtures += 1
            if f.is_prewire:
                total_prewires += 1
            lo, hi = _parse_msrp(f.msrp_range)
            budget_low += lo
            budget_high += hi
            fixtures_by_type[f.fixture_type] = (
                fixtures_by_type.get(f.fixture_type, 0) + 1
            )

    return {
        "rooms": rooms,
        "summary": {
            "total_fixtures": total_fixtures,
            "total_prewires": total_prewires,
            "budget_low": round(budget_low),
            "budget_high": round(budget_high),
            "fixtures_by_type": fixtures_by_type,
            "rooms_by_tier": rooms_by_tier,
        },
    }
