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

ROOMS_SYSTEM_PROMPT = """You are a precise computer-vision assistant analyzing a residential architectural floor plan.

COORDINATE SYSTEM:
- (0.0, 0.0) = top-left pixel of this image
- (1.0, 1.0) = bottom-right pixel of this image
- x increases left → right, y increases top → bottom

STEP-BY-STEP PROCESS:
1. Mentally divide the FULL IMAGE into a 3×3 grid:
   - Top row: y ∈ [0.00, 0.33], Middle row: y ∈ [0.33, 0.67], Bottom row: y ∈ [0.67, 1.00]
   - Left col: x ∈ [0.00, 0.33], Center col: x ∈ [0.33, 0.67], Right col: x ∈ [0.67, 1.00]
2. For EACH room, identify which grid cell(s) it occupies.
3. Report both a bounding box AND the position of the room's printed name text.

CRITICAL RULES:
- bbox must cover the full room from wall to wall.
- label_x/label_y is where the room's name text is physically printed — this is the room's visual center.
- A room in the right third of the image MUST have bbox_x2 > 0.67 and label_x > 0.60.
- A room in the bottom third MUST have bbox_y2 > 0.67 and label_y > 0.60.
- Report each room EXACTLY ONCE. Skip very small spaces (individual closets, nooks).

For each room return a JSON object with:
- name: the label printed on the plan exactly
- room_type: one of [kitchen, dining, living, family, great_room, master_bedroom, bedroom, master_bathroom, bathroom, half_bath, powder_room, hallway, entry, foyer, laundry, mudroom, pantry, closet, walk_in_closet, garage, porch, patio, office, den, bonus_room, exterior]
- label_x, label_y: center of the room's printed name text (fractions of image)
- bbox_x1, bbox_y1, bbox_x2, bbox_y2: tight rectangle around the room's walls (fractions of image)
- width_ft, length_ft: room dimensions in feet
- sqft: square footage
- ceiling_height_ft: if stated, else null

OUTPUT FORMAT — CRITICAL:
Your entire response must be a single JSON array and nothing else.
- Start with `[` and end with `]`.
- No prose, no reasoning, no markdown fences."""

