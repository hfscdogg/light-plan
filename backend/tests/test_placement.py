"""Where each fixture lands on the drawing.

The tool is only worth using if the overlay is a starting point a rep can
refine, not one they have to rebuild. Two failures made that worse than it
looked: fixtures that resolved to the same point drew as a single marker, so
the rep dragged one icon and found another underneath; and the placement
model's answers were thrown away whenever it echoed a room or fixture name
back in a different shape than we sent it.
"""

import math

import pytest

from app.models.schemas import FixtureAssignment, RoomData
from app.services.placement import (
    MIN_SEPARATION,
    compute_plan_positions,
    match_key,
    resolve_name,
    room_bounds,
    separate_overlapping,
)
from app.services.plan_parser import _as_fraction
from app.routers.plans import _resolve_plan_positions


def fixture(fixture_type, x, y):
    return FixtureAssignment(fixture_type=fixture_type, position_x=x, position_y=y)


def room(name, x1, y1, x2, y2, **kw):
    return RoomData(
        name=name, room_type=kw.pop("room_type", "other"),
        bbox_x1=x1, bbox_y1=y1, bbox_x2=x2, bbox_y2=y2, **kw,
    )


def gaps(positions):
    """Every pairwise distance between the markers in one room."""
    return [
        math.hypot(a[0] - b[0], a[1] - b[1])
        for i, a in enumerate(positions)
        for b in positions[i + 1 :]
    ]


def assert_all_separated(positions):
    assert len(set(positions)) == len(positions), f"fixtures share a point: {positions}"
    if len(positions) > 1:
        assert min(gaps(positions)) >= MIN_SEPARATION, (
            f"markers closer than {MIN_SEPARATION} draw as one: {positions}"
        )


# --- Fixtures that used to land on top of each other ---------------------


def test_two_island_pendants_keep_the_spacing_the_engine_gave_them():
    """The kitchen rule spaces a second island pendant deliberately.

    Both pendants were being forced to the room's geometric centre, which
    collapsed them onto one point and threw that spacing away.
    """
    kitchen = room("Kitchen", 0.10, 0.10, 0.40, 0.40)
    positions = compute_plan_positions(
        [kitchen],
        {"Kitchen": [fixture("pendant", 0.5, 0.4), fixture("pendant", 0.35, 0.4)]},
    )["Kitchen"]

    assert_all_separated(positions)
    # 0.5 and 0.35 across a 0.30-wide box are 0.045 apart; that is the layout
    # the engine asked for, not a nudge applied afterwards.
    assert positions == [(0.25, 0.22), (0.205, 0.22)]


def test_a_ceiling_fan_still_hangs_in_the_middle_of_the_room():
    """The centring rule existed for this; it has to survive its removal."""
    bedroom = room("Primary Bedroom", 0.60, 0.50, 0.85, 0.75)
    positions = compute_plan_positions(
        [bedroom], {"Primary Bedroom": [fixture("ceiling_fan", 0.5, 0.5)]}
    )["Primary Bedroom"]

    assert positions == [(0.725, 0.625)]


def test_a_fan_and_a_pendant_in_one_room_do_not_stack():
    great = room("Great Room", 0.50, 0.10, 0.90, 0.50)
    positions = compute_plan_positions(
        [great],
        {"Great Room": [fixture("ceiling_fan", 0.5, 0.5), fixture("pendant", 0.25, 0.7)]},
    )["Great Room"]

    assert_all_separated(positions)


def test_a_room_we_could_not_locate_does_not_become_one_pile():
    """No bbox and no label position means we genuinely do not know where the
    room is. The fixtures still have to be individually draggable."""
    positions = compute_plan_positions(
        [RoomData(name="Pantry", room_type="pantry")],
        {"Pantry": [fixture("recessed", 0.3, 0.3), fixture("recessed", 0.7, 0.7)]},
    )["Pantry"]

    assert_all_separated(positions)


