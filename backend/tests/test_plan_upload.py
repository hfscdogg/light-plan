"""Upload endpoint behaviour.

The regression these cover: the sales team uploaded plans that rendered on
screen with no fixtures on them at all. The fixture-placement pass is a second
model round-trip, and an unguarded failure there used to take down the whole
upload — discarding rooms that had already been read correctly.
"""

from conftest import upload_plan


def total_fixtures(payload):
    return sum(len(room["fixtures"]) for room in payload["rooms"])


def test_upload_returns_fixtures(client, project, stub_parser):
    r = upload_plan(client, project["id"])
    assert r.status_code == 201, r.text

    body = r.json()
    assert len(body["rooms"]) == 2
    assert total_fixtures(body) > 0

    # Every fixture needs a position on the plan image, or the viewer has
    # nothing to draw.
    for room in body["rooms"]:
        assert room["fixtures"], f"{room['name']} came back with no fixtures"
        for fixture in room["fixtures"]:
            assert fixture["plan_x"] is not None
            assert fixture["plan_y"] is not None
            assert 0.0 <= fixture["plan_x"] <= 1.0
            assert 0.0 <= fixture["plan_y"] <= 1.0


def test_placement_failure_does_not_fail_the_upload(client, project, stub_parser):
    """A raising placement pass must degrade, not 500.

    This is the bug Zack hit: the plan displayed, the rooms parsed fine, and
    the overlay came back empty because the request had already died.
    """
    stub_parser.placement = "raise"

    r = upload_plan(client, project["id"])
    assert r.status_code == 201, (
        "a failed placement call must fall back to algorithmic placement, "
        f"not fail the upload — got {r.status_code}: {r.text[:300]}"
    )
    assert total_fixtures(r.json()) > 0


def test_empty_placement_falls_back_to_algorithmic(client, project, stub_parser):
    stub_parser.placement = "empty"

    r = upload_plan(client, project["id"])
    assert r.status_code == 201, r.text
    assert total_fixtures(r.json()) > 0


def test_placement_outcomes_agree_on_fixture_count(client, project, stub_parser):
    """Which fixtures exist is the rules engine's call, not the model's.

    Placement only decides *where* they go, so a failed or empty placement
    pass must not change how many fixtures the builder is quoted.
    """
    counts = {}
    for mode in ("ok", "empty", "raise"):
        stub_parser.placement = mode
        r = client.post("/api/projects", json={"name": f"Project {mode}"})
        pid = r.json()["id"]
        counts[mode] = total_fixtures(upload_plan(client, pid).json())

    assert counts["ok"] == counts["empty"] == counts["raise"], counts


def test_reports_pages_analyzed_for_multipage_plan(client, project, stub_parser):
    """A builder's plan set is many sheets; only page 1 is read.

    Coordinates are fractions of the analyzed page and the viewer renders page
    1, so the response has to say what was left out.
    """
    stub_parser.page_count = 5

    body = upload_plan(client, project["id"]).json()
    assert body["page_count"] == 5
    assert body["pages_analyzed"] == 1


def test_single_page_upload_reports_one_page(client, project, stub_parser):
    body = upload_plan(client, project["id"]).json()
    assert body["page_count"] == 1
    assert body["pages_analyzed"] == 1


def test_rejects_unsupported_file_type(client, project, stub_parser):
    r = client.post(
        f"/api/projects/{project['id']}/plans/upload",
        files={"file": ("notes.txt", b"not a plan", "text/plain")},
    )
    assert r.status_code == 400


def test_upload_to_missing_project_is_404(client, stub_parser):
    r = upload_plan(client, "does-not-exist")
    assert r.status_code == 404


def test_reparse_survives_placement_failure(client, project, stub_parser):
    """Re-parsing is what the Good/Better/Best toggle does.

    It had the same unguarded placement call as upload, so a failure there
    made the tier toggle silently do nothing.
    """
    plan_id = upload_plan(client, project["id"]).json()["floor_plan_id"]

    stub_parser.placement = "raise"
    r = client.post(f"/api/projects/{project['id']}/plans/{plan_id}/parse")
    assert r.status_code == 200, r.text
    assert total_fixtures(r.json()) > 0


def test_reparse_applies_the_new_tier(client, project, stub_parser):
    plan_id = upload_plan(client, project["id"]).json()["floor_plan_id"]

    client.patch(f"/api/projects/{project['id']}", json={"tier": "best"})
    body = client.post(f"/api/projects/{project['id']}/plans/{plan_id}/parse").json()

    skus = {f["product_sku"] for r in body["rooms"] for f in r["fixtures"]}
    assert any(sku.startswith("KET-") for sku in skus), (
        f"tier change to 'best' should produce Ketra SKUs, got {sorted(skus)}"
    )


def test_upload_reads_the_requested_page(client, project, stub_parser):
    """Each floor of a plan set is analyzed on its own, on request.

    Both model passes must see the same sheet, or fixtures are placed against
    a different drawing than the rooms were read from.
    """
    stub_parser.page_count = 3

    r = upload_plan(client, project["id"], page=2)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["page"] == 2
    assert body["page_count"] == 3
    assert stub_parser.pages_read == [2]
    assert stub_parser.pages_placed == [2]


def test_upload_defaults_to_page_one(client, project, stub_parser):
    body = upload_plan(client, project["id"]).json()
    assert body["page"] == 1
    assert stub_parser.pages_read == [1]


def test_upload_of_a_page_that_does_not_exist_is_400(client, project, stub_parser):
    stub_parser.page_count = 2

    r = upload_plan(client, project["id"], page=5)
    assert r.status_code == 400, r.text
    assert "Page 5" in r.json()["detail"]


def test_upload_rejects_page_zero(client, project, stub_parser):
    r = upload_plan(client, project["id"], page=0)
    assert r.status_code == 422
