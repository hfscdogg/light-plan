"""Seating rooms on their walls, and reading the plan's scale.

Marshall's report: fixtures could be dragged around, but the tool did not know
where the walls were, so cans landed across them; and it asked him for the
square footage when the plan already says how big every room is.
"""

import base64
import io

import pytest
from PIL import Image, ImageDraw

from app.models.schemas import RoomData, as_feet
from app.services import walls
from app.services.plan_parser import PlanParser

W, H = 1000, 800


def plan(double_lines=False, counter=False):
    """Two rooms side by side, interiors (100,100)-(400,300) and (408,100)-(700,300).

    Walls are 8 px: solid, or drawn as two thin lines like many plan sets.
    The bottom wall of the left room has a door opening.
    """
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)

    def wall(box):
        x1, y1, x2, y2 = box
        if not double_lines:
            d.rectangle(box, fill="black")
        elif x2 - x1 > y2 - y1:  # horizontal: two lines along x
            d.rectangle((x1, y1, x2, y1 + 1), fill="black")
            d.rectangle((x1, y2 - 1, x2, y2), fill="black")
        else:
            d.rectangle((x1, y1, x1 + 1, y2), fill="black")
            d.rectangle((x2 - 1, y1, x2, y2), fill="black")

    wall((92, 92, 707, 99))      # top, both rooms
    wall((92, 300, 180, 307))    # bottom left, then a door
    wall((216, 300, 707, 307))
    wall((92, 92, 99, 307))      # left
    wall((400, 92, 407, 307))    # shared
    wall((700, 92, 707, 307))    # right
    if counter:
        # A counter edge: a hairline that runs the width of the room.
        d.line((110, 130, 390, 130), fill="black", width=1)
    d.text((230, 195), "KITCHEN", fill="black")
    return img


def frac(x1, y1, x2, y2):
    return (x1 / W, y1 / H, x2 / W, y2 / H)


def px(fit):
    return (round(fit.x1 * W), round(fit.y1 * H), round(fit.x2 * W), round(fit.y2 * H))


@pytest.mark.parametrize("double_lines", [False, True])
def test_a_box_drawn_round_the_label_grows_to_the_walls(double_lines):
    wall_map = walls.WallMap(plan(double_lines=double_lines))
    fit = wall_map.fit(frac(170, 160, 330, 240), (250 / W, 200 / H))

    assert fit.walls == 4
    assert px(fit) == (100, 100, 400, 300)


def test_a_box_spilling_into_the_next_room_comes_back_to_its_wall():
    wall_map = walls.WallMap(plan())
    fit = wall_map.fit(frac(80, 85, 470, 320), (250 / W, 200 / H))

    assert px(fit) == (100, 100, 400, 300)


def test_a_counter_line_is_not_a_wall():
    wall_map = walls.WallMap(plan(counter=True))
    fit = wall_map.fit(frac(170, 160, 330, 240), (250 / W, 200 / H))

    assert px(fit)[1] == 100, "the top edge stopped on the counter hairline"


def test_an_edge_with_no_wall_keeps_the_models_answer():
    img = Image.new("RGB", (W, H), "white")
    fit = walls.WallMap(img).fit(frac(170, 160, 330, 240), (0.25, 0.25))

    assert fit.walls == 0
    assert px(fit) == (170, 160, 330, 240)


def test_a_wall_that_would_leave_the_label_outside_the_room_is_refused():
    wall_map = walls.WallMap(plan())
    # A label sitting right of the shared wall belongs to the other room; a
    # box that claims it must not be squeezed into the left room.
    fit = wall_map.fit(frac(300, 160, 480, 240), (450 / W, 200 / H))

    x1, _, x2, _ = px(fit)
    assert x1 < 450 < x2


def room(name, bbox_px, width_ft=None, length_ft=None, room_type="bedroom", sqft=None):
    x1, y1, x2, y2 = frac(*bbox_px)
    return RoomData(
        name=name, room_type=room_type, width_ft=width_ft, length_ft=length_ft,
        sqft=sqft, bbox_x1=x1, bbox_y1=y1, bbox_x2=x2, bbox_y2=y2,
    )


def test_the_scale_comes_from_rooms_whose_size_is_printed():
    # 300 x 200 px printed as 15' x 10': 0.05 ft per pixel.  The size is
    # written length-first; which way round must not matter.
    rooms = [room("Kitchen", (100, 100, 400, 300), width_ft=10, length_ft=15)]

    assert walls.feet_per_pixel(rooms, W, H) == pytest.approx(0.05)