ROOMS_USER_PROMPT = (
    "Identify every room in this floor plan. For each, report its bounding "
    "box AND the position of its printed label text. JSON array only."
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

        Flow:
          1. Detect drawing content bounds via Pillow pixel analysis
             (deterministic, no API call — replaces the old Vision-based
             bounds detection which was unreliable).
          2. Crop the image to those bounds so whitespace margins are removed.
          3. Send the cropped image to Claude Vision for per-room bbox
             detection with a prompt that includes 3x3 grid spatial
             reasoning to combat Y-axis coordinate compression.
          4. Scale crop-relative bboxes back to full-image coordinates.
          5. Post-process: if bboxes are still compressed into a sub-region,
             linearly rescale to fill the expected drawing area.
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

        rooms = self._deduplicate_rooms(rooms)
        rooms = self._scale_rooms_to_full_image(rooms, bounds)
        rooms = self._calibrate_with_ocr(rooms, images, bounds)
        rooms = self._validate_and_rescale_rooms(rooms)
        rooms = self._refine_bboxes(rooms)
        rooms = self._clamp_to_drawing(rooms, bounds)

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

    _NO_CROP: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)

    # Padding added around detected content bounds (fraction per side).
    _BOUNDS_PAD = 0.01

    def _identify_drawing_bounds(
        self, images: list[tuple[str, str]]
    ) -> tuple[float, float, float, float]:
        """Detect the drawing bounds using Pillow pixel analysis.

        Converts the first image to grayscale, thresholds to find non-white
        content pixels, and returns their bounding box as fractions of the
        full image.  This is deterministic, fast, and does not cost an API
        call (the old Vision-based Pass 1 was unreliable and often returned
        overly tight or overly wide bounds that broke downstream coordinate
        accuracy).

        Returns ``(x1, y1, x2, y2)`` or ``_NO_CROP`` on failure.
        """
        try:
            b64_data, _ = images[0]
            raw_bytes = base64.standard_b64decode(b64_data)
            img = Image.open(io.BytesIO(raw_bytes))
            img.load()
            w, h = img.size

            gray = img.convert("L")

            # Content = pixels darker than 230.  This catches lines, text,
            # and fills while ignoring JPEG compression artifacts (~245+).
            content_mask = gray.point(lambda p: 255 if p < 230 else 0, "L")
            bbox = content_mask.getbbox()  # (left, upper, right, lower) | None

            if bbox is None:
                logger.warning("Pixel bounds: no content found in image")
                return self._NO_CROP

            left, upper, right, lower = bbox
            x1 = max(0.0, left / w - self._BOUNDS_PAD)
            y1 = max(0.0, upper / h - self._BOUNDS_PAD)
            x2 = min(1.0, right / w + self._BOUNDS_PAD)
            y2 = min(1.0, lower / h + self._BOUNDS_PAD)

            logger.info(
                "Pixel bounds: (%.3f, %.3f, %.3f, %.3f) from %d×%d image",
                x1, y1, x2, y2, w, h,
            )

            # If content already fills 95%+ of the image in both dimensions,
            # cropping would be a near no-op — skip it.
            if (x2 - x1) > 0.95 and (y2 - y1) > 0.95:
                logger.info("Pixel bounds span >95%% — skipping crop")
                return self._NO_CROP

            return (x1, y1, x2, y2)
        except Exception as e:  # noqa: BLE001
            logger.warning("Pixel bounds detection failed: %s", e)
            return self._NO_CROP

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

    # ------------------------------------------------------------------
    # Drawing bounds clamping
    # ------------------------------------------------------------------

    @staticmethod
    def _clamp_to_drawing(
        rooms: list[RoomData],
        bounds: tuple[float, float, float, float],
    ) -> list[RoomData]:
        """Clamp all room positions and bboxes to the drawing area.

        Prevents fixtures from appearing outside the floor plan drawing
        (e.g., in the title block area below 'Second Floor Plan' text).
        """
        bx1, by1, bx2, by2 = bounds
        if bounds == (0.0, 0.0, 1.0, 1.0):
            # No crop — use a generous default (top 80% of image is drawing)
            bx1, by1, bx2, by2 = 0.02, 0.02, 0.98, 0.82

        result: list[RoomData] = []
        for r in rooms:
            px = max(bx1, min(bx2, r.position_x)) if r.position_x else r.position_x
            py = max(by1, min(by2, r.position_y)) if r.position_y else r.position_y
            rx1 = max(bx1, r.bbox_x1) if r.bbox_x1 is not None else r.bbox_x1
            ry1 = max(by1, r.bbox_y1) if r.bbox_y1 is not None else r.bbox_y1
            rx2 = min(bx2, r.bbox_x2) if r.bbox_x2 is not None else r.bbox_x2
            ry2 = min(by2, r.bbox_y2) if r.bbox_y2 is not None else r.bbox_y2

            result.append(
                RoomData(
                    name=r.name, room_type=r.room_type, sqft=r.sqft,
                    width_ft=r.width_ft, length_ft=r.length_ft,
                    ceiling_height_ft=r.ceiling_height_ft,
                    position_x=px, position_y=py,
                    bbox_x1=rx1, bbox_y1=ry1, bbox_x2=rx2, bbox_y2=ry2,
                )
            )
        return result

    # ------------------------------------------------------------------
    # OCR calibration
    # ------------------------------------------------------------------

    @staticmethod
    def _ocr_room_positions(
        images: list[tuple[str, str]],
    ) -> list[tuple[str, float, float]]:
        """Run Tesseract OCR on the floor plan to find room label positions.

        Returns a dict mapping uppercase room keywords found in the OCR
        output to their (x, y) center coordinates as fractions of the
        original image.  Only high-confidence matches are included.
        """
        try:
            import pytesseract
        except ImportError:
            logger.debug("pytesseract not installed — skipping OCR calibration")
            return {}

        try:
            b64_data, _ = images[0]
            raw_bytes = base64.standard_b64decode(b64_data)
            img = Image.open(io.BytesIO(raw_bytes))
            img.load()
            orig_w, orig_h = img.size

            # Upscale 4× for better OCR accuracy on architectural text
            img_large = img.resize(
                (orig_w * 4, orig_h * 4), Image.LANCZOS
            )
            from PIL import ImageEnhance

            gray = img_large.convert("L")
            enhanced = ImageEnhance.Contrast(gray).enhance(2.5)
            binary = enhanced.point(lambda p: 255 if p > 160 else 0, "L")

            data = pytesseract.image_to_data(
                binary,
                output_type=pytesseract.Output.DICT,
                config="--psm 6 --oem 3",
            )

            room_keywords = {
                "BEDROOM", "BATH", "KITCHEN", "LIVING", "DINING",
                "GARAGE", "FAMILY", "FOYER", "ENTRY", "PORCH",
                "OFFICE", "LAUNDRY", "NURSERY", "MASTER", "BREAKFAST",
                "SCREENED", "BREEZEWAY", "PATIO", "STUDY", "CLOSET",
                "HALL", "CEILING", "COFFERED", "VAULTED", "POWDER",
                "UTILITY", "MUDROOM", "PANTRY", "BONUS", "LOFT",
                "GUEST", "NOOK", "GREAT", "DEN",
            }

            results: list[tuple[str, float, float]] = []

            # Run OCR with multiple PSM modes to maximize text detection
            for psm in [6, 11]:
                data = pytesseract.image_to_data(
                    binary,
                    output_type=pytesseract.Output.DICT,
                    config=f"--psm {psm} --oem 3",
                )
                for i in range(len(data["text"])):
                    text = data["text"][i].strip()
                    conf = int(data["conf"][i])
                    if conf < 40 or len(text) < 3:
                        continue
                    upper = text.upper()
                    if any(kw in upper for kw in room_keywords):
                        cx = (data["left"][i] + data["width"][i] // 2) / 4
                        cy = (data["top"][i] + data["height"][i] // 2) / 4
                        pos = (upper, cx / orig_w, cy / orig_h)
                        # Avoid duplicate detections (same text at same position)
                        is_dup = any(
                            r[0] == pos[0] and abs(r[1]-pos[1]) < 0.02 and abs(r[2]-pos[2]) < 0.02
                            for r in results
                        )
                        if not is_dup:
                            results.append(pos)

            logger.info("OCR found %d room-related text hits", len(results))
            return results
        except Exception as e:  # noqa: BLE001
            logger.warning("OCR calibration failed: %s", e)
            return {}

    @staticmethod
    def _group_ocr_texts(
        hits: list[tuple[str, float, float]],
    ) -> list[tuple[str, float, float]]:
        """Group OCR text hits that are on the same line into multi-word labels.

        Two OCR hits are grouped if they are within 3% Y and 20% X of
        each other — indicating they are adjacent words on the same text
        line (e.g., "Master" + "Bedroom" → "Master Bedroom").
        """
        if not hits:
            return []

        used = [False] * len(hits)
        groups: list[tuple[str, float, float]] = []

        for i in range(len(hits)):
            if used[i]:
                continue
            word_i, xi, yi = hits[i]
            group_words = [word_i]
            group_xs = [xi]
            group_ys = [yi]
            used[i] = True

            for j in range(len(hits)):
                if used[j]:
                    continue
                word_j, xj, yj = hits[j]
                if abs(yj - yi) < 0.015 and abs(xj - xi) < 0.15:
                    group_words.append(word_j)
                    group_xs.append(xj)
                    group_ys.append(yj)
                    used[j] = True

            label = " ".join(sorted(group_words, key=lambda w: group_xs[group_words.index(w)]))
            cx = sum(group_xs) / len(group_xs)
            cy = sum(group_ys) / len(group_ys)
            groups.append((label, cx, cy))

        return groups

    def _calibrate_with_ocr(
        self,
        rooms: list[RoomData],
        images: list[tuple[str, str]],
        bounds: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0),
    ) -> list[RoomData]:
        """Replace Vision's room positions with OCR-detected text positions.

        1. Run OCR to find individual word positions.
        2. Filter OCR results to the drawing area (exclude title blocks).
        3. Group nearby words into multi-word labels (e.g., "MASTER" +
           "BEDROOM" → "MASTER BEDROOM").
        3. Match grouped labels to Vision rooms:
           - Multi-word labels (like "MASTER BEDROOM") get priority
             matching to rooms containing ALL those words.
           - Single-word labels (like "BEDROOM") are assigned to
             remaining unmatched rooms by greedy distance matching.
        4. Replace Vision positions with OCR positions for all matches.
        """
        raw_hits = self._ocr_room_positions(images)
        if not raw_hits:
            return rooms

        # Filter OCR hits to drawing area (exclude title blocks, footer text)
        bx1, by1, bx2, by2 = bounds
        if bounds != self._NO_CROP:
            raw_hits = [
                (kw, x, y) for kw, x, y in raw_hits
                if bx1 - 0.02 <= x <= bx2 + 0.02 and by1 - 0.02 <= y <= by2 + 0.02
            ]
        else:
            # No crop info — filter out bottom 20% (typically title block)
            raw_hits = [(kw, x, y) for kw, x, y in raw_hits if y < 0.82]

        if not raw_hits:
            return rooms

        grouped = self._group_ocr_texts(raw_hits)
        logger.info("OCR grouped into %d labels: %s",
                     len(grouped),
                     [(l, round(x, 3), round(y, 3)) for l, x, y in grouped])

        # Phase 1: match multi-word OCR labels to rooms (high confidence)
        used_group_idx: set[int] = set()
        room_to_ocr: dict[int, tuple[float, float]] = {}

        for ri, r in enumerate(rooms):
            if r.position_x is None:
                continue
            name_upper = r.name.upper()
            name_words = set(w for w in name_upper.split() if len(w) > 3)
            if not name_words:
                continue

            # Try multi-word groups first (2+ words matching)
            for gi, (label, gx, gy) in enumerate(grouped):
                if gi in used_group_idx:
                    continue
                label_words = set(label.split())
                overlap = name_words & label_words
                if len(overlap) >= 2:
                    room_to_ocr[ri] = (gx, gy)
                    used_group_idx.add(gi)
                    break

        # Phase 2: for remaining unmatched rooms, match single-word groups
        # Use greedy assignment: sort all (room, group) pairs by a score
        # that combines name match and assigns greedily.
        unmatched_rooms = [
            ri for ri in range(len(rooms))
            if ri not in room_to_ocr and rooms[ri].position_x is not None
        ]
        unmatched_groups = [
            gi for gi in range(len(grouped))
            if gi not in used_group_idx
        ]

        if unmatched_rooms and unmatched_groups:
            # Score each (room, group) pair
            pairs: list[tuple[float, int, int, float, float]] = []
            for ri in unmatched_rooms:
                name_words = set(w for w in rooms[ri].name.upper().split() if len(w) > 3)
                for gi in unmatched_groups:
                    label, gx, gy = grouped[gi]
                    label_words = set(label.split())
                    if name_words & label_words:
                        # Use just the OCR position distance from image center
                        # as a tiebreaker (NOT distance from Vision position,
                        # since Vision positions are unreliable)
                        pairs.append((0, ri, gi, gx, gy))

            # Greedy assignment: process pairs, assign each room/group once
            for _, ri, gi, gx, gy in pairs:
                if ri in room_to_ocr or gi in used_group_idx:
                    continue
                room_to_ocr[ri] = (gx, gy)
                used_group_idx.add(gi)

        # Apply OCR positions
        calibrated: list[RoomData] = []
        for ri, r in enumerate(rooms):
            if ri in room_to_ocr:
                ocr_x, ocr_y = room_to_ocr[ri]
                if r.bbox_x1 is not None:
                    bw = r.bbox_x2 - r.bbox_x1
                    bh = r.bbox_y2 - r.bbox_y1
                    new_bx1 = max(0.0, ocr_x - bw / 2)
                    new_by1 = max(0.0, ocr_y - bh / 2)
                    new_bx2 = min(1.0, new_bx1 + bw)
                    new_by2 = min(1.0, new_by1 + bh)
                else:
                    new_bx1 = new_by1 = new_bx2 = new_by2 = None

                calibrated.append(
                    RoomData(
                        name=r.name,
                        room_type=r.room_type,
                        sqft=r.sqft,
                        width_ft=r.width_ft,
                        length_ft=r.length_ft,
                        ceiling_height_ft=r.ceiling_height_ft,
                        position_x=ocr_x,
                        position_y=ocr_y,
                        bbox_x1=new_bx1,
                        bbox_y1=new_by1,
                        bbox_x2=new_bx2,
                        bbox_y2=new_by2,
                    )
                )
            else:
                calibrated.append(r)

        logger.info(
            "OCR calibration: replaced %d/%d room positions",
            len(room_to_ocr), len(rooms),
        )
        return calibrated

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate_rooms(rooms: list[RoomData]) -> list[RoomData]:
        """Merge duplicate room entries from Vision.

        Vision sometimes reports the same room twice (once from the name
        text, once from the dimension text).  Group by normalized name,
        keep the entry with the largest sqft (or first if equal), and
        average positions when merging.
        """
        if not rooms:
            return rooms

        groups: dict[str, list[RoomData]] = {}
        for r in rooms:
            key = r.name.strip().upper()
            groups.setdefault(key, []).append(r)

        merged: list[RoomData] = []
        for key, entries in groups.items():
            if len(entries) == 1:
                merged.append(entries[0])
                continue

            # Pick the best entry (largest sqft or first)
            best = max(entries, key=lambda r: r.sqft or 0)

            # Average the label positions from all duplicates
            xs = [r.position_x for r in entries if r.position_x is not None]
            ys = [r.position_y for r in entries if r.position_y is not None]
            avg_x = sum(xs) / len(xs) if xs else best.position_x
            avg_y = sum(ys) / len(ys) if ys else best.position_y

            merged.append(
                RoomData(
                    name=best.name,
                    room_type=best.room_type,
                    sqft=best.sqft,
                    width_ft=best.width_ft,
                    length_ft=best.length_ft,
                    ceiling_height_ft=best.ceiling_height_ft,
                    position_x=avg_x,
                    position_y=avg_y,
                )
            )

        logger.info(
            "Dedup: %d rooms → %d (merged %d duplicates)",
            len(rooms), len(merged), len(rooms) - len(merged),
        )
        return merged

    # ------------------------------------------------------------------
    # Label-position → bbox computation
    # ------------------------------------------------------------------

    _MIN_BBOX = {
        "master_bedroom": (0.12, 0.10),
        "bedroom": (0.07, 0.06),
        "kitchen": (0.08, 0.06),
        "living": (0.08, 0.07),
        "family": (0.10, 0.08),
        "great_room": (0.12, 0.10),
        "dining": (0.05, 0.04),
        "master_bathroom": (0.05, 0.04),
        "bathroom": (0.03, 0.03),
        "garage": (0.12, 0.10),
        "porch": (0.04, 0.03),
        "entry": (0.03, 0.03),
        "foyer": (0.04, 0.03),
        "laundry": (0.03, 0.03),
        "office": (0.04, 0.03),
        "bonus_room": (0.06, 0.05),
    }
    _MIN_BBOX_DEFAULT = (0.03, 0.03)

    def _refine_bboxes(self, rooms: list[RoomData]) -> list[RoomData]:
        """Refine room bboxes using both Vision bbox AND label position.

        Uses the label position as the authoritative room center (for fan
        placement), but keeps the Vision bbox for fixture spread — with
        two corrections:

        1. If the label position falls OUTSIDE the bbox, shift the bbox
           to center on the label (the label is more likely correct since
           architects print it at the room center).
        2. Enforce minimum bbox sizes per room type and correct aspect
           ratios using the room's reported dimensions.

        The result: position_x/position_y = best available room center
        (label if inside bbox, else bbox center), bbox = Vision bbox
        corrected for size and centering.
        """
        if not rooms:
            return rooms

        result: list[RoomData] = []
        for r in rooms:
            x1, y1, x2, y2 = r.bbox_x1, r.bbox_y1, r.bbox_x2, r.bbox_y2
            label_x, label_y = r.position_x, r.position_y

            # If no bbox at all, compute one from label + minimums
            if x1 is None or y1 is None:
                if label_x is not None and label_y is not None:
                    min_w, min_h = self._MIN_BBOX.get(
                        r.room_type, self._MIN_BBOX_DEFAULT
                    )
                    x1 = max(0.0, label_x - min_w / 2)
                    y1 = max(0.0, label_y - min_h / 2)
                    x2 = min(1.0, label_x + min_w / 2)
                    y2 = min(1.0, label_y + min_h / 2)
                else:
                    result.append(r)
                    continue

            bw = x2 - x1
            bh = y2 - y1
            bbox_cx = (x1 + x2) / 2
            bbox_cy = (y1 + y2) / 2

            # Determine best room center
            if label_x is not None and label_y is not None:
                # If label is inside or near the bbox, trust it as center
                # Otherwise fall back to bbox center
                margin = max(bw, bh) * 0.5
                if (x1 - margin <= label_x <= x2 + margin and
                        y1 - margin <= label_y <= y2 + margin):
                    center_x, center_y = label_x, label_y
                else:
                    center_x, center_y = bbox_cx, bbox_cy
            else:
                center_x, center_y = bbox_cx, bbox_cy

            # Aspect-ratio correction using reported dimensions
            if r.width_ft and r.length_ft and r.width_ft > 0 and r.length_ft > 0:
                expected_ratio = r.width_ft / r.length_ft
                actual_ratio = bw / bh if bh > 0.001 else 999
                if actual_ratio > expected_ratio * 1.3:
                    bh = bw / expected_ratio
                elif actual_ratio < expected_ratio / 1.3:
                    bw = bh * expected_ratio

            # Enforce minimum bbox sizes
            min_w, min_h = self._MIN_BBOX.get(
                r.room_type, self._MIN_BBOX_DEFAULT
            )
            bw = max(bw, min_w)
            bh = max(bh, min_h)

            # Rebuild bbox centered on the best center
            new_x1 = max(0.0, center_x - bw / 2)
            new_y1 = max(0.0, center_y - bh / 2)
            new_x2 = min(1.0, new_x1 + bw)
            new_y2 = min(1.0, new_y1 + bh)

            result.append(
                RoomData(
                    name=r.name,
                    room_type=r.room_type,
                    sqft=r.sqft,
                    width_ft=r.width_ft,
                    length_ft=r.length_ft,
                    ceiling_height_ft=r.ceiling_height_ft,
                    position_x=center_x,
                    position_y=center_y,
                    bbox_x1=new_x1,
                    bbox_y1=new_y1,
                    bbox_x2=new_x2,
                    bbox_y2=new_y2,
                )
            )

        return result

    # ------------------------------------------------------------------
    # Legacy post-processing (kept for reference, no longer called)
    # ------------------------------------------------------------------

    def _validate_and_rescale_rooms(
        self, rooms: list[RoomData]
    ) -> list[RoomData]:
        """Detect Y-axis (or X-axis) coordinate compression and rescale.

        Claude Vision frequently compresses bbox coordinates toward the
        center or upper portion of the image.  For example, it places all
        rooms in y ∈ [0.10, 0.50] when the drawing actually spans
        y ∈ [0.10, 0.85].  This causes every lighting icon to cluster in
        the top half.

        Detection: if the total span of all bboxes in the y-dimension is
        below ``_COMPRESSION_THRESHOLD`` of the image, it is almost
        certainly compressed.

        Correction: linearly rescale the compressed axis so that the rooms
        span from their current minimum to a reasonable maximum (keeping
        relative positions intact).
        """
        _SPAN_THRESHOLD = 0.55   # total span < 55% → compressed
        _MAX_THRESHOLD = 0.70    # max extent < 70% → one side is clipped
        _TARGET_SPAN = 0.80     # rescale to cover ~80% of image

        if not rooms:
            return rooms

        y1s = [r.bbox_y1 for r in rooms if r.bbox_y1 is not None]
        y2s = [r.bbox_y2 for r in rooms if r.bbox_y2 is not None]
        x1s = [r.bbox_x1 for r in rooms if r.bbox_x1 is not None]
        x2s = [r.bbox_x2 for r in rooms if r.bbox_x2 is not None]

        if not y1s or not y2s:
            return rooms

        min_y, max_y = min(y1s), max(y2s)
        min_x, max_x = min(x1s), max(x2s)
        y_span = max_y - min_y
        x_span = max_x - min_x

        # Detect compression via EITHER small span OR low max extent.
        # A max_x of 0.53 means the right 47% of the image has no rooms,
        # which is almost certainly wrong for a floor plan drawing.
        rescale_y = y_span < _SPAN_THRESHOLD or max_y < _MAX_THRESHOLD
        rescale_x = x_span < _SPAN_THRESHOLD or max_x < _MAX_THRESHOLD

        if not rescale_y and not rescale_x:
            logger.info(
                "Bbox spread OK (x=[%.2f,%.2f] span=%.2f, y=[%.2f,%.2f] span=%.2f)",
                min_x, max_x, x_span, min_y, max_y, y_span,
            )
            return rooms

        logger.warning(
            "Bbox compression detected (x_span=%.2f, y_span=%.2f, "
            "y_range=[%.3f, %.3f], x_range=[%.3f, %.3f]). Rescaling.",
            x_span, y_span, min_y, max_y, min_x, max_x,
        )

        def _make_scaler(
            src_min: float, src_max: float, do_rescale: bool
        ):
            """Return a function that rescales a coordinate."""
            if not do_rescale:
                return lambda v: v
            src_span = src_max - src_min
            if src_span < 0.01:
                return lambda v: v  # degenerate — don't touch

            # Target: keep src_min roughly in place, expand to TARGET_SPAN
            tgt_min = max(0.02, src_min - 0.02)
            tgt_max = min(0.98, tgt_min + _TARGET_SPAN)
            tgt_span = tgt_max - tgt_min
            factor = tgt_span / src_span

            def scale(v):
                if v is None:
                    return None
                return max(0.0, min(1.0, tgt_min + (v - src_min) * factor))

            return scale

        sy = _make_scaler(min_y, max_y, rescale_y)
        sx = _make_scaler(min_x, max_x, rescale_x)

        rescaled: list[RoomData] = []
        for r in rooms:
            rescaled.append(
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

        new_x1s = [r.bbox_x1 for r in rescaled if r.bbox_x1 is not None]
        new_x2s = [r.bbox_x2 for r in rescaled if r.bbox_x2 is not None]
        new_y1s = [r.bbox_y1 for r in rescaled if r.bbox_y1 is not None]
        new_y2s = [r.bbox_y2 for r in rescaled if r.bbox_y2 is not None]
        if new_y1s and new_y2s:
            logger.info(
                "After rescale: x=[%.3f,%.3f] (was [%.3f,%.3f]) y=[%.3f,%.3f] (was [%.3f,%.3f])",
                min(new_x1s), max(new_x2s), min_x, max_x,
                min(new_y1s), max(new_y2s), min_y, max_y,
            )

        return rescaled

    # Minimum bbox dimensions (fraction of image) by room type.
    # Prevents fixtures from clustering in a thin sliver when Vision
    # returns an undersized bbox.
    _MIN_BBOX = {
        "master_bedroom": (0.12, 0.10),
        "bedroom": (0.07, 0.06),
        "kitchen": (0.08, 0.06),
        "living": (0.08, 0.07),
        "family": (0.10, 0.08),
        "great_room": (0.10, 0.08),
        "dining": (0.05, 0.04),
        "master_bathroom": (0.04, 0.04),
        "bathroom": (0.03, 0.03),
        "garage": (0.10, 0.08),
        "porch": (0.04, 0.03),
        "entry": (0.03, 0.03),
        "foyer": (0.04, 0.03),
        "laundry": (0.03, 0.03),
        "office": (0.03, 0.03),
        "bonus_room": (0.06, 0.05),
    }
    _MIN_BBOX_DEFAULT = (0.02, 0.02)

    def _expand_undersized_bboxes(self, rooms: list[RoomData]) -> list[RoomData]:
        """Expand bboxes that are too small for their room type or dimensions.

        Two expansion passes:

        1. **Aspect-ratio correction** — if the room reports ``width_ft``
           and ``length_ft``, compute the expected aspect ratio.  When the
           bbox aspect ratio is off by more than 1.8×, expand the short
           dimension so fixtures spread into a natural grid instead of a
           single row.

        2. **Minimum-size enforcement** — each room type has a minimum bbox
           size (fraction of image).  If the bbox is smaller, it is
           expanded symmetrically around its center.
        """
        if not rooms:
            return rooms

        expanded: list[RoomData] = []
        for r in rooms:
            x1, y1, x2, y2 = r.bbox_x1, r.bbox_y1, r.bbox_x2, r.bbox_y2
            if x1 is None or y1 is None:
                expanded.append(r)
                continue

            bw = x2 - x1
            bh = y2 - y1
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2

            # --- Pass 1: aspect-ratio correction ---
            if r.width_ft and r.length_ft and r.width_ft > 0 and r.length_ft > 0:
                expected_ratio = r.width_ft / r.length_ft
                actual_ratio = bw / bh if bh > 0.001 else 999

                if actual_ratio > expected_ratio * 1.2:
                    # Height is too small relative to width
                    target_h = bw / expected_ratio
                    bh = target_h
                elif actual_ratio < expected_ratio / 1.2:
                    # Width is too small relative to height
                    target_w = bh * expected_ratio
                    bw = target_w

            # --- Pass 2: minimum-size enforcement ---
            min_w, min_h = self._MIN_BBOX.get(r.room_type, self._MIN_BBOX_DEFAULT)
            bw = max(bw, min_w)
            bh = max(bh, min_h)

            # Rebuild bbox centered on original center, clamped to [0, 1]
            new_x1 = max(0.0, cx - bw / 2)
            new_y1 = max(0.0, cy - bh / 2)
            new_x2 = min(1.0, new_x1 + bw)
            new_y2 = min(1.0, new_y1 + bh)

            expanded.append(
                RoomData(
                    name=r.name,
                    room_type=r.room_type,
                    sqft=r.sqft,
                    width_ft=r.width_ft,
                    length_ft=r.length_ft,
                    ceiling_height_ft=r.ceiling_height_ft,
                    position_x=(new_x1 + new_x2) / 2,
                    position_y=(new_y1 + new_y2) / 2,
                    bbox_x1=new_x1,
                    bbox_y1=new_y1,
                    bbox_x2=new_x2,
                    bbox_y2=new_y2,
                )
            )

        return expanded

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

            # Label-position anchoring: use the printed text position as
            # the authoritative room center.  Fall back to bbox center or
            # explicit position fields for backward compatibility.
            label_x = item.get("label_x")
            label_y = item.get("label_y")

            bbox_x1 = item.get("bbox_x1")
            bbox_y1 = item.get("bbox_y1")
            bbox_x2 = item.get("bbox_x2")
            bbox_y2 = item.get("bbox_y2")

            if label_x is not None and label_y is not None:
                pos_x = float(label_x)
                pos_y = float(label_y)
            elif bbox_x1 is not None and bbox_x2 is not None:
                pos_x = (bbox_x1 + bbox_x2) / 2
                pos_y = (bbox_y1 + bbox_y2) / 2 if bbox_y1 is not None else None
            else:
                pos_x = item.get("position_x")
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