def test_a_full_room_of_recessed_cans_is_never_overlapping():
    kitchen = room("Kitchen", 0.20, 0.30, 0.40, 0.50)
    cans = [fixture("recessed", (i % 4) / 4, (i // 4) / 4) for i in range(12)]

    assert_all_separated(compute_plan_positions([kitchen], {"Kitchen": cans})["Kitchen"])


# --- The separation pass itself ------------------------------------------


def test_identical_points_are_pushed_apart():
    assert_all_separated(separate_overlapping([(0.5, 0.5)] * 5, (0.3, 0.3, 0.7, 0.7)))


def test_separated_fixtures_are_left_exactly_where_they_were():
    wanted = [(0.35, 0.35), (0.55, 0.35), (0.35, 0.65)]

    assert separate_overlapping(wanted, (0.3, 0.3, 0.7, 0.7)) == wanted


def test_a_displaced_fixture_stays_in_its_room():
    bounds = (0.30, 0.30, 0.50, 0.50)
    positions = separate_overlapping([(0.4, 0.4)] * 6, bounds)

    x1, y1, x2, y2 = bounds
    for x, y in positions:
        assert x1 <= x <= x2 and y1 <= y <= y2, f"{(x, y)} left the room"


def test_a_displaced_fixture_stays_near_where_it_belonged():
    """Separating markers must not fling a fixture across the room."""
    positions = separate_overlapping([(0.5, 0.5)] * 4, (0.1, 0.1, 0.9, 0.9))

    for x, y in positions:
        assert math.hypot(x - 0.5, y - 0.5) <= MIN_SEPARATION * 3


def test_a_tiny_room_still_gets_distinct_points():
    """A closet is smaller than the separation radius; overlapping markers are
    still worse than slightly tight ones."""
    positions = separate_overlapping([(0.5, 0.5)] * 3, (0.49, 0.49, 0.51, 0.51))

    assert len(set(positions)) == 3


def test_a_room_with_no_bounds_is_held_on_the_sheet():
    for x, y in separate_overlapping([(0.5, 0.5)] * 8, None):
        assert 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0


# --- Reading the placement model's answer --------------------------------


@pytest.mark.parametrize(
    "written,ours",
    [
        ("Kitchen", "Kitchen"),
        ("KITCHEN", "Kitchen"),
        ("  Kitchen  ", "Kitchen"),
        ("ceiling fan", "ceiling_fan"),
        ("Ceiling Fan", "ceiling_fan"),
        ("ceiling-fan", "ceiling_fan"),
        ("recessed light", "recessed"),
        ("Bathroom", "Bath"),
    ],
)
def test_names_the_model_echoed_back_resolve_to_ours(written, ours):
    assert resolve_name(written, [ours]) == ours


def test_an_ambiguous_answer_is_dropped_rather_than_guessed():
    """Assigning a fixture to the wrong room is worse than not placing it."""
    assert resolve_name("Bathroom", ["Bath", "Bathro"]) is None


def test_an_unrelated_name_does_not_match():
    assert resolve_name("Garage", ["Kitchen", "Primary Bedroom"]) is None


def test_an_empty_name_does_not_match():
    assert resolve_name("", ["Kitchen"]) is None
    assert resolve_name("   ", ["Kitchen"]) is None


def test_the_six_overlay_types_never_collide():
    types = ["recessed", "pendant", "sconce", "ceiling_fan", "coach_light", "exhaust_fan"]
    for name in types:
        assert resolve_name(name, types) == name


def test_match_key_ignores_shape_not_content():
    assert match_key("Ceiling Fan") == match_key("ceiling_fan") == "ceilingfan"
    assert match_key("Bedroom 2") != match_key("Bedroom 3")


@pytest.mark.parametrize(
    "written,expected",
    [
        (0.42, 0.42),
        (0, 0.0),
        (1, 1.0),
        ("0.42", 0.42),
        ("  0.42 ", 0.42),
        ("42%", 0.42),
        (42, 0.42),          # a bare percentage
        (100, 1.0),
    ],
)
def test_coordinates_are_read_as_a_fraction_of_the_sheet(written, expected):
    assert _as_fraction(written) == pytest.approx(expected)


@pytest.mark.parametrize(
    "written", [None, True, False, "", "left", "N/A", -0.5, 101, float("nan"),
                float("inf"), [0.5], {"x": 0.5}],
)
def test_an_unusable_coordinate_is_refused(written):
    """Refusing it drops the fixture back to its algorithmic spot; accepting
    it used to park the fixture in the top-left corner of the sheet."""
    assert _as_fraction(written) is None


# --- Merging the model's placements with the algorithmic layout ----------


class StubParser:
    def __init__(self, placements):
        self.placements = placements

    def place_fixtures_on_plan(self, *args, **kwargs):
        return self.placements


ROOMS = [room("Kitchen", 0.10, 0.10, 0.40, 0.40, room_type="kitchen")]
FIXTURES = {
    "Kitchen": [fixture("recessed", 0.2, 0.2), fixture("pendant", 0.5, 0.4)]
}
VISION = [(0.15, 0.15, "recessed"), (0.30, 0.30, "pendant")]


def resolve(placements):
    return _resolve_plan_positions(
        StubParser(placements), "plan.png", "png", ROOMS, FIXTURES
    )["Kitchen"]


@pytest.mark.parametrize(
    "echoed_room,echoed_types",
    [
        ("Kitchen", ("recessed", "pendant")),
        ("KITCHEN", ("recessed", "pendant")),
        (" Kitchen ", ("recessed", "pendant")),
        ("Kitchen", ("recessed light", "Pendant")),
        ("kitchen", ("Recessed", "pendant light")),
    ],
)
def test_placements_survive_however_the_model_spelled_the_names(
    echoed_room, echoed_types
):
    """Any of these used to discard the model's work for the whole room and
    fall back to the grid, which is exactly the overlay Zack had to redo."""
    placements = {
        echoed_room: [(x, y, t) for (x, y, _), t in zip(VISION, echoed_types)]
    }

    assert resolve(placements) == [(0.15, 0.15), (0.3, 0.3)]


def test_a_room_the_model_invented_is_refused():
    assert resolve({"Garage": VISION}) != [(0.15, 0.15), (0.3, 0.3)]


def test_a_fixture_type_that_is_not_in_the_room_is_refused():
    placements = {"Kitchen": [(0.15, 0.15, "sconce"), (0.30, 0.30, "pendant")]}
    positions = resolve(placements)

    assert (0.15, 0.15) not in positions
    assert (0.3, 0.3) in positions


def test_a_failed_placement_call_still_produces_a_usable_overlay():
    class Failing:
        def place_fixtures_on_plan(self, *args, **kwargs):
            raise RuntimeError("429 RESOURCE_EXHAUSTED")

    positions = _resolve_plan_positions(
        Failing(), "plan.png", "png", ROOMS, FIXTURES
    )["Kitchen"]

    assert_all_separated(positions)


def test_the_merged_overlay_is_never_overlapping():
    """The model places some fixtures and the grid fills in the rest; the two
    layouts know nothing about each other, so the result has to be checked."""
    fixtures = {"Kitchen": [fixture("recessed", i / 8, 0.5) for i in range(8)]}
    placements = {"Kitchen": [(0.20, 0.20, "recessed")] * 3}

    positions = _resolve_plan_positions(
        StubParser(placements), "plan.png", "png", ROOMS, fixtures
    )["Kitchen"]

    assert_all_separated(positions)


def test_the_log_says_how_much_of_the_overlay_the_model_placed(caplog):
    """The split between model and grid placements is what says whether the
    overlay is a good starting point or something the rep has to rebuild."""
    placements = {"Kitchen": [(0.15, 0.15, "recessed")]}

    with caplog.at_level("INFO"):
        _resolve_plan_positions(
            StubParser(placements), "plan.png", "png", ROOMS, FIXTURES
        )

    assert any(
        "1 of 2 fixtures from Vision, 1 from the grid" in r.message
        for r in caplog.records
    ), [r.message for r in caplog.records]
