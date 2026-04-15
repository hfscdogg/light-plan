import base64
import io
import json
import logging
import re

import anthropic
from PIL import Image

from app.config import settings
from app.models.schemas import RoomData

logger = logging.getLogger(__name__)

# Canonical room types the rules engine understands
KNOWN_ROOM_TYPES = {
    "kitchen",
    "dining",
    "living",
    "family",
    "great_room",
    "master_bedroom",
    "bedroom",
    "master_bathroom",
    "bathroom",
    "half_bath",
    "powder_room",
    "hallway",
    "entry",
    "foyer",
    "laundry",
    "mudroom",
    "pantry",
    "closet",
    "walk_in_closet",
    "garage",
    "porch",
    "patio",
    "office",
    "den",
    "bonus_room",
    "exterior",
}

# Synonyms for normalizing Claude's free-text room type labels
ROOM_TYPE_SYNONYMS = {
    "kit": "kitchen",
    "kitch": "kitchen",
    "din": "dining",
    "dining room": "dining",
    "living room": "living",
    "liv": "living",
    "family room": "family",
    "fam": "family",
    "great room": "great_room",
    "greatroom": "great_room",
    "master bedroom": "master_bedroom",
    "master bed": "master_bedroom",
    "master": "master_bedroom",
    "primary bedroom": "master_bedroom",
    "primary bed": "master_bedroom",
    "primary suite": "master_bedroom",
    "owners suite": "master_bedroom",
    "owner's suite": "master_bedroom",
    "bed": "bedroom",
    "bedroom 2": "bedroom",
    "bedroom 3": "bedroom",
    "bedroom 4": "bedroom",
    "bed 2": "bedroom",
    "bed 3": "bedroom",
    "bed 4": "bedroom",
    "guest bedroom": "bedroom",
    "guest bed": "bedroom",
    "guest room": "bedroom",
    "master bathroom": "master_bathroom",
    "master bath": "master_bathroom",
    "primary bathroom": "master_bathroom",
    "primary bath": "master_bathroom",
    "owners bath": "master_bathroom",
    "owner's bath": "master_bathroom",
    "bath": "bathroom",
    "bathroom 2": "bathroom",
    "bath 2": "bathroom",
    "full bath": "bathroom",
    "hall bath": "bathroom",
    "half bath": "half_bath",
    "half": "half_bath",
    "powder": "powder_room",
    "powder room": "powder_room",
    "hall": "hallway",
    "corridor": "hallway",
    "entry": "entry",
    "entryway": "entry",
    "entrance": "entry",
    "front entry": "entry",
    "foyer": "foyer",
    "laundry": "laundry",
    "laundry room": "laundry",
    "utility": "laundry",
    "utility room": "laundry",
    "mud room": "mudroom",
    "mud": "mudroom",
    "pantry": "pantry",
    "walk-in pantry": "pantry",
    "closet": "closet",
    "walk-in closet": "walk_in_closet",
    "walk in closet": "walk_in_closet",
    "wic": "walk_in_closet",
    "garage": "garage",
    "2 car garage": "garage",
    "3 car garage": "garage",
    "two car garage": "garage",
    "three car garage": "garage",
    "porch": "porch",
    "front porch": "porch",
    "covered porch": "porch",
    "back porch": "porch",
    "rear porch": "porch",
    "patio": "patio",
    "covered patio": "patio",
    "office": "office",
    "home office": "office",
    "study": "office",
    "den": "den",
    "bonus": "bonus_room",
    "bonus room": "bonus_room",
    "media room": "bonus_room",
    "game room": "bonus_room",
    "loft": "bonus_room",
    "exterior": "exterior",
    "outside": "exterior",
}

# ---------------------------------------------------------------------------
# Pass 1 — Identify the drawing's tight bounds within the full sheet
# ---------------------------------------------------------------------------

BOUNDS_SYSTEM_PROMPT = """You are analyzing a residential architectural floor plan sheet. Your ONLY job on this pass is to return the tight rectangular bounds of the actual floor plan DRAWING within the full image, ignoring everything else on the sheet.

EXCLUDE from the bounds:
- Sheet title / plan name at the top (e.g. "Dover V", "First Floor Plan")
- Title block, logos, legends, scale bars, square-footage callouts, CRAFTED FOR LIFE / brand artwork at the bottom or side
- Sheet borders and white margins
- Notes and disclaimers

INCLUDE in the bounds:
- The outermost building wall lines
- Any attached garages, covered porches, decks, and patios that are drawn as part of the floor plan

Coordinates are fractions of the full image (0 = left/top, 1 = right/bottom, x grows right, y grows down).

OUTPUT — return ONLY a single JSON object with exactly these four keys:
{"x1": <float>, "y1": <float>, "x2": <float>, "y2": <float>}

No prose, no explanation, no markdown fences."""

