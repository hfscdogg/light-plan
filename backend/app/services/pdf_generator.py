"""Branded PDF generation for LightPlan — Livewire design system.

Ink/copper/bone palette. Tier comparison images at native 3:2 aspect.
Helvetica (closest to Montserrat available in PDF).
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

# ── Livewire tokens ──
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

# ── Images ──
_TIER_DIR = Path(__file__).parent.parent / "static" / "tiers"
_IMG_RATIO = 2 / 3  # h/w — all images are 1536×1024 (3:2)

_ROOMS = [
    ("Kitchen", "kitchen.png"),
    ("Living Room", "living.png"),
    ("Bedroom", "bedroom.png"),
    ("Dining Room", "dining.png"),
    ("Bathroom", "bathroom.png"),
]


# ── Reusable helpers ──

def _img(filename, w_in):
    """Load tier image at correct 3:2 aspect. Returns Image or None."""
    p = _TIER_DIR / filename
    if not p.exists():
        return None
    try:
        return Image(str(p), width=w_in * inch, height=w_in * _IMG_RATIO * inch)
    except Exception:
        return None


def _line(w=7.0):
    t = Table([[""]], colWidths=[w * inch], rowHeights=[1.5])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), COPPER)]))
    return t


def _ey():
    return ParagraphStyle("EY", fontName="Helvetica", fontSize=8, textColor=COPPER_700, leading=10)


def _hd():
    return ParagraphStyle("HD", fontName="Helvetica", fontSize=20, textColor=INK_800, leading=24)


def _bd():
    return ParagraphStyle("BD", fontName="Helvetica", fontSize=10, textColor=INK_500, leading=15)


def _sec(eyebrow, heading):
    """Eyebrow + heading + copper line."""
    return [
        Paragraph(eyebrow, _ey()), Spacer(1, 4),
        Paragraph(heading, _hd()), Spacer(1, 3),
        _line(), Spacer(1, 14),
    ]


# ═══════════════════════════════════════════════════════════════════════
#  PAGE 1 — COVER
# ═══════════════════════════════════════════════════════════════════════

def _cover(name, address, tier, builder):
    el = []
    date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

    # ── Full-width dark block ──
    hdr = Table([
        [Paragraph("LIVEWIRE LIGHTING", ParagraphStyle(
            "CE", fontName="Helvetica", fontSize=9, textColor=COPPER,
            alignment=TA_CENTER, leading=11))],
        [Spacer(1, 16)],
        [Paragraph("Lighting", ParagraphStyle(
            "CT1", fontName="Helvetica", fontSize=44, textColor=WHITE,
            alignment=TA_CENTER, leading=48))],
        [Paragraph("Estimate", ParagraphStyle(
            "CT2", fontName="Helvetica-Oblique", fontSize=44,
            textColor=colors.HexColor("#B0B0A4"), alignment=TA_CENTER, leading=48))],
        [Spacer(1, 12)],
        [_line(3)],
        [Spacer(1, 12)],
        [Paragraph(name, ParagraphStyle(
            "CN", fontName="Helvetica", fontSize=14, textColor=INK_300,
            alignment=TA_CENTER))],
    ], colWidths=[7 * inch])
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), INK_900),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, 0), 40),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 36),
    ]))
    el.append(hdr)
    el.append(Spacer(1, 3))
    el.append(_line())
    el.append(Spacer(1, 16))

    # ── Living room hero (wider, more cinematic than kitchen) ──
    hero = _img("living.png", 7.0)
    if hero:
        el.append(hero)
        el.append(Spacer(1, 16))

    # ── Details in a compact 2×2 grid ──
    lbl = ParagraphStyle("DL", fontName="Helvetica", fontSize=7, textColor=COPPER_700, leading=9)
    val = ParagraphStyle("DV", fontName="Helvetica", fontSize=11, textColor=INK_800, leading=14)

    pairs = [(k, v) for k, v in [
        ("PROJECT", name), ("ADDRESS", address), ("BUILDER", builder), ("DATE", date_str),
    ] if v]

    if len(pairs) >= 4:
        grid = Table([
            [Paragraph(pairs[0][0], lbl), Paragraph(pairs[0][1], val),
             Paragraph(pairs[1][0], lbl), Paragraph(pairs[1][1], val)],
            [Paragraph(pairs[2][0], lbl), Paragraph(pairs[2][1], val),
             Paragraph(pairs[3][0], lbl), Paragraph(pairs[3][1], val)],
        ], colWidths=[0.9 * inch, 2.6 * inch, 0.9 * inch, 2.6 * inch])
    else:
        rows = [[Paragraph(k, lbl), Paragraph(v, val)] for k, v in pairs]
        grid = Table(rows, colWidths=[1.1 * inch, 5.9 * inch])

    grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BONE_300),
    ]))
    el.append(grid)

    el.append(Spacer(1, 20))
    el.append(Paragraph(
        "This estimate provides a preliminary range of anticipated costs. "
        "Figures may be adjusted as design details are finalized.",
        ParagraphStyle("FN", fontName="Helvetica-Oblique", fontSize=8,
                       textColor=INK_400, alignment=TA_CENTER, leading=12),
    ))

    return el


# ═══════════════════════════════════════════════════════════════════════
#  PAGE 2 — ESTIMATE SUMMARY
# ═══════════════════════════════════════════════════════════════════════

def _summary(s):
    el = []
    el.extend(_sec("ESTIMATE OVERVIEW", "Investment Overview"))

    lo, hi = s.get("budget_low", 0), s.get("budget_high", 0)
    sqft = s.get("total_sqft", 0)
    fix = s.get("total_fixtures", 0)
    pre = s.get("total_prewires", 0)

    # Budget box
    box = Table([
        [Paragraph(f"${lo:,.0f}  —  ${hi:,.0f}", ParagraphStyle(
            "BH", fontName="Helvetica", fontSize=30, textColor=INK_800,
            alignment=TA_CENTER, leading=34))],
        [Paragraph("Estimated investment range · excluding tax", ParagraphStyle(
            "BS", fontName="Helvetica", fontSize=9, textColor=INK_400,
            alignment=TA_CENTER))],
    ], colWidths=[7 * inch])
    box.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), BONE_100),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, 0), 20), ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
    ]))
    el.append(box)
    el.append(Spacer(1, 16))

    # Metrics
    ml = ParagraphStyle("ML", fontName="Helvetica", fontSize=7, textColor=COPPER_700, alignment=TA_CENTER)
    mv = ParagraphStyle("MV", fontName="Helvetica", fontSize=20, textColor=INK_800, alignment=TA_CENTER)
    el.append(Table([
        [Paragraph("TOTAL SQFT", ml), Paragraph("FIXTURES", ml), Paragraph("PRE-WIRES", ml)],
        [Paragraph(f"{sqft:,}", mv), Paragraph(str(fix), mv), Paragraph(str(pre), mv)],
    ], colWidths=[2.33 * inch] * 3))
    el.append(Spacer(1, 16))
    el.append(_line())
    el.append(Spacer(1, 14))

    # Tier table
    el.append(Paragraph("TIER ALLOCATION", _ey()))
    el.append(Spacer(1, 8))
    th = ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700)
    td = ParagraphStyle("TD", fontName="Helvetica", fontSize=10, textColor=INK_700)
    tb = ParagraphStyle("TB", fontName="Helvetica-Bold", fontSize=10, textColor=INK_800)

    rbt = s.get("rooms_by_tier", {})
    rows = [
        [Paragraph("TIER", th), Paragraph("SPLIT", th), Paragraph("ROOMS", th), Paragraph("PRODUCT LINE", th)],
        [Paragraph("Good", tb), Paragraph(f"{s.get('pct_good',0)}%", td),
         Paragraph(str(rbt.get("good", 0)), td), Paragraph("Builder Grade — Halo, Commercial Electric", td)],
        [Paragraph("Better", tb), Paragraph(f"{s.get('pct_better',0)}%", td),
         Paragraph(str(rbt.get("better", 0)), td), Paragraph("DMF / WAC Lighting", td)],
        [Paragraph("Best", tb), Paragraph(f"{s.get('pct_best',0)}%", td),
         Paragraph(str(rbt.get("best", 0)), td), Paragraph("Ketra — full-spectrum tunable", td)],
    ]
    tt = Table(rows, colWidths=[0.8 * inch, 0.7 * inch, 0.7 * inch, 4.8 * inch])
    tt.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BONE_100),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BONE_300),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    el.append(tt)
    el.append(Spacer(1, 16))

    # Fixture breakdown
    fbt = s.get("fixtures_by_type", {})
    if fbt:
        el.append(Paragraph("FIXTURE BREAKDOWN", _ey()))
        el.append(Spacer(1, 8))
        fd = [[Paragraph("TYPE", ParagraphStyle("FH", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700)),
               Paragraph("COUNT", ParagraphStyle("FH2", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700, alignment=TA_RIGHT))]]
        for ft, c in sorted(fbt.items(), key=lambda x: -x[1]):
            fd.append([Paragraph(ft.replace("_", " ").title(), td),
                       Paragraph(str(c), ParagraphStyle("FC", fontName="Helvetica", fontSize=10, textColor=INK_800, alignment=TA_RIGHT))])
        ft_t = Table(fd, colWidths=[5 * inch, 2 * inch])
        ft_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BONE_100),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, BONE_300),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        el.append(ft_t)

    return el


# ═══════════════════════════════════════════════════════════════════════
#  PAGES 3-4 — TIER VISUALS (2 images per page, compact)
# ═══════════════════════════════════════════════════════════════════════

def _tier_visuals():
    avail = [(l, fn) for l, fn in _ROOMS if (_TIER_DIR / fn).exists()]
    if not avail:
        return []

    el = []
    # Images at 6" wide = 4" tall (3:2). Two per page = 8" + labels fits in ~9.25" usable.
    W = 6.0
    PER_PAGE = 2

    for i, (label, fn) in enumerate(avail):
        if i == 0:
            el.extend(_sec("WHAT EACH TIER LOOKS LIKE", "Good · Better · Best"))
            el.append(Paragraph(
                "The same room, three levels of lighting design. Each tier adds "
                "layers of light, better products, and a more refined atmosphere.",
                _bd(),
            ))
            el.append(Spacer(1, 12))
        elif i % PER_PAGE == 0:
            el.append(PageBreak())
            el.extend(_sec("TIER VISUALS", "Continued"))

        el.append(Paragraph(label.upper(), _ey()))
        el.append(Spacer(1, 4))
        img = _img(fn, W)
        if img:
            el.append(img)
        el.append(Spacer(1, 16))

    return el


# ═══════════════════════════════════════════════════════════════════════
#  FIXTURE SCHEDULE
# ═══════════════════════════════════════════════════════════════════════

def _schedule(rooms_with_fixtures, tier):
    el = []
    el.extend(_sec("FIXTURE SCHEDULE", "Room-by-Room Detail"))

    th = ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700)
    tc = ParagraphStyle("TC", fontName="Helvetica", fontSize=9, textColor=INK_700)
    tcb = ParagraphStyle("TCB", fontName="Helvetica-Bold", fontSize=9, textColor=INK_800)
    tcs = ParagraphStyle("TCS", fontName="Helvetica", fontSize=8, textColor=INK_400)
    tcr = ParagraphStyle("TCR", fontName="Helvetica", fontSize=9, textColor=INK_500, alignment=TA_RIGHT)
    tcc = ParagraphStyle("TCC", fontName="Helvetica", fontSize=10, textColor=INK_800, alignment=TA_CENTER)

    data = [[
        Paragraph("ROOM", th), Paragraph("FIXTURE TYPE", th),
        Paragraph("QTY", ParagraphStyle("THC", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700, alignment=TA_CENTER)),
        Paragraph("PRODUCT", th),
        Paragraph("BUDGET", ParagraphStyle("THR", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700, alignment=TA_RIGHT)),
    ]]

    for room, fixtures in rooms_with_fixtures.items():
        grp = {}
        for f in fixtures:
            k = f.fixture_type
            if k not in grp:
                grp[k] = {"qty": 0, "prod": f.product_desc or f.product_sku or "", "msrp": f.msrp_range or ""}
            grp[k]["qty"] += 1
        first = True
        for ft, info in grp.items():
            data.append([
                Paragraph(room if first else "", tcb if first else tc),
                Paragraph(ft.replace("_", " ").title(), tc),
                Paragraph(str(info["qty"]), tcc),
                Paragraph(info["prod"], tcs),
                Paragraph(info["msrp"], tcr),
            ])
            first = False

    tbl = Table(data, colWidths=[1.4 * inch, 1.2 * inch, 0.5 * inch, 2.2 * inch, 1.7 * inch], repeatRows=1)
    cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), BONE_100),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, BONE_300),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            cmds.append(("BACKGROUND", (0, i), (-1, i), BONE))
    tbl.setStyle(TableStyle(cmds))
    el.append(tbl)
    el.append(Spacer(1, 14))
    el.append(_line())
    el.append(Spacer(1, 8))
    el.append(Paragraph(
        "Dimming-ready layout. All pre-wire locations prepared for future installation. "
        "Contact your Livewire representative about Lutron integration.",
        ParagraphStyle("FN", fontName="Helvetica-Oblique", fontSize=8, textColor=INK_400),
    ))
    return el


# ═══════════════════════════════════════════════════════════════════════
#  FOOTER
# ═══════════════════════════════════════════════════════════════════════

def _footer(canvas, doc):
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
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════

class PDFGenerator:

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
        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf, pagesize=letter,
            topMargin=0.5 * inch, bottomMargin=0.75 * inch,
            leftMargin=0.75 * inch, rightMargin=0.75 * inch,
        )
        story = []

        # Page 1: Cover
        if include_cover:
            story.extend(_cover(project_name, project_address, tier, builder_name))
            story.append(PageBreak())

        # Page 2: Estimate summary (if form-driven)
        if estimate_summary:
            story.extend(_summary(estimate_summary))
            story.append(PageBreak())

        # Pages 3+: Tier visuals (2 per page)
        vis = _tier_visuals()
        if vis:
            story.extend(vis)
            story.append(PageBreak())

        # Fixture schedule
        story.extend(_schedule(rooms_with_fixtures, tier))

        # Optional floor plan reference
        if floor_plan_image_path and os.path.isfile(floor_plan_image_path):
            story.append(PageBreak())
            story.extend(_sec("REFERENCE", "Uploaded Floor Plan"))
            try:
                from reportlab.lib.utils import ImageReader
                ir = ImageReader(floor_plan_image_path)
                iw, ih = ir.getSize()
                r = ih / iw
                dw = 6.5 * inch
                dh = min(dw * r, 8 * inch)
                if dh == 8 * inch:
                    dw = dh / r
                story.append(Image(floor_plan_image_path, width=dw, height=dh))
            except Exception:
                story.append(Paragraph("Could not load floor plan image.", _bd()))

        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
        return buf.getvalue()
