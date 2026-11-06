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
    ambient_grid,
    even_grid,
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


def test_ambient_grid_handles_degenerate_rooms():
    """Zero or negative dimensions must not crash or return an empty grid."""
    for width, length in [(0, 10), (10, 0), (-5, 10), (3, 3)]:
        grid = ambient_grid(width, length)
        assert grid
        assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in grid)


def test_ambient_grid_scales_with_room_size():
    small = ambient_grid(10, 10)
    large = ambient_grid(30, 30)
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


# Morgan: the ambient layer read as very busy, the Keel plan worst of all.
# Cans went in at half the ceiling height, and the kitchen got a ring of them
# on 36" centres — ten-plus in a 13' kitchen, sixteen in a 21' living room.


def recessed_count(room_type, width, length, tier="better", ceiling=9):
    fixtures = LightingEngine().process_single_room(
        room(room_type, width_ft=width, length_ft=length,
             sqft=width * length, ceiling_height_ft=ceiling),
        tier,
    )
    return len(cans(fixtures))


@pytest.mark.parametrize(
    "room_type, width, length, at_most",
    [
        ("kitchen", 13, 10, 4),
        ("kitchen", 13, 16, 6),
        ("living", 21, 20, 8),
        ("dining", 10, 10, 2),
        ("laundry", 8, 6.67, 1),
        ("laundry", 12, 6, 2),
        ("walk_in_closet", 7, 6, 1),
        ("closet", 4, 2.5, 1),
        ("bathroom", 8, 5, 1),
        ("den", 11, 10, 2),
    ],
)
def test_ambient_cans_are_not_crowded(room_type, width, length, at_most):
    assert 1 <= recessed_count(room_type, width, length) <= at_most


@pytest.mark.parametrize("room_type", ["kitchen", "living", "den", "laundry"])
def test_no_two_ambient_cans_are_closer_than_six_feet(room_type):
    width, length = 21, 20
    fixtures = LightingEngine().process_single_room(
        room(room_type, width_ft=width, length_ft=length, sqft=width * length), "best"
    )
    general = [
        (f.position_x * width, f.position_y * length)
        for f in fixtures
        if f.fixture_type == "recessed" and "accent" not in f.zone
    ]
    for i, (x1, y1) in enumerate(general):
        for x2, y2 in general[i + 1:]:
            # Kitchens run 0.8x the room spacing, floored at 6 ft: 4.8 ft.
            assert ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5 >= 4.8


def test_a_kitchen_still_gets_light_across_the_room():
    fixtures = LightingEngine().process_single_room(
        room("kitchen", width_ft=13, length_ft=10, sqft=130), "good"
    )
    points = cans(fixtures)
    assert len(points) >= 4
    assert is_full_grid(points)


def test_a_bigger_package_never_has_fewer_cans():
    for room_type, w, l in [("living", 21, 20), ("kitchen", 16, 14), ("den", 14, 12)]:
        counts = [recessed_count(room_type, w, l, t) for t in TIERS]
        assert counts == sorted(counts), (room_type, counts)


# Zack's markup of the Keel plan after the spacing fix.


def of_type(fixtures, fixture_type):
    return [f for f in fixtures if f.fixture_type == fixture_type]


def test_dining_gets_a_chandelier_and_a_pair_of_cans_not_a_fan():
    for tier in TIERS:
        fixtures = LightingEngine().process_single_room(
            room("dining", width_ft=12, length_ft=11, sqft=132), tier
        )
        assert len(of_type(fixtures, "chandelier")) == 1
        assert not of_type(fixtures, "ceiling_fan")
        assert len(cans(fixtures)) == 2
        # The cans flank the chandelier rather than sitting under it.
        for x, y in cans(fixtures):
            assert (x, y) != pytest.approx((0.5, 0.5), abs=0.05)


@pytest.mark.parametrize("tier", TIERS)
def test_an_island_never_gets_a_single_pendant(tier):
    fixtures = LightingEngine().process_single_room(
        room("kitchen", width_ft=13, length_ft=13.8, sqft=180), tier
    )
    assert len(of_type(fixtures, "pendant")) >= 2


def test_a_long_kitchen_gets_three_pendants():
    fixtures = LightingEngine().process_single_room(
        room("kitchen", width_ft=18, length_ft=13, sqft=234), "better"
    )
    assert len(of_type(fixtures, "pendant")) == 3


@pytest.mark.parametrize("tier", TIERS)
def test_a_bath_has_one_vanity_light_and_a_wet_can_first(tier):
    fixtures = LightingEngine().process_single_room(
        room("bathroom", width_ft=8, length_ft=5, sqft=40), tier
    )
    assert len(of_type(fixtures, "sconce")) == 1
    recessed = of_type(fixtures, "recessed")
    assert recessed and "wet location" in recessed[0].notes


def test_a_large_primary_bath_gets_a_light_over_each_sink_and_a_shower_can():
    fixtures = LightingEngine().process_single_room(
        room("master_bathroom", width_ft=11, length_ft=9, sqft=99), "better"
    )
    assert len(of_type(fixtures, "sconce")) == 2
    recessed = of_type(fixtures, "recessed")
    assert len(recessed) == 2
    assert sum("wet location" in f.notes for f in recessed) == 1


def test_walk_in_closet_cans_sit_on_the_aisle():
    fixtures = LightingEngine().process_single_room(
        room("walk_in_closet", width_ft=6, length_ft=12, sqft=72), "better"
    )
    points = cans(fixtures)
    assert len(points) == 2
    assert all(x == pytest.approx(0.5) for x, _ in points)


def test_the_accent_layer_has_something_in_it():
    fixtures = LightingEngine().process_single_room(
        room("living", width_ft=21.6, length_ft=20, sqft=432), "better"
    )
    assert len(of_type(fixtures, "accent")) >= 2


def test_scene_keypads_go_in_the_shared_rooms_and_the_primary():
    engine = LightingEngine()
    for room_type in ("living", "kitchen", "master_bedroom"):
        fixtures = engine.process_single_room(room(room_type), "better")
        assert len(of_type(fixtures, "keypad")) == 1, room_type
    for room_type in ("bedroom", "bathroom", "closet", "walk_in_closet"):
        fixtures = engine.process_single_room(room(room_type), "better")
        assert not of_type(fixtures, "keypad"), room_type


def test_keypads_stay_out_of_the_fixture_bom():
    from app.services.estimate_calculator import calculate_estimate

    rooms = [{"name": "Living", "room_type": "living", "sqft": 300,
              "width_ft": 20, "length_ft": 15}]
    result = calculate_estimate(rooms, pct_good=0, pct_better=100, pct_best=0)

    assert "keypad" not in result["summary"]["fixtures_by_type"]
    assert all(
        f["fixture_type"] != "keypad" for f in result["rooms"][0]["fixtures"]
    )
