"""Room coordinates written as percentages.

gemini-3.1-pro-preview (the model new API keys get, since gemini-2.5-pro is
closed to them) writes room labels and boxes as 0-100 percentages, sometimes
mixed with 0-1 fractions in one room.  Read raw, every room landed off the
sheet with a negative size and all its fixtures piled into one corner.
"""

import json

import pytest

from app.services.plan_parser import PlanParser


@pytest.fixture
def parser():
    return PlanParser.__new__(PlanParser)


def read_one(parser, **coords):
    (room,) = parser._parse_response(
        json.dumps([{"name": "Bedroom", "room_type": "bedroom", **coords}])
    )
    return room


def test_percentages_are_read_as_fractions(parser):
    room = read_one(
        parser, label_x=44.8, label_y=39.6,
        bbox_x1=28.6, bbox_y1=26.0, bbox_x2=61.0, bbox_y2=52.0,
    )

    assert (room.position_x, room.position_y) == pytest.approx((0.448, 0.396))
    assert (room.bbox_x1, room.bbox_y1, room.bbox_x2, room.bbox_y2) == pytest.approx(
        (0.286, 0.26, 0.61, 0.52)
    )


def test_a_room_mixing_fractions_and_percentages_is_read_consistently(parser):
    """The 21:53 upload: fraction boxes with percentage label heights."""
    room = read_one(
        parser, label_x=0.442, label_y=45.0,
        bbox_x1=0.356, bbox_y1=0.380, bbox_x2=0.646, bbox_y2=0.519,
    )

    assert room.position_y == pytest.approx(0.45)
    assert room.bbox_x1 < room.position_x < room.bbox_x2
    assert room.bbox_y1 < room.position_y < room.bbox_y2


def test_fractions_are_unchanged(parser):
    room = read_one(
        parser, label_x=0.5, label_y=0.25,
        bbox_x1=0.4, bbox_y1=0.2, bbox_x2=0.6, bbox_y2=0.3,
    )

    assert (room.position_x, room.position_y) == (0.5, 0.25)
    assert (room.bbox_x1, room.bbox_y1, room.bbox_x2, room.bbox_y2) == (0.4, 0.2, 0.6, 0.3)


def test_a_reversed_box_is_put_the_right_way_round(parser):
    room = read_one(parser, bbox_x1=0.6, bbox_y1=0.3, bbox_x2=0.4, bbox_y2=0.2)

    assert (room.bbox_x1, room.bbox_y1, room.bbox_x2, room.bbox_y2) == (0.4, 0.2, 0.6, 0.3)
    assert (room.position_x, room.position_y) == pytest.approx((0.5, 0.25))


def test_a_box_with_an_unreadable_corner_is_dropped(parser):
    """Half a box is no box: the room falls back to its label position."""
    room = read_one(
        parser, label_x=0.5, label_y=0.5,
        bbox_x1=0.4, bbox_y1="n/a", bbox_x2=0.6, bbox_y2=0.6,
    )

    assert room.bbox_x1 is None and room.bbox_y2 is None
    assert (room.position_x, room.position_y) == (0.5, 0.5)
