"""Branded PDF generation for LightPlan — Livewire design system.

Ink/copper/bone palette. Tier comparison images at native 3:2 aspect.
Professional typography with Helvetica (closest to Montserrat in PDF).
"""

import io
import os
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Livewire color tokens ──
INK_900 = colors.HexColor("#12120F")
INK_800 = colors.HexColor("#1C1C18")
INK_700 = colors.HexColor("#2A2A24")
INK_500 = colors.HexColor("#5B5B52")
INK_400 = colors.HexColor("#85857A")
INK_300 = colors.HexColor("#B0B0A4")
COPPER = colors.HexColor("#F7941D")
COPPER_700 = colors.HexColor("#A85200")
BONE = colors.HexColor("#FAF8F2")
BONE_100 = colors.HexColor("#F4F0E8")
BONE_200 = colors.HexColor("#ECE6D9")
BONE_300 = colors.HexColor("#DFD7C5")
WHITE = colors.white

# ── Tier image config ──
_TIER_IMAGES_DIR = Path(__file__).parent.parent / "static" / "tiers"
_IMG_RATIO = 2 / 3  # height/width (all images are 1536x1024 = 3:2)

_TIER_ROOMS = [
    ("Kitchen", "kitchen.png"),
    ("Living Room", "living.png"),
    ("Bedroom", "bedroom.png"),
    ("Dining Room", "dining.png"),
    ("Bathroom", "bathroom.png"),
]


def _tier_image(filename, width_in=7.0):
    """Load a tier image at correct 3:2 aspect ratio. Returns Image or None."""
    path = _TIER_IMAGES_DIR / filename
    if not path.exists():
        return None
    try:
        return Image(str(path), width=width_in * inch, height=width_in * _IMG_RATIO * inch)
    except Exception:
        return None


def _copper_line(width=7.0):
    t = Table([[""]], colWidths=[width * inch], rowHeights=[1.5])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), COPPER)]))
    return t


def _eyebrow_style():
    return ParagraphStyle(
        "Eyebrow", fontName="Helvetica", fontSize=8,
        textColor=COPPER_700, leading=10,
    )


def _heading_style():
    return ParagraphStyle(
        "Heading", fontName="Helvetica", fontSize=20,
        textColor=INK_800, leading=24, spaceBefore=0, spaceAfter=0,
    )


def _body_style():
    return ParagraphStyle(
        "Body", fontName="Helvetica", fontSize=10,
        textColor=INK_500, leading=15,
    )


def _section_header(eyebrow_text, heading_text):
    """Reusable: EYEBROW + Heading + copper line."""
    return [
        Paragraph(eyebrow_text, _eyebrow_style()),
        Spacer(1, 4),
        Paragraph(heading_text, _heading_style()),
        Spacer(1, 3),
        _copper_line(),
        Spacer(1, 14),
    ]


# ═══════════════════════════════════════════════════════════════════════
# Page builders
# ═══════════════════════════════════════════════════════════════════════

def _cover_page(project_name, project_address, tier, builder_name):
    """Page 1: dark header, kitchen hero image, project details."""
    elements = []
    date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

    # ── Dark header block ──
    hdr = Table([
        [Paragraph("LIVEWIRE LIGHTING",
                    ParagraphStyle("CE", fontName="Helvetica", fontSize=8,
                                   textColor=COPPER, alignment=TA_CENTER))],
        [Spacer(1, 10)],
        [Paragraph("Lighting Estimate",
                    ParagraphStyle("CT", fontName="Helvetica", fontSize=36,
                                   textColor=WHITE, alignment=TA_CENTER, leading=40))],
        [Spacer(1, 6)],
        [Paragraph(project_name,
                    ParagraphStyle("CS", fontName="Helvetica-Oblique", fontSize=13,
                                   textColor=INK_400, alignment=TA_CENTER))],
    ], colWidths=[7 * inch])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK_900),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, 0), 48),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 40),
    ]))
    elements.append(hdr)
    elements.append(Spacer(1, 3))
    elements.append(_copper_line())
    elements.append(Spacer(1, 20))

    # ── Kitchen hero image ──
    img = _tier_image("kitchen.png", 7.0)
    if img:
        elements.append(img)
        elements.append(Spacer(1, 20))

    # ── Details ──
    lbl_s = ParagraphStyle("DL", fontName="Helvetica", fontSize=7, textColor=COPPER_700)
    val_s = ParagraphStyle("DV", fontName="Helvetica", fontSize=11, textColor=INK_800, leading=14)

    for label, value in [("PROJECT", project_name), ("ADDRESS", project_address),
                         ("BUILDER", builder_name), ("DATE", date_str)]:
        if not value:
            continue
        row = Table([[Paragraph(label, lbl_s), Paragraph(value, val_s)]],
                    colWidths=[1.1 * inch, 5.9 * inch])
        row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, BONE_300),
        ]))
        elements.append(row)

    return elements


