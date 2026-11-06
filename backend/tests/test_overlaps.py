"""Room boxes the plan reader drew over one another.

The fixture below is the room list the model returned for Morgan's Keel
plan on 6 Nov 2026 (from the production log): an open plan read as three
boxes stacked on one area, bedrooms that took in their closets, and a
primary bedroom that took in its walk-in and bath.
"""

import pytest

from app.models.schemas import FixtureAssignment, RoomData
from app.services.overlaps import carve_enclosed, split_open_plan, untangle
from app.services.placement import drop_stacked_cans

KEEL = """\
BEDROOM 3|bedroom|0.279 0.227|0.213 0.134 0.358 0.369
CLOSET|closet|0.265 0.343|0.213 0.323 0.314 0.369
BATH 2|bathroom|0.269 0.405|0.213 0.376 0.336 0.465
CLOSET 2|closet|0.265 0.495|0.213 0.471 0.314 0.521
BEDROOM 2|bedroom|0.281 0.595|0.213 0.471 0.358 0.705
KITCHEN|kitchen|0.452 0.196|0.362 0.134 0.623 0.395
PANTRY|pantry|0.522 0.156|0.501 0.134 0.542 0.178
DINING|dining|0.557 0.289|0.362 0.134 0.623 0.705
LIVING ROOM|living|0.493 0.522|0.362 0.134 0.623 0.542
LAUNDRY|laundry|0.711 0.156|0.604 0.134 0.788 0.238
LINEN|closet|0.649 0.223|0.626 0.199 0.672 0.238
COAT|closet|0.633 0.405|0.615 0.381 0.653 0.436
WIC|walk_in_closet|0.671 0.323|0.626 0.243 0.711 0.475
PRIMARY BATH|master_bathroom|0.741 0.367|0.716 0.243 0.788 0.475
PRIMARY BEDROOM|master_bedroom|0.710 0.577|0.626 0.243 0.788 0.761
PORCH|porch|0.496 0.764|0.185 0.715 0.815 0.847"""

# The Keel page image was 862 x 596.
ASPECT = 862 / 596


def keel():
    rooms = []
    for line in KEEL.splitlines():
        name, room_type, label, box = line.split("|")
        lx, ly = map(float, label.split())
        x1, y1, x2, y2 = map(float, box.split())
        rooms.append(RoomData(
            name=name, room_type=room_type, position_x=lx, position_y=ly,
            bbox_x1=x1, bbox_y1=y1, bbox_x2=x2, bbox_y2=y2,
        ))
    return rooms


def boxes(rooms):
    return {r.name: (r.bbox_x1, r.bbox_y1, r.bbox_x2, r.bbox_y2) for r in rooms}


def area(box):
    return (box[2] - box[0]) * (box[3] - box[1])


def overlap(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, w) * max(0.0, h)


@pytest.fixture
def fixed():
    return boxes(untangle(keel(), ASPECT))


def test_the_open_plan_becomes_three_rooms_that_do_not_overlap(fixed):
    kitchen, dining, living = fixed["KITCHEN"], fixed["DINING"], fixed["LIVING ROOM"]
    for a, b in ((kitchen, dining), (kitchen, living), (dining, living)):
        assert overlap(a, b) == pytest.approx(0, abs=1e-9)


def test_kitchen_and_dining_sit_side_by_side_above_the_living_room(fixed):
    kitchen, dining, living = fixed["KITCHEN"], fixed["DINING"], fixed["LIVING ROOM"]
    assert kitchen[2] == pytest.approx(dining[0])          # kitchen left, dining right
    assert kitchen[3] == pytest.approx(living[1])          # both above the living room
    assert dining[3] == pytest.approx(living[1])


def test_the_living_room_reaches_the_front_wall(fixed):
    # Zack's item 3: nothing lit for 13 ft in from the front wall.
    assert fixed["LIVING ROOM"][3] == pytest.approx(0.705)


def test_every_room_still_holds_its_own_name(fixed):
    for room in keel():
        x1, y1, x2, y2 = fixed[room.name]
        assert x1 < room.position_x < x2 and y1 < room.position_y < y2, room.name


def test_bedrooms_no_longer_take_in_their_closets(fixed):
    # Zack's item 15.
    assert fixed["BEDROOM 3"][3] == pytest.approx(0.323)   # stops at the closet
    assert fixed["BEDROOM 2"][1] == pytest.approx(0.521)
    assert overlap(fixed["BEDROOM 3"], fixed["CLOSET"]) == pytest.approx(0, abs=1e-9)
    assert overlap(fixed["BEDROOM 2"], fixed["CLOSET 2"]) == pytest.approx(0, abs=1e-9)


