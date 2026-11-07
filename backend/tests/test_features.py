"""Kitchen, porch and primary bedroom laid out around what is drawn in them.

Hatteras (Keel Custom Homes), positions as the production read put them on
7 Nov 2026, with features read off the drawing.
"""

import math

import pytest

from app.models.schemas import FixtureAssignment, RoomData
from app.services.features import add_missed_closets, apply_features, page_scale, parse_features


def room(name, room_type, box, w, l):
    x1, y1, x2, y2 = box
    return RoomData(name=name, room_type=room_type, width_ft=w, length_ft=l,
                    bbox_x1=x1, bbox_y1=y1, bbox_x2=x2, bbox_y2=y2,
                    position_x=(x1 + x2) / 2, position_y=(y1 + y2) / 2)


def fx(t, notes="", prewire=False):
    return FixtureAssignment(fixture_type=t, notes=notes, is_prewire=prewire)


ROOMS = [
    room("KITCHEN", "kitchen", (0.371, 0.166, 0.513, 0.361), 13.83, 13.0),
    room("LIVING ROOM", "living_room", (0.37, 0.36, 0.617, 0.69), 21.6, 20.0),
    room("PRIMARY BEDROOM", "master_bedroom", (0.618, 0.479, 0.769, 0.686), 13.42, 15.08),
    room("PORCH", "porch", (0.232, 0.695, 0.769, 0.805), 48.33, 7.0),
]

FIXTURES = {
    "KITCHEN": [fx("pendant", "Island pendant 1 of 2", True), fx("recessed"),
                fx("pendant", "Island pendant 2 of 2", True), fx("recessed"),
                fx("under_cabinet", prewire=True), fx("recessed"), fx("recessed")],
    "PRIMARY BEDROOM": [fx("recessed")] * 6 + [fx("ceiling_fan", prewire=True),
                        fx("switched_outlet"), fx("switched_outlet")],
    "LIVING ROOM": [fx("keypad", "Welcome scene keypad, beside the front door")],
    "PORCH": [fx("coach_light", "Entry coach light")]
             + [fx("recessed", "Porch ceiling light, wet-rated")] * 4,
}
POSITIONS = {
    "KITCHEN": [(0.459, 0.286), (0.407, 0.312), (0.459, 0.34), (0.477, 0.312),
                (0.442, 0.175), (0.407, 0.214), (0.477, 0.214)],
    "PRIMARY BEDROOM": [(0.641, 0.514), (0.694, 0.514), (0.746, 0.514), (0.641, 0.651),
                        (0.694, 0.651), (0.746, 0.651), (0.693, 0.582),
                        (0.67, 0.666), (0.761, 0.666)],
    "LIVING ROOM": [(0.585, 0.691)],
    "PORCH": [(0.586, 0.7), (0.3, 0.75), (0.43, 0.75), (0.57, 0.75), (0.7, 0.75)],
}
FEATURES = {
    "kitchen": {"room_name": "KITCHEN", "island": [0.44, 0.253, 0.4775, 0.381],
                "sink": [0.4235, 0.18],
                "cabinet_runs": [[0.40, 0.195, 0.495, 0.195], [0.3975, 0.27, 0.3975, 0.33]]},
    "porch": {"room_name": "PORCH",
              "columns": [[0.23, 0.801], [0.3915, 0.801], [0.6085, 0.801], [0.77, 0.801]],
              "front_door": {"hinge_end": [0.5875, 0.69], "latch_end": [0.5575, 0.69]}},
    "primary_bedroom": {"room_name": "PRIMARY BEDROOM", "headboard_wall": "left",
                        "bed_center": [0.618, 0.6]},
}


@pytest.fixture
def laid_out():
    return apply_features(ROOMS, FIXTURES, POSITIONS, FEATURES)


def of(result, name, kind):
    fixtures, positions = result
    return [(f, p) for f, p in zip(fixtures[name], positions[name]) if f.fixture_type == kind]


def test_no_kitchen_can_is_on_the_island_or_its_edge(laid_out):
    # Zack #8: a can sat on the right edge of the island.
    ix1, iy1, ix2, iy2 = FEATURES["kitchen"]["island"]
    for _, (x, y) in of(laid_out, "KITCHEN", "recessed"):
        assert not (ix1 - 0.01 < x < ix2 + 0.01 and iy1 - 0.01 < y < iy2 + 0.01)


def test_a_can_is_centered_on_the_sink(laid_out):
    sink = [p for f, p in of(laid_out, "KITCHEN", "recessed") if "sink" in f.notes]
    assert sink == [pytest.approx((0.4235, 0.18))]
    assert len(of(laid_out, "KITCHEN", "recessed")) == 4      # moved, not added


def test_pendants_run_along_the_island(laid_out):
    pendants = [p for _, p in of(laid_out, "KITCHEN", "pendant")]
    assert all(x == pytest.approx(0.45875) for x, _ in pendants)
    assert 0.253 < pendants[0][1] < pendants[1][1] < 0.381