def _estimate_summary_page(summary):
    """Page 2: budget range, metrics, tier allocation."""
    elements = []
    elements.extend(_section_header("ESTIMATE OVERVIEW", "Investment Overview"))

    lo = summary.get("budget_low", 0)
    hi = summary.get("budget_high", 0)
    sqft = summary.get("total_sqft", 0)
    fixtures = summary.get("total_fixtures", 0)
    prewires = summary.get("total_prewires", 0)

    # ── Budget box ──
    box = Table([
        [Paragraph(f"${lo:,.0f}  —  ${hi:,.0f}",
                    ParagraphStyle("BH", fontName="Helvetica", fontSize=28,
                                   textColor=INK_800, alignment=TA_CENTER, leading=32))],
        [Paragraph("Estimated investment range · excluding applicable tax",
                    ParagraphStyle("BS", fontName="Helvetica", fontSize=9,
                                   textColor=INK_400, alignment=TA_CENTER))],
    ], colWidths=[7 * inch])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BONE_100),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, 0), 18),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 14),
    ]))
    elements.append(box)
    elements.append(Spacer(1, 18))

    # ── Metrics ──
    m_lbl = ParagraphStyle("ML", fontName="Helvetica", fontSize=7, textColor=COPPER_700, alignment=TA_CENTER)
    m_val = ParagraphStyle("MV", fontName="Helvetica", fontSize=20, textColor=INK_800, alignment=TA_CENTER)
    metrics = Table([
        [Paragraph("TOTAL SQFT", m_lbl), Paragraph("FIXTURES", m_lbl), Paragraph("PRE-WIRES", m_lbl)],
        [Paragraph(f"{sqft:,}", m_val), Paragraph(str(fixtures), m_val), Paragraph(str(prewires), m_val)],
    ], colWidths=[2.33 * inch, 2.33 * inch, 2.33 * inch])
    metrics.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 2),
    ]))
    elements.append(metrics)
    elements.append(Spacer(1, 20))
    elements.append(_copper_line())
    elements.append(Spacer(1, 16))

    # ── Tier allocation ──
    elements.append(Paragraph("TIER ALLOCATION", _eyebrow_style()))
    elements.append(Spacer(1, 8))

    pct_g = summary.get("pct_good", 0)
    pct_b = summary.get("pct_better", 0)
    pct_be = summary.get("pct_best", 0)
    rbt = summary.get("rooms_by_tier", {})

    th_s = ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700)
    td_s = ParagraphStyle("TD", fontName="Helvetica", fontSize=10, textColor=INK_700)
    td_b = ParagraphStyle("TDB", fontName="Helvetica-Bold", fontSize=10, textColor=INK_800)

    tier_data = [
        [Paragraph("TIER", th_s), Paragraph("ALLOCATION", th_s),
         Paragraph("ROOMS", th_s), Paragraph("PRODUCT LINE", th_s)],
    ]
    for name, pct, cnt, line in [
        ("Good", pct_g, rbt.get("good", 0), "Builder Grade — Halo, Commercial Electric"),
        ("Better", pct_b, rbt.get("better", 0), "DMF / WAC Lighting"),
        ("Best", pct_be, rbt.get("best", 0), "Ketra — full-spectrum tunable"),
    ]:
        tier_data.append([
            Paragraph(name, td_b),
            Paragraph(f"{pct}%", ParagraphStyle("TDP", fontName="Helvetica", fontSize=10, textColor=INK_700, alignment=TA_CENTER)),
            Paragraph(str(cnt), ParagraphStyle("TDC", fontName="Helvetica", fontSize=10, textColor=INK_500, alignment=TA_CENTER)),
            Paragraph(line, ParagraphStyle("TDL", fontName="Helvetica", fontSize=9, textColor=INK_500)),
        ])

    tt = Table(tier_data, colWidths=[0.9 * inch, 1.0 * inch, 0.8 * inch, 4.3 * inch])
    tt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BONE_100),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BONE_300),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(tt)
    elements.append(Spacer(1, 18))

    # ── Fixture breakdown ──
    fbt = summary.get("fixtures_by_type", {})
    if fbt:
        elements.append(Paragraph("FIXTURE BREAKDOWN", _eyebrow_style()))
        elements.append(Spacer(1, 8))
        fd = [[Paragraph("FIXTURE TYPE", ParagraphStyle("FH", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700)),
               Paragraph("COUNT", ParagraphStyle("FH2", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700, alignment=TA_RIGHT))]]
        for ft, c in sorted(fbt.items(), key=lambda x: -x[1]):
            fd.append([
                Paragraph(ft.replace("_", " ").title(), ParagraphStyle("FD", fontName="Helvetica", fontSize=10, textColor=INK_700)),
                Paragraph(str(c), ParagraphStyle("FD2", fontName="Helvetica", fontSize=10, textColor=INK_800, alignment=TA_RIGHT)),
            ])
        ft_table = Table(fd, colWidths=[5.0 * inch, 2.0 * inch])
        ft_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BONE_100),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, BONE_300),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(ft_table)

    return elements


