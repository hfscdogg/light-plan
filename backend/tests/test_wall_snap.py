"""Keypads and accent lights go on a drawn wall, not an open-plan split."""

from PIL import Image, ImageDraw

from app.models.schemas import FixtureAssignment, RoomData
from app.services.wall_snap import snap_to_walls
from app.services.walls import WallMap

# A 20 x 20 ft room, box (0.3, 0.3)-(0.5, 0.5) on a 1000 x 1000 px page, so the
# page is 100 ft across.  Thick walls left, top and right; the bottom is open,
# like a kitchen open to the living room.
BOX = (0.3, 0.3, 0.5, 0.5)


def page(open_bottom=True):
    img = Image.new("RGB", (1000, 1000), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([295, 295, 305, 505], fill="black")       # left
    d.rectangle([295, 295, 505, 305], fill="black")       # top
    d.rectangle([495, 295, 505, 505], fill="black")       # right
    if not open_bottom:
        d.rectangle([295, 495, 505, 505], fill="black")
    return WallMap(img)


ROOM = RoomData(name="Kitchen", room_type="kitchen", width_ft=20.0, length_ft=20.0,
                position_x=0.4, position_y=0.4,
                bbox_x1=BOX[0], bbox_y1=BOX[1], bbox_x2=BOX[2], bbox_y2=BOX[3])


def run(fixtures, positions, wall_map=None):
    return snap_to_walls(wall_map or page(), [ROOM], {"Kitchen": fixtures},
                         {"Kitchen": positions})["Kitchen"]


def test_a_keypad_in_the_open_floor_moves_onto_the_nearest_wall():
    # Hatteras, 7 Nov 2026: the Entertain keypad in the open beside the island.
    (x, y), = run([FixtureAssignment(fixture_type="keypad")], [(0.46, 0.45)])
    assert 0.49 < x < 0.5 and abs(y - 0.45) < 0.03      # half a foot in from the right wall


def test_a_keypad_on_the_open_side_moves_to_a_wall():
    (x, y), = run([FixtureAssignment(fixture_type="keypad")], [(0.4, 0.497)])
    assert x < 0.31 or x > 0.49 or y < 0.31


def test_a_keypad_already_on_a_wall_stays():
    assert run([FixtureAssignment(fixture_type="keypad")], [(0.31, 0.4)]) == [(0.31, 0.4)]


def test_accents_off_any_wall_go_along_the_most_solid_side():
    # Hatteras full size: two accents on the kitchen/living split, at the island.
    accents = [FixtureAssignment(fixture_type="accent")] * 2
    placed = run(accents, [(0.38, 0.45), (0.42, 0.45)])
    xs = {round(x, 3) for x, _ in placed}
    ys = {round(y, 3) for _, y in placed}
    on_a_side = len(xs) == 1 or len(ys) == 1
    assert on_a_side
    assert all(0.3 < x < 0.5 and 0.3 < y < 0.5 for x, y in placed)
    assert all(y < 0.49 for _, y in placed)               # never along the open side


def test_accents_along_a_wall_stay():
    accents = [FixtureAssignment(fixture_type="accent")] * 2
    spots = [(0.32, 0.37), (0.32, 0.43)]
    assert run(accents, spots) == spots


def test_a_can_on_a_wall_line_is_pulled_back_into_its_room():
    # Catalina, 7 Nov 2026: a living-room can sat on the wall line.
    from app.services.wall_snap import pull_off_walls
    (x, y), = pull_off_walls(page(), [ROOM], {"Kitchen": [FixtureAssignment(fixture_type="recessed")]},
                             {"Kitchen": [(0.40, 0.301)]})["Kitchen"]
    assert y > 0.306 and abs(x - 0.40) < 0.01


def test_pendants_and_cans_clear_of_walls_stay_put():
    from app.services.wall_snap import pull_off_walls
    img_map = page()
    fixtures = [FixtureAssignment(fixture_type="pendant"), FixtureAssignment(fixture_type="recessed")]
    spots = [(0.40, 0.301), (0.40, 0.40)]
    assert pull_off_walls(img_map, [ROOM], {"Kitchen": fixtures}, {"Kitchen": spots})["Kitchen"] == spots