def test_a_room_whose_box_does_not_match_its_printed_size_is_ignored():
    rooms = [
        room("Kitchen", (100, 100, 400, 300), width_ft=15, length_ft=10),
        # Printed square, drawn 3:2: whatever this box is, it is not that room.
        room("Bed 2", (100, 100, 400, 300), width_ft=12, length_ft=12),
    ]

    assert walls.feet_per_pixel(rooms, W, H) == pytest.approx(0.05)


def test_no_printed_sizes_means_no_scale():
    assert walls.feet_per_pixel([room("Kitchen", (100, 100, 400, 300))], W, H) is None


def test_rooms_without_a_printed_size_are_measured():
    rooms = [
        room("Kitchen", (100, 100, 400, 300), width_ft=10, length_ft=15),
        room("Bath", (408, 100, 568, 220), room_type="bathroom"),
        room("Garage", (100, 400, 540, 840), room_type="garage"),
    ]

    measured = walls.measure_rooms(rooms, 0.05, W, H)
    kitchen, bath, garage = measured

    # Printed size kept, but turned to run the way the box does.
    assert (kitchen.width_ft, kitchen.length_ft, kitchen.sqft) == (15, 10, 150)
    assert (bath.width_ft, bath.length_ft, bath.sqft) == (8.0, 6.0, 48)
    # The garage is measured but is not living space.
    assert walls.floor_area(measured) == 198


