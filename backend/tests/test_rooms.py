"""Unlabeled spaces, ceiling heights and naming rooms.

Marshall's Hanover plan: the second-floor baths and the closets had no names
printed in them, so the tool skipped them and they got no lights at all.  He
also wanted to be asked for each floor's ceiling height, not square footage.
"""

import json

import pytest

from app.models.schemas import RoomData
from app.services.plan_parser import PlanParser
from conftest import upload_plan


@pytest.fixture
def parser():
    return PlanParser.__new__(PlanParser)


def test_an_unlabeled_space_is_kept_and_flagged(parser):
    raw = json.dumps([
        {"name": "Kitchen", "room_type": "kitchen", "labeled": True},
        {"name": "Bath", "room_type": "bathroom", "labeled": False},
        {"name": "Closet", "room_type": "closet", "labeled": "false"},
        {"name": "Primary Bedroom", "room_type": "master_bedroom"},
        {"name": "", "room_type": "closet"},
    ])

    rooms = parser._parse_response(raw)

    assert [r.labeled for r in rooms] == [True, False, False, True, False]
    assert rooms[4].name == "Unnamed space"


def box(name, x1, y1, x2, y2, labeled=True):
    return RoomData(
        name=name, room_type="bathroom", labeled=labeled,
        position_x=(x1 + x2) / 2, position_y=(y1 + y2) / 2,
        bbox_x1=x1, bbox_y1=y1, bbox_x2=x2, bbox_y2=y2,
    )


def test_two_rooms_with_one_name_are_both_kept(parser):
    """Dedup used to merge every "Bath" on the floor into one room."""
    rooms = [box("Bath", 0.1, 0.1, 0.2, 0.2, False), box("Bath", 0.6, 0.6, 0.7, 0.7, False)]

    assert len(parser._deduplicate_rooms(rooms)) == 2


def test_one_room_read_twice_is_merged_and_keeps_its_box(parser):
    rooms = [box("Bath", 0.1, 0.1, 0.2, 0.2), box("BATH", 0.11, 0.1, 0.2, 0.21)]

    (merged,) = parser._deduplicate_rooms(rooms)
    assert merged.bbox_x1 is not None, "a merged room lost its box"


def test_rooms_that_share_a_name_are_numbered(parser):
    rooms = [box("Bath", 0.1, 0.1, 0.2, 0.2), box("Bath", 0.6, 0.6, 0.7, 0.7),
             box("Bath 2", 0.3, 0.3, 0.4, 0.4), box("Bath", 0.8, 0.8, 0.9, 0.9)]

    names = [r.name for r in parser._unique_names(rooms)]
    assert names == ["Bath", "Bath 3", "Bath 2", "Bath 4"]


ROOMS = [
    RoomData(
        name="Kitchen", room_type="kitchen", width_ft=16, length_ft=15,
        position_x=0.3, position_y=0.4, ceiling_height_ft=None,
        bbox_x1=0.2, bbox_y1=0.3, bbox_x2=0.4, bbox_y2=0.5,
    ),
    RoomData(
        name="Great Room", room_type="great_room", width_ft=20, length_ft=18,
        position_x=0.7, position_y=0.4, ceiling_height_ft=18,
        bbox_x1=0.6, bbox_y1=0.3, bbox_x2=0.85, bbox_y2=0.5,
    ),
    RoomData(
        name="Closet", room_type="closet", labeled=False, width_ft=5, length_ft=4,
        position_x=0.3, position_y=0.7, ceiling_height_ft=None,
        bbox_x1=0.25, bbox_y1=0.65, bbox_x2=0.35, bbox_y2=0.75,
    ),
]


def by_name(body):
    return {r["name"]: r for r in body["rooms"]}


def test_the_floor_ceiling_height_reaches_every_room_without_its_own(client, project, stub_parser):
    stub_parser.rooms = ROOMS

    r = client.post(
        f"/api/projects/{project['id']}/plans/upload?ceiling_height=8",
        files={"file": ("plan.png", b"x", "image/png")},
    )
    assert r.status_code == 201, r.text
    rooms = by_name(r.json())

    assert rooms["Kitchen"]["ceiling_height_ft"] == 8
    assert rooms["Closet"]["ceiling_height_ft"] == 8
    assert rooms["Great Room"]["ceiling_height_ft"] == 18, "a printed vault was overwritten"
    assert r.json()["ceiling_height_ft"] == 8