def _tier_visuals_pages():
    """Pages showing Good/Better/Best comparison images — 2 per page, correct aspect ratio."""
    available = [(label, str(_TIER_IMAGES_DIR / fn))
                 for label, fn in _TIER_ROOMS
                 if (_TIER_IMAGES_DIR / fn).exists()]
    if not available:
        return []

    elements = []
    # Page 1: header + first 2 images
    elements.extend(_section_header("WHAT EACH TIER LOOKS LIKE", "Good · Better · Best"))
    elements.append(Paragraph(
        "The same room, three levels of lighting design. Each tier adds layers "
        "of light — more fixtures, better products, and a more refined atmosphere.",
        _body_style(),
    ))
    elements.append(Spacer(1, 12))

    # At 6.5" wide, 3:2 images are 4.33" tall. Two fit on a page with headings.
    img_w = 6.8

    for i, (label, path) in enumerate(available):
        if i == 2:
            elements.append(PageBreak())
            elements.extend(_section_header("TIER VISUALS", "Continued"))

        if i == 4:
            elements.append(PageBreak())
            elements.extend(_section_header("TIER VISUALS", "Continued"))

        elements.append(Paragraph(label.upper(), _eyebrow_style()))
        elements.append(Spacer(1, 4))
        img = _tier_image(os.path.basename(path), img_w)
        if img:
            elements.append(img)
        elements.append(Spacer(1, 14))

    return elements


