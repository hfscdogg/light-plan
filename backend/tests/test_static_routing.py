"""Which page the app serves.

The plan viewer (preview.html) is the product and the only UI: AI room
detection, the draggable fixture overlay, the tier pricing, the PDF plan.
The original React uploader carried the bugs reported in August and is
retired, so every page-shaped request answers with the viewer — there is one
UI rather than two that drift apart.
"""

import os

import pytest

from app.main import PRODUCTION_PAGE, resolve_frontend_dir, resolve_static_path


@pytest.fixture
def build(tmp_path):
    """What the image ships: the viewer, plus anything beside it."""
    (tmp_path / PRODUCTION_PAGE).write_text("<html>plan viewer</html>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    return tmp_path


def served(build, path):
    resolved = resolve_static_path(str(build), path)
    return None if resolved is None else os.path.basename(resolved)


def test_root_serves_the_plan_viewer(build):
    assert served(build, "") == PRODUCTION_PAGE


def test_index_html_serves_the_plan_viewer(build):
    """Anyone with a bookmarked /index.html lands on the product too."""
    assert served(build, "index.html") == PRODUCTION_PAGE


def test_preview_url_still_works(build):
    """The link already sent to the sales team must keep working."""
    assert served(build, PRODUCTION_PAGE) == PRODUCTION_PAGE


@pytest.mark.parametrize("path", ["classic", "/classic/", "//classic"])
def test_the_retired_uploader_is_not_reachable(build, path):
    """/classic was the old React page; it must not come back by URL."""
    assert served(build, path) == PRODUCTION_PAGE


def test_index_html_serves_the_viewer(build):
    """A bookmarked /index.html lands on the product."""
    assert served(build, "index.html") == PRODUCTION_PAGE


def test_real_files_are_served(build):
    assert served(build, "assets/app.js") == "app.js"


def test_unknown_routes_fall_back_to_the_viewer(build):
    """A mistyped or stale URL lands on the product, not a dead page."""
    assert served(build, "projects/abc123") == PRODUCTION_PAGE


def test_unknown_routes_resolve_to_the_viewer_file(build):
    """Every page-shaped request resolves to the one page that exists."""
    for path in ("projects/abc123", "anything/at/all", "classic"):
        assert served(build, path) == PRODUCTION_PAGE


def test_real_asset_files_are_still_served_verbatim(build):
    """Retiring a page must not stop assets resolving."""
    assert served(build, "assets/app.js") == "app.js"


@pytest.mark.parametrize(
    "attack",
    [
        "../config.py",
        "../../etc/passwd",
        "assets/../../app/config.py",
        "a/b/../../../../etc/passwd",
    ],
)
def test_path_traversal_is_refused(build, attack):
    """A path escaping the build directory is a 404, not a file read."""
    assert resolve_static_path(str(build), attack) is None


def test_traversal_lookalikes_are_not_treated_as_escapes(build):
    """Containment is decided by resolving the path, not by matching "..".

    "...." is a legal directory name, so this never leaves the build
    directory — it is simply an unknown route.
    """
    assert served(build, "....//....//etc/passwd") == PRODUCTION_PAGE


def test_traversal_that_stays_inside_is_allowed(build):
    """Refusing traversal must not break legitimate nested paths."""
    assert served(build, "assets/../assets/app.js") == "app.js"


# --- Finding the viewer on disk -----------------------------------------
#
# There is no bundler any more: the deployed image copies the page into
# backend/static, and a checkout has it only at frontend/public.


def test_prefers_the_deployed_static_directory(tmp_path):
    backend = tmp_path / "backend"
    (backend / "static").mkdir(parents=True)
    (backend / "static" / PRODUCTION_PAGE).write_text("deployed")
    source = tmp_path / "frontend" / "public"
    source.mkdir(parents=True)
    (source / PRODUCTION_PAGE).write_text("checkout")

    assert resolve_frontend_dir(str(backend), str(tmp_path)) == str(backend / "static")


def test_falls_back_to_the_source_directory_in_a_checkout(tmp_path):
    """Running uvicorn from a clone must still serve the real page."""
    backend = tmp_path / "backend"
    backend.mkdir()
    source = tmp_path / "frontend" / "public"
    source.mkdir(parents=True)
    (source / PRODUCTION_PAGE).write_text("checkout")

    assert resolve_frontend_dir(str(backend), str(tmp_path)) == str(source)


def test_returns_none_when_the_viewer_is_nowhere(tmp_path):
    backend = tmp_path / "backend"
    backend.mkdir()

    assert resolve_frontend_dir(str(backend), str(tmp_path)) is None


def test_a_static_directory_without_the_viewer_is_not_used(tmp_path):
    """An empty or stale static dir must not shadow the source page."""
    backend = tmp_path / "backend"
    (backend / "static").mkdir(parents=True)
    (backend / "static" / "leftover.txt").write_text("stale")
    source = tmp_path / "frontend" / "public"
    source.mkdir(parents=True)
    (source / PRODUCTION_PAGE).write_text("checkout")

    assert resolve_frontend_dir(str(backend), str(tmp_path)) == str(source)
