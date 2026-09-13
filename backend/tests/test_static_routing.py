"""Which page the bare domain serves.

The plan viewer (preview.html) is the product — AI room detection, the
draggable fixture overlay, the tier pricing — and it is what Livewire hands
to builders. It answers on "/" so the link is just the domain. The older
React uploader stays reachable at /classic.
"""

import os

import pytest

from app.main import LEGACY_PATH, PRODUCTION_PAGE, resolve_static_path


@pytest.fixture
def build(tmp_path):
    """A frontend build containing both pages."""
    (tmp_path / "index.html").write_text("<html>react uploader</html>")
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


def test_legacy_uploader_stays_reachable(build):
    assert served(build, LEGACY_PATH) == "index.html"
    assert served(build, f"/{LEGACY_PATH}/") == "index.html"


def test_real_files_are_served(build):
    assert served(build, "assets/app.js") == "app.js"


def test_unknown_routes_fall_back_to_the_spa(build):
    """Client-side routes in the React app must still resolve."""
    assert served(build, "projects/abc123") == "index.html"


def test_root_falls_back_when_the_viewer_is_missing(tmp_path):
    """A build without preview.html must still serve something."""
    (tmp_path / "index.html").write_text("<html>react uploader</html>")

    assert served(tmp_path, "") == "index.html"


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
    directory — it is an unknown route, and the SPA handles it.
    """
    assert served(build, "....//....//etc/passwd") == "index.html"


def test_traversal_that_stays_inside_is_allowed(build):
    """Refusing traversal must not break legitimate nested paths."""
    assert served(build, "assets/../index.html") == "index.html"