def test_ceiling_height_sets_the_spacing_of_the_cans(client, stub_parser):
    # A den: the kitchen rule spaces its cans on 36" centres regardless.
    stub_parser.rooms = [ROOMS[0].model_copy(update={"name": "Den", "room_type": "den"})]
    counts = {}
    for ceiling in (8, 12):
        pid = client.post("/api/projects", json={"name": f"c{ceiling}"}).json()["id"]
        body = client.post(
            f"/api/projects/{pid}/plans/upload?ceiling_height={ceiling}",
            files={"file": ("plan.png", b"x", "image/png")},
        ).json()
        counts[ceiling] = sum(
            f["fixture_type"] == "recessed" for f in body["rooms"][0]["fixtures"]
        )

    assert counts[8] > counts[12], counts


def test_an_unreasonable_ceiling_height_is_refused(client, project, stub_parser):
    r = client.post(
        f"/api/projects/{project['id']}/plans/upload?ceiling_height=0",
        files={"file": ("plan.png", b"x", "image/png")},
    )
    assert r.status_code == 422


def test_unlabeled_rooms_are_flagged_and_get_fixtures(client, project, stub_parser):
    stub_parser.rooms = ROOMS

    rooms = by_name(upload_plan(client, project["id"]).json())

    assert rooms["Closet"]["labeled"] is False
    assert rooms["Kitchen"]["labeled"] is True
    assert rooms["Closet"]["fixtures"], "an unnamed space must still be lit"


def test_measured_square_footage_is_reported(client, project, stub_parser):
    stub_parser.measured_sqft = 1480.0

    body = upload_plan(client, project["id"]).json()
    assert body["measured_sqft"] == 1480.0


def test_no_scale_means_no_square_footage(client, project, stub_parser):
    assert upload_plan(client, project["id"]).json()["measured_sqft"] is None


def test_analysis_runs_off_the_event_loop(client, project, stub_parser):
    """The second floor waited minutes for the first: the model calls ran on
    the event loop, so nothing else — not even a health check — was served."""
    upload_plan(client, project["id"])
    assert stub_parser.on_event_loop == [False]


def uploaded(client, project, stub_parser):
    stub_parser.rooms = ROOMS
    body = upload_plan(client, project["id"]).json()
    return body["floor_plan_id"], by_name(body)


def test_naming_a_space_keeps_its_fixtures(client, project, stub_parser):
    plan_id, rooms = uploaded(client, project, stub_parser)
    closet = rooms["Closet"]

    r = client.patch(
        f"/api/projects/{project['id']}/plans/{plan_id}/rooms/{closet['id']}",
        json={"name": "Linen"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Linen"
    assert [f["id"] for f in r.json()["fixtures"]] == [f["id"] for f in closet["fixtures"]]


def test_a_space_that_is_really_a_bath_is_lit_as_a_bath(client, project, stub_parser):
    plan_id, rooms = uploaded(client, project, stub_parser)
    closet = rooms["Closet"]

    r = client.patch(
        f"/api/projects/{project['id']}/plans/{plan_id}/rooms/{closet['id']}",
        json={"name": "Hall Bath", "room_type": "bathroom"},
    )
    assert r.status_code == 200, r.text
    room = r.json()
    types = {f["fixture_type"] for f in room["fixtures"]}
    assert room["room_type"] == "bathroom"
    assert "exhaust_fan" in types or "sconce" in types, types
    for f in room["fixtures"]:
        assert closet["bbox_x1"] <= f["plan_x"] <= closet["bbox_x2"]
        assert closet["bbox_y1"] <= f["plan_y"] <= closet["bbox_y2"]


def test_two_rooms_cannot_share_a_name(client, project, stub_parser):
    plan_id, rooms = uploaded(client, project, stub_parser)

    r = client.patch(
        f"/api/projects/{project['id']}/plans/{plan_id}/rooms/{rooms['Closet']['id']}",
        json={"name": "Kitchen"},
    )
    assert r.status_code == 409


def test_a_made_up_room_type_is_refused(client, project, stub_parser):
    plan_id, rooms = uploaded(client, project, stub_parser)

    r = client.patch(
        f"/api/projects/{project['id']}/plans/{plan_id}/rooms/{rooms['Closet']['id']}",
        json={"room_type": "ballroom"},
    )
    assert r.status_code == 400


def test_a_room_in_another_project_is_404(client, project, stub_parser):
    plan_id, rooms = uploaded(client, project, stub_parser)
    other = client.post("/api/projects", json={"name": "Other"}).json()["id"]

    r = client.patch(
        f"/api/projects/{other}/plans/{plan_id}/rooms/{rooms['Closet']['id']}",
        json={"name": "Linen"},
    )
    assert r.status_code == 404
