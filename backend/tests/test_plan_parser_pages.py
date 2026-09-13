"""PDF page handling.

Every coordinate the parser returns is a fraction of one page image, and the
viewer only ever renders page 1 of an upload. Reading a whole plan set produced
room boxes measured against sheets the user never sees, so fixtures landed in
meaningless places.
"""

import base64
import sys
import types

import pytest
from PIL import Image

from app.services.plan_parser import PlanParser


@pytest.fixture
def fake_pdf2image(monkeypatch):
    """Stand in for poppler, and record the page range it was asked for."""
    calls = {}

    def convert_from_path(path, dpi=None, first_page=None, last_page=None):
        calls["dpi"] = dpi
        calls["first_page"] = first_page
        calls["last_page"] = last_page
        total = calls.get("total_pages", 5)
        last = min(last_page or total, total)
        first = first_page or 1
        return [Image.new("RGB", (80, 60), "white") for _ in range(last - first + 1)]

    def pdfinfo_from_path(path):
        return {"Pages": calls.get("total_pages", 5)}

    module = types.ModuleType("pdf2image")
    module.convert_from_path = convert_from_path
    module.pdfinfo_from_path = pdfinfo_from_path
    monkeypatch.setitem(sys.modules, "pdf2image", module)
    return calls


@pytest.fixture
def parser():
    # Bypass __init__ so no Gemini client is constructed.
    return PlanParser.__new__(PlanParser)


def test_multipage_pdf_rasterizes_only_page_one(parser, fake_pdf2image):
    fake_pdf2image["total_pages"] = 5

    images, total_pages = parser._load_images(
        "/tmp/plan-set.pdf", "pdf", max_pages=PlanParser.MAX_ANALYSIS_PAGES
    )

    assert len(images) == 1, "only the page the viewer renders should be analyzed"
    assert fake_pdf2image["first_page"] == 1
    assert fake_pdf2image["last_page"] == 1


def test_multipage_pdf_reports_the_true_page_count(parser, fake_pdf2image):
    """The count describes the upload, not the slice we read."""
    fake_pdf2image["total_pages"] = 5

    _, total_pages = parser._load_images(
        "/tmp/plan-set.pdf", "pdf", max_pages=PlanParser.MAX_ANALYSIS_PAGES
    )
    assert total_pages == 5


def test_page_count_falls_back_when_pdfinfo_is_unavailable(parser, fake_pdf2image, monkeypatch):
    """pdfinfo shells out to poppler and can fail; that must not break upload."""
    fake_pdf2image["total_pages"] = 3

    import pdf2image

    def boom(path):
        raise OSError("pdfinfo not found on PATH")

    monkeypatch.setattr(pdf2image, "pdfinfo_from_path", boom)

    images, total_pages = parser._load_images("/tmp/plan.pdf", "pdf", max_pages=1)
    assert total_pages == len(images) == 1


def test_unlimited_reads_every_page(parser, fake_pdf2image):
    fake_pdf2image["total_pages"] = 5

    images, total_pages = parser._load_images("/tmp/plan.pdf", "pdf", max_pages=None)
    assert len(images) == 5
    assert total_pages == 5


def test_image_upload_is_always_a_single_page(parser, tmp_path):
    png = tmp_path / "plan.png"
    png.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQ"
            "GAhKmMIQAAAABJRU5ErkJggg=="
        )
    )

    images, total_pages = parser._load_images(str(png), "png")
    assert total_pages == 1
    assert len(images) == 1
    assert images[0][1] == "image/png"


def test_jpg_upload_declares_jpeg_media_type(parser, tmp_path):
    jpg = tmp_path / "plan.jpg"
    Image.new("RGB", (10, 10), "white").save(str(jpg), format="JPEG")

    images, _ = parser._load_images(str(jpg), "jpg")
    assert images[0][1] == "image/jpeg"


def test_only_page_one_is_sent_to_the_placement_pass(parser, fake_pdf2image, monkeypatch):
    """Placement must share the coordinate space the room read used."""
    fake_pdf2image["total_pages"] = 4
    seen = {}

    original = PlanParser._load_images

    def spy(self, file_path, file_type, max_pages=None):
        seen["max_pages"] = max_pages
        return original(self, file_path, file_type, max_pages=max_pages)

    monkeypatch.setattr(PlanParser, "_load_images", spy)

    # The call fails later (no client), but only after loading images — which
    # is the part under test.
    with pytest.raises(Exception):
        parser.place_fixtures_on_plan("/tmp/plan.pdf", "pdf", rooms_with_fixtures={})

    assert seen["max_pages"] == PlanParser.MAX_ANALYSIS_PAGES
