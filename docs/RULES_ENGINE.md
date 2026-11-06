# Lighting Rules Engine

This document describes the default lighting fixture rules applied by LightPlan when generating a layout.

## General Principles

- Ambient can spacing is based on ceiling height: about one ceiling height between cans, tightened a little for Better and Best (see the grid algorithm below)
- Outer cans sit half a spacing off the walls
- Bedrooms are the exception: a fixed 2x2 or 2x3 grid, inset at least 24 inches
- Every room receives a dimming zone assignment (tracked internally for future Lutron integration)
- All fixture positions are stored as relative coordinates (0 to 1) so they scale to any rendering size
- Pre-wire locations are marked separately from fixture placements

## Room Type Rules

### Kitchen
- Recessed grid at 0.8x the standard spacing; at least 4 cans in a kitchen of 100 sq ft or more
- Island pendant pre-wires: 2, or 3 at Best or where the kitchen's long side is 16 ft or more
- Scene keypad ("Entertain") at the kitchen's main entry
- Under-cabinet lighting pre-wire (Better and Best tiers)
- Zones: kitchen-general, kitchen-island, kitchen-accent

### Master Bedroom
- 4 recessed cans (Good) or 6 (Better and Best), as a full 2x2 or 2x3 grid; never a can at the center, where the fan goes
- Ceiling fan pre-wire at room center
- Switched outlet locations on each side of the bed wall (not drawn on the plan viewer)
- Scene keypad ("Goodnight") inside the bedroom door
- Zones: master-general, master-bed

### Bedroom
- 4 recessed cans as a 2x2 grid (6 as a 2x3 grid at Best); never a can at the center, where the fan goes
- Ceiling fan pre-wire at center (Better and Best tiers)
- Switched outlet near bed area
- Zones: bedroom-{name}

### Bathroom (Full and Primary)
- One vanity light centered over the mirror; a primary bath of 80 sq ft or more gets one over each sink
- Wet-rated recessed can (IC/AT) over the tub or in the shower; the placement model positions it, since the grid cannot see the tub
- A second recessed can at Better and Best, in a bath of 60 sq ft or more, in the open floor and never over the sink
- Exhaust fan combo unit
- Zones: bath-vanity, bath-general

### Half Bath / Powder Room
- 1 to 2 recessed cans
- Vanity sconce or recessed above mirror
- Exhaust fan
- Zones: powder-{name}

### Hallway
- Recessed cans on 6 to 8 foot centers along the long axis
- Zones: hallway-{name}

### Living Room / Family Room / Great Room
- Recessed grid using the standard spacing; at least 4 cans in a room of 150 sq ft or more (2 below that); with a fan, the center can is left out
- Ceiling fan pre-wire at center (Better and Best tiers)
- Accent wall-wash trims on the feature wall: 2 at Better, 3 at Best
- Scene keypad ("Welcome") beside the front door

### Dining
- Chandelier pre-wire centered over the table (Accent layer)
- Two recessed cans flanking it on the long axis; four at Best in a dining room of 150 sq ft or more
- No ceiling fan
- Zones: living-general, living-accent

### Exterior
- Coach lights at each garage bay, front porch and rear entry
- Soffit pre-wire at corners for landscape uplighting (Better and Best tiers)
- Zones: exterior-entry, exterior-landscape

### Laundry / Mudroom
- One can, two in a long room

### Closet / Walk-in Closet / Pantry
- One can, two in a closet over 60 sq ft, centered on the aisle along the closet's long axis

### Default (Any Other Room)
- Recessed grid using the standard spacing; at least 2 cans in a room of 80 sq ft or more
- Single dimming zone named after the room

## Recessed Grid Algorithm

Ambient cans (everything except bedrooms) use `ambient_grid` in `backend/app/services/lighting_engine.py`.

1. Spacing: `max(6 ft, ceiling_height_ft * factor)`, where factor is 1.0 (Good), 0.85 (Better) or 0.75 (Best); kitchens multiply that by 0.8
2. Columns: `max(1, round(width / spacing))`; rows: `max(1, round(length / spacing))`
3. Add or remove a row or column to meet the room's minimum or maximum count, keeping the grid full
4. Each can sits at the centre of its cell, so the outer cans are half a spacing off the walls
5. With a ceiling fan, an odd-by-odd grid drops its centre can

On a 9 ft ceiling that is about 9 ft between cans at Good, 7.7 ft at Better and 6.75 ft at Best. The old rule (half the ceiling height, plus 36-inch perimeter cans in kitchens) put 10+ cans in a 13 ft kitchen and 16 in a 21 x 20 living room; the plan read as crowded.

## Tier Modifiers

| Tier | Fixture Count | Pre-wires | Product Line |
|------|--------------|-----------|--------------|
| Good | Base count | None | Builder grade (Halo, Commercial Electric) |
| Better | Tighter ambient spacing (0.85x) | Fans, accent, under-cabinet | DMF, WAC Lighting |
| Best | Tighter ambient spacing (0.75x) | All including landscape | Ketra (full-spectrum tunable) |

## Notes

- The BOM output shows fixtures only. No dimmer or control system line items: scene keypads appear on the plan viewer's Controls layer but are left out of the estimate and PDF schedule.
- Zone assignments are stored in the database for future Lutron/Ketra integration but are not displayed on the builder-facing PDF.
- Fixture positions use a 0-1 coordinate system relative to the room boundaries.