def test_under_cabinet_follows_each_cabinet_run(laid_out):
    # Zack #10: one short run, and the range wall had none.
    strips = of(laid_out, "KITCHEN", "under_cabinet")
    assert [p for _, p in strips] == [pytest.approx((0.4475, 0.195)), pytest.approx((0.3975, 0.3))]
    assert all("run" in f.notes for f, _ in strips)


def test_porch_lights_are_centered_on_the_bays(laid_out):
    # Zack #17: three bays between four columns, one light centered in each.
    lights = [p for f, p in of(laid_out, "PORCH", "recessed")]
    assert [round(x, 3) for x, _ in lights] == [0.311, 0.5, 0.689]


def test_the_door_light_is_beside_the_door_not_on_it(laid_out):
    (_, (x, y)), = of(laid_out, "PORCH", "coach_light")
    assert x < 0.5575            # past the latch end, clear of the opening
    assert 0.5575 - x == pytest.approx(1.25 / page_scale(ROOMS)[0], rel=0.05)


def test_primary_cans_flank_the_bed_and_the_fan_is_on_it(laid_out):
    # Zack #16: the bed goes against the left wall, centered at y 0.6.
    fan = of(laid_out, "PRIMARY BEDROOM", "ceiling_fan")[0][1]
    assert fan[1] == pytest.approx(0.6)
    ys = sorted({round(y, 3) for _, (_, y) in of(laid_out, "PRIMARY BEDROOM", "recessed")})
    assert len(ys) == 2 and ys[0] < 0.6 - 0.04 and ys[1] > 0.6 + 0.04
    outlets = of(laid_out, "PRIMARY BEDROOM", "switched_outlet")
    assert all(x < 0.63 for _, (x, _) in outlets)              # on the headboard wall


def test_rooms_without_readable_features_are_left_alone():
    bad = {"kitchen": {"room_name": "KITCHEN", "island": [5, 5, 6, 6], "sink": "by the window"},
           "porch": {"room_name": "PORCH", "columns": []},
           "primary_bedroom": {"room_name": "PRIMARY BEDROOM", "headboard_wall": "ceiling"}}
    fixtures, positions = apply_features(ROOMS, FIXTURES, POSITIONS, bad)
    for name in FIXTURES:
        assert [f.fixture_type for f in fixtures[name]] == [f.fixture_type for f in FIXTURES[name]]
        assert positions[name] == POSITIONS[name]


def test_an_unreadable_reply_changes_nothing():
    assert parse_features("not json") == {}
    assert parse_features(None) == {}
    assert apply_features(ROOMS, FIXTURES, POSITIONS, {}) == (FIXTURES, POSITIONS)


def test_the_front_door_keypad_is_on_the_latch_side_inside(laid_out):
    # Hatteras, 7 Nov 2026: on two of five runs it was on the hinge side.
    (_, (x, y)), = of(laid_out, "LIVING ROOM", "keypad")
    assert x < 0.5575          # past the latch end, away from the hinge at 0.5875
    assert y < 0.69            # inside the house, not on the porch


# Camden at 960 px, 7 Nov 2026: two runs left out both coat closets and both
# linen closets.  The foyer's coat closet sits inside the foyer's box.
CAMDEN = [
    room("Foyer", "foyer", (0.55, 0.55, 0.68, 0.65), 13.25, 7.4),
    room("Living Room", "living_room", (0.43, 0.31, 0.68, 0.55), 14.8, 20.4),
    room("Closet", "closet", (0.70, 0.43, 0.76, 0.47), 5.0, 2.5),
]


def closets(reported):
    return add_missed_closets(CAMDEN, {r.name: [] for r in CAMDEN},
                              {r.name: [] for r in CAMDEN}, {"closets": reported}, "better", 9.0)


def test_a_closet_inside_another_rooms_box_is_added_and_lit():
    rooms, fixtures, positions = closets([{"name": "Coats", "box": [0.655, 0.56, 0.675, 0.61]}])
    (coats,) = [r for r in rooms if r.name == "Coats"]
    assert coats.room_type == "closet"
    assert [f.fixture_type for f in fixtures["Coats"]] == ["recessed"]
    (x, y), = positions["Coats"]
    assert 0.655 <= x <= 0.675 and 0.56 <= y <= 0.61


def test_a_closet_already_read_is_not_added_again():
    rooms, _, _ = closets([{"name": "Closet", "box": [0.70, 0.43, 0.76, 0.47]}])
    assert [r.name for r in rooms] == [r.name for r in CAMDEN]


def test_closets_off_the_house_or_room_sized_are_ignored():
    rooms, _, _ = closets([
        {"name": "Shed", "box": [0.05, 0.05, 0.08, 0.08]},          # outside the house
        {"name": "Storage", "box": [0.45, 0.32, 0.66, 0.54]},       # a whole room
        {"name": "Linen", "box": "by the bath"},
    ])
    assert [r.name for r in rooms] == [r.name for r in CAMDEN]
