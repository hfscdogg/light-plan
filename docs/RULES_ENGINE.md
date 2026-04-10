# Lighting Rules Engine

This document describes the default lighting fixture rules applied by LightPlan when generating a layout.

## General Principles

- Recessed can spacing is based on ceiling height: `spacing = ceiling_height / 2`
- Minimum distance from walls: 24 inches (or half the spacing, whichever is greater)
- Every room receives a dimming zone assignment (tracked internally for future Lutron integration)
- All fixture positions are stored as relative coordinates (0 to 1) so they scale to any rendering size
- Pre-wire locations are marked separately from fixture placements

## Room Type Rules

### Kitchen
- Perimeter recessed cans on 36-inch centers, inset 18 inches from walls
- Pendant pre-wire centered over island area (1 to 2 locations)
- Under-cabinet lighting pre-wire (Better and Best tiers)
- Zones: kitchen-general, kitchen-island, kitchen-accent

### Master Bedroom
- 4 to 6 recessed cans depending on room size (grid algorithm)
- Ceiling fan pre-wire at room center
- Switched outlet locations on each side of the bed wall
- Zones: master-general, master-bed

### Bedroom
- 4 recessed cans using standard grid algorithm
- Ceiling fan pre-wire at center (Better and Best tiers)
- Switched outlet near bed area
- Zones: bedroom-{name}

### Bathroom (Full)
- Vanity sconce pair flanking the mirror
- Shower recessed can (IC/AT rated for wet location)
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
- Recessed grid using standard spacing algorithm
- Ceiling fan pre-wire at center (Better and Best tiers)
- Accent lighting pre-wire along feature wall (Best tier)
- Zones: living-general, living-accent

### Exterior
- Coach lights at each garage bay, front porch and rear entry
- Soffit pre-wire at corners for landscape uplighting (Better and Best tiers)
- Zones: exterior-entry, exterior-landscape

### Default (Any Other Room)
- Recessed grid using standard spacing algorithm
- Single dimming zone named after the room

## Recessed Grid Algorithm

1. Calculate spacing: `ceiling_height_ft / 2`
2. Calculate wall inset: `max(spacing / 2, 2.0)` feet
3. Compute effective room dimensions: `width - 2 * inset` by `length - 2 * inset`
4. Calculate grid: `columns = floor(effective_width / spacing) + 1`, `rows = floor(effective_length / spacing) + 1`
5. Place fixtures at grid intersections
6. Convert positions to 0-1 relative coordinates within the room bounds

## Tier Modifiers

| Tier | Fixture Count | Pre-wires | Product Line |
|------|--------------|-----------|--------------|
| Good | Base count | None | Builder grade (Halo, Commercial Electric) |
| Better | Base + 10-20% | Fans, accent, under-cabinet | DMF, WAC Lighting |
| Best | Base + 25-40% | All including landscape | Ketra (full-spectrum tunable) |

## Notes

- The BOM output shows fixtures only. No dimmer or control system line items.
- Zone assignments are stored in the database for future Lutron/Ketra integration but are not displayed on the builder-facing PDF.
- Fixture positions use a 0-1 coordinate system relative to the room boundaries.
