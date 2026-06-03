"""Assign a lighting tier to each room based on global percentage split.

Rooms are sorted by "visibility priority" — high-traffic, high-impact
rooms get the best tier first. The percentage allocation drives sqft
thresholds, not room count, so "10% Best" means the top 10% of the
home's total sqft gets Best-tier fixtures.
"""

PRIORITY_ORDER = [
    "kitchen",
    "master_bedroom",
    "living",
    "great_room",
    "family",
    "dining",
    "master_bathroom",
    "foyer",
    "office",
    "den",
    "bonus_room",
    "bedroom",
    "entry",
    "bathroom",
    "half_bath",
    "hallway",
    "laundry",
    "mudroom",
    "pantry",
    "closet",
    "walk_in_closet",
    "porch",
    "patio",
    "garage",
]


def _priority(room_type: str) -> int:
    try:
        return PRIORITY_ORDER.index(room_type)
    except ValueError:
        return len(PRIORITY_ORDER)


def allocate_tiers(
    rooms: list[dict],
    pct_good: int,
    pct_better: int,
    pct_best: int,
) -> list[dict]:
    """Assign a tier to each room based on the global percentage split.

    Each room dict must have 'room_type' and 'sqft' keys.
    Returns the same room dicts with 'assigned_tier' added/updated.

    The algorithm assigns tiers by sqft weight:
    - Sort rooms by visibility priority (highest-impact first)
    - Walk the sorted list, assigning 'best' until the best sqft
      budget is exhausted, then 'better', then 'good'
    """
    total_sqft = sum(r.get("sqft", 0) or 0 for r in rooms)
    if total_sqft <= 0:
        for r in rooms:
            r["assigned_tier"] = "better"
        return rooms

    best_budget = total_sqft * pct_best / 100
    better_budget = total_sqft * pct_better / 100

    sorted_rooms = sorted(rooms, key=lambda r: _priority(r.get("room_type", "")))

    best_used = 0.0
    better_used = 0.0

    for r in sorted_rooms:
        sqft = r.get("sqft", 0) or 0
        if best_used + sqft <= best_budget + 0.5:
            r["assigned_tier"] = "best"
            best_used += sqft
        elif better_used + sqft <= better_budget + 0.5:
            r["assigned_tier"] = "better"
            better_used += sqft
        else:
            r["assigned_tier"] = "good"

    return rooms
