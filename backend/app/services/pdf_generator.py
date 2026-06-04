"""LightPlan™ PDF — Luxury lighting design proposal.

Inspired by Apple, Restoration Hardware, Architectural Digest.
Minimalist white backgrounds, generous whitespace, large photography,
warm brass accent (#B08D57). No heavy tables, no spreadsheet aesthetics.
"""

import io
import os
from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
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

# ── Design tokens ──
INK = colors.HexColor("#1C1C18")
INK_LIGHT = colors.HexColor("#4A4A42")
INK_MUTED = colors.HexColor("#7A7A72")
INK_HINT = colors.HexColor("#A0A098")
BRASS = colors.HexColor("#B08D57")
BRASS_LIGHT = colors.HexColor("#D4BA8A")
WHITE = colors.white
WARM_GRAY = colors.HexColor("#F7F6F3")
RULE_COLOR = colors.HexColor("#E8E5DF")

# ── Images ──
_TIER_DIR = Path(__file__).parent.parent / "static" / "tiers"
_IMG_RATIO = 2 / 3  # all images 1536×1024

_ROOMS = [
    ("Kitchen", "kitchen.png"),
    ("Living Room", "living.png"),
    ("Bedroom", "bedroom.png"),
    ("Dining Room", "dining.png"),
    ("Bathroom", "bathroom.png"),
]

# ── Tier descriptions (emotional, not technical) ──
_TIER_COPY = {
    "good": {
        "label": "Good",
        "headline": "Basic illumination",
        "bullets": [
            "Functional lighting only",
            "Minimal layering",
            "More visible shadows",
        ],
        "experience": "Reliable functional illumination.",
        "products": "Builder-grade fixtures",
    },
    "better": {
        "label": "Better",
        "headline": "Enhanced comfort",
        "bullets": [
            "Balanced ambient lighting",
            "Improved task visibility",
            "More architectural emphasis",
        ],
        "experience": "Professional-grade architectural lighting.",
        "products": "DMF + Lutron",
    },
    "best": {
        "label": "Best",
        "headline": "Luxury lighting experience",
        "bullets": [
            "Layered architectural lighting",
            "Dramatic visual depth",
            "Premium fixture performance",
            "Tunable light capability",
        ],
        "experience": "Circadian-aware lighting with premium architectural integration.",
        "products": "Ketra + Lutron",
    },
}

_ROOM_QUOTES = {
    "Kitchen": {
        "good": "Enough light to work.",
        "better": "Comfortable for everyday living.",
        "best": "A kitchen you'll never want to leave.",
    },
    "Living Room": {
        "good": "Adequate for daily use.",
        "better": "A room that feels intentional.",
        "best": "Every evening feels like an event.",
    },
    "Bedroom": {
        "good": "Basic overhead light.",
        "better": "Restful and balanced.",
        "best": "A retreat designed for how you actually live.",
    },
    "Dining Room": {
        "good": "Functional for meals.",
        "better": "Sets the right tone for dinner.",
        "best": "Every gathering becomes memorable.",
    },
    "Bathroom": {
        "good": "Sufficient task lighting.",
        "better": "Clean, flattering light.",
        "best": "A spa experience, every morning.",
    },
}


def _img(fn, w):
    p = _TIER_DIR / fn
    if not p.exists():
        return None
    try:
        return Image(str(p), width=w * inch, height=w * _IMG_RATIO * inch)
    except Exception:
        return None


def _brass_rule(w=7.0):
    t = Table([[""]], colWidths=[w * inch], rowHeights=[0.75])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BRASS)]))
    return t


def _thin_rule(w=7.0):
    t = Table([[""]], colWidths=[w * inch], rowHeights=[0.5])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), RULE_COLOR)]))
    return t


# ═══════════════════════════════════════════════════════════════════════
#  COVER
# ═══════════════════════════════════════════════════════════════════════

