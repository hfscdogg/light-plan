"""Branded PDF generation for LightPlan deliverables.

Generates a professional fixture schedule PDF with Livewire branding
using a dark charcoal and gold color scheme.
"""

import io
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from reportlab.graphics.shapes import (
    Circle,
    Drawing,
    Rect,
    String,
)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

INK_900 = colors.HexColor("#12120F")
INK_800 = colors.HexColor("#1C1C18")
INK_700 = colors.HexColor("#2A2A24")
INK_500 = colors.HexColor("#5B5B52")
INK_400 = colors.HexColor("#85857A")
COPPER = colors.HexColor("#F7941D")
COPPER_700 = colors.HexColor("#A85200")
BONE = colors.HexColor("#FAF8F2")
BONE_100 = colors.HexColor("#F4F0E8")
BONE_200 = colors.HexColor("#ECE6D9")
BONE_300 = colors.HexColor("#DFD7C5")
WHITE = colors.white
# Legacy aliases used by existing methods
CHARCOAL = INK_800
CHARCOAL_LIGHT = INK_700
GOLD = COPPER
GOLD_LIGHT = colors.HexColor("#F6A85F")
LIGHT_GRAY = BONE_100
MID_GRAY = BONE_300
HINT = INK_400
MUTED = INK_500


def _styles():
    """Build custom paragraph styles matching the IC aesthetic."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "LPTitle",
            parent=base["Title"],
            fontName="Helvetica",
            fontSize=32,
            textColor=CHARCOAL,
            alignment=TA_CENTER,
            spaceAfter=4,
            leading=36,
        ),
        "subtitle": ParagraphStyle(
            "LPSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            textColor=GOLD,
            alignment=TA_CENTER,
            spaceAfter=16,
        ),
        "heading": ParagraphStyle(
            "LPHeading",
            parent=base["Heading1"],
            fontName="Helvetica",
            fontSize=18,
            textColor=CHARCOAL,
            spaceBefore=12,
            spaceAfter=6,
            leading=22,
        ),
        "body": ParagraphStyle(
            "LPBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=MUTED,
            leading=15,
        ),
        "body_white": ParagraphStyle(
            "LPBodyWhite",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=WHITE,
            leading=15,
        ),
        "eyebrow": ParagraphStyle(
            "LPEyebrow",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=GOLD,
            leading=10,
        ),
        "footer": ParagraphStyle(
            "LPFooter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=HINT,
            alignment=TA_CENTER,
        ),
        "table_header": ParagraphStyle(
            "LPTableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            textColor=GOLD,
        ),
        "table_cell": ParagraphStyle(
            "LPTableCell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9,
            textColor=CHARCOAL,
        ),
        "room_label": ParagraphStyle(
            "LPRoomLabel",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=CHARCOAL,
        ),
    }


class PDFGenerator:
    """Generate branded LightPlan PDF deliverables."""

    def __init__(self):
        self.styles = _styles()

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
        """Generate the complete PDF and return as bytes."""
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            topMargin=0.5 * inch,
            bottomMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
        )

        story = []

        if include_cover:
            story.extend(
                self._cover_page(project_name, project_address, tier, builder_name)
            )
            story.append(PageBreak())

            if estimate_summary:
                story.extend(self._estimate_summary_page(estimate_summary))
                story.append(PageBreak())
            else:
                story.extend(self._why_smart_lighting_page())
                story.append(PageBreak())

        # Tier comparison visuals page
        tier_visuals = self._tier_visuals_page()
        if tier_visuals:
            story.extend(tier_visuals)
            story.append(PageBreak())

        # Legacy concept gallery (floor plan mode only)
        if not estimate_summary:
            concept_elements = self._concept_gallery_page(tier)
            if concept_elements:
                story.extend(concept_elements)
                story.append(PageBreak())

        # Schematic layout page (floor plan mode only)
        if not estimate_summary and schematic_layout and schematic_layout.get("rooms"):
            story.extend(self._schematic_page(schematic_layout))
            story.append(PageBreak())

        story.extend(self._fixture_schedule(rooms_with_fixtures, tier))

        # Reference floor plan page (if image exists on disk)
        if floor_plan_image_path and os.path.isfile(floor_plan_image_path):
            story.append(PageBreak())
            story.extend(self._reference_plan_page(floor_plan_image_path))

        doc.build(story, onFirstPage=self._page_footer, onLaterPages=self._page_footer)
        return buffer.getvalue()

    _TIER_IMAGES_DIR = Path(__file__).parent.parent.parent.parent / "frontend" / "public" / "images" / "tiers"

    def _copper_line(self, width=7):
        """Thin copper accent line."""
        t = Table([[""]], colWidths=[width * inch], rowHeights=[1.5])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), COPPER)]))
        return t

    def _cover_page(
        self,
        project_name: str,
        project_address: str,
        tier: str,
        builder_name: str,
    ) -> list:
        """Build the branded cover page — Livewire design system."""
        elements = []
        date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

        # Dark header block with brand
        eyebrow_style = ParagraphStyle(
            "CoverEyebrow", fontName="Helvetica", fontSize=8,
            textColor=COPPER, alignment=TA_CENTER, leading=10,
        )
        title_style = ParagraphStyle(
            "CoverTitle", fontName="Helvetica", fontSize=36,
            textColor=colors.white, alignment=TA_CENTER, leading=40,
        )
        sub_style = ParagraphStyle(
            "CoverSub", fontName="Helvetica", fontSize=11,
            textColor=colors.HexColor("#85857A"), alignment=TA_CENTER,
        )

        header_data = [
            [Paragraph("LIVEWIRE LIGHTING", eyebrow_style)],
            [Spacer(1, 8)],
            [Paragraph("Lighting Estimate", title_style)],
            [Spacer(1, 6)],
            [Paragraph(project_name, sub_style)],
        ]
        header_table = Table(header_data, colWidths=[7 * inch])
        header_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), INK_900),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, 0), 56),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 48),
        ]))
        elements.append(header_table)
        elements.append(Spacer(1, 4))

        # Copper accent line
        elements.append(self._copper_line())
        elements.append(Spacer(1, 32))

        # Project details — clean two-column layout
        detail_pairs = [
            ("Project", project_name),
            ("Address", project_address or ""),
            ("Builder", builder_name or ""),
            ("Date", date_str),
        ]

        lbl_style = ParagraphStyle(
            "DetailLabel", fontName="Helvetica", fontSize=8,
            textColor=COPPER_700, leading=12,
        )
        val_style = ParagraphStyle(
            "DetailValue", fontName="Helvetica", fontSize=11,
            textColor=INK_800, leading=15,
        )

        for label, value in detail_pairs:
            if not value:
                continue
            row = Table(
                [[Paragraph(label.upper(), lbl_style), Paragraph(value, val_style)]],
                colWidths=[1.3 * inch, 5.7 * inch],
            )
            row.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, BONE_300),
            ]))
            elements.append(row)

        elements.append(Spacer(1, 40))

        # Closing note
        elements.append(Paragraph(
            "This estimate provides a preliminary range of anticipated costs. "
            "Figures may be adjusted as design details are finalized.",
            ParagraphStyle(
                "CoverNote", fontName="Helvetica-Oblique", fontSize=9,
                textColor=INK_400, leading=14, alignment=TA_CENTER,
            ),
        ))

        return elements

    def _estimate_summary_page(self, summary: dict) -> list:
        """Estimate overview page — Livewire design system."""
        elements = []

        elements.append(Paragraph("ESTIMATE OVERVIEW", self.styles["eyebrow"]))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph("Investment Overview", self.styles["heading"]))
        elements.append(self._copper_line())
        elements.append(Spacer(1, 20))

        budget_lo = summary.get("budget_low", 0)
        budget_hi = summary.get("budget_high", 0)
        total_sqft = summary.get("total_sqft", 0)
        total_fixtures = summary.get("total_fixtures", 0)

        # Budget hero
        budget_block = Table(
            [
                [Paragraph(
                    f"${budget_lo:,.0f}  —  ${budget_hi:,.0f}",
                    ParagraphStyle("BudgetHero", fontName="Helvetica", fontSize=28,
                                   textColor=INK_800, alignment=TA_CENTER, leading=32),
                )],
                [Paragraph(
                    "Estimated investment · excluding applicable tax",
                    ParagraphStyle("BudgetSub", fontName="Helvetica", fontSize=9,
                                   textColor=INK_400, alignment=TA_CENTER),
                )],
            ],
            colWidths=[7 * inch],
        )
        budget_block.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BONE_100),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, 0), 20),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 16),
            ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ]))
        elements.append(budget_block)
        elements.append(Spacer(1, 20))

        # Key metrics
        metrics = Table(
            [
                [
                    Paragraph("TOTAL SQFT", ParagraphStyle("ML", fontName="Helvetica", fontSize=7, textColor=COPPER_700, alignment=TA_CENTER)),
                    Paragraph("FIXTURES", ParagraphStyle("ML2", fontName="Helvetica", fontSize=7, textColor=COPPER_700, alignment=TA_CENTER)),
                    Paragraph("PRE-WIRES", ParagraphStyle("ML3", fontName="Helvetica", fontSize=7, textColor=COPPER_700, alignment=TA_CENTER)),
                ],
                [
                    Paragraph(f"{total_sqft:,}", ParagraphStyle("MV", fontName="Helvetica", fontSize=18, textColor=INK_800, alignment=TA_CENTER)),
                    Paragraph(str(total_fixtures), ParagraphStyle("MV2", fontName="Helvetica", fontSize=18, textColor=INK_800, alignment=TA_CENTER)),
                    Paragraph(str(summary.get("total_prewires", 0)), ParagraphStyle("MV3", fontName="Helvetica", fontSize=18, textColor=INK_800, alignment=TA_CENTER)),
                ],
            ],
            colWidths=[2.3 * inch, 2.3 * inch, 2.3 * inch],
        )
        metrics.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, 0), 2),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 4),
            ("LINEBELOW", (0, 1), (-1, 1), 0.5, BONE_300),
        ]))
        elements.append(metrics)
        elements.append(Spacer(1, 20))

        # Tier allocation
        elements.append(Paragraph("TIER ALLOCATION", self.styles["eyebrow"]))
        elements.append(Spacer(1, 8))

        pct_good = summary.get("pct_good", 0)
        pct_better = summary.get("pct_better", 0)
        pct_best = summary.get("pct_best", 0)
        rooms_by_tier = summary.get("rooms_by_tier", {})

        tier_data = [
            [
                Paragraph("TIER", ParagraphStyle("TH1", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700)),
                Paragraph("ALLOCATION", ParagraphStyle("TH2", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700, alignment=TA_CENTER)),
                Paragraph("ROOMS", ParagraphStyle("TH3", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700, alignment=TA_CENTER)),
                Paragraph("PRODUCT LINE", ParagraphStyle("TH4", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700)),
            ],
        ]
        for label, pct, count, line in [
            ("Good", pct_good, rooms_by_tier.get("good", 0), "Builder Grade (Halo, Commercial Electric)"),
            ("Better", pct_better, rooms_by_tier.get("better", 0), "DMF / WAC Lighting"),
            ("Best", pct_best, rooms_by_tier.get("best", 0), "Ketra (full-spectrum tunable)"),
        ]:
            tier_data.append([
                Paragraph(label, ParagraphStyle("TD1", fontName="Helvetica-Bold", fontSize=10, textColor=INK_800)),
                Paragraph(f"{pct}%", ParagraphStyle("TD2", fontName="Helvetica", fontSize=10, textColor=INK_700, alignment=TA_CENTER)),
                Paragraph(str(count), ParagraphStyle("TD3", fontName="Helvetica", fontSize=10, textColor=INK_500, alignment=TA_CENTER)),
                Paragraph(line, ParagraphStyle("TD4", fontName="Helvetica", fontSize=9, textColor=INK_500)),
            ])

        tier_table = Table(tier_data, colWidths=[1.0 * inch, 1.1 * inch, 0.8 * inch, 4.1 * inch])
        tier_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), BONE_100),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, BONE_300),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elements.append(tier_table)
        elements.append(Spacer(1, 20))

        # Tier comparison image — kitchen as universal example
        kitchen_img = self._TIER_IMAGES_DIR / "kitchen.png"
        if kitchen_img.exists():
            elements.append(Paragraph("WHAT EACH TIER LOOKS LIKE", self.styles["eyebrow"]))
            elements.append(Spacer(1, 6))
            try:
                img = Image(str(kitchen_img), width=7 * inch, height=3.2 * inch)
                elements.append(img)
            except Exception:
                pass
            elements.append(Spacer(1, 16))

        # Fixture breakdown
        fixtures_by_type = summary.get("fixtures_by_type", {})
        if fixtures_by_type:
            elements.append(Paragraph("FIXTURE BREAKDOWN", self.styles["eyebrow"]))
            elements.append(Spacer(1, 8))

            fix_data = [
                [
                    Paragraph("FIXTURE TYPE", ParagraphStyle("FH1", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700)),
                    Paragraph("COUNT", ParagraphStyle("FH2", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700, alignment=TA_RIGHT)),
                ],
            ]
            for ftype, count in sorted(fixtures_by_type.items(), key=lambda x: -x[1]):
                fix_data.append([
                    Paragraph(ftype.replace("_", " ").title(), ParagraphStyle("FD1", fontName="Helvetica", fontSize=10, textColor=INK_700)),
                    Paragraph(str(count), ParagraphStyle("FD2", fontName="Helvetica", fontSize=10, textColor=INK_800, alignment=TA_RIGHT)),
                ])

            fix_table = Table(fix_data, colWidths=[5 * inch, 2 * inch])
            fix_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), BONE_100),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, BONE_300),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]))
            elements.append(fix_table)

        return elements

    def _tier_visuals_page(self) -> list:
        """Full page showing Good/Better/Best comparison images for key rooms."""
        room_images = [
            ("Kitchen", "kitchen.png"),
            ("Living Room", "living.png"),
            ("Bedroom", "bedroom.png"),
            ("Dining Room", "dining.png"),
            ("Bathroom", "bathroom.png"),
        ]

        available = []
        for label, filename in room_images:
            path = self._TIER_IMAGES_DIR / filename
            if path.exists():
                available.append((label, str(path)))

        if not available:
            return []

        elements = []
        elements.append(Paragraph("WHAT EACH TIER LOOKS LIKE", self.styles["eyebrow"]))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph("Good · Better · Best", self.styles["heading"]))
        elements.append(self._copper_line())
        elements.append(Spacer(1, 6))

        elements.append(Paragraph(
            "The same room, three levels of lighting design. "
            "Each tier adds layers of light — more fixtures, better products, "
            "and a more refined atmosphere.",
            ParagraphStyle("TierVisIntro", fontName="Helvetica", fontSize=9,
                           textColor=INK_400, leading=13),
        ))
        elements.append(Spacer(1, 10))

        # Show up to 3 images per page (they're wide triptychs)
        img_w = 7 * inch
        img_h = 2.6 * inch

        for label, path in available[:3]:
            elements.append(Spacer(1, 4))
            elements.append(Paragraph(
                label.upper(),
                ParagraphStyle("RoomVisLabel", fontName="Helvetica-Bold",
                               fontSize=7, textColor=COPPER_700),
            ))
            elements.append(Spacer(1, 3))
            try:
                img = Image(path, width=img_w, height=img_h)
                elements.append(img)
            except Exception:
                pass
            elements.append(Spacer(1, 6))

        return elements

    def _why_smart_lighting_page(self) -> list:
        """Build the 'Why Smart Lighting' cover sheet."""
        elements = []

        elements.append(Paragraph("Why Smart Lighting?", self.styles["heading"]))
        elements.append(Spacer(1, 8))

        # Gold accent line
        line_data = [[""]]
        line_table = Table(line_data, colWidths=[7 * inch], rowHeights=[2])
        line_table.setStyle(
            TableStyle([("BACKGROUND", (0, 0), (-1, -1), GOLD)])
        )
        elements.append(line_table)
        elements.append(Spacer(1, 16))

        body = self.styles["body"]
        paragraphs = [
            (
                "Lighting accounts for up to 20% of a home's energy use. A well-designed "
                "lighting layout does more than look good. It improves comfort, increases "
                "home value and reduces long-term energy costs."
            ),
            (
                "Most builders rely on the electrician to place fixtures based on code "
                "minimums. The result is functional but uninspired. Homebuyers notice the "
                "difference between a thoughtfully lit home and one that was wired as an "
                "afterthought."
            ),
            (
                "<b>What you get with a LightPlan layout:</b>"
            ),
            (
                "\u2022  Fixture placement optimized for each room's purpose and size<br/>"
                "\u2022  Pre-wire locations for ceiling fans, accent lighting and landscape uplighting<br/>"
                "\u2022  A clear fixture schedule your electrician can bid from<br/>"
                "\u2022  Product recommendations matched to your project's budget"
            ),
            (
                "Every layout is dimming-ready, so your buyers can upgrade to smart "
                "controls at any point without rewiring. The pre-wire is the hard part. "
                "Get it right before drywall and everything else is easy."
            ),
            (
                "This report was prepared by Livewire, your local technology integration "
                "partner. We handle everything from fixture selection to installation and "
                "programming. Ask your rep about Lutron integration options."
            ),
        ]

        for p in paragraphs:
            elements.append(Paragraph(p, body))
            elements.append(Spacer(1, 10))

        return elements

    # Path to pre-generated concept images
    _CONCEPTS_DIR = Path(__file__).parent.parent / "static" / "concepts"

    # Rooms to include in the concept gallery (display order)
    _CONCEPT_ROOMS = [
        ("kitchen", "Kitchen"),
        ("living", "Living Room"),
        ("master_bedroom", "Master Bedroom"),
        ("master_bathroom", "Master Bathroom"),
        ("dining", "Dining Room"),
    ]

    def _concept_gallery_page(self, tier: str) -> list:
        """Build a concept visuals page showing room renders for the tier."""
        tier_key = tier.lower()
        tier_label = {"good": "Good", "better": "Better", "best": "Best"}.get(
            tier_key, tier.title()
        )

        # Find available images for this tier
        available: list[tuple[str, str]] = []
        for room_key, room_label in self._CONCEPT_ROOMS:
            img_path = self._CONCEPTS_DIR / f"{room_key}_{tier_key}.jpg"
            if not img_path.exists():
                img_path = self._CONCEPTS_DIR / f"{room_key}_{tier_key}.png"
            if img_path.exists():
                available.append((room_label, str(img_path)))

        if not available:
            return []

        elements = []

        elements.append(
            Paragraph("Concept Visuals", self.styles["heading"])
        )
        elements.append(
            Paragraph(
                f"<b>{tier_label}</b> Package",
                self.styles["body"],
            )
        )
        elements.append(Spacer(1, 4))

        # Gold accent line
        line_data = [[""]]
        line_table = Table(line_data, colWidths=[7 * inch], rowHeights=[2])
        line_table.setStyle(
            TableStyle([("BACKGROUND", (0, 0), (-1, -1), GOLD)])
        )
        elements.append(line_table)
        elements.append(Spacer(1, 8))

        elements.append(
            Paragraph(
                "These renderings illustrate the lighting quality and layering "
                f"typical of the {tier_label} package. Final fixture selection "
                "and placement follows the schedule on subsequent pages.",
                ParagraphStyle(
                    "ConceptIntro",
                    fontName="Helvetica",
                    fontSize=9,
                    textColor=colors.HexColor("#666666"),
                    leading=13,
                ),
            )
        )
        elements.append(Spacer(1, 12))

        # Lay out images in a 2-column grid
        # Each image is ~3.2" wide, ~1.8" tall (16:9 aspect)
        img_w = 3.2 * inch
        img_h = 1.8 * inch
        caption_style = ParagraphStyle(
            "ConceptCaption",
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=CHARCOAL,
            alignment=TA_CENTER,
            spaceBefore=2,
            spaceAfter=8,
        )

        # Build rows of 2 images each
        rows = []
        for i in range(0, len(available), 2):
            row_data = []
            for j in range(2):
                if i + j < len(available):
                    label, path = available[i + j]
                    try:
                        img = Image(path, width=img_w, height=img_h)
                        cell = [img, Paragraph(label, caption_style)]
                    except Exception:
                        cell = [Paragraph(f"[{label}]", caption_style)]
                else:
                    cell = [Paragraph("", caption_style)]
                row_data.append(cell)
            rows.append(row_data)

        if rows:
            # Build a table with 2 columns for the image grid
            for row in rows:
                grid_data = [[]]
                for cell_items in row:
                    # Stack image + caption into a sub-table
                    sub_data = [[item] for item in cell_items]
                    sub_table = Table(sub_data, colWidths=[img_w + 10])
                    sub_table.setStyle(
                        TableStyle(
                            [
                                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("TOPPADDING", (0, 0), (-1, -1), 2),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                            ]
                        )
                    )
                    grid_data[0].append(sub_table)

                row_table = Table(
                    grid_data,
                    colWidths=[3.5 * inch, 3.5 * inch],
                )
                row_table.setStyle(
                    TableStyle(
                        [
                            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ]
                    )
                )
                elements.append(row_table)

        return elements

    def _fixture_schedule(self, rooms_with_fixtures: dict, tier: str) -> list:
        """Build the fixture schedule table — Livewire design system."""
        elements = []

        elements.append(Paragraph("FIXTURE SCHEDULE", self.styles["eyebrow"]))
        elements.append(Spacer(1, 4))
        elements.append(Paragraph("Room-by-Room Detail", self.styles["heading"]))
        elements.append(self._copper_line())
        elements.append(Spacer(1, 12))

        # Build table data
        hdr_style = ParagraphStyle(
            "FSHdr", fontName="Helvetica-Bold", fontSize=7,
            textColor=COPPER_700,
        )
        header = [
            Paragraph("ROOM", hdr_style),
            Paragraph("FIXTURE TYPE", hdr_style),
            Paragraph("QTY", ParagraphStyle("FSHdrC", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700, alignment=TA_CENTER)),
            Paragraph("PRODUCT", hdr_style),
            Paragraph("BUDGET", ParagraphStyle("FSHdrR", fontName="Helvetica-Bold", fontSize=7, textColor=COPPER_700, alignment=TA_RIGHT)),
        ]
        table_data = [header]

        for room_name, fixtures in rooms_with_fixtures.items():
            fixture_groups: dict[str, dict] = {}
            for f in fixtures:
                key = f.fixture_type
                if key not in fixture_groups:
                    fixture_groups[key] = {
                        "qty": 0,
                        "product": f.product_desc or f.product_sku or "",
                        "msrp": f.msrp_range or "",
                    }
                fixture_groups[key]["qty"] += 1

            first_in_room = True
            for ftype, info in fixture_groups.items():
                room_cell = (
                    Paragraph(room_name, self.styles["room_label"])
                    if first_in_room
                    else Paragraph("", self.styles["table_cell"])
                )
                first_in_room = False

                type_label = ftype.replace("_", " ").title()
                row = [
                    room_cell,
                    Paragraph(type_label, self.styles["table_cell"]),
                    Paragraph(str(info["qty"]), ParagraphStyle("QtyCell", fontName="Helvetica", fontSize=10, textColor=INK_800, alignment=TA_CENTER)),
                    Paragraph(info["product"], ParagraphStyle("ProdCell", fontName="Helvetica", fontSize=8, textColor=INK_400)),
                    Paragraph(info["msrp"], ParagraphStyle("MsrpCell", fontName="Helvetica", fontSize=9, textColor=INK_500, alignment=TA_RIGHT)),
                ]
                table_data.append(row)

        col_widths = [1.4 * inch, 1.2 * inch, 0.5 * inch, 2.2 * inch, 1.7 * inch]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)

        style_commands = [
            ("BACKGROUND", (0, 0), (-1, 0), BONE_100),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, BONE_300),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]

        # Subtle alternating rows
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                style_commands.append(("BACKGROUND", (0, i), (-1, i), BONE))

        table.setStyle(TableStyle(style_commands))
        elements.append(table)

        elements.append(Spacer(1, 16))
        elements.append(self._copper_line())
        elements.append(Spacer(1, 8))

        elements.append(Paragraph(
            "This layout is dimming-ready. All pre-wire locations are prepared for future fixture installation. "
            "Contact your Livewire representative about Lutron integration options.",
            ParagraphStyle("Footnote", fontName="Helvetica-Oblique", fontSize=8, textColor=INK_400),
        ))

        return elements

    def _schematic_page(self, schematic_layout: dict) -> list:
        """Render the schematic layout as vector graphics on a PDF page."""
        elements = []

        elements.append(Paragraph("Lighting Layout", self.styles["heading"]))
        elements.append(Spacer(1, 4))

        # Gold accent line
        line_data = [[""]]
        line_table = Table(line_data, colWidths=[7 * inch], rowHeights=[2])
        line_table.setStyle(
            TableStyle([("BACKGROUND", (0, 0), (-1, -1), GOLD)])
        )
        elements.append(line_table)
        elements.append(Spacer(1, 10))

        canvas_info = schematic_layout.get("canvas", {})
        src_w = canvas_info.get("width", 1000)
        src_h = canvas_info.get("height", 750)

        # Target drawing area: 7" wide x 5.25" tall
        draw_w = 504  # 7 * 72
        draw_h = 378  # 5.25 * 72

        scale_x = draw_w / src_w
        scale_y = draw_h / src_h
        scale = min(scale_x, scale_y)

        actual_w = src_w * scale
        actual_h = src_h * scale

        drawing = Drawing(actual_w, actual_h)

        rooms = schematic_layout.get("rooms", [])

        room_stroke = colors.HexColor("#d1d5db")
        room_fill = colors.HexColor("#fafafa")

        for room in rooms:
            rect = room.get("rect", {})
            rx = rect.get("x", 0) * scale
            # Flip y: reportlab Drawing has y=0 at bottom
            ry = actual_h - (rect.get("y", 0) + rect.get("h", 0)) * scale
            rw = rect.get("w", 0) * scale
            rh = rect.get("h", 0) * scale

            room_rect = Rect(
                rx, ry, rw, rh,
                rx=3, ry=3,
                fillColor=room_fill,
                strokeColor=room_stroke,
                strokeWidth=0.75,
            )
            drawing.add(room_rect)

            # Room label at top-left of rect
            label = room.get("label", room.get("name", ""))
            label_x = rx + 4
            label_y = ry + rh - 10  # near the top in flipped coords
            label_str = String(
                label_x, label_y, label,
                fontName="Helvetica-Bold",
                fontSize=6,
                fillColor=CHARCOAL,
            )
            drawing.add(label_str)

            # Fixture count at top-right
            count = room.get("fixture_count", 0)
            count_text = f"{count} fixtures"
            count_x = rx + rw - 4
            count_y = ry + rh - 10
            count_str = String(
                count_x, count_y, count_text,
                fontName="Helvetica",
                fontSize=5,
                fillColor=colors.HexColor("#666666"),
                textAnchor="end",
            )
            drawing.add(count_str)

            # Draw fixture icons
            for fixture in room.get("fixtures", []):
                fx = fixture.get("x", 0) * scale
                fy = actual_h - fixture.get("y", 0) * scale
                ftype = fixture.get("type", "recessed")
                fcolor = colors.HexColor(fixture.get("color", "#444444"))

                radius = 3 if ftype in ("ceiling_fan", "pendant") else 2.5
                circle = Circle(
                    fx, fy, radius,
                    fillColor=fcolor,
                    strokeColor=None,
                    strokeWidth=0,
                )
                drawing.add(circle)

        elements.append(drawing)
        elements.append(Spacer(1, 14))

        # Legend
        legend_types = {
            "recessed": ("#444444", "Recessed"),
            "pendant": ("#d97706", "Pendant"),
            "sconce": ("#7c3aed", "Sconce"),
            "ceiling_fan": ("#16a34a", "Ceiling Fan"),
            "coach_light": ("#ca8a04", "Coach Light"),
            "exhaust_fan": ("#64748b", "Exhaust Fan"),
        }

        # Determine which fixture types appear in this layout
        types_present = set()
        for room in rooms:
            for fixture in room.get("fixtures", []):
                types_present.add(fixture.get("type", ""))

        legend_items = [
            (color, label)
            for key, (color, label) in legend_types.items()
            if key in types_present
        ]

        if legend_items:
            legend_w = actual_w
            legend_h = 16
            legend_drawing = Drawing(legend_w, legend_h)

            x_offset = 0
            spacing = legend_w / max(len(legend_items), 1)

            for i, (hex_color, label) in enumerate(legend_items):
                cx = x_offset + i * spacing + 6
                cy = legend_h / 2

                dot = Circle(
                    cx, cy, 3,
                    fillColor=colors.HexColor(hex_color),
                    strokeColor=None,
                    strokeWidth=0,
                )
                legend_drawing.add(dot)

                txt = String(
                    cx + 6, cy - 3, label,
                    fontName="Helvetica",
                    fontSize=7,
                    fillColor=CHARCOAL,
                )
                legend_drawing.add(txt)

            elements.append(legend_drawing)

        return elements

    def _reference_plan_page(self, image_path: str) -> list:
        """Show the original uploaded floor plan image."""
        elements = []

        elements.append(Paragraph("Reference Floor Plan", self.styles["heading"]))
        elements.append(Spacer(1, 4))

        # Gold accent line
        line_data = [[""]]
        line_table = Table(line_data, colWidths=[7 * inch], rowHeights=[2])
        line_table.setStyle(
            TableStyle([("BACKGROUND", (0, 0), (-1, -1), GOLD)])
        )
        elements.append(line_table)
        elements.append(Spacer(1, 10))

        try:
            img_reader = ImageReader(image_path)
            img_w, img_h = img_reader.getSize()

            # Max display area: 6.5" x 8" (468 x 576 points)
            max_w = 6.5 * inch
            max_h = 8 * inch

            ratio = min(max_w / img_w, max_h / img_h)
            display_w = img_w * ratio
            display_h = img_h * ratio

            img = Image(image_path, width=display_w, height=display_h)
            img.hAlign = "CENTER"
            elements.append(img)
        except Exception:
            elements.append(
                Paragraph(
                    "Floor plan image could not be loaded.",
                    self.styles["body"],
                )
            )

        return elements

    @staticmethod
    def _page_footer(canvas, doc):
        """Draw page footer — Livewire design system."""
        canvas.saveState()
        # Copper line
        canvas.setStrokeColor(COPPER)
        canvas.setLineWidth(0.5)
        canvas.line(0.75 * inch, 0.62 * inch, letter[0] - 0.75 * inch, 0.62 * inch)
        # Footer text
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(INK_400)
        canvas.drawString(0.75 * inch, 0.45 * inch, "LightPlan by Livewire")
        canvas.drawRightString(
            letter[0] - 0.75 * inch, 0.45 * inch,
            f"Page {canvas.getPageNumber()}",
        )
        canvas.restoreState()
