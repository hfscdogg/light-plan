"""Fixture rules engine.

Whatever the model does or fails to do, the engine decides what a room gets.
The upload path treats its output as the source of truth for the quote, so
"no fixtures" must never be a valid answer for a parsed room.
"""

import pytest

from app.models.schemas import RoomData
from app.services.lighting_engine import (
    RULE_REGISTRY,
    LightingEngine,
    even_grid,
    recessed_grid,
)

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


# Marshall: the cans did not sit on an even grid.  Bedrooms took the first few
# points of a bigger grid — corners, then whatever came next — and a can at
# the centre sat under the ceiling fan and got shoved aside.


def cans(fixtures):
    return [(f.position_x, f.position_y) for f in fixtures if f.fixture_type == "recessed"]


def fan(fixtures):
    return [(f.position_x, f.position_y) for f in fixtures if f.fixture_type == "ceiling_fan"]


def is_full_grid(points):
    """Every row has the same columns: a rows x cols grid, nothing missing."""
    xs = sorted({round(x, 4) for x, _ in points})
    ys = sorted({round(y, 4) for _, y in points})
    return len(points) == len(xs) * len(ys) and {
        (round(x, 4), round(y, 4)) for x, y in points
    } == {(x, y) for x in xs for y in ys}


@pytest.mark.parametrize(
    "room_type, tier, expected",
    [
        ("master_bedroom", "good", 4),
        ("master_bedroom", "better", 6),
        ("master_bedroom", "best", 6),
        ("bedroom", "good", 4),
        ("bedroom", "better", 4),
        ("bedroom", "best", 6),
    ],
)
def test_bedroom_cans_form_a_full_grid(room_type, tier, expected):
    fixtures = LightingEngine().process_single_room(
        room(room_type, width_ft=15.92, length_ft=15.5), tier
    )
    points = cans(fixtures)

    assert len(points) == expected
    assert is_full_grid(points), points
    # Symmetric about the centre of the room.
    assert sum(x for x, _ in points) / len(points) == pytest.approx(0.5)
    assert sum(y for _, y in points) / len(points) == pytest.approx(0.5)


@pytest.mark.parametrize("room_type", ["master_bedroom", "bedroom", "living", "dining"])
@pytest.mark.parametrize("tier", TIERS)
def test_no_can_sits_under_the_fan(room_type, tier):
    # 15 x 15 at 9 ft gives the living rule a 3x3 grid, centre included.
    fixtures = LightingEngine().process_single_room(
        room(room_type, width_ft=15, length_ft=15), tier
    )
    for fx, fy in fan(fixtures):
        for x, y in cans(fixtures):
            assert (x, y) != pytest.approx((fx, fy), abs=0.05)


def test_the_grid_runs_the_long_way_of_the_room():
    # Six cans in a room twice as long as it is wide: 2 across, 3 down.
    points = even_grid(10, 20, 6)

    assert len({x for x, _ in points}) == 2
    assert len({y for _, y in points}) == 3


def test_a_room_too_small_to_inset_still_gets_its_cans():
    points = even_grid(3, 3, 4)

    assert len(points) == 4
    assert all(0 < x < 1 and 0 < y < 1 for x, y in points)
    assert len(set(points)) == 4
