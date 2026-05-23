"""Branded PDF generation for LightPlan deliverables.

Generates a professional fixture schedule PDF with Livewire branding
using a dark charcoal and gold color scheme.
"""

import io
import os
from collections import defaultdict
from datetime import datetime, timezone

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

CHARCOAL = colors.HexColor("#2D2D2D")
CHARCOAL_LIGHT = colors.HexColor("#3D3D3D")
GOLD = colors.HexColor("#C9A84C")
GOLD_LIGHT = colors.HexColor("#D4BA6A")
WHITE = colors.white
LIGHT_GRAY = colors.HexColor("#F5F5F5")
MID_GRAY = colors.HexColor("#E0E0E0")


def _styles():
    """Build custom paragraph styles for the branded PDF."""
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "LPTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=28,
            textColor=WHITE,
            alignment=TA_CENTER,
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "LPSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=14,
            textColor=GOLD,
            alignment=TA_CENTER,
            spaceAfter=20,
        ),
        "heading": ParagraphStyle(
            "LPHeading",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            textColor=CHARCOAL,
            spaceBefore=16,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "LPBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10,
            textColor=CHARCOAL,
            leading=14,
        ),
        "body_white": ParagraphStyle(
            "LPBodyWhite",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            textColor=WHITE,
            leading=16,
        ),
        "footer": ParagraphStyle(
            "LPFooter",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=colors.HexColor("#999999"),
            alignment=TA_CENTER,
        ),
        "table_header": ParagraphStyle(
            "LPTableHeader",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=9,
            textColor=WHITE,
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
            story.extend(self._why_smart_lighting_page())
            story.append(PageBreak())

        # Schematic layout page (if data provided)
        if schematic_layout and schematic_layout.get("rooms"):
            story.extend(self._schematic_page(schematic_layout))
            story.append(PageBreak())

        story.extend(self._fixture_schedule(rooms_with_fixtures, tier))

        # Reference floor plan page (if image exists on disk)
        if floor_plan_image_path and os.path.isfile(floor_plan_image_path):
            story.append(PageBreak())
            story.extend(self._reference_plan_page(floor_plan_image_path))

        doc.build(story, onFirstPage=self._page_footer, onLaterPages=self._page_footer)
        return buffer.getvalue()

    def _cover_page(
        self,
        project_name: str,
        project_address: str,
        tier: str,
        builder_name: str,
    ) -> list:
        """Build the branded cover page elements."""
        elements = []

        # Dark background header block
        tier_label = {"good": "Good", "better": "Better", "best": "Best"}.get(tier, tier.title())
        date_str = datetime.now(timezone.utc).strftime("%B %d, %Y")

        # Title block using a dark table as background
        header_data = [
            [Paragraph("LIGHTPLAN", self.styles["title"])],
            [Paragraph("by Livewire", self.styles["subtitle"])],
        ]
        header_table = Table(header_data, colWidths=[7 * inch])
        header_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), CHARCOAL),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("TOPPADDING", (0, 0), (-1, 0), 60),
                    ("BOTTOMPADDING", (0, -1), (-1, -1), 40),
                ]
            )
        )
        elements.append(header_table)

        elements.append(Spacer(1, 40))

        # Gold accent line
        line_data = [[""] ]
        line_table = Table(line_data, colWidths=[7 * inch], rowHeights=[3])
        line_table.setStyle(
            TableStyle([("BACKGROUND", (0, 0), (-1, -1), GOLD)])
        )
        elements.append(line_table)

        elements.append(Spacer(1, 40))

        # Project details
        details = [
            ("Project", project_name),
            ("Address", project_address or ""),
            ("Builder", builder_name or ""),
            ("Package Tier", tier_label),
            ("Date", date_str),
        ]
        for label, value in details:
            if value:
                elements.append(
                    Paragraph(
                        f"<b>{label}:</b>  {value}",
                        self.styles["body"],
                    )
                )
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

    def _fixture_schedule(self, rooms_with_fixtures: dict, tier: str) -> list:
        """Build the fixture schedule table grouped by room."""
        elements = []

        elements.append(Paragraph("Fixture Schedule", self.styles["heading"]))

        tier_label = {"good": "Good", "better": "Better", "best": "Best"}.get(tier, tier.title())
        elements.append(
            Paragraph(
                f"Package: <b>{tier_label}</b>",
                self.styles["body"],
            )
        )
        elements.append(Spacer(1, 8))

        # Gold accent line
        line_data = [[""]]
        line_table = Table(line_data, colWidths=[7 * inch], rowHeights=[2])
        line_table.setStyle(
            TableStyle([("BACKGROUND", (0, 0), (-1, -1), GOLD)])
        )
        elements.append(line_table)
        elements.append(Spacer(1, 12))

        # Build table data
        header = [
            Paragraph("Room", self.styles["table_header"]),
            Paragraph("Fixture Type", self.styles["table_header"]),
            Paragraph("Qty", self.styles["table_header"]),
            Paragraph("Product", self.styles["table_header"]),
            Paragraph("Budget Range", self.styles["table_header"]),
            Paragraph("Notes", self.styles["table_header"]),
        ]
        table_data = [header]

        for room_name, fixtures in rooms_with_fixtures.items():
            # Aggregate fixtures by type within the room
            fixture_groups: dict[str, dict] = {}
            for f in fixtures:
                key = f.fixture_type
                if key not in fixture_groups:
                    fixture_groups[key] = {
                        "qty": 0,
                        "product": f.product_desc or f.product_sku or "",
                        "msrp": f.msrp_range or "",
                        "notes": [],
                    }
                fixture_groups[key]["qty"] += 1
                if f.notes and f.notes not in fixture_groups[key]["notes"]:
                    fixture_groups[key]["notes"].append(f.notes)

            first_in_room = True
            for ftype, info in fixture_groups.items():
                room_cell = (
                    Paragraph(room_name, self.styles["room_label"])
                    if first_in_room
                    else Paragraph("", self.styles["table_cell"])
                )
                first_in_room = False

                type_label = ftype.replace("_", " ").title()
                notes_str = "; ".join(info["notes"]) if info["notes"] else ""

                row = [
                    room_cell,
                    Paragraph(type_label, self.styles["table_cell"]),
                    Paragraph(str(info["qty"]), self.styles["table_cell"]),
                    Paragraph(info["product"], self.styles["table_cell"]),
                    Paragraph(info["msrp"], self.styles["table_cell"]),
                    Paragraph(notes_str, self.styles["table_cell"]),
                ]
                table_data.append(row)

        col_widths = [1.2 * inch, 1.1 * inch, 0.4 * inch, 1.6 * inch, 0.9 * inch, 1.8 * inch]
        table = Table(table_data, colWidths=col_widths, repeatRows=1)

        # Style the table
        style_commands = [
            # Header row
            ("BACKGROUND", (0, 0), (-1, 0), CHARCOAL),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.5, MID_GRAY),
            ("LINEBELOW", (0, 0), (-1, 0), 1.5, GOLD),
            # Padding
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            # Alignment
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]

        # Alternating row shading (skip header)
        for i in range(1, len(table_data)):
            if i % 2 == 0:
                style_commands.append(("BACKGROUND", (0, i), (-1, i), LIGHT_GRAY))

        table.setStyle(TableStyle(style_commands))
        elements.append(table)

        # Footnote
        elements.append(Spacer(1, 20))

        # Gold line before footnote
        elements.append(line_table)
        elements.append(Spacer(1, 8))

        elements.append(
            Paragraph(
                "This layout is dimming-ready. Ask your Livewire rep about Lutron integration options.",
                ParagraphStyle(
                    "Footnote",
                    fontName="Helvetica-Oblique",
                    fontSize=8,
                    textColor=colors.HexColor("#666666"),
                ),
            )
        )

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
        """Draw page footer with page number and branding."""
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#999999"))
        canvas.drawCentredString(
            letter[0] / 2,
            0.5 * inch,
            f"LightPlan by Livewire  |  Page {canvas.getPageNumber()}",
        )
        # Gold line above footer
        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(0.5)
        canvas.line(
            0.75 * inch,
            0.65 * inch,
            letter[0] - 0.75 * inch,
            0.65 * inch,
        )
        canvas.restoreState()