def _fixture_schedule(rooms_with_fixtures, tier):
    """Fixture schedule table — clean bone/copper styling."""
    elements = []
    elements.extend(_section_header("FIXTURE SCHEDULE", "Room-by-Room Detail"))

    # Table header
    th = ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700)
    tc = ParagraphStyle("TC", fontName="Helvetica", fontSize=9, textColor=INK_700)
    tc_bold = ParagraphStyle("TCB", fontName="Helvetica-Bold", fontSize=9, textColor=INK_800)
    tc_sm = ParagraphStyle("TCS", fontName="Helvetica", fontSize=8, textColor=INK_400)
    tc_r = ParagraphStyle("TCR", fontName="Helvetica", fontSize=9, textColor=INK_500, alignment=TA_RIGHT)
    tc_c = ParagraphStyle("TCC", fontName="Helvetica", fontSize=10, textColor=INK_800, alignment=TA_CENTER)

    header = [
        Paragraph("ROOM", th),
        Paragraph("FIXTURE TYPE", th),
        Paragraph("QTY", ParagraphStyle("THC", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700, alignment=TA_CENTER)),
        Paragraph("PRODUCT", th),
        Paragraph("BUDGET", ParagraphStyle("THR", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700, alignment=TA_RIGHT)),
    ]
    data = [header]

    for room_name, fixtures in rooms_with_fixtures.items():
        groups = {}
        for f in fixtures:
            k = f.fixture_type
            if k not in groups:
                groups[k] = {"qty": 0, "product": f.product_desc or f.product_sku or "", "msrp": f.msrp_range or ""}
            groups[k]["qty"] += 1

        first = True
        for ftype, info in groups.items():
            data.append([
                Paragraph(room_name if first else "", tc_bold if first else tc),
                Paragraph(ftype.replace("_", " ").title(), tc),
                Paragraph(str(info["qty"]), tc_c),
                Paragraph(info["product"], tc_sm),
                Paragraph(info["msrp"], tc_r),
            ])
            first = False

    tbl = Table(data, colWidths=[1.4 * inch, 1.2 * inch, 0.5 * inch, 2.2 * inch, 1.7 * inch], repeatRows=1)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), BONE_100),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BONE_300),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            cmds.append(("BACKGROUND", (0, i), (-1, i), BONE))
    tbl.setStyle(TableStyle(cmds))
    elements.append(tbl)

    elements.append(Spacer(1, 14))
    elements.append(_copper_line())
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(
        "This layout is dimming-ready. All pre-wire locations are prepared "
        "for future fixture installation. Contact your Livewire representative "
        "about Lutron integration options.",
        ParagraphStyle("FN", fontName="Helvetica-Oblique", fontSize=8, textColor=INK_400),
    ))

    return elements


def _page_footer(canvas, doc):
    """Footer: copper line, brand left, page right."""
    canvas.saveState()
    canvas.setStrokeColor(COPPER)
    canvas.setLineWidth(0.5)
    canvas.line(0.75 * inch, 0.62 * inch, letter[0] - 0.75 * inch, 0.62 * inch)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(INK_400)
    canvas.drawString(0.75 * inch, 0.45 * inch, "LightPlan by Livewire")
    canvas.drawRightString(letter[0] - 0.75 * inch, 0.45 * inch, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

class PDFGenerator:
    """Generate branded LightPlan PDF deliverables."""

    def generate(
        self,
        project_name: str,
        project_address: str,
        tier: str,
        rooms_with_fixtures: dict,
        builder_name: str = "",
        include_cover: bool = True,
        schematic_layout: dict | None = None,
        floor_plan_image_path: str | None = None,
        estimate_summary: dict | None = None,
    ) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            topMargin=0.5 * inch, bottomMargin=0.75 * inch,
            leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        )

        story = []

        if include_cover:
            story.extend(_cover_page(project_name, project_address, tier, builder_name))
            story.append(PageBreak())

            if estimate_summary:
                story.extend(_estimate_summary_page(estimate_summary))
                story.append(PageBreak())

        # Tier comparison visuals
        visuals = _tier_visuals_pages()
        if visuals:
            story.extend(visuals)
            story.append(PageBreak())

        # Fixture schedule
        story.extend(_fixture_schedule(rooms_with_fixtures, tier))

        # Optional floor plan reference
        if floor_plan_image_path and os.path.isfile(floor_plan_image_path):
            story.append(PageBreak())
            story.extend(self._reference_plan_page(floor_plan_image_path))

        doc.build(story, onFirstPage=_page_footer, onLaterPages=_page_footer)
        return buffer.getvalue()

    @staticmethod
    def _reference_plan_page(image_path: str) -> list:
        """Render the uploaded floor plan as a reference page."""
        elements = []
        elements.extend(_section_header("REFERENCE", "Uploaded Floor Plan"))
        try:
            from reportlab.lib.utils import ImageReader as IR
            ir = IR(image_path)
            iw, ih = ir.getSize()
            ratio = ih / iw
            display_w = 6.5 * inch
            display_h = display_w * ratio
            max_h = 8 * inch
            if display_h > max_h:
                display_h = max_h
                display_w = display_h / ratio
            elements.append(Image(image_path, width=display_w, height=display_h))
        except Exception:
            elements.append(Paragraph("Could not load floor plan image.", _body_style()))
        return elements