BOUNDS_USER_PROMPT = (
    "Return ONLY the JSON object giving the tight bounds of the floor plan "
    "drawing within this image. No other text."
)


# ---------------------------------------------------------------------------
# Pass 2 — Identify rooms within the (cropped) drawing
# ---------------------------------------------------------------------------

ROOMS_SYSTEM_PROMPT = """You are a precise computer-vision assistant analyzing a residential architectural floor plan. The image you are looking at has been pre-cropped to the floor plan drawing itself — there is no title block, no sheet border, no whitespace margin to worry about. Treat the image you see as the full drawing.

For every distinct room or space visible, return a tight bounding box as fractions of THIS image's dimensions (0 = top-left, 1 = bottom-right).

Walk through the plan room by room starting from the top-left. For each room:
- Trace the interior wall lines — the bbox should hug the walls, not the text label.
- Do not let a room's bbox overlap another room's (hallways may touch neighbors edge-on).
- The bbox center (cx, cy) must match where the room is drawn. A room in the lower-center of the plan must have cy > 0.5, not < 0.4.
- Box width/height should be proportional to the room's drawn size relative to its neighbors.

For each room, return a JSON object with:
- name: the label printed on the plan exactly (e.g. "Master Bedroom", "Bedroom 2", "Master Bath")
- room_type: one of [kitchen, dining, living, family, great_room, master_bedroom, bedroom, master_bathroom, bathroom, half_bath, powder_room, hallway, entry, foyer, laundry, mudroom, pantry, closet, walk_in_closet, garage, porch, patio, office, den, bonus_room, exterior]
- sqft: from printed dimensions if shown, else estimated from proportions
- width_ft, length_ft: in feet
- ceiling_height_ft: use the plan value if stated, else null
- bbox_x1, bbox_y1, bbox_x2, bbox_y2: tight rectangle around the room's interior walls, as fractions of this image

Include every distinct space: bedrooms, bathrooms, kitchen, living, dining, closets, hallways, laundry, pantry, garage, porches, patios, exterior.

OUTPUT FORMAT — CRITICAL:
Your entire response must be a single JSON array and nothing else.
- Start with `[` and end with `]`.
- No prose, no reasoning, no markdown fences."""

ROOMS_USER_PROMPT = (
    "Identify every room in this floor plan and output a JSON array with a "
    "tight bbox for each room. Respond with the JSON array only — no prose, "
    "no markdown."
)

# Back-compat aliases so any external imports keep working
SYSTEM_PROMPT = ROOMS_SYSTEM_PROMPT
USER_PROMPT = ROOMS_USER_PROMPT