def test_the_primary_bedroom_gives_up_its_walk_in_and_bath(fixed):
    # Zack's item 16: the fan sat 3 ft off centre.
    bedroom = fixed["PRIMARY BEDROOM"]
    assert bedroom[1] == pytest.approx(0.475)
    assert overlap(bedroom, fixed["WIC"]) == pytest.approx(0, abs=1e-9)
    assert overlap(bedroom, fixed["PRIMARY BATH"]) == pytest.approx(0, abs=1e-9)


def test_a_small_closet_in_a_corner_does_not_cut_the_room(fixed):
    # The linen closet covers a quarter of the laundry's side; the pantry a
    # sliver of the kitchen's.  Neither is worth reshaping the room for.
    assert fixed["LAUNDRY"] == boxes(keel())["LAUNDRY"]
    assert fixed["KITCHEN"][1] == pytest.approx(0.134)


def test_rooms_that_do_not_overlap_are_left_alone():
    rooms = [
        RoomData(name="A", room_type="kitchen", position_x=0.2, position_y=0.2,
                 bbox_x1=0.1, bbox_y1=0.1, bbox_x2=0.3, bbox_y2=0.3),
        RoomData(name="B", room_type="living", position_x=0.6, position_y=0.6,
                 bbox_x1=0.5, bbox_y1=0.5, bbox_x2=0.7, bbox_y2=0.7),
    ]
    assert boxes(untangle(rooms)) == boxes(rooms)


def test_open_plan_rooms_whose_names_overlap_are_left_as_read():
    rooms = [
        RoomData(name="Kitchen", room_type="kitchen", position_x=0.5, position_y=0.5,
                 bbox_x1=0.1, bbox_y1=0.1, bbox_x2=0.9, bbox_y2=0.9),
        RoomData(name="Dining", room_type="dining", position_x=0.501, position_y=0.5,
                 bbox_x1=0.1, bbox_y1=0.1, bbox_x2=0.9, bbox_y2=0.6),
    ]
    assert boxes(split_open_plan(rooms)) == boxes(rooms)


def test_a_cut_never_pushes_a_room_name_outside_its_box():
    # The closet runs along the bottom, but the bedroom's name is printed
    # below the closet's top edge: cutting there would orphan the name.
    rooms = [
        RoomData(name="Bed", room_type="bedroom", position_x=0.5, position_y=0.8,
                 bbox_x1=0.0, bbox_y1=0.0, bbox_x2=1.0, bbox_y2=1.0),
        RoomData(name="Closet", room_type="closet", position_x=0.3, position_y=0.9,
                 bbox_x1=0.0, bbox_y1=0.7, bbox_x2=0.8, bbox_y2=1.0),
    ]
    assert boxes(carve_enclosed(rooms))["Bed"] == (0.0, 0.0, 1.0, 1.0)


# --- Cans stacked on another room's cans -------------------------------------


def can(notes=""):
    return FixtureAssignment(fixture_type="recessed", position_x=0.5, position_y=0.5, notes=notes)


def room_box(name, x1, y1, x2, y2):
    return RoomData(name=name, room_type="other", bbox_x1=x1, bbox_y1=y1, bbox_x2=x2, bbox_y2=y2)


def test_the_bigger_room_gives_up_a_can_stacked_on_a_closets():
    rooms = [room_box("Laundry", 0.6, 0.1, 0.8, 0.25), room_box("Linen", 0.62, 0.2, 0.67, 0.25)]
    fixtures = {"Laundry": [can(), can()], "Linen": [can()]}
    positions = {"Laundry": [(0.65, 0.22), (0.75, 0.15)], "Linen": [(0.645, 0.225)]}

    kept, kept_positions = drop_stacked_cans(rooms, fixtures, positions)

    assert len(kept["Laundry"]) == 1 and kept_positions["Laundry"] == [(0.75, 0.15)]
    assert len(kept["Linen"]) == 1


def test_cans_in_one_room_and_far_apart_cans_are_kept():
    rooms = [room_box("A", 0.0, 0.0, 0.5, 0.5), room_box("B", 0.5, 0.0, 1.0, 0.5)]
    fixtures = {"A": [can(), can()], "B": [can()]}
    positions = {"A": [(0.30, 0.30), (0.31, 0.31)], "B": [(0.60, 0.30)]}

    kept, kept_positions = drop_stacked_cans(rooms, fixtures, positions)

    assert kept == fixtures and kept_positions == positions


