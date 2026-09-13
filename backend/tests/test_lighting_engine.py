"""Fixture rules engine.

Whatever the model does or fails to do, the engine decides what a room gets.
The upload path treats its output as the source of truth for the quote, so
"no fixtures" must never be a valid answer for a parsed room.
"""

import pytest

from app.models.schemas import RoomData
from app.services.lighting_engine import RULE_REGISTRY, LightingEngine, recessed_grid

TIERS = ["good", "better", "best"]


def room(room_type="bedroom", name="Room", **kw):
    return RoomData(
        name=name, room_type=room_type,
        width_ft=kw.get("width_ft", 12), length_ft=kw.get("length_ft", 14),
        sqft=kw.get("sqft", 168), ceiling_height_ft=kw.get("ceiling_height_ft", 9),
    )


@pytest.mark.parametrize("room_type", sorted(RULE_REGISTRY))
@pytest.mark.parametrize("tier", TIERS)
def test_every_room_type_gets_fixtures(room_type, tier):
    fixtures = LightingEngine().process_single_room(room(room_type), tier)
    assert fixtures, f"{room_type} at tier {tier} produced no fixtures"


@pytest.mark.parametrize("tier", TIERS)
def test_unknown_room_type_falls_back_rather_than_producing_nothing(tier):
    fixtures = LightingEngine().process_single_room(room("wine_cellar"), tier)
    assert fixtures


@pytest.mark.parametrize("room_type", sorted(RULE_REGISTRY))
def test_fixtures_carry_pricing_for_every_room_type(room_type):
    """A fixture with no SKU or price is a hole in the builder's quote."""
    for fixture in LightingEngine().process_single_room(room(room_type), "better"):
        assert fixture.product_sku, f"{room_type}/{fixture.fixture_type} has no SKU"
        assert fixture.msrp_range, f"{room_type}/{fixture.fixture_type} has no price"


@pytest.mark.parametrize("room_type", sorted(RULE_REGISTRY))
def test_positions_stay_inside_the_room(room_type):
    for fixture in LightingEngine().process_single_room(room(room_type), "better"):
        assert 0.0 <= fixture.position_x <= 1.0
        assert 0.0 <= fixture.position_y <= 1.0


def test_tier_changes_the_products():
    """Zack's report: toggling Good/Better/Best changed nothing on screen."""
    engine = LightingEngine()
    skus = {
        tier: {f.product_sku for f in engine.process_single_room(room("kitchen"), tier)}
        for tier in TIERS
    }

    assert skus["good"] != skus["better"] != skus["best"]
    assert any(s.startswith("KET-") for s in skus["best"])


def test_missing_dimensions_still_produce_a_layout():
    """The parser often returns a room with no width or length."""
    bare = RoomData(name="Bonus", room_type="bonus_room")
    assert LightingEngine().process_single_room(bare, "better")


def test_process_rooms_covers_every_room():
    rooms = [room("kitchen", name="Kitchen"), room("bedroom", name="Bed 2")]
    result = LightingEngine().process_rooms(rooms, "better")

    assert set(result) == {"Kitchen", "Bed 2"}
    assert all(fixtures for fixtures in result.values())


def test_recessed_grid_handles_degenerate_rooms():
    """Zero or negative dimensions must not crash or return an empty grid."""
    for width, length in [(0, 10), (10, 0), (-5, 10), (3, 3)]:
        grid = recessed_grid(width, length)
        assert grid
        assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in grid)


def test_recessed_grid_scales_with_room_size():
    small = recessed_grid(10, 10)
    large = recessed_grid(30, 30)
    assert len(large) > len(small)