def png_b64(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode()


def test_the_parser_seats_rooms_and_measures_the_floor():
    parser = PlanParser.__new__(PlanParser)
    rooms = [
        RoomData(
            name="Kitchen", room_type="kitchen", width_ft=15, length_ft=10,
            position_x=250 / W, position_y=200 / H,
            bbox_x1=170 / W, bbox_y1=160 / H, bbox_x2=330 / W, bbox_y2=240 / H,
        ),
        RoomData(
            name="Pantry", room_type="pantry", labeled=False,
            position_x=550 / W, position_y=200 / H,
            bbox_x1=470 / W, bbox_y1=150 / H, bbox_x2=630 / W, bbox_y2=250 / H,
        ),
    ]

    fitted = parser._fit_to_walls(rooms, (png_b64(plan()), "image/png"), (0, 0, 1, 1))
    kitchen, pantry = fitted

    assert (round(kitchen.bbox_x1 * W), round(kitchen.bbox_x2 * W)) == (100, 400)
    assert (round(pantry.bbox_x1 * W), round(pantry.bbox_x2 * W)) == (408, 700)
    # 292 x 200 px at 0.05 ft/px.
    assert (pantry.width_ft, pantry.length_ft) == (14.6, 10.0)
    assert pantry.labeled is False, "fitting must not forget the room was unnamed"
    assert parser.measured_sqft == 150 + 146
    assert parser.scale_ft_per_px == pytest.approx(0.05)


def test_without_a_scale_the_parser_falls_back_to_typical_sizes():
    parser = PlanParser.__new__(PlanParser)
    rooms = [
        RoomData(
            name="Bedroom", room_type="bedroom",
            position_x=250 / W, position_y=200 / H,
            bbox_x1=170 / W, bbox_y1=160 / H, bbox_x2=330 / W, bbox_y2=240 / H,
        ),
    ]

    (bedroom,) = parser._fit_to_walls(rooms, (png_b64(plan()), "image/png"), (0, 0, 1, 1))

    assert bedroom.width_ft and bedroom.length_ft
    assert parser.measured_sqft is None


# Marshall's second floor failed outright: the model copied the room sizes off
# the plan as printed — "12'-8\"" — and one such room threw the whole page out.


@pytest.mark.parametrize(
    "printed, feet",
    [
        ("12'-8\"", 12.67),
        ("11'-11\"", 11.92),
        ("12' 8\"", 12.67),
        ("16'-3 1/4\"", 16.27),
        ("12’-8”", 12.67),
        ("9'-0\"", 9.0),
        ("12'", 12.0),
        ("12 ft 6 in", 12.5),
        ("12.5", 12.5),
        (12, 12.0),
        ("1,200 sq ft", 1200.0),
        ("vaulted", None),
        ("", None),
        (0, None),
        (None, None),
    ],
)
def test_sizes_are_read_as_printed(printed, feet):
    assert as_feet(printed) == feet


def test_a_page_with_sizes_in_feet_and_inches_is_read():
    parser = PlanParser.__new__(PlanParser)
    raw = (
        '[{"name": "BEDROOM 3", "room_type": "bedroom", "label_x": 0.5, '
        '"label_y": 0.5, "bbox_x1": 0.4, "bbox_y1": 0.1, "bbox_x2": 0.6, '
        '"bbox_y2": 0.25, "width_ft": "12\'-8\\"", "length_ft": "11\'-11\\"", '
        '"ceiling_height_ft": "vaulted"}]'
    )

    (bedroom,) = parser._parse_response(raw)

    assert (bedroom.width_ft, bedroom.length_ft) == (12.67, 11.92)
    assert bedroom.ceiling_height_ft is None


# The cans did not sit inside the walls: a side with no wall drawn along it (a
# cased opening, an open plan) kept the model's box grown by a third, and the
# grid of cans ran through the wall into the next room.


def open_plan():
    """Two rooms, (100,100)-(400,300) and (408,100)-(700,300), all 8 px walls,
    except that the left room is open to the sheet below: no bottom wall."""
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    for box in [
        (92, 92, 707, 99),      # top
        (408, 300, 707, 307),   # bottom, right room only
        (92, 92, 99, 500),      # left, running on past the opening
        (400, 92, 407, 307),    # shared
        (700, 92, 707, 307),    # right
    ]:
        d.rectangle(box, fill="black")
    return img


def test_the_scale_comes_from_facing_walls():
    wall_map = walls.WallMap(open_plan())
    left = room("Den", (120, 120, 380, 280), width_ft=15, length_ft=10)
    right = room("Bed", (430, 120, 680, 280), width_ft=14.6, length_ft=10)
    seated = [
        (r, wall_map.fit((r.bbox_x1, r.bbox_y1, r.bbox_x2, r.bbox_y2)))
        for r in (left, right)
    ]

    assert walls.span_scale(seated, W, H) == pytest.approx(0.05, rel=0.02)


def test_one_span_cannot_set_the_scale():
    fit = walls.Fit(0.1, 0.125, 0.4, 0.375, snapped=(True, False, True, False))
    rooms = [(room("Den", (100, 100, 400, 300), width_ft=15, length_ft=10), fit)]

    assert walls.span_scale(rooms, W, H) is None


def test_a_side_with_no_wall_is_placed_by_the_printed_size():
    parser = PlanParser.__new__(PlanParser)
    rooms = [
        RoomData(
            name="Den", room_type="den", width_ft=15, length_ft=10,
            position_x=250 / W, position_y=200 / H,
            bbox_x1=150 / W, bbox_y1=150 / H, bbox_x2=350 / W, bbox_y2=330 / H,
        ),
        RoomData(
            name="Bed", room_type="bedroom", width_ft=14.6, length_ft=10,
            position_x=550 / W, position_y=200 / H,
            bbox_x1=450 / W, bbox_y1=150 / H, bbox_x2=650 / W, bbox_y2=250 / H,
        ),
    ]

    den, _ = parser._fit_to_walls(rooms, (png_b64(open_plan()), "image/png"), (0, 0, 1, 1))

    # 10 ft at 0.05 ft/px is 200 px down from the top wall — not the model's
    # box grown by a third, which ran on to y=366.
    assert round(den.bbox_y2 * H) == pytest.approx(300, abs=4)
    assert (round(den.bbox_x1 * W), round(den.bbox_x2 * W)) == (100, 400)


def test_a_wall_one_printed_size_away_does_not_turn_the_room():
    # Walls found 300 px apart across, and only the top wall down.  Printed
    # 12' x 15', a 15' span across would turn the room — but then the room
    # would hang 12' below the top wall and lose its label; as printed, it
    # keeps both.
    fit = walls.Fit(0.1, 0.125, 0.4, 0.5, snapped=(True, True, True, False))
    xs, ys = walls.size_box(fit, 12, 15, 0.05, W, H, (0.25, 0.45))

    assert xs is None, "15 ft of walls is not this room's 12 ft width"
    assert ys == pytest.approx((0.125, 0.125 + 15 / 0.05 / H))
