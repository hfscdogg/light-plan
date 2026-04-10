import base64
import json
import logging
import re

import anthropic

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

SYSTEM_PROMPT = """You are analyzing a residential architectural floor plan image. Your job is to identify every distinct room or space visible in the plan and locate their boundaries precisely.

For each room, provide:
- name: the label shown on the plan (e.g. "Kitchen", "Bedroom 2", "Master Bath"). Use the label exactly as printed if visible.
- room_type: a normalized type from this list: kitchen, dining, living, family, great_room, master_bedroom, bedroom, master_bathroom, bathroom, half_bath, powder_room, hallway, entry, foyer, laundry, mudroom, pantry, closet, walk_in_closet, garage, porch, patio, office, den, bonus_room, exterior
- sqft: estimated square footage. Calculate from dimensions if shown on the plan. If not shown, estimate based on the room's visual proportion relative to other rooms.
- width_ft: estimated width in feet
- length_ft: estimated length in feet
- ceiling_height_ft: if noted on the plan, use that value. Otherwise return null.
- bbox_x1: LEFT edge of the room as a fraction (0 to 1) of the plan image width
- bbox_y1: TOP edge of the room as a fraction (0 to 1) of the plan image height
- bbox_x2: RIGHT edge of the room as a fraction (0 to 1) of the plan image width
- bbox_y2: BOTTOM edge of the room as a fraction (0 to 1) of the plan image height

The bounding box should tightly follow the interior walls of each room. Be precise: trace the inner wall lines to set each edge. The coordinates should define a rectangle that contains the room's floor area but does not extend into adjacent rooms or walls.

Important:
- Include ALL rooms you can identify, including hallways, closets, garage and exterior spaces
- If a room label is partially visible or you can infer the room type from context (fixtures, layout), include it with your best guess
- When dimensions are shown on the plan, use them. When they are not, estimate based on typical residential proportions.
- Focus on getting the bounding box coordinates accurate. These will be used to place lighting fixtures, so precision matters.
- Return ONLY a valid JSON array. No markdown fencing, no explanation, no commentary."""

USER_PROMPT = "Analyze this floor plan and return a JSON array of all rooms found."


class PlanParser:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.claude_model

    def parse_plan(self, file_path: str, file_type: str) -> list[RoomData]:
        """Parse a floor plan image and return structured room data."""
        images = self._load_images(file_path, file_type)
        raw_response = self._call_claude(images)
        rooms = self._parse_response(raw_response)
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
        """Send floor plan images to Claude Vision and get room analysis."""
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

        content.append({"type": "text", "text": USER_PROMPT})

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )

        return response.content[0].text

    def _parse_response(self, raw: str) -> list[RoomData]:
        """Parse Claude's response into structured RoomData objects."""
        # Strip markdown code fences if present
        cleaned = raw.strip()
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Claude response as JSON: {e}")
            logger.error(f"Raw response: {raw[:500]}")
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