def _cover(name, address, tier, builder):
    el = []
    date_str = datetime.now(timezone.utc).strftime("%B %Y")

    el.append(Spacer(1, 60))

    # LightPlan™ mark
    el.append(Paragraph(
        "LightPlan™",
        ParagraphStyle("Mark", fontName="Helvetica", fontSize=14,
                       textColor=BRASS, alignment=TA_CENTER, leading=16),
    ))
    el.append(Spacer(1, 24))

    # Main title
    el.append(Paragraph(
        "A Personalized Lighting<br/>Design Strategy",
        ParagraphStyle("Title", fontName="Helvetica-Bold", fontSize=32,
                       textColor=INK, alignment=TA_CENTER, leading=38),
    ))
    el.append(Spacer(1, 20))
    el.append(_brass_rule(2))
    el.append(Spacer(1, 20))

    # For the residence
    el.append(Paragraph(
        f"For the {name}",
        ParagraphStyle("ForName", fontName="Helvetica", fontSize=16,
                       textColor=INK_LIGHT, alignment=TA_CENTER, leading=20),
    ))
    if address:
        el.append(Spacer(1, 6))
        el.append(Paragraph(
            address,
            ParagraphStyle("Addr", fontName="Helvetica", fontSize=11,
                           textColor=INK_MUTED, alignment=TA_CENTER),
        ))

    el.append(Spacer(1, 8))
    el.append(Paragraph(
        date_str,
        ParagraphStyle("Date", fontName="Helvetica", fontSize=11,
                       textColor=INK_HINT, alignment=TA_CENTER),
    ))

    el.append(Spacer(1, 36))

    # Hero image — living room (cinematic, aspirational)
    hero = _img("living.png", 7.0)
    if hero:
        el.append(hero)

    el.append(Spacer(1, 36))

    # Tagline
    el.append(Paragraph(
        "Better lighting creates a better home.",
        ParagraphStyle("Tag", fontName="Helvetica-Oblique", fontSize=13,
                       textColor=INK_MUTED, alignment=TA_CENTER, leading=16),
    ))

    return el


# ═══════════════════════════════════════════════════════════════════════
#  EXECUTIVE SUMMARY — "Your Home's Lighting Story"
# ═══════════════════════════════════════════════════════════════════════

