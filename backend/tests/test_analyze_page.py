"""The features read runs alongside the placement pass, not after it."""

import time

from app.models.schemas import RoomData
from app.routers import plans
from app.services.plan_parser import PlanParser


def test_the_features_read_overlaps_the_placement_pass(monkeypatch):
    room = RoomData(name="Kitchen", room_type="kitchen", width_ft=13, length_ft=13,
                    bbox_x1=0.3, bbox_y1=0.3, bbox_x2=0.5, bbox_y2=0.5,
                    position_x=0.4, position_y=0.4)
    calls = []

    def slow_placement(parser, file_path, file_type, rooms, fixtures, page=1):
        time.sleep(0.4)
        calls.append("placement")
        return {name: [(0.4, 0.4)] * len(fx) for name, fx in fixtures.items()}

    def slow_features(self, file_path, file_type, rooms, page=1):
        time.sleep(0.4)
        calls.append("features")
        return None

    def no_page(self, *a, **k):
        raise OSError("no page in this test")

    monkeypatch.setattr(PlanParser, "__init__", lambda self: None)
    monkeypatch.setattr(PlanParser, "parse_plan", lambda self, *a, **k: ([room], "[]", 1))
    monkeypatch.setattr(PlanParser, "read_plan_features", slow_features)
    monkeypatch.setattr(PlanParser, "_load_images", no_page)
    monkeypatch.setattr(plans, "_resolve_plan_positions", slow_placement)

    start = time.monotonic()
    rooms, _, _, fixtures, positions, _ = plans._analyze_page("plan.png", "png", 1, "better", 9.0)
    elapsed = time.monotonic() - start

    assert sorted(calls) == ["features", "placement"]
    assert elapsed < 0.7            # one after the other would be 0.8 s
    assert len(positions["Kitchen"]) == len(fixtures["Kitchen"])
