"""Generate default room lists from total square footage.

Uses builder-standard room mixes keyed by home size bracket.
Each room gets a percentage of the total sqft, with width/length
derived from typical aspect ratios per room type.
"""

import math

TYPICAL_ASPECT = {
    "kitchen": (1.15, 1.0),
    "dining": (1.1, 1.0),
    "living": (1.15, 1.0),
    "family": (1.2, 1.0),
    "great_room": (1.3, 1.0),
    "master_bedroom": (1.15, 1.0),
    "bedroom": (1.1, 1.0),
    "master_bathroom": (1.25, 1.0),
    "bathroom": (1.3, 1.0),
    "half_bath": (1.25, 1.0),
    "hallway": (3.0, 1.0),
    "entry": (1.3, 1.0),
    "foyer": (1.2, 1.0),
    "laundry": (1.3, 1.0),
    "office": (1.1, 1.0),
    "den": (1.1, 1.0),
    "bonus_room": (1.2, 1.0),
    "garage": (1.0, 1.0),
    "porch": (2.0, 1.0),
    "patio": (1.5, 1.0),
    "closet": (1.5, 1.0),
    "walk_in_closet": (1.3, 1.0),
    "pantry": (1.5, 1.0),
    "mudroom": (1.5, 1.0),
}

TEMPLATES = {
    "under_2000": [
        {"name": "Kitchen", "room_type": "kitchen", "pct": 0.12},
        {"name": "Living Room", "room_type": "living", "pct": 0.16},
        {"name": "Dining Room", "room_type": "dining", "pct": 0.08},
        {"name": "Master Bedroom", "room_type": "master_bedroom", "pct": 0.14},
        {"name": "Master Bathroom", "room_type": "master_bathroom", "pct": 0.05},
        {"name": "Bedroom 2", "room_type": "bedroom", "pct": 0.10},
        {"name": "Bedroom 3", "room_type": "bedroom", "pct": 0.09},
        {"name": "Bathroom", "room_type": "bathroom", "pct": 0.04},
        {"name": "Hallway", "room_type": "hallway", "pct": 0.05},
        {"name": "Laundry", "room_type": "laundry", "pct": 0.04},
        {"name": "Entry", "room_type": "entry", "pct": 0.03},
        {"name": "Garage", "room_type": "garage", "pct": 0.07},
        {"name": "Porch", "room_type": "porch", "pct": 0.03},
    ],
    "2000_3000": [
        {"name": "Kitchen", "room_type": "kitchen", "pct": 0.11},
        {"name": "Living Room", "room_type": "living", "pct": 0.14},
        {"name": "Dining Room", "room_type": "dining", "pct": 0.07},
        {"name": "Master Bedroom", "room_type": "master_bedroom", "pct": 0.13},
        {"name": "Master Bathroom", "room_type": "master_bathroom", "pct": 0.06},
        {"name": "Bedroom 2", "room_type": "bedroom", "pct": 0.09},
        {"name": "Bedroom 3", "room_type": "bedroom", "pct": 0.08},
        {"name": "Bathroom", "room_type": "bathroom", "pct": 0.04},
        {"name": "Half Bath", "room_type": "half_bath", "pct": 0.02},
        {"name": "Hallway", "room_type": "hallway", "pct": 0.05},
        {"name": "Laundry", "room_type": "laundry", "pct": 0.04},
        {"name": "Entry", "room_type": "entry", "pct": 0.03},
        {"name": "Office", "room_type": "office", "pct": 0.06},
        {"name": "Garage", "room_type": "garage", "pct": 0.06},
        {"name": "Porch", "room_type": "porch", "pct": 0.02},
    ],
    "3000_5000": [
        {"name": "Kitchen", "room_type": "kitchen", "pct": 0.10},
        {"name": "Living Room", "room_type": "living", "pct": 0.12},
        {"name": "Family Room", "room_type": "family", "pct": 0.10},
        {"name": "Dining Room", "room_type": "dining", "pct": 0.06},
        {"name": "Master Bedroom", "room_type": "master_bedroom", "pct": 0.11},
        {"name": "Master Bathroom", "room_type": "master_bathroom", "pct": 0.06},
        {"name": "Bedroom 2", "room_type": "bedroom", "pct": 0.07},
        {"name": "Bedroom 3", "room_type": "bedroom", "pct": 0.07},
        {"name": "Bedroom 4", "room_type": "bedroom", "pct": 0.06},
        {"name": "Bathroom 2", "room_type": "bathroom", "pct": 0.04},
        {"name": "Half Bath", "room_type": "half_bath", "pct": 0.02},
        {"name": "Hallway", "room_type": "hallway", "pct": 0.04},
        {"name": "Laundry", "room_type": "laundry", "pct": 0.03},
        {"name": "Office", "room_type": "office", "pct": 0.05},
        {"name": "Entry / Foyer", "room_type": "foyer", "pct": 0.03},
        {"name": "Garage", "room_type": "garage", "pct": 0.04},
    ],
    "5000_8000": [
        {"name": "Kitchen", "room_type": "kitchen", "pct": 0.08},
        {"name": "Great Room", "room_type": "great_room", "pct": 0.12},
        {"name": "Formal Living", "room_type": "living", "pct": 0.07},
        {"name": "Dining Room", "room_type": "dining", "pct": 0.05},
        {"name": "Master Suite", "room_type": "master_bedroom", "pct": 0.10},
        {"name": "Master Bathroom", "room_type": "master_bathroom", "pct": 0.06},
        {"name": "Bedroom 2", "room_type": "bedroom", "pct": 0.06},
        {"name": "Bedroom 3", "room_type": "bedroom", "pct": 0.06},
        {"name": "Bedroom 4", "room_type": "bedroom", "pct": 0.05},
        {"name": "Guest Suite", "room_type": "bedroom", "pct": 0.05},
        {"name": "Bathroom 2", "room_type": "bathroom", "pct": 0.03},
        {"name": "Bathroom 3", "room_type": "bathroom", "pct": 0.03},
        {"name": "Half Bath", "room_type": "half_bath", "pct": 0.01},
        {"name": "Hallway", "room_type": "hallway", "pct": 0.04},
        {"name": "Laundry", "room_type": "laundry", "pct": 0.03},
        {"name": "Office / Study", "room_type": "office", "pct": 0.05},
        {"name": "Bonus Room", "room_type": "bonus_room", "pct": 0.05},
        {"name": "Foyer", "room_type": "foyer", "pct": 0.03},
        {"name": "Garage", "room_type": "garage", "pct": 0.03},
    ],
    "over_8000": [
        {"name": "Kitchen", "room_type": "kitchen", "pct": 0.07},
        {"name": "Great Room", "room_type": "great_room", "pct": 0.10},
        {"name": "Formal Living", "room_type": "living", "pct": 0.06},
        {"name": "Formal Dining", "room_type": "dining", "pct": 0.04},
        {"name": "Master Suite", "room_type": "master_bedroom", "pct": 0.08},
        {"name": "Master Bathroom", "room_type": "master_bathroom", "pct": 0.05},
        {"name": "Bedroom 2", "room_type": "bedroom", "pct": 0.05},
        {"name": "Bedroom 3", "room_type": "bedroom", "pct": 0.05},
        {"name": "Bedroom 4", "room_type": "bedroom", "pct": 0.04},
        {"name": "Bedroom 5", "room_type": "bedroom", "pct": 0.04},
        {"name": "Guest Suite", "room_type": "bedroom", "pct": 0.05},
        {"name": "Bathroom 2", "room_type": "bathroom", "pct": 0.03},
        {"name": "Bathroom 3", "room_type": "bathroom", "pct": 0.02},
        {"name": "Bathroom 4", "room_type": "bathroom", "pct": 0.02},
        {"name": "Powder Room", "room_type": "half_bath", "pct": 0.01},
        {"name": "Hallway", "room_type": "hallway", "pct": 0.04},
        {"name": "Upper Hall", "room_type": "hallway", "pct": 0.03},
        {"name": "Laundry", "room_type": "laundry", "pct": 0.03},
        {"name": "Office / Study", "room_type": "office", "pct": 0.04},
        {"name": "Den / Library", "room_type": "den", "pct": 0.04},
        {"name": "Bonus Room", "room_type": "bonus_room", "pct": 0.04},
        {"name": "Foyer", "room_type": "foyer", "pct": 0.03},
        {"name": "Mudroom", "room_type": "mudroom", "pct": 0.02},
        {"name": "Garage", "room_type": "garage", "pct": 0.03},
        {"name": "Covered Patio", "room_type": "patio", "pct": 0.03},
    ],
}