def _story_page(summary):
    el = []
    lo = summary.get("budget_low", 0)
    hi = summary.get("budget_high", 0)
    sqft = summary.get("total_sqft", 0)
    fixtures = summary.get("total_fixtures", 0)

    el.append(Spacer(1, 20))
    el.append(Paragraph("YOUR HOME'S LIGHTING STORY",
        ParagraphStyle("SE", fontName="Helvetica", fontSize=9,
                       textColor=BRASS, alignment=TA_LEFT, leading=11)))
    el.append(Spacer(1, 10))
    el.append(_brass_rule(2))
    el.append(Spacer(1, 20))

    el.append(Paragraph(
        "Our goal is to create a layered lighting environment that enhances "
        "the architecture, improves functionality, and creates memorable "
        "spaces for everyday living.",
        ParagraphStyle("Narrative", fontName="Helvetica", fontSize=12,
                       textColor=INK_LIGHT, leading=20),
    ))
    el.append(Spacer(1, 16))

    el.append(Paragraph(
        "Lighting affects how your home feels — comfort, mood, entertaining, "
        "architecture, and daily routines. The right lighting design doesn't "
        "just illuminate a room. It transforms it.",
        ParagraphStyle("Narrative2", fontName="Helvetica", fontSize=11,
                       textColor=INK_MUTED, leading=18),
    ))
    el.append(Spacer(1, 28))
    el.append(_thin_rule())
    el.append(Spacer(1, 20))

    # Key metrics — large, clean, spaced
    ml = ParagraphStyle("ML", fontName="Helvetica", fontSize=8, textColor=BRASS, alignment=TA_CENTER)
    mv = ParagraphStyle("MV", fontName="Helvetica", fontSize=28, textColor=INK, alignment=TA_CENTER, leading=32)

    el.append(Table([
        [Paragraph("TOTAL SQUARE FOOTAGE", ml), Paragraph("FIXTURES", ml), Paragraph("PRE-WIRES", ml)],
        [Paragraph(f"{sqft:,}", mv), Paragraph(str(fixtures), mv),
         Paragraph(str(summary.get("total_prewires", 0)), mv)],
    ], colWidths=[2.33 * inch] * 3))

    el.append(Spacer(1, 24))
    el.append(_thin_rule())
    el.append(Spacer(1, 20))

    # Investment range — clean, not a spreadsheet
    el.append(Paragraph("ESTIMATED INVESTMENT RANGE",
        ParagraphStyle("IR", fontName="Helvetica", fontSize=8,
                       textColor=BRASS, alignment=TA_CENTER)))
    el.append(Spacer(1, 10))
    el.append(Paragraph(
        f"${lo:,.0f}  —  ${hi:,.0f}",
        ParagraphStyle("IV", fontName="Helvetica", fontSize=32,
                       textColor=INK, alignment=TA_CENTER, leading=36),
    ))
    el.append(Spacer(1, 6))
    el.append(Paragraph(
        "Excluding applicable tax. Final pricing confirmed during design.",
        ParagraphStyle("IN", fontName="Helvetica", fontSize=9,
                       textColor=INK_HINT, alignment=TA_CENTER),
    ))

    el.append(Spacer(1, 28))
    el.append(_thin_rule())
    el.append(Spacer(1, 16))

    # Tier summary — outcome-first, not brand-first
    for tier_key in ["good", "better", "best"]:
        tc = _TIER_COPY[tier_key]
        rbt = summary.get("rooms_by_tier", {})
        count = rbt.get(tier_key, 0)
        if count == 0:
            continue

        el.append(Table([
            [Paragraph(tc["label"].upper(), ParagraphStyle("TL", fontName="Helvetica-Bold", fontSize=9, textColor=INK)),
             Paragraph(tc["experience"], ParagraphStyle("TE", fontName="Helvetica-Oblique", fontSize=10, textColor=INK_MUTED)),
             Paragraph(f"{count} room{'s' if count != 1 else ''}", ParagraphStyle("TC", fontName="Helvetica", fontSize=9, textColor=INK_HINT, alignment=TA_RIGHT))],
        ], colWidths=[0.8 * inch, 4.4 * inch, 1.8 * inch]))
        el.append(Spacer(1, 6))

    return el


# ═══════════════════════════════════════════════════════════════════════
#  ROOM PAGES — One room per page, full visual impact
# ═══════════════════════════════════════════════════════════════════════

def _room_page(room_label, filename):
    """Full page for one room: title + image + tier descriptions + emotional quotes."""
    el = []
    img = _img(filename, 7.0)
    quotes = _ROOM_QUOTES.get(room_label, {})

    el.append(Spacer(1, 16))

    # Room title — large, elegant
    el.append(Paragraph(room_label,
        ParagraphStyle("RT", fontName="Helvetica-Bold", fontSize=28,
                       textColor=INK, leading=32)))
    el.append(Spacer(1, 4))
    el.append(_brass_rule(1.5))
    el.append(Spacer(1, 16))

    # Full-width comparison image
    if img:
        el.append(img)
    el.append(Spacer(1, 16))

    # Three-column tier descriptions
    desc_data = []
    for tier_key in ["good", "better", "best"]:
        tc = _TIER_COPY[tier_key]
        bullets = "".join(f"<br/>• {b}" for b in tc["bullets"])
        cell_content = (
            f"<b>{tc['label'].upper()}</b><br/><br/>"
            f"<i>{tc['headline']}</i>"
            f"{bullets}"
        )
        desc_data.append(Paragraph(cell_content,
            ParagraphStyle(f"Desc_{tier_key}", fontName="Helvetica", fontSize=8,
                           textColor=INK_LIGHT, leading=12)))

    desc_table = Table([desc_data], colWidths=[2.33 * inch] * 3)
    desc_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    el.append(desc_table)
    el.append(Spacer(1, 14))

    # Emotional quotes
    if quotes:
        el.append(_thin_rule())
        el.append(Spacer(1, 10))
        el.append(Paragraph("WHAT CHANGES?",
            ParagraphStyle("WC", fontName="Helvetica", fontSize=8,
                           textColor=BRASS, leading=10)))
        el.append(Spacer(1, 8))

        quote_cells = []
        for tier_key in ["good", "better", "best"]:
            q = quotes.get(tier_key, "")
            quote_cells.append(Paragraph(
                f"<b>{tier_key.title()}</b><br/><i>\"{q}\"</i>",
                ParagraphStyle(f"Q_{tier_key}", fontName="Helvetica", fontSize=9,
                               textColor=INK_MUTED, leading=13)))

        qt = Table([quote_cells], colWidths=[2.33 * inch] * 3)
        qt.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        el.append(qt)

    return el


