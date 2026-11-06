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


# --- Room outlines written some other way --------------------------------------
#
# 2 of 6 full-size Hatteras runs came back with every room named and none
# outlined: whatever the model wrote for the boxes was thrown away, and each
# room's fixtures were laid out around its name.

import pytest  # noqa: E402

from app.services.plan_parser import PlanParser  # noqa: E402


@pytest.fixture
def reader():
    p = PlanParser.__new__(PlanParser)
    p._sent_size = (1600, 1131)
    return p


@pytest.mark.parametrize(
    "item",
    [
        {"bbox_x1": 0.2, "bbox_y1": 0.3, "bbox_x2": 0.4, "bbox_y2": 0.6},
        {"bbox_x1": "20%", "bbox_y1": "30%", "bbox_x2": "40%", "bbox_y2": "60%"},
        {"bbox_x1": 20, "bbox_y1": 30, "bbox_x2": 40, "bbox_y2": 60},
        {"bbox": [0.2, 0.3, 0.4, 0.6]},
        {"bbox": {"x1": 0.2, "y1": 0.3, "x2": 0.4, "y2": 0.6}},
        {"bounding_box": {"xmin": 0.2, "ymin": 0.3, "xmax": 0.4, "ymax": 0.6}},
        {"box_2d": [300, 200, 600, 400]},  # Gemini's own: y first, 0-1000
    ],
)
def test_every_way_of_writing_a_box_reads_the_same(reader, item):
    assert reader._read_box(item) == pytest.approx([0.2, 0.3, 0.4, 0.6], abs=0.002)


def test_a_box_in_pixels_is_read_against_the_image_sent():
    p = PlanParser.__new__(PlanParser)
    p._sent_size = (2560, 1809)
    box = p._read_box({"bbox_x1": 512, "bbox_y1": 542.7, "bbox_x2": 1024, "bbox_y2": 1085.4})
    assert box == pytest.approx([0.2, 0.3, 0.4, 0.6], abs=0.002)


def test_a_box_that_cannot_be_read_is_none(reader):
    assert reader._read_box({}) is None
    assert reader._read_box({"bbox": [0.1, 0.2]}) is None
    assert reader._read_box({"bbox": ["a", "b", "c", "d"]}) is None


def test_a_large_image_is_shrunk_for_the_room_read(tmp_path, monkeypatch):
    import base64, io, json
    from PIL import Image, ImageDraw

    plan = tmp_path / "plan.png"
    img = Image.new("RGB", (2560, 1809), "white")
    ImageDraw.Draw(img).rectangle([600, 400, 1960, 1400], outline="black", width=10)
    img.save(plan)

    seen = []

    def fake_call(self, images):
        with Image.open(io.BytesIO(base64.standard_b64decode(images[0][0]))) as sent:
            seen.append(sent.size)
        return json.dumps([{"name": "Living", "room_type": "living", "label_x": 0.5,
                            "label_y": 0.5, "box_2d": [100, 100, 900, 900]}])

    monkeypatch.setattr(PlanParser, "_call_gemini", fake_call)
    rooms, _, _ = PlanParser.__new__(PlanParser).parse_plan(str(plan), "png")

    assert max(seen[0]) <= 1600
    assert rooms[0].bbox_x1 is not None


def test_a_small_image_still_reads_0_to_1000_as_0_to_1000():
    # The 960 x 678 Hatteras upload: the model wrote Bath 2 on the 0-1000
    # scale, and reading it as pixels stretched it 1.47x down the page.
    p = PlanParser.__new__(PlanParser)
    p._sent_size = (960, 678)
    box = p._read_box({"bbox_x1": 236, "bbox_y1": 386, "bbox_x2": 346, "bbox_y2": 469})
    assert box == pytest.approx([0.236, 0.386, 0.346, 0.469])