class PlanParser:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model

    def parse_plan(self, file_path: str, file_type: str) -> list[RoomData]:
        """Parse a floor plan image and return structured room data.

        Two-pass Vision flow:
          1. Ask Claude for the tight bounds of the actual floor plan drawing
             within the full image (excluding title, title block, margins).
          2. Crop the image to those bounds with Pillow so the drawing fills
             the frame, then ask Claude for per-room bounding boxes.
          3. Scale the returned room bboxes from crop-relative coordinates
             back into full-image coordinates before returning, so downstream
             placement and overlay code keeps working in the original image
             coordinate system.

        If either Vision call or the crop step fails, the flow degrades to
        single-pass parsing of the full original image.
        """
        images = self._load_images(file_path, file_type)

        bounds = self._identify_drawing_bounds(images)
        cropped_images = self._crop_images(images, bounds)

        raw_response = self._call_claude(cropped_images)
        rooms = self._parse_response(raw_response)

        logger.info(
            "Pass 2 returned %d rooms (bounds=%s, no_crop=%s)",
            len(rooms),
            tuple(round(v, 3) for v in bounds),
            bounds == self._NO_CROP,
        )

        rooms = self._scale_rooms_to_full_image(rooms, bounds)

        return rooms, raw_response

    def _load_images(self, file_path: str, file_type: str) -> list[tuple[str, str]]:
        """Load floor plan as base64-encoded images.

        Returns a list of (base64_data, media_type) tuples.
        For PDFs, each page becomes a separate image.
        """
        if file_type == "pdf":
            return self._pdf_to_images(file_path)
        else:
            media_type = "image/png" if file_type == "png" else "image/jpeg"
            with open(file_path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode("utf-8")
            return [(data, media_type)]

    def _pdf_to_images(self, file_path: str) -> list[tuple[str, str]]:
        """Convert PDF pages to PNG images using pdf2image."""
        try:
            from pdf2image import convert_from_path

            pages = convert_from_path(file_path, dpi=200)
            images = []
            for page in pages:
                import io

                buffer = io.BytesIO()
                page.save(buffer, format="PNG")
                data = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")
                images.append((data, "image/png"))
            return images
        except ImportError:
            logger.error("pdf2image not installed. Install with: pip install pdf2image")
            raise
        except Exception as e:
            logger.error(f"Failed to convert PDF to images: {e}")
            raise

    def _call_claude(self, images: list[tuple[str, str]]) -> str:
        """Send floor plan images to Claude Vision and get room analysis.

        Uses an assistant prefill of "[" to force the response to start as a
        JSON array. The prefill character is prepended back onto the returned
        text before parsing, since prefill tokens are not part of the model's
        output.
        """
        content = []

        for b64_data, media_type in images:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64_data,
                    },
                }
            )

        content.append({"type": "text", "text": ROOMS_USER_PROMPT})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=ROOMS_SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": content},
                {"role": "assistant", "content": "["},
            ],
        )

        # Prepend the prefill so the parser sees the full JSON array.
        return "[" + response.content[0].text

    # ------------------------------------------------------------------
    # Two-pass helpers
    # ------------------------------------------------------------------

    # Any crop that doesn't span at least this fraction of the image in
    # both dimensions is treated as nonsense and ignored. The drawing
    # always dominates the sheet on real floor plans, so a detection
    # smaller than this is almost certainly Claude hugging one room or
    # misreading the bounds.
    _MIN_BOUNDS_SPAN = 0.55

    # Safety pad added around detected bounds before cropping (in image
    # fractions on each side). Claude Vision tends to hug the drawing a
    # touch too tight; the pad prevents accidentally clipping an edge
    # room. Clamped to [0, 1] after the pad is applied.
    _BOUNDS_PAD = 0.03

    _NO_CROP: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)

    def _identify_drawing_bounds(
        self, images: list[tuple[str, str]]
    ) -> tuple[float, float, float, float]:
        """Pass 1: ask Claude for the tight bounds of the drawing within the image.

        Returns ``(x1, y1, x2, y2)`` as fractions of the full image. Falls
        back to ``(0.0, 0.0, 1.0, 1.0)`` (no crop) if the call fails or
        returns invalid / implausibly small bounds.
        """
        try:
            content: list[dict] = []
            for b64_data, media_type in images:
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                    }
                )
            content.append({"type": "text", "text": BOUNDS_USER_PROMPT})

            response = self.client.messages.create(
                model=self.model,
                max_tokens=256,
                system=BOUNDS_SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": content},
                    {"role": "assistant", "content": "{"},
                ],
            )

            raw = "{" + response.content[0].text
            cleaned = raw.strip()
            cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
            cleaned = re.sub(r"\n?```\s*$", "", cleaned)
            cleaned = cleaned.strip()

            if cleaned and cleaned[0] != "{":
                start = cleaned.find("{")
                end = cleaned.rfind("}")
                if start != -1 and end > start:
                    cleaned = cleaned[start : end + 1]

            data = json.loads(cleaned)
            x1 = float(data["x1"])
            y1 = float(data["y1"])
            x2 = float(data["x2"])
            y2 = float(data["y2"])
        except Exception as e:  # noqa: BLE001 — best-effort fallback
            logger.warning("Drawing-bounds detection failed: %s", e)
            return self._NO_CROP

        # Clamp to [0, 1]
        x1 = max(0.0, min(1.0, x1))
        y1 = max(0.0, min(1.0, y1))
        x2 = max(0.0, min(1.0, x2))
        y2 = max(0.0, min(1.0, y2))

        if x1 >= x2 or y1 >= y2:
            logger.warning("Drawing bounds inverted: %s", (x1, y1, x2, y2))
            return self._NO_CROP

        if (x2 - x1) < self._MIN_BOUNDS_SPAN or (y2 - y1) < self._MIN_BOUNDS_SPAN:
            logger.warning(
                "Drawing bounds implausibly small (span < %.2f): %s — falling back to full image",
                self._MIN_BOUNDS_SPAN,
                (x1, y1, x2, y2),
            )
            return self._NO_CROP

        # Pad outward so we don't accidentally clip an edge room, then clamp.
        padded = (
            max(0.0, x1 - self._BOUNDS_PAD),
            max(0.0, y1 - self._BOUNDS_PAD),
            min(1.0, x2 + self._BOUNDS_PAD),
            min(1.0, y2 + self._BOUNDS_PAD),
        )
        logger.info(
            "Pass 1 bounds raw=%s padded=%s",
            (round(x1, 3), round(y1, 3), round(x2, 3), round(y2, 3)),
            tuple(round(v, 3) for v in padded),
        )
        return padded

    def _crop_images(
        self,
        images: list[tuple[str, str]],
        bounds: tuple[float, float, float, float],
    ) -> list[tuple[str, str]]:
        """Crop each image to ``bounds`` using Pillow.

        Returns a list of new ``(base64, media_type)`` tuples. When bounds
        indicate a no-op crop, the original list is returned unchanged. On
        a per-image failure, that image is returned uncropped.
        """
        if bounds == self._NO_CROP:
            return images

        x1, y1, x2, y2 = bounds
        cropped: list[tuple[str, str]] = []

        for b64_data, media_type in images:
            try:
                raw = base64.standard_b64decode(b64_data)
                with Image.open(io.BytesIO(raw)) as img:
                    img.load()
                    w, h = img.size
                    box = (
                        int(round(x1 * w)),
                        int(round(y1 * h)),
                        int(round(x2 * w)),
                        int(round(y2 * h)),
                    )
                    crop = img.crop(box)
                    if crop.mode not in ("RGB", "RGBA"):
                        crop = crop.convert("RGB")
                    buffer = io.BytesIO()
                    crop.save(buffer, format="PNG")
                    new_b64 = base64.standard_b64encode(buffer.getvalue()).decode("utf-8")
                    cropped.append((new_b64, "image/png"))
            except Exception as e:  # noqa: BLE001
                logger.warning("Failed to crop image, passing through uncropped: %s", e)
                cropped.append((b64_data, media_type))

        return cropped

    def _scale_rooms_to_full_image(
        self,
        rooms: list[RoomData],
        bounds: tuple[float, float, float, float],
    ) -> list[RoomData]:
        """Map room bbox / position coords from crop-relative to full image.

        With a no-op crop this is a pass-through. Otherwise each coordinate
        ``c`` in ``[0, 1]`` of the crop is mapped to ``bounds_min + c * span``
        in the full image.
        """
        if bounds == self._NO_CROP:
            return rooms

        x1, y1, x2, y2 = bounds
        dx = x2 - x1
        dy = y2 - y1

        def sx(v: float | None) -> float | None:
            return None if v is None else x1 + v * dx

        def sy(v: float | None) -> float | None:
            return None if v is None else y1 + v * dy

        scaled: list[RoomData] = []
        for r in rooms:
            scaled.append(
                RoomData(
                    name=r.name,
                    room_type=r.room_type,
                    sqft=r.sqft,
                    width_ft=r.width_ft,
                    length_ft=r.length_ft,
                    ceiling_height_ft=r.ceiling_height_ft,
                    position_x=sx(r.position_x),
                    position_y=sy(r.position_y),
                    bbox_x1=sx(r.bbox_x1),
                    bbox_y1=sy(r.bbox_y1),
                    bbox_x2=sx(r.bbox_x2),
                    bbox_y2=sy(r.bbox_y2),
                )
            )
        return scaled

    def _parse_response(self, raw: str) -> list[RoomData]:
        """Parse Claude's response into structured RoomData objects.

        Tolerant to the model wrapping the JSON in markdown fences or in a
        short reasoning preamble: if the cleaned text doesn't start with a
        JSON opener, we slice from the first ``[`` (or ``{``) to the matching
        last closer before parsing.
        """
        # Strip markdown code fences if present
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        cleaned = cleaned.strip()

        # Preamble tolerance: if we don't start on a JSON opener, slice to the
        # outermost array/object so `json.loads` has a chance.
        if cleaned and cleaned[0] not in "[{":
            arr_start = cleaned.find("[")
            arr_end = cleaned.rfind("]")
            if arr_start != -1 and arr_end > arr_start:
                cleaned = cleaned[arr_start : arr_end + 1]
            else:
                obj_start = cleaned.find("{")
                obj_end = cleaned.rfind("}")
                if obj_start != -1 and obj_end > obj_start:
                    cleaned = cleaned[obj_start : obj_end + 1]

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse Claude response as JSON: %s (raw length=%d)",
                e,
                len(raw),
            )
            logger.error("Raw response preview: %s", raw[:800])
            raise ValueError(f"Claude returned invalid JSON: {e}")

        if not isinstance(data, list):
            if isinstance(data, dict) and "rooms" in data:
                data = data["rooms"]
            else:
                raise ValueError("Expected a JSON array of rooms")

        rooms = []
        for item in data:
            room_type = self._normalize_room_type(
                item.get("room_type", ""),
                item.get("name", ""),
            )

            # Extract bounding box
            bbox_x1 = item.get("bbox_x1")
            bbox_y1 = item.get("bbox_y1")
            bbox_x2 = item.get("bbox_x2")
            bbox_y2 = item.get("bbox_y2")

            # Compute center from bbox if available, fall back to position fields
            if bbox_x1 is not None and bbox_x2 is not None:
                pos_x = (bbox_x1 + bbox_x2) / 2
            else:
                pos_x = item.get("position_x")

            if bbox_y1 is not None and bbox_y2 is not None:
                pos_y = (bbox_y1 + bbox_y2) / 2
            else:
                pos_y = item.get("position_y")

            rooms.append(
                RoomData(
                    name=item.get("name", "Unknown Room"),
                    room_type=room_type,
                    sqft=item.get("sqft"),
                    width_ft=item.get("width_ft"),
                    length_ft=item.get("length_ft"),
                    ceiling_height_ft=item.get("ceiling_height_ft"),
                    position_x=pos_x,
                    position_y=pos_y,
                    bbox_x1=bbox_x1,
                    bbox_y1=bbox_y1,
                    bbox_x2=bbox_x2,
                    bbox_y2=bbox_y2,
                )
            )

        return rooms

    def _normalize_room_type(self, raw_type: str, room_name: str) -> str:
        """Normalize a room type string to a canonical value."""
        # Try the raw type first
        normalized = raw_type.lower().strip().replace("-", "_").replace(" ", "_")
        if normalized in KNOWN_ROOM_TYPES:
            return normalized

        # Try synonym lookup on the raw type
        lower_raw = raw_type.lower().strip()
        if lower_raw in ROOM_TYPE_SYNONYMS:
            return ROOM_TYPE_SYNONYMS[lower_raw]

        # Try synonym lookup on the room name
        lower_name = room_name.lower().strip()
        if lower_name in ROOM_TYPE_SYNONYMS:
            return ROOM_TYPE_SYNONYMS[lower_name]

        # Try partial matching on the room name
        for synonym, canonical in ROOM_TYPE_SYNONYMS.items():
            if synonym in lower_name:
                return canonical

        # Try partial matching on the raw type
        for synonym, canonical in ROOM_TYPE_SYNONYMS.items():
            if synonym in lower_raw:
                return canonical

        logger.warning(f"Could not normalize room type '{raw_type}' (name: '{room_name}'), defaulting to 'other'")
        return "other"

    # ------------------------------------------------------------------
    # Pass 2: Fixture placement (constrained by room bounding boxes)
    # ------------------------------------------------------------------

    # Only place major fixture types on the overlay for a cleaner visual
    OVERLAY_FIXTURE_TYPES = {
        "recessed", "pendant", "sconce", "ceiling_fan",
        "coach_light", "exhaust_fan",
    }

    PLACEMENT_SYSTEM_PROMPT = """You are a professional residential lighting designer placing fixtures on a floor plan.

You will receive:
1. A floor plan image
2. A list of rooms with their bounding boxes on the image, and the fixtures to place in each room

Each room includes a bounding box: (x1, y1) is the top-left corner and (x2, y2) is the bottom-right corner, as fractions of the image dimensions (0 to 1).

CRITICAL CONSTRAINT: Every fixture MUST be placed INSIDE its room's bounding box. A fixture's plan_x must be between the room's x1 and x2, and plan_y must be between y1 and y2. Do NOT place any fixture outside its room's bounding box.

Place fixtures like a professional lighting designer:
- Recessed cans: symmetrical grid pattern within the room. Keep them evenly spaced and at least 15-20% of the room width inset from walls. Arrange in clean rows and columns.
- Sconces: on the vanity/mirror wall of bathrooms, positioned where the mirror flanks would be
- Pendant pre-wires: centered over the kitchen island area or dining table
- Ceiling fan pre-wires: at the geometric center of the room
- Exhaust fans: centered in the bathroom, offset from the main ceiling area
- Coach lights: on the exterior wall next to entry doors or garage door openings

For each fixture, return:
- room_name: exactly matching the room name provided
- fixture_type: exactly matching the type provided
- plan_x: x position on the plan image (0 to 1), MUST be within the room's x1 to x2
- plan_y: y position on the plan image (0 to 1), MUST be within the room's y1 to y2

Return ONLY a valid JSON array. No markdown, no explanation."""

    def place_fixtures_on_plan(
        self,
        file_path: str,
        file_type: str,
        rooms_with_fixtures: dict[str, list],
        rooms_data: list[RoomData] | None = None,
    ) -> dict[str, list[tuple[float, float, str]]]:
        """Second pass: send plan image + fixture list + bounding boxes to Claude.

        Only places major fixture types (recessed, pendant, sconce, ceiling_fan,
        coach_light, exhaust_fan) for a cleaner overlay.
        """
        images = self._load_images(file_path, file_type)

        # Build room bounding box lookup
        bbox_lookup = {}
        if rooms_data:
            for rd in rooms_data:
                if rd.bbox_x1 is not None:
                    bbox_lookup[rd.name] = {
                        "x1": round(rd.bbox_x1, 3),
                        "y1": round(rd.bbox_y1, 3),
                        "x2": round(rd.bbox_x2, 3),
                        "y2": round(rd.bbox_y2, 3),
                    }

        # Build the fixture list, filtered to overlay types only
        room_sections = []
        for room_name, fixtures in rooms_with_fixtures.items():
            overlay_fixtures = [
                f for f in fixtures if f.fixture_type in self.OVERLAY_FIXTURE_TYPES
            ]
            if not overlay_fixtures:
                continue

            bbox = bbox_lookup.get(room_name)
            if bbox:
                room_header = (
                    f"Room: {room_name}\n"
                    f"  Bounding box: x1={bbox['x1']}, y1={bbox['y1']}, "
                    f"x2={bbox['x2']}, y2={bbox['y2']}"
                )
            else:
                room_header = f"Room: {room_name}"

            fixture_lines = []
            for f in overlay_fixtures:
                fixture_lines.append(f"  - {f.fixture_type}")

            room_sections.append(room_header + "\n" + "\n".join(fixture_lines))

        fixture_list_text = (
            "Place the following fixtures on the floor plan. "
            "Each fixture MUST be placed inside its room's bounding box.\n\n"
            + "\n\n".join(room_sections)
        )

        # Build the API call
        content = []
        for b64_data, media_type in images:
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64_data,
                    },
                }
            )
        content.append({"type": "text", "text": fixture_list_text})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=self.PLACEMENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )

        raw = response.content[0].text

        # Parse response
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            placements = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse placement response: {e}")
            logger.error(f"Raw: {raw[:500]}")
            return {}

        if not isinstance(placements, list):
            if isinstance(placements, dict) and "fixtures" in placements:
                placements = placements["fixtures"]
            else:
                logger.error("Placement response was not a list")
                return {}

        # Post-process: clamp fixtures to their room's bounding box
        result: dict[str, list[tuple[float, float, str]]] = {}
        for p in placements:
            room = p.get("room_name", "")
            fx = p.get("plan_x", 0.5)
            fy = p.get("plan_y", 0.5)
            ftype = p.get("fixture_type", "")

            # Clamp to bounding box if available
            bbox = bbox_lookup.get(room)
            if bbox:
                fx = max(bbox["x1"] + 0.005, min(bbox["x2"] - 0.005, fx))
                fy = max(bbox["y1"] + 0.005, min(bbox["y2"] - 0.005, fy))

            if room not in result:
                result[room] = []
            result[room].append((fx, fy, ftype))

        return result