def test_a_wet_rated_can_is_never_dropped():
    rooms = [room_box("Bedroom", 0.0, 0.0, 0.5, 0.5), room_box("Bath", 0.3, 0.3, 0.4, 0.4)]
    wet = can("Over the tub / shower. IC/AT rated, wet location")
    fixtures = {"Bedroom": [can()], "Bath": [wet]}
    positions = {"Bedroom": [(0.35, 0.35)], "Bath": [(0.355, 0.355)]}

    kept, _ = drop_stacked_cans(rooms, fixtures, positions)

    assert kept["Bath"] == [wet]
    assert kept["Bedroom"] == []


# --- Hatteras (Keel's published plan), run through production 6 Nov 2026 ----
#
# Room lists from two production runs of the plan Morgan used, at the size
# she uploaded it (960 px) and full size (2560 px).  Open-plan rooms are given
# the area they shared before the split (the split keeps its outer edges), and
# the primary bedroom its box before the cuts the log records.

HATTERAS_960 = """\
BEDROOM 3|bedroom|0.294 0.251|0.232 0.165 0.368 0.339
CLOSET|closet|0.279 0.355|0.232 0.339 0.326 0.381
BATH 2|bathroom|0.283 0.408|0.232 0.386 0.346 0.469
CLOSET 2|closet|0.279 0.493|0.232 0.473 0.326 0.515
BEDROOM 2|bedroom|0.294 0.592|0.232 0.515 0.368 0.686
KITCHEN|kitchen|0.454 0.228|0.371 0.038 0.615 0.538
PANTRY|pantry|0.520 0.186|0.501 0.165 0.539 0.205
DINING|dining|0.552 0.308|0.371 0.038 0.615 0.538
LIVING ROOM|living|0.493 0.528|0.371 0.038 0.615 0.538
LAUNDRY|laundry|0.696 0.191|0.597 0.165 0.769 0.261
LINEN|closet|0.639 0.246|0.619 0.228 0.660 0.261
WIC|walk_in_closet|0.660 0.331|0.619 0.265 0.698 0.483
COAT|closet|0.625 0.417|0.606 0.391 0.643 0.442
PRIMARY BATH|master_bathroom|0.725 0.379|0.701 0.265 0.769 0.483
PRIMARY BEDROOM|master_bedroom|0.696 0.575|0.619 0.441 0.769 0.702
PORCH|porch|0.495 0.749|0.028 0.696 0.973 0.962"""

HATTERAS_2560 = """\
BEDROOM 3|bedroom|0.295 0.251|0.232 0.166 0.368 0.341
CLOSET|closet|0.279 0.355|0.232 0.341 0.327 0.373
BATH 2|bathroom|0.283 0.411|0.236 0.386 0.347 0.469
CLOSET 2|closet|0.279 0.496|0.232 0.482 0.327 0.513
BEDROOM 2|bedroom|0.295 0.586|0.232 0.513 0.368 0.686
KITCHEN|kitchen|0.454 0.221|0.371 0.038 0.615 0.686
PANTRY|pantry|0.520 0.189|0.500 0.166 0.539 0.209
DINING|dining|0.552 0.308|0.371 0.038 0.615 0.686
LIVING ROOM|living|0.493 0.521|0.371 0.038 0.615 0.686
LAUNDRY|laundry|0.696 0.185|0.606 0.166 0.769 0.261
LINEN|closet|0.639 0.246|0.618 0.228 0.661 0.261
WIC|walk_in_closet|0.660 0.334|0.632 0.243 0.686 0.479
COAT|closet|0.624 0.416|0.606 0.391 0.643 0.442
PRIMARY BATH|master_bathroom|0.725 0.375|0.702 0.323 0.769 0.470
SHR|bathroom|0.733 0.305|0.703 0.269 0.767 0.314
PRIMARY BEDROOM|master_bedroom|0.696 0.568|0.619 0.260 0.769 0.686
PORCH|porch|0.495 0.742|0.028 0.695 0.973 0.962"""

# Where the walls are on the published Hatteras plan, as page fractions.
BACK_WALL, FRONT_WALL = 0.165, 0.686