# ═══════════════════════════════════════════════════════════════════════
#  FIXTURE SCHEDULE (APPENDIX)
# ═══════════════════════════════════════════════════════════════════════

def _schedule(rooms_with_fixtures, tier):
    el = []
    el.append(Spacer(1, 16))
    el.append(Paragraph("APPENDIX",
        ParagraphStyle("AE", fontName="Helvetica", fontSize=8,
                       textColor=BRASS, leading=10)))
    el.append(Spacer(1, 6))
    el.append(Paragraph("Detailed Fixture Schedule",
        ParagraphStyle("AH", fontName="Helvetica-Bold", fontSize=20,
                       textColor=INK, leading=24)))
    el.append(Spacer(1, 4))
    el.append(_brass_rule())
    el.append(Spacer(1, 14))

    th = ParagraphStyle("TH", fontName="Helvetica-Bold", fontSize=7, textColor=BRASS)
    tc = ParagraphStyle("TC", fontName="Helvetica", fontSize=9, textColor=INK_LIGHT)
    tcb = ParagraphStyle("TCB", fontName="Helvetica-Bold", fontSize=9, textColor=INK)
    tcs = ParagraphStyle("TCS", fontName="Helvetica", fontSize=8, textColor=INK_HINT)
    tcr = ParagraphStyle("TCR", fontName="Helvetica", fontSize=9, textColor=INK_MUTED, alignment=TA_RIGHT)
    tcc = ParagraphStyle("TCC", fontName="Helvetica", fontSize=10, textColor=INK, alignment=TA_CENTER)

    data = [[
        Paragraph("ROOM", th), Paragraph("FIXTURE TYPE", th),
        Paragraph("QTY", ParagraphStyle("THC", fontName="Helvetica-Bold", fontSize=7, textColor=BRASS, alignment=TA_CENTER)),
        Paragraph("PRODUCT", th),
        Paragraph("BUDGET", ParagraphStyle("THR", fontName="Helvetica-Bold", fontSize=7, textColor=BRASS, alignment=TA_RIGHT)),
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
        ("BACKGROUND", (0, 0), (-1, 0), WARM_GRAY),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, RULE_COLOR),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for i in range(2, len(data), 2):
        cmds.append(("BACKGROUND", (0, i), (-1, i), WARM_GRAY))
    tbl.setStyle(TableStyle(cmds))
    el.append(tbl)

    el.append(Spacer(1, 12))
    el.append(Paragraph(
        "Dimming-ready layout. Pre-wire locations prepared for future installation. "
        "Contact Livewire for Lutron integration options.",
        ParagraphStyle("FN", fontName="Helvetica-Oblique", fontSize=8, textColor=INK_HINT),
    ))
    return el


# ═══════════════════════════════════════════════════════════════════════
#  CLOSING PAGE — "The Livewire Difference"
# ═══════════════════════════════════════════════════════════════════════

def _closing():
    el = []
    el.append(Spacer(1, 60))

    el.append(Paragraph("The Livewire Difference",
        ParagraphStyle("CL", fontName="Helvetica-Bold", fontSize=28,
                       textColor=INK, alignment=TA_CENTER, leading=32)))
    el.append(Spacer(1, 12))
    el.append(_brass_rule(2))
    el.append(Spacer(1, 24))

    el.append(Paragraph(
        "Beautiful lighting is not about more fixtures.<br/>"
        "It's about placing light where it matters.",
        ParagraphStyle("CLB", fontName="Helvetica-Oblique", fontSize=16,
                       textColor=INK_LIGHT, alignment=TA_CENTER, leading=24),
    ))
    el.append(Spacer(1, 36))

    # Four pillars
    pillars = [
        ("DESIGN EXPERTISE", "Thoughtful lighting design tailored to your home's architecture and how you live."),
        ("PROFESSIONAL INSTALLATION", "Clean, meticulous installation by experienced technicians."),
        ("PROGRAMMING & TUNING", "Every scene calibrated. Every dimmer set. Light that responds to your day."),
        ("LIFETIME SUPPORT", "We're here after move-in. Updates, adjustments, and expansions as your home evolves."),
    ]

    for title, desc in pillars:
        el.append(Paragraph(title,
            ParagraphStyle("PT", fontName="Helvetica-Bold", fontSize=9,
                           textColor=BRASS, leading=11)))
        el.append(Spacer(1, 4))
        el.append(Paragraph(desc,
            ParagraphStyle("PD", fontName="Helvetica", fontSize=11,
                           textColor=INK_MUTED, leading=16)))
        el.append(Spacer(1, 16))

    el.append(Spacer(1, 20))

    # Closing hero
    hero = _img("kitchen.png", 7.0)
    if hero:
        el.append(hero)

    return el


# ═══════════════════════════════════════════════════════════════════════
#  FOOTER
# ═══════════════════════════════════════════════════════════════════════

def _footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(RULE_COLOR)
    canvas.setLineWidth(0.5)
    canvas.line(0.75 * inch, 0.58 * inch, letter[0] - 0.75 * inch, 0.58 * inch)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(INK_HINT)
    canvas.drawString(0.75 * inch, 0.42 * inch, "LightPlan™ by Livewire")
    canvas.drawRightString(letter[0] - 0.75 * inch, 0.42 * inch, f"{canvas.getPageNumber()}")
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

        # 1. Cover
        if include_cover:
            story.extend(_cover(project_name, project_address, tier, builder_name))
            story.append(PageBreak())

        # 2. Your Home's Lighting Story
        if estimate_summary:
            story.extend(_story_page(estimate_summary))
            story.append(PageBreak())

        # 3-7. Room pages — one per page, full visual impact
        for label, fn in _ROOMS:
            if (_TIER_DIR / fn).exists():
                story.extend(_room_page(label, fn))
                story.append(PageBreak())

        # 8. Appendix: detailed fixture schedule
        story.extend(_schedule(rooms_with_fixtures, tier))
        story.append(PageBreak())

        # 9. The Livewire Difference
        story.extend(_closing())

        # Optional: floor plan reference
        if floor_plan_image_path and os.path.isfile(floor_plan_image_path):
            story.append(PageBreak())
            story.append(Spacer(1, 16))
            story.append(Paragraph("REFERENCE", ParagraphStyle(
                "RE", fontName="Helvetica", fontSize=8, textColor=BRASS)))
            story.append(Spacer(1, 6))
            story.append(Paragraph("Uploaded Floor Plan", ParagraphStyle(
                "RH", fontName="Helvetica-Bold", fontSize=20, textColor=INK, leading=24)))
            story.append(Spacer(1, 4))
            story.append(_brass_rule())
            story.append(Spacer(1, 14))
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
                pass

        doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
        return buf.getvalue()