def _sqft_to_bracket(total_sqft: int) -> str:
    if total_sqft < 2000:
        return "under_2000"
    if total_sqft < 3000:
        return "2000_3000"
    if total_sqft < 5000:
        return "3000_5000"
    if total_sqft < 8000:
        return "5000_8000"
    return "over_8000"


def _dims_from_sqft(room_sqft: float, room_type: str) -> tuple[float, float]:
    """Derive width and length from sqft using typical aspect ratios."""
    aspect_w, aspect_l = TYPICAL_ASPECT.get(room_type, (1.1, 1.0))
    ratio = aspect_w / aspect_l
    length = math.sqrt(room_sqft / ratio)
    width = length * ratio
    return round(max(4, width), 1), round(max(4, length), 1)


def generate_rooms(
    total_sqft: int,
    ceiling_height: float = 9.0,
    template_key: str | None = None,
) -> list[dict]:
    """Generate a default room list from total square footage.

    Returns a list of dicts with: name, room_type, sqft, width_ft,
    length_ft, ceiling_height_ft, sort_order.
    """
    bracket = template_key or _sqft_to_bracket(total_sqft)
    template = TEMPLATES.get(bracket, TEMPLATES["2000_3000"])

    rooms = []
    for i, spec in enumerate(template):
        room_sqft = round(total_sqft * spec["pct"])
        width, length = _dims_from_sqft(room_sqft, spec["room_type"])
        rooms.append({
            "name": spec["name"],
            "room_type": spec["room_type"],
            "sqft": room_sqft,
            "width_ft": width,
            "length_ft": length,
            "ceiling_height_ft": ceiling_height,
            "sort_order": i,
        })

    return rooms