def parse(text):
    rooms = []
    for line in text.splitlines():
        name, room_type, label, box = line.split("|")
        lx, ly = map(float, label.split())
        x1, y1, x2, y2 = map(float, box.split())
        rooms.append(RoomData(
            name=name, room_type=room_type, position_x=lx, position_y=ly,
            bbox_x1=x1, bbox_y1=y1, bbox_x2=x2, bbox_y2=y2,
        ))
    return rooms


@pytest.mark.parametrize("text, aspect", [(HATTERAS_960, 960 / 678), (HATTERAS_2560, 2560 / 1809)])
def test_hatteras_open_plan_stays_inside_the_house(text, aspect):
    fixed = boxes(untangle(parse(text), aspect))
    kitchen, dining, living = fixed["KITCHEN"], fixed["DINING"], fixed["LIVING ROOM"]
    # Not above the back wall (the kitchen ran to 0.038 on both runs)...
    assert kitchen[1] == pytest.approx(BACK_WALL, abs=0.005)
    assert dining[1] == pytest.approx(BACK_WALL, abs=0.005)
    # ...and the living room reaches the front wall, not a 1 ft sliver.
    assert living[3] == pytest.approx(FRONT_WALL, abs=0.02)
    assert living[3] - living[1] > 0.25
    # Kitchen and dining side by side, living room below them.
    assert kitchen[2] == pytest.approx(dining[0])
    assert kitchen[3] == pytest.approx(living[1]) == pytest.approx(dining[3])


def test_hatteras_primary_bedroom_loses_the_suite_band_across_its_top():
    fixed = boxes(untangle(parse(HATTERAS_2560), 2560 / 1809))
    bedroom = fixed["PRIMARY BEDROOM"]
    # Full width: one run cut the walk-in's column off its left instead,
    # leaving a bedroom half its width with the bath still inside it.
    assert bedroom[0] == pytest.approx(0.619) and bedroom[2] == pytest.approx(0.769)
    assert bedroom[1] == pytest.approx(0.479)
    for suite in ("WIC", "PRIMARY BATH", "SHR"):
        assert overlap(bedroom, fixed[suite]) < 0.1 * area(fixed[suite]), suite


def test_hatteras_bedrooms_lose_their_closets():
    for text in (HATTERAS_960, HATTERAS_2560):
        fixed = boxes(untangle(parse(text)))
        assert overlap(fixed["BEDROOM 3"], fixed["CLOSET"]) == pytest.approx(0, abs=1e-9)
        assert overlap(fixed["BEDROOM 2"], fixed["CLOSET 2"]) == pytest.approx(0, abs=1e-9)


def test_an_open_area_is_not_stretched_through_another_room():
    # A dining room's box stops short of the back wall because the pantry
    # and mudroom are in the way: it must not be pulled through them.
    rooms = [
        RoomData(name="Kitchen", room_type="kitchen", position_x=0.3, position_y=0.5,
                 bbox_x1=0.2, bbox_y1=0.4, bbox_x2=0.6, bbox_y2=0.8),
        RoomData(name="Dining", room_type="dining", position_x=0.5, position_y=0.6,
                 bbox_x1=0.2, bbox_y1=0.4, bbox_x2=0.6, bbox_y2=0.8),
        RoomData(name="Mudroom", room_type="mudroom", position_x=0.4, position_y=0.25,
                 bbox_x1=0.2, bbox_y1=0.1, bbox_x2=0.6, bbox_y2=0.4),
        RoomData(name="Bed", room_type="bedroom", position_x=0.8, position_y=0.3,
                 bbox_x1=0.6, bbox_y1=0.1, bbox_x2=0.9, bbox_y2=0.8),
        RoomData(name="Bath", room_type="bathroom", position_x=0.1, position_y=0.3,
                 bbox_x1=0.0, bbox_y1=0.1, bbox_x2=0.2, bbox_y2=0.8),
    ]
    fixed = boxes(split_open_plan(rooms))
    assert min(fixed["Kitchen"][1], fixed["Dining"][1]) == pytest.approx(0.4)


def test_a_box_drawn_past_the_wall_gives_back_the_rooms_it_overlaps():
    # The 960 px run drew the primary bedroom from 0.441, a foot above its
    # wall, over the bottom of the walk-in and bath (which end at 0.483).
    fixed = boxes(untangle(parse(HATTERAS_960), 960 / 678))
    assert fixed["PRIMARY BEDROOM"][1] == pytest.approx(0.483)
    assert fixed["PRIMARY BEDROOM"][3] == pytest.approx(0.702)
